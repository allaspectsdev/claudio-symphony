#!/usr/bin/env python3
"""Platform-native paths and legacy-data migration for Claudio Symphony.

The source/plugin checkout is immutable application code.  User configuration,
runtime state, generated samples, imported songs, custom presets, logs, and
recordings live in OS-appropriate directories so plugin upgrades cannot erase
them.  Set ``CLAUDIO_HOME`` to keep every mutable directory under one portable
root (also used by the test suite).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
BUILTIN_PRESETS_DIR = APP_ROOT / "presets"
WEB_DIR = APP_ROOT / "web"


def _expand_env_path(name, fallback):
    value = os.environ.get(name)
    return Path(value).expanduser() if value else Path(fallback).expanduser()


PORTABLE_HOME = os.environ.get("CLAUDIO_HOME")
if PORTABLE_HOME:
    USER_ROOT = Path(PORTABLE_HOME).expanduser().resolve()
    CONFIG_DIR = USER_ROOT / "config"
    STATE_DIR = USER_ROOT / "state"
    DATA_DIR = USER_ROOT / "data"
    CACHE_DIR = USER_ROOT / "cache"
    LOG_DIR = USER_ROOT / "logs"
elif sys.platform == "darwin":
    USER_ROOT = Path.home() / "Library" / "Application Support" / "Claudio"
    CONFIG_DIR = USER_ROOT / "config"
    STATE_DIR = USER_ROOT / "state"
    DATA_DIR = USER_ROOT / "data"
    CACHE_DIR = Path.home() / "Library" / "Caches" / "Claudio"
    LOG_DIR = Path.home() / "Library" / "Logs" / "Claudio"
elif sys.platform.startswith("win"):
    roaming = _expand_env_path("APPDATA", Path.home() / "AppData" / "Roaming") / "Claudio"
    local = _expand_env_path("LOCALAPPDATA", Path.home() / "AppData" / "Local") / "Claudio"
    USER_ROOT = roaming
    CONFIG_DIR = roaming / "config"
    DATA_DIR = roaming / "data"
    STATE_DIR = local / "state"
    CACHE_DIR = local / "cache"
    LOG_DIR = local / "logs"
else:
    CONFIG_DIR = _expand_env_path("XDG_CONFIG_HOME", Path.home() / ".config") / "claudio"
    STATE_DIR = _expand_env_path("XDG_STATE_HOME", Path.home() / ".local" / "state") / "claudio"
    DATA_DIR = _expand_env_path("XDG_DATA_HOME", Path.home() / ".local" / "share") / "claudio"
    CACHE_DIR = _expand_env_path("XDG_CACHE_HOME", Path.home() / ".cache") / "claudio"
    LOG_DIR = STATE_DIR / "logs"
    USER_ROOT = DATA_DIR


CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_FILE = STATE_DIR / "sessions.json"
RULES_FILE = STATE_DIR / "rules.json"
SONG_STATE_FILE = STATE_DIR / "song.json"
USER_PRESETS_DIR = DATA_DIR / "presets"
PRESET_HISTORY_DIR = DATA_DIR / "preset_history"
SONGS_DIR = DATA_DIR / "songs"
RECORDINGS_DIR = DATA_DIR / "recordings"
SAMPLES_DIR = CACHE_DIR / "samples"
RATE_CACHE_DIR = CACHE_DIR / "rate_cache"
MIGRATION_FILE = STATE_DIR / "migration.json"

LEGACY_CONFIG_FILE = APP_ROOT / "config.json"
LEGACY_STATE_DIR = APP_ROOT / "state"
LEGACY_LOG_DIR = APP_ROOT / "logs"
LEGACY_SONGS_DIR = APP_ROOT / "songs"
LEGACY_RECORDINGS_DIR = APP_ROOT / "recordings"


def ensure_dirs():
    for directory in (CONFIG_DIR, STATE_DIR, DATA_DIR, CACHE_DIR, LOG_DIR,
                      USER_PRESETS_DIR, PRESET_HISTORY_DIR, SONGS_DIR,
                      RECORDINGS_DIR, SAMPLES_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _copy_file_if_missing(src, dst):
    if src.is_file() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def _copy_tree_contents(src, dst, *, ignore=None):
    if not src.is_dir():
        return 0
    copied = 0
    dst.mkdir(parents=True, exist_ok=True)
    ignored = set(ignore or ())
    for item in src.iterdir():
        if item.name in ignored or item.name == "__pycache__":
            continue
        target = dst / item.name
        if item.is_dir():
            if not target.exists():
                shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                copied += 1
        elif not target.exists():
            shutil.copy2(item, target)
            copied += 1
    return copied


def _legacy_preset_is_custom(directory):
    try:
        return bool(json.loads((directory / "preset.json").read_text()).get("custom"))
    except Exception:
        return False


def _legacy_builtin_was_edited(directory):
    preset = directory / "preset.json"
    default = directory / "preset.default.json"
    try:
        return preset.is_file() and default.is_file() and preset.read_bytes() != default.read_bytes()
    except OSError:
        return False


def migration_status():
    ensure_dirs()
    try:
        status = json.loads(MIGRATION_FILE.read_text()) if MIGRATION_FILE.exists() else {}
    except Exception:
        status = {}
    legacy_large = (LEGACY_RECORDINGS_DIR.exists() or LEGACY_SONGS_DIR.exists()
                    or any((p / "samples").exists() for p in BUILTIN_PRESETS_DIR.iterdir() if p.is_dir()))
    return {
        "small_complete": bool(status.get("small_complete")),
        "large_complete": bool(status.get("large_complete")),
        "legacy_large_found": bool(legacy_large),
    }


def migrate_legacy(*, include_large=False):
    """Copy legacy checkout-local data without deleting its source.

    Small config/state/log and preset overrides are safe during startup.  Large
    recordings, songs, and rendered samples move only during an explicit setup
    or migration command; playback retains a legacy fallback until then.
    """
    ensure_dirs()
    result = {"config": 0, "state": 0, "logs": 0, "preset_overrides": 0,
              "songs": 0, "recordings": 0, "samples": 0}
    result["config"] += int(_copy_file_if_missing(LEGACY_CONFIG_FILE, CONFIG_FILE))
    result["state"] += _copy_tree_contents(
        LEGACY_STATE_DIR, STATE_DIR,
        ignore={"rate_cache", "recording", "midiplay", "timelines"}
        if not include_large else {"rate_cache"},
    )
    result["logs"] += _copy_tree_contents(LEGACY_LOG_DIR, LOG_DIR)

    if BUILTIN_PRESETS_DIR.exists():
        for directory in BUILTIN_PRESETS_DIR.iterdir():
            if not directory.is_dir() or not (directory / "preset.json").exists():
                continue
            target = USER_PRESETS_DIR / directory.name
            if _legacy_preset_is_custom(directory):
                target.mkdir(parents=True, exist_ok=True)
                result["preset_overrides"] += int(_copy_file_if_missing(directory / "preset.json", target / "preset.json"))
                _copy_file_if_missing(directory / "preset.default.json", target / "preset.default.json")
                if include_large and (directory / "samples").exists():
                    result["samples"] += _copy_tree_contents(directory / "samples", target / "samples")
            elif _legacy_builtin_was_edited(directory):
                target.mkdir(parents=True, exist_ok=True)
                result["preset_overrides"] += int(_copy_file_if_missing(directory / "preset.json", target / "preset.json"))
            if include_large and (directory / "samples").exists() and not _legacy_preset_is_custom(directory):
                result["samples"] += _copy_tree_contents(directory / "samples", SAMPLES_DIR / directory.name)

    if include_large:
        result["songs"] += _copy_tree_contents(LEGACY_SONGS_DIR, SONGS_DIR)
        result["recordings"] += _copy_tree_contents(LEGACY_RECORDINGS_DIR, RECORDINGS_DIR)

    status = migration_status()
    status["small_complete"] = True
    if include_large:
        status["large_complete"] = True
    MIGRATION_FILE.write_text(json.dumps(status, indent=2) + "\n")
    return result


# Keep imports safe for hooks: only small files are copied automatically.
ensure_dirs()
if not migration_status()["small_complete"]:
    try:
        migrate_legacy(include_large=False)
    except Exception:
        pass
