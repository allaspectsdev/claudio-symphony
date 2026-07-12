import json
import tempfile
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
            self.assertFalse(path.with_name(path.name + ".lock").exists())
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

    def test_stale_lock_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            lock = path.with_name(path.name + ".lock")
            lock.write_text("abandoned")
            old = time.time() - 60
            __import__("os").utime(lock, (old, old))
            stateio.save_json(path, {"ok": True})
            self.assertEqual(stateio.load_json(path, {}), {"ok": True})
            self.assertFalse(lock.exists())


class RuntimeTransactionTests(unittest.TestCase):
    def test_session_updates_do_not_drop_parallel_hooks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sessions = root / "sessions.json"
            timeline = root / "timeline"
            with mock.patch.object(event, "SESSIONS_FILE", sessions), \
                 mock.patch.object(event, "TIMELINE", timeline):
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
                 mock.patch.object(song, "load_song", return_value=fake_song):
                with ThreadPoolExecutor(max_workers=20) as pool:
                    played = list(pool.map(lambda _: song.next_note("demo"), range(50)))
            self.assertEqual(sorted(played), list(range(60, 110)))
            self.assertEqual(stateio.load_json(state, {})["positions"]["demo"], 50)

    def test_mioi_allows_only_one_parallel_trigger(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(event, "STATE", Path(td)):
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(lambda _: event.check_mioi("meadow", "bell", 60),
                                        range(50)))
            self.assertEqual(sum(1 for allowed, _ in results if allowed), 1)
            pressure = Path(td) / "meadow" / "pressure-bell.txt"
            self.assertEqual(int(pressure.read_text()), 49)


if __name__ == "__main__":
    unittest.main()
