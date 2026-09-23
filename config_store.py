#!/usr/bin/env python3
"""Shared transactional access to Claudio's global configuration."""
from __future__ import annotations

import copy

import paths
import stateio


DEFAULT_PRESET = "meadow"
DEFAULT_CONFIG = {
    "preset": DEFAULT_PRESET,
    "master_gain": 0.55,
    "drone_gain": 0.0,
    "quant": {"enabled": False, "bpm": 120.0, "grid": 0.5},
}


def defaults():
    return copy.deepcopy(DEFAULT_CONFIG)


def load(path=None):
    data = stateio.load_json(path or paths.CONFIG_FILE, {})
    # A hand-edited config.json holding [] or "x" must not crash every caller.
    return data if isinstance(data, dict) else {}


def save(data, path=None):
    stateio.save_json(path or paths.CONFIG_FILE, data)
    return data


def update(mutator, path=None):
    def guarded(config):
        config = config if isinstance(config, dict) else {}
        replacement = mutator(config)
        return config if replacement is None else replacement
    return stateio.update_json(path or paths.CONFIG_FILE, {}, guarded)


def patch(values=None, remove=(), path=None):
    def mutate(config):
        config.update(values or {})
        for key in remove:
            config.pop(key, None)
    return update(mutate, path)


def active_preset(path=None):
    return load(path).get("preset", DEFAULT_PRESET)
