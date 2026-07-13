#!/usr/bin/env python3
"""Immutable built-in presets with mutable user overlays and sample caches."""
from __future__ import annotations

import json
import difflib
import re
import shutil
import time
from pathlib import Path

import paths
import preset_schema
import stateio


_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def valid_name(name):
    return isinstance(name, str) and _NAME_RE.fullmatch(name) is not None


def builtin_dir(name):
    return paths.BUILTIN_PRESETS_DIR / name if valid_name(name) else None


def user_dir(name):
    return paths.USER_PRESETS_DIR / name if valid_name(name) else None


def _has_preset(directory):
    return bool(directory and (directory / "preset.json").is_file())


def list_names():
    names = set()
    for root in (paths.BUILTIN_PRESETS_DIR, paths.USER_PRESETS_DIR):
        if root.exists():
            names.update(d.name for d in root.iterdir() if d.is_dir() and _has_preset(d))
    return sorted(names)


def source_dir(name):
    user = user_dir(name)
    if _has_preset(user):
        return user
    builtin = builtin_dir(name)
    return builtin if _has_preset(builtin) else None


def preset_path(name):
    directory = source_dir(name)
    return directory / "preset.json" if directory else None


def default_path(name):
    user = user_dir(name)
    if user and (user / "preset.default.json").is_file():
        return user / "preset.default.json"
    builtin = builtin_dir(name)
    return (builtin / "preset.default.json") if builtin and (builtin / "preset.default.json").is_file() else None


def load(name, default=None):
    path = preset_path(name)
    return stateio.load_json(path, default) if path else default


def _normalized(name, data):
    if not valid_name(name):
        raise ValueError("invalid preset name")
    data = dict(data)
    data["schema_version"] = preset_schema.CURRENT_VERSION
    data["name"] = name
    preset_schema.assert_valid(data)
    return data


def _history_dir(name):
    return paths.PRESET_HISTORY_DIR / name if valid_name(name) else None


def _snapshot(name, data, *, coalesce=True):
    if not data:
        return None
    data = _normalized(name, data)
    directory = _history_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    latest = max(directory.glob("*.json"), default=None)
    if coalesce and latest is not None and time.time() - latest.stat().st_mtime < 2.0:
        return latest  # coalesce rapid slider/input updates into one undo step
    path = directory / f"{time.time_ns()}.json"
    stateio.save_json(path, data)
    entries = sorted(directory.glob("*.json"), reverse=True)
    for old in entries[25:]:
        old.unlink()
    return path


def _write(name, data, *, save_default=False):
    directory = user_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    stateio.save_json(directory / "preset.json", data)
    if save_default:
        stateio.save_json(directory / "preset.default.json", data)
    return directory / "preset.json"


def save(name, data, *, save_default=False, record_history=True):
    data = _normalized(name, data)
    current = load(name)
    if record_history and current is not None and current != data:
        _snapshot(name, current)
    return _write(name, data, save_default=save_default)


def update(name, mutator):
    current = load(name)
    if current is None:
        raise ValueError(f"unknown preset {name!r}")
    changed = json.loads(json.dumps(current))
    mutator(changed)
    save(name, changed)
    return changed


def is_custom(name):
    return bool((load(name, {}) or {}).get("custom"))


def is_user_override(name):
    return _has_preset(user_dir(name))


def render_path(name):
    builtin = builtin_dir(name)
    path = builtin / "render.py" if builtin else None
    return path if path and path.is_file() else None


def sample_output_dir(name):
    if is_custom(name):
        return user_dir(name) / "samples"
    return paths.SAMPLES_DIR / name


def sample_read_dir(name):
    preferred = sample_output_dir(name)
    if preferred.exists() and next(preferred.rglob("*.wav"), None) is not None:
        return preferred
    # Upgrade compatibility: legacy renders remain playable until migration or
    # regeneration copies them into the user cache.
    legacy = builtin_dir(name)
    legacy = legacy / "samples" if legacy else None
    if legacy and legacy.exists() and next(legacy.rglob("*.wav"), None) is not None:
        return legacy
    return preferred


def sample_asset(name, relative):
    """Resolve one sample file/directory with per-asset legacy fallback.

    This matters during partial renders: one freshly cached voice must not hide
    the other voices that still exist only in a legacy checkout sample tree.
    """
    preferred_base = sample_output_dir(name).resolve()
    try:
        preferred = (preferred_base / relative).resolve()
        preferred.relative_to(preferred_base)
    except (OSError, ValueError):
        return preferred_base / "__invalid__"
    if preferred.is_file() or (preferred.is_dir() and next(preferred.rglob("*.wav"), None)):
        return preferred
    legacy_base = builtin_dir(name)
    legacy_base = (legacy_base / "samples").resolve() if legacy_base else None
    if legacy_base:
        try:
            legacy = (legacy_base / relative).resolve()
            legacy.relative_to(legacy_base)
            if legacy.exists():
                return legacy
        except (OSError, ValueError):
            pass
    return preferred


