#!/usr/bin/env python3
"""
record.py lifecycle tests: cooperative stop, early-stop truncation, and
self-healing of a leaked active.json. No audio is played — the recorder only
mixes WAVs — and every path is redirected into a temp dir.
"""
import json
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
try:
    import record  # noqa: E402  (needs numpy)
except Exception:  # pragma: no cover
    record = None


@unittest.skipIf(record is None, "record.py needs numpy")
class RecordLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name)
        rec_dir = d / "recording"
        rec_dir.mkdir()
        self._patches = [
            mock.patch.object(record, "REC_DIR", rec_dir),
            mock.patch.object(record, "ACTIVE", rec_dir / "active.json"),
            mock.patch.object(record, "EVENTS", rec_dir / "events.jsonl"),
            mock.patch.object(record, "STOP_SENTINEL", rec_dir / "stop"),
            mock.patch.object(record, "OUT_DIR", d / "recordings"),
            mock.patch.object(record, "_to_m4a", return_value=None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def _open_window(self, *, age_s=2.0, duration=30, pid=424242):
        meta = {"start": time.time() - age_s, "duration": duration,
                "out": "claudio-test", "pid": pid, "src": "test",
                "drone": False, "drone_gain": 0.3}
        record.EVENTS.write_text("")
        record.ACTIVE.write_text(json.dumps(meta))
        return meta

    def test_finalize_truncates_to_elapsed_on_early_stop(self):
        self._open_window(age_s=2.0, duration=30)
        res = record.finalize()
        self.assertFalse(record.ACTIVE.exists())
        self.assertLess(res["seconds"], 5.0)        # not the requested 30s
        self.assertGreaterEqual(res["seconds"], 1.0)

    def test_finalize_is_claimed_once(self):
        self._open_window()
        self.assertIsNotNone(record.finalize())
        self.assertIsNone(record.finalize())          # second caller: nothing to do

    def test_stale_active_json_self_heals(self):
        self._open_window(pid=424242)
        with mock.patch.object(record.audio, "pid_alive", return_value=False):
            st = record.status()
            self.assertFalse(st["active"])
            self.assertFalse(record.ACTIVE.exists())
            self.assertEqual(len(st["recordings"]), 1)   # the take was salvaged
            self.assertFalse(record.is_active())

    def test_start_clears_stale_window(self):
        self._open_window(pid=424242)
        with mock.patch.object(record.audio, "pid_alive", return_value=False):
            meta = record.start(10, pid=12345)
        self.assertEqual(json.loads(record.ACTIVE.read_text())["pid"], meta["pid"])

    def test_live_recorder_not_healed(self):
        self._open_window(pid=424242)
        with mock.patch.object(record.audio, "pid_alive", return_value=True):
            self.assertTrue(record.status()["active"])
        self.assertTrue(record.ACTIVE.exists())

    def test_request_stop_is_cooperative(self):
        self._open_window(pid=424242)

        def fake_recorder():                          # the recorder's poll loop
            deadline = time.time() + 3
            while time.time() < deadline:
                if record.STOP_SENTINEL.exists():
                    record.finalize()
                    return
                time.sleep(0.02)
        t = threading.Thread(target=fake_recorder)
        t.start()
        with mock.patch.object(record.audio, "pid_alive", return_value=True), \
             mock.patch.object(record.audio, "terminate_pid") as term:
            self.assertTrue(record.request_stop(wait=2.0))
        t.join()
        term.assert_not_called()                      # never hard-killed
        self.assertFalse(record.ACTIVE.exists())
        self.assertFalse(record.STOP_SENTINEL.exists())

    def test_request_stop_falls_back_to_terminate_then_finalizes(self):
        self._open_window(pid=424242)
        with mock.patch.object(record.audio, "pid_alive", return_value=True), \
             mock.patch.object(record.audio, "terminate_pid") as term:
            self.assertTrue(record.request_stop(wait=0.2))
        term.assert_called_once_with(424242)
        self.assertFalse(record.ACTIVE.exists())      # we mixed it on its behalf
        self.assertEqual(len(record.list_recordings()), 1)

    def test_request_stop_nothing_recording(self):
        self.assertFalse(record.request_stop(wait=0.1))

    def test_run_stops_on_sentinel(self):
        saved = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
        threading.Timer(0.3, lambda: record.STOP_SENTINEL.write_text("1")).start()
        try:
            t0 = time.time()
            res = record.run(30, src="test")
        finally:
            signal.signal(signal.SIGINT, saved[0])
            signal.signal(signal.SIGTERM, saved[1])
        self.assertLess(time.time() - t0, 5.0)
        self.assertLess(res["seconds"], 5.0)
        self.assertFalse(record.ACTIVE.exists())
        self.assertFalse(record.STOP_SENTINEL.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
