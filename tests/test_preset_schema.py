import json
import shutil
import tempfile
import unittest
from pathlib import Path

import preset_schema
import preset_store


PRESETS = Path(__file__).resolve().parents[1] / "presets"


class BundledPresetTests(unittest.TestCase):
    def test_every_bundled_preset_and_default_is_valid(self):
        files = sorted(PRESETS.glob("*/preset*.json"))
        self.assertEqual(len(files), 80)
        failures = {}
        for path in files:
            errors = preset_schema.validate(json.loads(path.read_text()))
            if errors:
                failures[str(path.relative_to(PRESETS))] = errors
        self.assertEqual(failures, {})

    def test_preset_name_matches_directory(self):
        mismatches = []
        for path in PRESETS.glob("*/preset*.json"):
            if json.loads(path.read_text()).get("name") != path.parent.name:
                mismatches.append(str(path))
        self.assertEqual(mismatches, [])


class ValidationTests(unittest.TestCase):
    def valid_preset(self):
        return {
            "schema_version": 1,
            "name": "test",
            "description": "test preset",
            "master_gain": 0.5,
            "scale_pitches": [57, 60, 64],
            "voices": {"tone": {"dir": "tone", "gain": 0.5, "mioi": 0.2}},
            "events": {"Stop": {"default": "tone"}},
        }

    def test_rejects_unknown_schema_version(self):
        preset = self.valid_preset()
        preset["schema_version"] = 99
        self.assertTrue(any("unsupported" in error for error in preset_schema.validate(preset)))

    def test_scale_pitches_are_optional_for_unpitched_custom_presets(self):
        preset = self.valid_preset()
        preset.pop("scale_pitches")
        self.assertEqual(preset_schema.validate(preset), [])

    def test_rejects_path_traversal_and_unknown_voice(self):
        preset = self.valid_preset()
        preset["voices"]["tone"]["dir"] = "../outside"
        preset["events"]["Stop"]["default"] = "missing"
        errors = preset_schema.validate(preset)
        self.assertTrue(any("safe directory" in error for error in errors))
        self.assertTrue(any("unknown voice" in error for error in errors))

    def test_rejects_out_of_range_audio_values(self):
        preset = self.valid_preset()
        preset["voices"]["tone"]["gain"] = 3
        preset["voices"]["tone"]["delay"] = {"feedback": 0.99}
        errors = preset_schema.validate(preset)
        self.assertGreaterEqual(len(errors), 2)


class PresetPortabilityTests(unittest.TestCase):
    def tearDown(self):
        for name in ("test_portable", "test_imported"):
            directory = preset_store.user_dir(name)
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
            history = preset_store._history_dir(name)
            if history:
                shutil.rmtree(history, ignore_errors=True)

    def test_save_history_undo_export_and_import(self):
        original = dict(preset_store.load("meadow"))
        original["description"] = "portable original"
        preset_store.save("test_portable", original)

        changed = dict(original)
        changed["description"] = "portable changed"
        preset_store.save("test_portable", changed)
        self.assertEqual(len(preset_store.history("test_portable")), 1)
        self.assertEqual(preset_store.load("test_portable")["description"], "portable changed")

        self.assertTrue(preset_store.undo("test_portable"))
        self.assertEqual(preset_store.load("test_portable")["description"], "portable original")

        with tempfile.TemporaryDirectory() as directory:
            exported = preset_store.export_to("test_portable", Path(directory) / "portable.json")
            imported = preset_store.import_from(exported, "test_imported")
        self.assertEqual(imported, "test_imported")
        self.assertEqual(preset_store.load(imported)["description"], "portable original")
        self.assertEqual(preset_schema.validate(preset_store.load(imported)), [])

    def test_restore_specific_snapshot_and_reject_future_import_schema(self):
        original = dict(preset_store.load("meadow"))
        original["description"] = "first version"
        preset_store.save("test_portable", original)
        changed = dict(original)
        changed["description"] = "second version"
        preset_store.save("test_portable", changed)
        entry_id = preset_store.history("test_portable")[0]["id"]
        self.assertTrue(preset_store.restore("test_portable", entry_id))
        self.assertEqual(preset_store.load("test_portable")["description"], "first version")

        future = dict(original)
        future["schema_version"] = 999
        with self.assertRaises(preset_schema.PresetValidationError):
            preset_store.import_data(future, "test_imported")


if __name__ == "__main__":
    unittest.main()
