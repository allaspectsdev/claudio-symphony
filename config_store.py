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
    return stateio.load_json(path or paths.CONFIG_FILE, {})


def save(data, path=None):
    stateio.save_json(path or paths.CONFIG_FILE, data)
    return data


def update(mutator, path=None):
    return stateio.update_json(path or paths.CONFIG_FILE, {}, mutator)


def patch(values=None, remove=(), path=None):
    def mutate(config):
        config.update(values or {})
        for key in remove:
            config.pop(key, None)
    return update(mutate, path)


def active_preset(path=None):
    return load(path).get("preset", DEFAULT_PRESET)
