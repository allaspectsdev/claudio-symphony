import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
import preset_store


ROOT = Path(__file__).resolve().parents[1]


class PlatformPathTests(unittest.TestCase):
    def test_portable_home_keeps_every_mutable_path_outside_checkout(self):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env["CLAUDIO_HOME"] = home
            code = (
                "import json, paths; "
                "print(json.dumps([str(paths.CONFIG_FILE), str(paths.STATE_DIR), "
                "str(paths.USER_PRESETS_DIR), str(paths.SAMPLES_DIR)]))"
            )
            output = subprocess.check_output(
                [sys.executable, "-c", code], cwd=ROOT, env=env, text=True
            )
            resolved_home = Path(home).resolve()
            for value in json.loads(output):
                self.assertTrue(Path(value).resolve().is_relative_to(resolved_home))

    def test_import_survives_uncreatable_home(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "regular-file"
            blocker.write_text("")
            env = os.environ.copy()
            env["CLAUDIO_HOME"] = str(blocker / "home")
            proc = subprocess.run(
                [sys.executable, "-c", "import paths; print(paths.STATE_DIR)"],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stderr, "")
            self.assertTrue(proc.stdout.strip().endswith("state"))

    def test_completed_migration_skips_legacy_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "migration.json"
            marker.write_text(json.dumps({"small_complete": True, "large_complete": True}))
            scan = mock.Mock()
            scan.iterdir.side_effect = AssertionError("legacy preset scan ran")
            with mock.patch.object(paths, "MIGRATION_FILE", marker), \
                 mock.patch.object(paths, "LEGACY_RECORDINGS_DIR", scan), \
                 mock.patch.object(paths, "BUILTIN_PRESETS_DIR", scan):
                status = paths.migration_status()
            self.assertEqual(status["small_complete"], True)
            self.assertEqual(status["large_complete"], True)

    def test_builtin_edit_becomes_user_overlay_and_reset_removes_it(self):
        original = preset_store.load("meadow")
        self.assertIsNotNone(original)
        changed = dict(original)
        changed["description"] = "test overlay"
        written = preset_store.save("meadow", changed)
        self.assertTrue(written.is_relative_to(paths.USER_PRESETS_DIR))
        self.assertEqual(preset_store.load("meadow")["description"], "test overlay")
        self.assertTrue(preset_store.reset("meadow"))
        self.assertEqual(preset_store.load("meadow"), original)

    def test_renderer_environment_targets_cache_and_active_config(self):
        env = preset_store.renderer_env("meadow")
        self.assertEqual(Path(env["CLAUDIO_SAMPLES_DIR"]), paths.SAMPLES_DIR / "meadow")
        self.assertEqual(Path(env["CLAUDIO_PRESET_CONFIG"]), preset_store.preset_path("meadow"))

    def test_partial_cache_falls_back_per_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builtins = root / "presets"
            cache = root / "cache"
            preset = builtins / "demo"
            (preset / "samples" / "cached").mkdir(parents=True)
            (preset / "samples" / "legacy").mkdir(parents=True)
            (preset / "preset.json").write_text("{}")
            (preset / "samples" / "cached" / "old.wav").write_bytes(b"old")
            (preset / "samples" / "legacy" / "only.wav").write_bytes(b"legacy")
            (cache / "demo" / "cached").mkdir(parents=True)
            (cache / "demo" / "cached" / "new.wav").write_bytes(b"new")
            with mock.patch.object(paths, "BUILTIN_PRESETS_DIR", builtins), \
                 mock.patch.object(paths, "SAMPLES_DIR", cache):
                self.assertTrue(preset_store.sample_asset("demo", "cached").is_relative_to(cache.resolve()))
                self.assertTrue(preset_store.sample_asset("demo", "legacy").is_relative_to(builtins.resolve()))


class MigrationTests(unittest.TestCase):
    def test_large_migration_copies_without_deleting_legacy_data(self):
        with tempfile.TemporaryDirectory() as legacy:
            legacy = Path(legacy)
            config = legacy / "config.json"
            config.write_text('{"preset":"meadow"}\n')
            songs = legacy / "songs"
            songs.mkdir()
            (songs / "one.mid").write_bytes(b"midi")
            recordings = legacy / "recordings"
            recordings.mkdir()
            (recordings / "one.wav").write_bytes(b"wav")
            builtins = legacy / "presets"
            meadow = builtins / "meadow"
            (meadow / "samples" / "voice").mkdir(parents=True)
            preset = {"description": "built in"}
            (meadow / "preset.json").write_text(json.dumps(preset))
            (meadow / "preset.default.json").write_text(json.dumps(preset))
            (meadow / "samples" / "voice" / "one.wav").write_bytes(b"wav")

            with mock.patch.multiple(
                paths,
                LEGACY_CONFIG_FILE=config,
                LEGACY_STATE_DIR=legacy / "state",
                LEGACY_LOG_DIR=legacy / "logs",
                LEGACY_SONGS_DIR=songs,
                LEGACY_RECORDINGS_DIR=recordings,
                BUILTIN_PRESETS_DIR=builtins,
            ):
                result = paths.migrate_legacy(include_large=True)

            self.assertIn(result["config"], (0, 1))
            self.assertTrue(config.exists())
            self.assertTrue((paths.SONGS_DIR / "one.mid").exists())
            self.assertTrue((paths.RECORDINGS_DIR / "one.wav").exists())
            self.assertTrue((paths.SAMPLES_DIR / "meadow" / "voice" / "one.wav").exists())
            self.assertTrue((songs / "one.mid").exists())
            self.assertTrue((recordings / "one.wav").exists())


if __name__ == "__main__":
    unittest.main()
