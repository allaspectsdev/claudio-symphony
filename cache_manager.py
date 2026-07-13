#!/usr/bin/env python3
"""Inspect and safely maintain Claudio's disposable generated-audio cache."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import config_store
import paths
import preset_store
import stateio


DEFAULT_LIMIT_MB = 1024
MIN_LIMIT_MB = 64
MAX_LIMIT_MB = 16384
_LOCK_TARGET = paths.STATE_DIR / "cache-maintenance"


def _files(root):
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]


def _size(root):
    total = 0
    for path in _files(root):
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def _updated(root):
    values = []
    for path in _files(root):
        try:
            values.append(path.stat().st_mtime)
        except OSError:
            pass
    return max(values, default=0.0)


def limit_mb(config_path=None):
    raw = (config_store.load(config_path).get("cache") or {}).get("max_mb", DEFAULT_LIMIT_MB)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_LIMIT_MB
    return 0 if value <= 0 else max(MIN_LIMIT_MB, min(MAX_LIMIT_MB, value))


def _status(config_path=None):
    samples = []
    if paths.SAMPLES_DIR.exists():
        for directory in sorted(path for path in paths.SAMPLES_DIR.iterdir() if path.is_dir()):
            samples.append({
                "name": directory.name,
                "bytes": _size(directory),
                "updated": _updated(directory),
            })
    sample_bytes = sum(item["bytes"] for item in samples)
    rate_bytes = _size(paths.RATE_CACHE_DIR)
    total_bytes = _size(paths.CACHE_DIR)
    maximum = limit_mb(config_path)
    return {
        "total_bytes": total_bytes,
        "sample_bytes": sample_bytes,
        "rate_bytes": rate_bytes,
        "other_bytes": max(0, total_bytes - sample_bytes - rate_bytes),
        "limit_mb": maximum,
        "limit_bytes": maximum * 1024 * 1024 if maximum else 0,
        "over_limit": bool(maximum and total_bytes > maximum * 1024 * 1024),
        "samples": samples,
        "cache_dir": str(paths.CACHE_DIR),
    }


def status(config_path=None):
    return _status(config_path)


def set_limit(value, config_path=None, *, preserve=()):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("cache limit must be a whole number of MB or 0 for unlimited")
    if value != 0 and not MIN_LIMIT_MB <= value <= MAX_LIMIT_MB:
        raise ValueError(f"cache limit must be 0 or {MIN_LIMIT_MB}..{MAX_LIMIT_MB} MB")

    def mutate(config):
        config.setdefault("cache", {})["max_mb"] = value
    config_store.update(mutate, config_path)
    return trim(config_path=config_path, preserve=preserve)


def _remove(path):
    before = _size(path)
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)
    return before


def _invalidate_render_state(names):
    for name in names:
        if not preset_store.valid_name(name):
            continue
        state = paths.STATE_DIR / name
        for marker in (state / ".rendered", state / ".rendering"):
            try:
                marker.unlink()
            except OSError:
                pass


def _render_in_progress(name):
    marker = paths.STATE_DIR / name / ".rendering.lock"
    try:
        return marker.is_file() and time.time() - marker.stat().st_mtime < 900
    except OSError:
        return False


def clear(scope, *, preset=None, config_path=None):
    removed = []
    freed = 0
    with stateio.file_lock(_LOCK_TARGET, timeout=5.0):
        if scope in ("rate", "all"):
            freed += _remove(paths.RATE_CACHE_DIR)
            removed.append("rate")
        if scope in ("samples", "all"):
            directories = list(paths.SAMPLES_DIR.iterdir()) if paths.SAMPLES_DIR.exists() else []
            cleared = []
            for directory in directories:
                if directory.is_dir() and _render_in_progress(directory.name):
                    continue
                freed += _remove(directory)
                cleared.append(directory.name)
            _invalidate_render_state(cleared)
            removed.extend(cleared)
        elif scope == "preset":
            if not preset_store.valid_name(preset):
                raise ValueError("invalid preset name")
            if _render_in_progress(preset):
                raise ValueError(f"preset {preset!r} is rendering; try again when it finishes")
            target = paths.SAMPLES_DIR / preset
            freed += _remove(target)
            _invalidate_render_state((preset,))
            removed.append(preset)
        elif scope not in ("rate", "samples", "all"):
            raise ValueError("cache scope must be rate, samples, preset, or all")
        paths.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        paths.RATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return {"freed_bytes": freed, "removed": removed, **_status(config_path)}


def trim(*, config_path=None, preserve=()):
    preserve = {name for name in preserve if preset_store.valid_name(name)}
    removed = []
    freed = 0
    maximum = limit_mb(config_path)
    if not maximum:
        return {"freed_bytes": 0, "removed": [], **_status(config_path)}
    target = maximum * 1024 * 1024
    with stateio.file_lock(_LOCK_TARGET, timeout=5.0):
        current = _size(paths.CACHE_DIR)
        if current > target and paths.RATE_CACHE_DIR.exists():
            amount = _remove(paths.RATE_CACHE_DIR)
            freed += amount
            current -= amount
            if amount:
                removed.append("rate")
        candidates = []
        if paths.SAMPLES_DIR.exists():
            candidates = sorted(
                (directory for directory in paths.SAMPLES_DIR.iterdir()
                 if directory.is_dir() and directory.name not in preserve
                 and not _render_in_progress(directory.name)),
                key=_updated,
            )
        for directory in candidates:
            if current <= target:
                break
            amount = _remove(directory)
            freed += amount
            current -= amount
            removed.append(directory.name)
            _invalidate_render_state((directory.name,))
        paths.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        paths.RATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return {"freed_bytes": freed, "removed": removed, **_status(config_path)}
