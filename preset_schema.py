#!/usr/bin/env python3
"""Versioned validation contract for Claudio preset JSON documents."""
from __future__ import annotations

import re


CURRENT_VERSION = 1
_SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_SAFE_DIR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class PresetValidationError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(data, *, require_version=True):
    """Return human-readable validation errors without raising."""
    errors = []
    if not isinstance(data, dict):
        return ["preset: expected an object"]

    version = data.get("schema_version")
    if version is None and require_version:
        errors.append("schema_version: missing (expected 1)")
    elif version is not None and version != CURRENT_VERSION:
        errors.append(f"schema_version: unsupported {version!r} (expected {CURRENT_VERSION})")

    name = data.get("name")
    if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
        errors.append("name: expected a lowercase preset identifier")
    if not isinstance(data.get("description"), str):
        errors.append("description: expected a string")

    for key, lo, hi in (("master_gain", 0, 1), ("drone_gain", 0, 1),
                        ("reverb_scale", 0, 2)):
        if key in data and (not _number(data[key]) or not lo <= data[key] <= hi):
            errors.append(f"{key}: expected a number from {lo} to {hi}")

    pitches = data.get("scale_pitches")
    if pitches is not None:
        if not isinstance(pitches, list) or not pitches:
            errors.append("scale_pitches: expected a non-empty MIDI-note list when provided")
        elif any(not isinstance(note, int) or isinstance(note, bool) or not 0 <= note <= 127
                 for note in pitches):
            errors.append("scale_pitches: every note must be an integer from 0 to 127")

    voices = data.get("voices")
    if not isinstance(voices, dict) or not voices:
        errors.append("voices: expected a non-empty object")
        voices = {}
    for voice, spec in voices.items():
        at = f"voices.{voice}"
        if not isinstance(voice, str) or not _SAFE_NAME.fullmatch(voice):
            errors.append(f"{at}: invalid voice identifier")
        if not isinstance(spec, dict):
            errors.append(f"{at}: expected an object")
            continue
        directory = spec.get("dir")
        if not isinstance(directory, str) or not _SAFE_DIR.fullmatch(directory):
            errors.append(f"{at}.dir: expected one safe directory name")
        for key, lo, hi in (("gain", 0, 1), ("mioi", 0.01, 120)):
            value = spec.get(key)
            if not _number(value) or not lo <= value <= hi:
                errors.append(f"{at}.{key}: expected a number from {lo} to {hi}")
        if "rate_jitter" in spec and not isinstance(spec["rate_jitter"], bool):
            errors.append(f"{at}.rate_jitter: expected a boolean")
        if "tonal_anchor_midi" in spec and (
            not isinstance(spec["tonal_anchor_midi"], int)
            or isinstance(spec["tonal_anchor_midi"], bool)
            or not 0 <= spec["tonal_anchor_midi"] <= 127
        ):
            errors.append(f"{at}.tonal_anchor_midi: expected an integer from 0 to 127")
        _validate_effect(spec.get("reverb"), at + ".reverb", "reverb", errors)
        _validate_effect(spec.get("delay"), at + ".delay", "delay", errors)

    events = data.get("events")
    if not isinstance(events, dict):
        errors.append("events: expected an object")
        events = {}
    voice_names = set(voices)
    for event, spec in events.items():
        at = f"events.{event}"
        if not isinstance(event, str) or not event or len(event) > 80:
            errors.append(f"{at}: invalid event name")
        if not isinstance(spec, dict):
            errors.append(f"{at}: expected an object")
            continue
        for key in ("default", "on_failure"):
            if key in spec and spec[key] is not None and spec[key] not in voice_names:
                errors.append(f"{at}.{key}: unknown voice {spec[key]!r}")
        by_tool = spec.get("by_tool", {})
        if not isinstance(by_tool, dict):
            errors.append(f"{at}.by_tool: expected an object")
        else:
            for tool, voice in by_tool.items():
                if not isinstance(tool, str) or not tool:
                    errors.append(f"{at}.by_tool: invalid tool name")
                if voice is not None and voice not in voice_names:
                    errors.append(f"{at}.by_tool.{tool}: unknown voice {voice!r}")
        effect = spec.get("effect")
        if effect is not None:
            if not isinstance(effect, dict):
                errors.append(f"{at}.effect: expected an object")
            else:
                _validate_effect(effect.get("delay"), at + ".effect.delay", "delay", errors)

    drone = data.get("drone")
    if drone is not None and (not isinstance(drone, str) or not _SAFE_DIR.fullmatch(drone)):
        errors.append("drone: expected a safe WAV filename or null")
    return errors


def _validate_effect(value, at, kind, errors):
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{at}: expected an object")
        return
    ranges = (("wet", 0, 1), ("decay", 0.1, 20), ("brightness", 0, 1)) \
        if kind == "reverb" else (("ms", 40, 2000), ("feedback", 0, 0.85), ("count", 0, 8))
    for key, lo, hi in ranges:
        if key in value and (not _number(value[key]) or not lo <= value[key] <= hi):
            errors.append(f"{at}.{key}: expected a number from {lo} to {hi}")


def assert_valid(data):
    errors = validate(data)
    if errors:
        raise PresetValidationError(errors)
    return data
