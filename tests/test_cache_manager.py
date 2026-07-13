import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cache_manager
import paths
import render_worker


def sparse_file(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.seek(size - 1)
        handle.write(b"\0")


class CacheManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.samples = self.cache / "samples"
        self.rate = self.cache / "rate_cache"
        self.config = self.root / "config.json"
        self.state = self.root / "state"
        self.user_presets = self.root / "data" / "presets"
        self.patches = [
            mock.patch.object(paths, "CACHE_DIR", self.cache),
            mock.patch.object(paths, "SAMPLES_DIR", self.samples),
            mock.patch.object(paths, "RATE_CACHE_DIR", self.rate),
            mock.patch.object(paths, "STATE_DIR", self.state),
            mock.patch.object(paths, "USER_PRESETS_DIR", self.user_presets),
            mock.patch.object(cache_manager, "_LOCK_TARGET", self.root / "cache-maintenance"),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temp.cleanup()

    def test_status_breaks_down_samples_and_pitch_cache(self):
        sparse_file(self.samples / "meadow" / "voice" / "one.wav", 1024)
        sparse_file(self.rate / "pitch.wav", 2048)
        status = cache_manager.status(self.config)
        self.assertEqual(status["sample_bytes"], 1024)
        self.assertEqual(status["rate_bytes"], 2048)
        self.assertEqual(status["total_bytes"], 3072)
        self.assertEqual(status["samples"][0]["name"], "meadow")

    def test_limit_trims_rate_then_old_presets_but_preserves_active(self):
        mb = 1024 * 1024
        sparse_file(self.rate / "pitch.wav", 2 * mb)
        sparse_file(self.samples / "old" / "voice" / "one.wav", 40 * mb)
        sparse_file(self.samples / "active" / "voice" / "one.wav", 40 * mb)
        result = cache_manager.set_limit(64, self.config, preserve=("active",))
        self.assertFalse(self.rate.exists() and any(self.rate.iterdir()))
        self.assertFalse((self.samples / "old").exists())
        self.assertTrue((self.samples / "active").exists())
        self.assertLessEqual(result["total_bytes"], 64 * mb)

    def test_clearing_generated_preset_never_touches_durable_custom_data(self):
        sparse_file(self.samples / "mine" / "voice" / "generated.wav", 1024)
        durable = self.user_presets / "mine" / "samples" / "voice" / "custom.wav"
        sparse_file(durable, 2048)
        (self.state / "mine").mkdir(parents=True)
        (self.state / "mine" / ".rendered").write_text("1")
        (self.state / "mine" / ".rendering").write_text("1")
        result = cache_manager.clear("preset", preset="mine", config_path=self.config)
        self.assertEqual(result["freed_bytes"], 1024)
        self.assertFalse((self.samples / "mine").exists())
        self.assertTrue(durable.exists())
        self.assertFalse((self.state / "mine" / ".rendered").exists())
        self.assertFalse((self.state / "mine" / ".rendering").exists())

    def test_limit_validation_and_unlimited_mode(self):
        with self.assertRaises(ValueError):
            cache_manager.set_limit(1, self.config)
        result = cache_manager.set_limit(0, self.config)
        self.assertEqual(result["limit_mb"], 0)
        self.assertEqual(json.loads(self.config.read_text())["cache"]["max_mb"], 0)

    def test_clear_skips_a_preset_with_an_active_render_lock(self):
        sparse_file(self.samples / "busy" / "voice" / "one.wav", 1024)
        sparse_file(self.samples / "idle" / "voice" / "one.wav", 1024)
        (self.state / "busy").mkdir(parents=True)
        (self.state / "busy" / ".rendering.lock").write_text("locked")
        result = cache_manager.clear("samples", config_path=self.config)
        self.assertTrue((self.samples / "busy").exists())
        self.assertFalse((self.samples / "idle").exists())
        self.assertEqual(result["freed_bytes"], 1024)
        with self.assertRaises(ValueError):
            cache_manager.clear("preset", preset="busy", config_path=self.config)

    def test_render_worker_enforces_limit_after_successful_render(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.object(render_worker.preset_store, "render_path", return_value=Path("render.py")), \
             mock.patch.object(render_worker.preset_store, "renderer_env", return_value={"CLAUDIO_SAMPLES_DIR": "out"}), \
             mock.patch.object(render_worker.subprocess, "run", return_value=completed) as run, \
             mock.patch.object(render_worker.cache_manager, "trim") as trim:
            self.assertEqual(render_worker.render("meadow", ["mallet"]), 0)
        self.assertEqual(run.call_args.args[0][-1], "mallet")
        trim.assert_called_once_with(preserve=("meadow",))
        self.assertFalse((self.state / "meadow" / ".rendering").exists())

    def test_failed_render_keeps_backoff_marker(self):
        completed = mock.Mock(returncode=1)
        with mock.patch.object(render_worker.preset_store, "render_path", return_value=Path("render.py")), \
             mock.patch.object(render_worker.preset_store, "renderer_env", return_value={}), \
             mock.patch.object(render_worker.subprocess, "run", return_value=completed), \
             mock.patch.object(render_worker.cache_manager, "trim") as trim:
            self.assertEqual(render_worker.render("meadow"), 1)
        self.assertTrue((self.state / "meadow" / ".rendering").exists())
        trim.assert_not_called()


if __name__ == "__main__":
    unittest.main()
