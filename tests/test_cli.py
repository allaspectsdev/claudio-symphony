"""CLI behaviour tests. Every run uses a throwaway HOME and CLAUDIO_HOME so the
real ~/.claude/settings.json and user data are never touched."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = str(ROOT / "cli.py")
MARKER = "__claudio_symphony__"


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._data = tempfile.TemporaryDirectory()
        self.home = Path(self._home.name)
        self.env = os.environ.copy()
        # USERPROFILE: Path.home() ignores HOME on Windows.
        self.env.update(HOME=self._home.name, USERPROFILE=self._home.name,
                        CLAUDIO_HOME=self._data.name)
        self.env.pop("CLAUDE_PLUGIN_ROOT", None)
        self.settings = self.home / ".claude" / "settings.json"

    def tearDown(self):
        self._home.cleanup()
        self._data.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, CLI, *args], cwd=ROOT, env=self.env,
                              capture_output=True, text=True, timeout=60)

    def read_settings(self):
        return json.loads(self.settings.read_text())


class InstallTests(CliTestCase):
    def test_fresh_home_install_succeeds_and_is_idempotent(self):
        first = self.run_cli("install")
        self.assertEqual(first.returncode, 0, first.stderr)
        after_first = self.settings.read_text()
        hooks = self.read_settings()["hooks"]
        self.assertIn("PostToolUse", hooks)

        second = self.run_cli("install")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already present", second.stdout)
        self.assertEqual(self.settings.read_text(), after_first)
        for blocks in self.read_settings()["hooks"].values():
            ours = [h for b in blocks for h in b["hooks"] if h.get(MARKER)]
            self.assertEqual(len(ours), 1)

    def test_install_refreshes_stale_hook_and_keeps_foreign_hooks(self):
        foreign = {"type": "command", "command": "echo hi"}
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"hooks": {"Stop": [
            {"matcher": "*", "hooks": [foreign]},
            {"matcher": "*", "hooks": [{"type": "command",
                                        "command": "python3 /old/place/event.py",
                                        MARKER: True}]},
        ]}}))
        result = self.run_cli("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("updated: Stop", result.stdout)
        stop = self.read_settings()["hooks"]["Stop"]
        self.assertEqual(stop[0]["hooks"], [foreign])
        ours = [h for b in stop for h in b["hooks"] if h.get(MARKER)]
        self.assertEqual(len(ours), 1)
        self.assertEqual(ours[0]["command"], sys.executable)
        self.assertEqual(ours[0]["args"], [str(ROOT / "event.py")])

    def test_corrupt_settings_aborts_install_without_writing(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"hooks": {,}')
        result = self.run_cli("install")
        self.assertEqual(result.returncode, 1)
        self.assertIn("line 1", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.settings.read_text(), '{"hooks": {,}')
        self.assertFalse((self.home / ".claude" / "backups").exists())

    def test_corrupt_settings_status_still_reports(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("not json")
        result = self.run_cli("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("active preset", result.stdout)

    def test_install_help_does_not_write(self):
        result = self.run_cli("install", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("install", result.stdout)
        self.assertFalse(self.settings.exists())


class DispatchTests(CliTestCase):
    def test_unknown_command_exits_2(self):
        result = self.run_cli("definitely-not-a-command")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown command", result.stderr)

    def test_help_exits_0(self):
        for flag in ("--help", "-h", "help"):
            result = self.run_cli(flag)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Presets", result.stdout)

    def test_non_numeric_volume_exits_2(self):
        result = self.run_cli("volume", "abc")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_error_paths_exit_nonzero(self):
        for args in (("preset", "use", "nosuch"), ("scale", "use", "nosuch"),
                     ("root", "H"), ("map", "NoSuchEvent", "x")):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 1, args)


class MappingTests(CliTestCase):
    def by_tool(self):
        code = ("import json, cli; p = cli.load_preset(cli.active_preset_name()); "
                "print(json.dumps(p['events']['PostToolUse'].get('by_tool', {})))")
        out = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT,
                                      env=self.env, text=True)
        return json.loads(out)

    def test_mute_tool_stores_explicit_silence(self):
        result = self.run_cli("mute", "PostToolUse:Edit")
        self.assertEqual(result.returncode, 0, result.stderr)
        by_tool = self.by_tool()
        self.assertIn("Edit", by_tool)
        self.assertIsNone(by_tool["Edit"])

        result = self.run_cli("unmute", "PostToolUse:Edit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Edit", self.by_tool())


if __name__ == "__main__":
    unittest.main()
