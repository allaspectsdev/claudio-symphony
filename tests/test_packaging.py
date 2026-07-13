import json
import re
import unittest
from pathlib import Path

import cli


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_package_and_plugin_versions_stay_in_sync(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        package_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE).group(1)
        plugin_version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        init_version = re.search(
            r'^__version__ = "([^"]+)"$', (ROOT / "__init__.py").read_text(), re.MULTILINE
        ).group(1)
        self.assertEqual(package_version, plugin_version)
        self.assertEqual(package_version, init_version)

    def test_console_entrypoint_and_runtime_assets_are_declared(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        self.assertIn('claudio = "claudio_symphony.cli:entrypoint"', pyproject)
        self.assertIn('"presets/*/*.json"', pyproject)
        self.assertIn('"web/*.js"', pyproject)
        self.assertTrue(callable(cli.entrypoint))

    def test_readme_documents_isolated_tool_installation(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("uv tool install git+https://github.com/allaspectsdev/claudio-symphony.git", readme)
        self.assertIn("pipx install git+https://github.com/allaspectsdev/claudio-symphony.git", readme)


if __name__ == "__main__":
    unittest.main()