def reset(name):
    if not valid_name(name):
        return False
    user = user_dir(name)
    if is_custom(name):
        default = default_path(name)
        if not default:
            return False
        current = load(name)
        restored = _normalized(name, stateio.load_json(default, {}))
        if current != restored:
            _snapshot(name, current, coalesce=False)
        _write(name, restored)
        return True
    override = user / "preset.json" if user else None
    if override and override.exists():
        _snapshot(name, load(name), coalesce=False)
        override.unlink()
        try:
            if user.exists() and not any(user.iterdir()):
                user.rmdir()
        except OSError:
            pass
        return True
    return default_path(name) is not None


def delete_custom(name):
    directory = user_dir(name)
    if not directory or not is_custom(name):
        return False
    shutil.rmtree(directory)
    shutil.rmtree(_history_dir(name), ignore_errors=True)
    return True


def rename_custom(name, new_name):
    if not valid_name(new_name) or new_name in list_names() or not is_custom(name):
        return False
    source = user_dir(name)
    target = user_dir(new_name)
    source.rename(target)
    old_history = _history_dir(name)
    new_history = _history_dir(new_name)
    if old_history.exists():
        if new_history.exists():
            shutil.rmtree(new_history)
        old_history.rename(new_history)
    data = load(new_name, {})
    data["name"] = new_name
    save(new_name, data, record_history=False)
    default = target / "preset.default.json"
    if default.exists():
        baseline = stateio.load_json(default, {})
        baseline["name"] = new_name
        stateio.save_json(default, preset_schema.assert_valid({
            **baseline, "schema_version": preset_schema.CURRENT_VERSION
        }))
    return True


def history(name):
    directory = _history_dir(name)
    if not directory or not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        data = stateio.load_json(path, {})
        result.append({
            "id": path.stem,
            "path": path,
            "timestamp": path.stat().st_mtime,
            "description": data.get("description", ""),
        })
    return result


def undo(name):
    entries = history(name)
    if not entries:
        return False
    entry = entries[0]
    restored = _normalized(name, stateio.load_json(entry["path"], {}))
    _write(name, restored)
    entry["path"].unlink()
    return True


def restore(name, entry_id):
    if not valid_name(name) or not isinstance(entry_id, str) or not entry_id.isdigit():
        return False
    path = _history_dir(name) / f"{entry_id}.json"
    if not path.is_file():
        return False
    restored = _normalized(name, stateio.load_json(path, {}))
    current = load(name)
    if current != restored:
        _snapshot(name, current, coalesce=False)
        _write(name, restored)
    return True


def export_to(name, destination):
    data = load(name)
    if data is None:
        raise ValueError(f"unknown preset {name!r}")
    destination = Path(destination).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2) + "\n")
    return destination


def import_from(source, name=None):
    source = Path(source).expanduser()
    data = json.loads(source.read_text())
    return import_data(data, name or data.get("name") or source.stem)


def import_data(data, name=None):
    if not isinstance(data, dict):
        raise ValueError("preset import must contain one JSON object")
    incoming_version = data.get("schema_version")
    if incoming_version not in (None, preset_schema.CURRENT_VERSION):
        raise preset_schema.PresetValidationError([
            f"schema_version: unsupported {incoming_version!r} "
            f"(expected {preset_schema.CURRENT_VERSION})"
        ])
    target = name or data.get("name")
    if not valid_name(target):
        raise ValueError("import needs a valid lowercase preset name")
    save(target, data)
    return target


def diff_from_default(name):
    current = load(name)
    if current is None:
        raise ValueError(f"unknown preset {name!r}")
    baseline_path = default_path(name)
    baseline = stateio.load_json(baseline_path, {}) if baseline_path else {}
    before = json.dumps(baseline, indent=2, sort_keys=True).splitlines(keepends=True)
    after = json.dumps(current, indent=2, sort_keys=True).splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        before, after, fromfile=f"{name}:default", tofile=f"{name}:current"
    ))


def renderer_env(name):
    config = preset_path(name)
    return {
        "CLAUDIO_SAMPLES_DIR": str(sample_output_dir(name)),
        "CLAUDIO_PRESET_CONFIG": str(config) if config else "",
    }
