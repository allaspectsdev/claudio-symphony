import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import event
import song
import stateio


class StateIOTests(unittest.TestCase):
    def test_concurrent_updates_retain_every_increment(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "counter.json"
            def increment(_):
                stateio.update_json(path, {"count": 0},
                                    lambda d: d.update(count=d["count"] + 1))
            with ThreadPoolExecutor(max_workers=32) as pool:
                list(pool.map(increment, range(200)))
            self.assertEqual(json.loads(path.read_text()), {"count": 200})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_concurrent_saves_never_share_a_temp_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            errors = []
            def write(i):
                try:
                    stateio.save_json(path, {"writer": i, "payload": "x" * 1000})
                except Exception as exc:  # pragma: no cover - assertion reports details
                    errors.append(exc)
            with ThreadPoolExecutor(max_workers=32) as pool:
                list(pool.map(write, range(200)))
            self.assertEqual(errors, [])
            self.assertIn("writer", json.loads(path.read_text()))

    def test_leftover_lock_file_does_not_block(self):
        # A lock file left behind by an old/killed process is just a file; the
        # kernel lock it once carried died with its owner.
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.with_name(path.name + ".lock").write_text("abandoned")
            start = time.monotonic()
            stateio.save_json(path, {"ok": True}, timeout=stateio.HOT_TIMEOUT)
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertEqual(stateio.load_json(path, {}), {"ok": True})

    def test_contenders_stay_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.with_name(path.name + ".lock").write_text("orphan")
            inside, peak = [0], [0]
            guard = threading.Lock()
            barrier = threading.Barrier(16)
            def contend(_):
                barrier.wait()
                with stateio.file_lock(path, timeout=10.0):
                    with guard:
                        inside[0] += 1
                        peak[0] = max(peak[0], inside[0])
                    time.sleep(0.005)
                    with guard:
                        inside[0] -= 1
            with ThreadPoolExecutor(max_workers=16) as pool:
                list(pool.map(contend, range(16)))
            self.assertEqual(peak[0], 1)

    def test_held_lock_times_out_quickly(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            with stateio.file_lock(path):
                start = time.monotonic()
                with self.assertRaises(stateio.LockTimeout):
                    with stateio.file_lock(path, timeout=stateio.HOT_TIMEOUT):
                        pass
                self.assertLess(time.monotonic() - start, 0.9)
            # Released on exit: immediately acquirable again.
            with stateio.file_lock(path, timeout=0):
                pass

    def test_lock_of_killed_process_is_released_immediately(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            ready = Path(td) / "ready"
            holder = subprocess.Popen([sys.executable, "-c", (
                "import sys, time, pathlib, stateio\n"
                "with stateio.file_lock(sys.argv[1]):\n"
                "    pathlib.Path(sys.argv[2]).write_text('1')\n"
                "    time.sleep(60)\n"), str(path), str(ready)],
                cwd=str(Path(__file__).resolve().parents[1]))
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                with self.assertRaises(stateio.LockTimeout):
                    stateio.save_json(path, {}, timeout=0.1)
            finally:
                holder.kill()
                holder.wait()
            # The OS drops the dead holder's lock (Windows may take a moment).
            stateio.save_json(path, {"ok": True}, timeout=2.0)
            self.assertEqual(stateio.load_json(path, {}), {"ok": True})


class RuntimeTransactionTests(unittest.TestCase):
    def test_session_updates_do_not_drop_parallel_hooks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sessions = root / "sessions.json"
            timeline = root / "timeline"
            # Serialization, not the bounded hot-path wait, is under test here
            # (test_held_lock_times_out_quickly covers that): 100 hooks in one
            # process would otherwise queue past HOT_TIMEOUT on slow CI hosts.
            with mock.patch.object(event, "SESSIONS_FILE", sessions), \
                 mock.patch.object(event, "TIMELINE", timeline), \
                 mock.patch.object(event, "LOCK_KW", {"timeout": 10.0}):
                def update(i):
                    event.update_session_record(f"session-{i}", f"/tmp/project-{i}",
                                                "PostToolUse", "meadow", "default")
                with ThreadPoolExecutor(max_workers=32) as pool:
                    list(pool.map(update, range(100)))
            active = json.loads(sessions.read_text())["active"]
            self.assertEqual(len(active), 100)
            self.assertEqual(active["session-42"]["cwd"], "/tmp/project-42")

    def test_song_pointer_advances_once_per_parallel_event(self):
        notes = [{"midi": 60 + i, "beat": i, "velocity": 100, "channel": 0}
                 for i in range(60)]
        fake_song = {"notes": notes, "bpm": 120, "ppq": 480}
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "song.json"
            stateio.save_json(state, {"channel": {"demo": "all"}})
            with mock.patch.object(song, "STATE_FILE", state), \
                 mock.patch.object(song, "load_song", return_value=fake_song), \
                 mock.patch.object(stateio, "HOT_TIMEOUT", 10.0):
                with ThreadPoolExecutor(max_workers=20) as pool:
                    played = list(pool.map(lambda _: song.next_note("demo"), range(50)))
            self.assertEqual(sorted(played), list(range(60, 110)))
            self.assertEqual(stateio.load_json(state, {})["positions"]["demo"], 50)

    def test_mioi_allows_only_one_parallel_trigger(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(event, "STATE", Path(td)), \
                mock.patch.object(event, "LOCK_KW", {"timeout": 10.0}):
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(lambda _: event.check_mioi("meadow", "bell", 60),
                                        range(50)))
            self.assertEqual(sum(1 for allowed, _ in results if allowed), 1)
            pressure = Path(td) / "meadow" / "pressure-bell.txt"
            self.assertEqual(int(pressure.read_text()), 49)


if __name__ == "__main__":
    unittest.main()
