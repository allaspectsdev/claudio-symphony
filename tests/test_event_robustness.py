"""Hook-process robustness: silent failure, bounded lock waits, data retention."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import event

ROOT = Path(__file__).resolve().parents[1]
EVENT = ROOT / "event.py"


def run_hook(stdin_bytes, home, timeout=10):
    env = os.environ.copy()
    env["CLAUDIO_HOME"] = str(home)
    start = time.monotonic()
    proc = subprocess.run([sys.executable, str(EVENT)], input=stdin_bytes,
                          capture_output=True, env=env, cwd=str(ROOT), timeout=timeout)
    return proc, time.monotonic() - start


def silent_home(root):
    """A CLAUDIO_HOME whose config points at a missing preset, so a hook run
    exercises session bookkeeping but never renders or plays audio."""
    home = Path(root) / "home"
    (home / "config").mkdir(parents=True)
    (home / "config" / "config.json").write_text(json.dumps({"preset": "zz-missing"}))
    return home


class HookSilenceTests(unittest.TestCase):
    def assertSilentExit(self, proc):
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b"")
        self.assertEqual(proc.stdout, b"")

    def test_bad_stdin_exits_zero_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            home = silent_home(td)
            for payload in (b"not json {", b"\xff\xfe\x80{bad utf8", b"", b"[1, 2]"):
                with self.subTest(payload=payload):
                    proc, _ = run_hook(payload, home)
                    self.assertSilentExit(proc)

    def test_unwritable_home_exits_zero_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "regular-file"
            blocker.write_text("not a directory")
            payload = json.dumps({"hook_event_name": "PostToolUse",
                                  "session_id": "x", "tool_name": "Read"}).encode()
            proc, _ = run_hook(payload, blocker / "home")
            self.assertSilentExit(proc)

    def test_orphaned_hot_lock_does_not_stall_hook(self):
        with tempfile.TemporaryDirectory() as td:
            home = silent_home(td)
            state = home / "state"
            state.mkdir(parents=True)
            payload = json.dumps({"hook_event_name": "PostToolUse",
                                  "session_id": "orphan", "tool_name": "Read"}).encode()
            # Lock actively held by a live process (this test): wait is bounded.
            import stateio
            with stateio.file_lock(state / "sessions.json"):
                proc, elapsed = run_hook(payload, home)
            self.assertSilentExit(proc)
            self.assertLess(elapsed, 1.0)
            # Leftover lock file from a killed hook: no wait, record written.
            (state / "sessions.json.lock").write_text("orphan")
            proc, elapsed = run_hook(payload, home)
            self.assertSilentExit(proc)
            self.assertLess(elapsed, 1.0)
            sessions = json.loads((state / "sessions.json").read_text())
            self.assertIn("orphan", sessions["active"])


class FailureFlagTests(unittest.TestCase):
    def test_post_tool_use_failure_is_a_failure(self):
        self.assertTrue(event.is_failure({"hook_event_name": "PostToolUseFailure",
                                          "tool_name": "Bash", "error": "boom"}))
        self.assertTrue(event.is_failure({"hook_event_name": "PostToolUse", "error": "boom"}))
        self.assertFalse(event.is_failure({"hook_event_name": "PostToolUse", "tool_name": "Read"}))

    def test_explicit_null_on_failure_silences_failures(self):
        preset = {"events": {"PostToolUse": {"default": "ok", "on_failure": None,
                                             "by_tool": {"Bash": None}}}}
        self.assertIsNone(event.resolve_voice(preset, "PostToolUseFailure", {"tool_name": "Read"}))
        self.assertIsNone(event.resolve_voice(preset, "PostToolUse", {"tool_name": "Bash"}))
        del preset["events"]["PostToolUse"]["on_failure"]
        self.assertEqual(event.resolve_voice(preset, "PostToolUseFailure", {}), "ok")


class CwdRuleTests(unittest.TestCase):
    def test_windows_style_paths_match_either_separator(self):
        self.assertTrue(event.cwd_rule_match(r"C:\Users\me\work\app", "C:/Users/me/work"))
        self.assertTrue(event.cwd_rule_match("C:/Users/me/work/app", "C:\\Users\\me\\work\\"))
        self.assertTrue(event.cwd_rule_match(r"C:\Users\me\work", r"C:\Users\me\work"))
        self.assertTrue(event.cwd_rule_match(r"C:\Users\me\work\app", "C:/Users/*/work/*"))
        self.assertFalse(event.cwd_rule_match(r"C:\Users\me\workshop", "C:/Users/me/work"))

    def test_posix_prefix_matching_unchanged(self):
        self.assertTrue(event.cwd_rule_match("/home/me/work/app", "/home/me/work/"))
        self.assertFalse(event.cwd_rule_match("/home/me/workshop", "/home/me/work"))


class TimelineRetentionTests(unittest.TestCase):
    def test_session_prune_keeps_timeline_but_ages_old_ones(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sessions = root / "sessions.json"
            timeline = root / "timeline"
            timeline.mkdir()
            stale = time.time() - event.SESSION_TTL_S - 60
            sessions.write_text(json.dumps({"active": {
                "expired": {"last_seen": stale}}}))
            recent = timeline / "expired.ndjson"
            recent.write_text('{"t": 1, "e": "Stop"}\n')
            ancient = timeline / "ancient.ndjson"
            ancient.write_text('{"t": 1, "e": "Stop"}\n')
            old = time.time() - (event.TIMELINE_KEEP_DAYS + 1) * 86400
            os.utime(ancient, (old, old))
            with mock.patch.object(event, "SESSIONS_FILE", sessions), \
                 mock.patch.object(event, "TIMELINE", timeline):
                event.update_session_record("fresh", "/tmp", "PostToolUse", "meadow", "default")
            active = json.loads(sessions.read_text())["active"]
            self.assertNotIn("expired", active)
            self.assertTrue(recent.exists())          # replayable after the session record expires
            self.assertFalse(ancient.exists())

    def test_timeline_count_is_capped_but_active_sessions_are_kept(self):
        with tempfile.TemporaryDirectory() as td:
            timeline = Path(td)
            now = time.time()
            for i in range(5):
                f = timeline / f"s{i}.ndjson"
                f.write_text("{}\n")
                os.utime(f, (now - i * 60, now - i * 60))
            with mock.patch.object(event, "TIMELINE", timeline), \
                 mock.patch.object(event, "TIMELINE_KEEP_FILES", 2):
                event.prune_timelines(keep=["s4"])
            self.assertEqual(sorted(p.stem for p in timeline.glob("*.ndjson")),
                             ["s0", "s1", "s4"])


class HousekeepingTests(unittest.TestCase):
    def test_event_log_rotates_when_large(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "event.log"
            log.write_text("x" * 64)
            with mock.patch.object(event, "LOG", log), \
                 mock.patch.object(event, "LOG_MAX_BYTES", 32):
                event.log("hello")
            self.assertEqual(log.with_name("event.log.1").read_text(), "x" * 64)
            self.assertTrue(log.read_text().endswith("hello\n"))

    def test_rendered_marker_is_not_rewritten_every_event(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            samples = root / "samples" / "voice"
            samples.mkdir(parents=True)
            (samples / "a.wav").write_bytes(b"RIFF")
            with mock.patch.object(event, "STATE", root / "state"), \
                 mock.patch.object(event.preset_store, "sample_read_dir",
                                   return_value=root / "samples"):
                self.assertTrue(event.ensure_rendered("demo"))
                marker = root / "state" / "demo" / ".rendered"
                marker.write_text("sentinel")
                self.assertTrue(event.ensure_rendered("demo"))
                self.assertEqual(marker.read_text(), "sentinel")


if __name__ == "__main__":
    unittest.main()
