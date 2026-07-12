import json
import unittest
from pathlib import Path

import cli
import event

HERE = Path(__file__).resolve().parent.parent


class HookManifestTests(unittest.TestCase):
    def test_bootstrap_never_installs_python_packages(self):
        source = (HERE / "bin" / "bootstrap.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("PIP_MARK", source)
        self.assertIn("did not install anything automatically", source)

    def test_plugin_hooks_are_async_bounded_and_exec_form(self):
        hooks = json.loads((HERE / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertIn("PostToolUseFailure", hooks)
        handlers = [handler for groups in hooks.values() for group in groups
                    for handler in group.get("hooks", [])]
        self.assertGreater(len(handlers), 0)
        for handler in handlers:
            self.assertIs(handler.get("async"), True)
            self.assertEqual(handler.get("timeout"), 1)
            self.assertEqual(handler.get("command"), "python3")
            self.assertIsInstance(handler.get("args"), list)
            self.assertEqual(len(handler["args"]), 1)

    def test_manual_installer_includes_failure_event(self):
        self.assertIn("PostToolUseFailure", cli.HOOK_EVENTS)
        handler = cli.hook_block_for()["hooks"][0]
        self.assertIs(handler["async"], True)
        self.assertEqual(handler["timeout"], 1)
        self.assertEqual(handler["command"], __import__("sys").executable)
        self.assertEqual(handler["args"], [cli.EVENT_PATH])


class FailureMappingTests(unittest.TestCase):
    def setUp(self):
        self.preset = {
            "events": {
                "PostToolUse": {
                    "default": "success",
                    "on_failure": "failure",
                    "by_tool": {"Bash": "shell-success"},
                }
            }
        }

    def test_failure_event_uses_existing_on_failure_mapping(self):
        voice = event.resolve_voice(self.preset, "PostToolUseFailure",
                                    {"tool_name": "Bash", "error": "boom"})
        self.assertEqual(voice, "failure")

    def test_success_event_still_uses_tool_override(self):
        voice = event.resolve_voice(self.preset, "PostToolUse", {"tool_name": "Bash"})
        self.assertEqual(voice, "shell-success")

    def test_failure_activity_rolls_up_under_post_tool_use(self):
        self.assertEqual(event.mapping_event_name("PostToolUseFailure"), "PostToolUse")


if __name__ == "__main__":
    unittest.main()
