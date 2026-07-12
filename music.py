#!/usr/bin/env python3
"""Pure shared music-domain definitions used by hooks, CLI, TUI, and web UI."""
from __future__ import annotations

import time


MAPPABLE_EVENTS = [
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "SubagentStop", "Stop", "SessionEnd", "Notification", "PreCompact",
]
HOOK_EVENTS = [
    "SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "PreToolUse",
    "PostToolUse", "PostToolUseFailure", "SubagentStop", "Notification", "PreCompact",
]

SCALES = {
    "A_major": ([9, 11, 1, 2, 4, 6, 8], [9, 4]),
    "A_pent": ([9, 11, 1, 4, 6], [9, 4]),
    "A_lydian": ([9, 11, 1, 3, 4, 6, 8], [9, 4]),
    "A_lydian_pent": ([9, 11, 1, 3, 6], [9, 6]),
    "A_dorian": ([9, 11, 0, 2, 4, 6, 7], [9, 4]),
    "A_aeolian": ([9, 11, 0, 2, 4, 5, 7], [9, 4]),
    "A_in_sen": ([9, 10, 0, 4, 5], [9, 4]),
    "A_phrygian": ([9, 10, 0, 2, 4, 5, 7], [9, 4]),
    "A_yo": ([9, 11, 2, 4, 7], [9, 4]),
    "A_hijaz": ([9, 10, 1, 2, 4, 5, 7], [9, 4]),
}

CHORDS = {
    "A": ([9, 1, 4], 9), "Am": ([9, 0, 4], 9),
    "B": ([11, 3, 6], 11), "Bm": ([11, 2, 6], 11),
    "C": ([0, 4, 7], 0), "C#m": ([1, 4, 8], 1),
    "D": ([2, 6, 9], 2), "Dm": ([2, 5, 9], 2),
    "E": ([4, 8, 11], 4), "Em": ([4, 7, 11], 4),
    "F": ([5, 9, 0], 5), "F#m": ([6, 9, 1], 6),
    "G": ([7, 11, 2], 7),
}

PROGRESSIONS = {
    "pop": ["A", "E", "F#m", "D"],
    "doo_wop": ["A", "F#m", "D", "E"],
    "andalusian": ["Am", "G", "F", "E"],
    "canon": ["A", "E", "F#m", "C#m", "D", "A", "D", "E"],
    "lofi": ["Bm", "E", "A", "F#m"],
}


def chord_step(progression, now=None):
    steps = progression.get("steps") or []
    if not steps:
        return None, None
    seconds = max(2.0, float(progression.get("step_s", 8) or 8))
    index = int((now if now is not None else time.time()) // seconds) % len(steps)
    return index, steps[index]


def expand_pcs_to_midis(pitch_classes, low=57, high=88):
    return [midi for midi in range(low, high + 1) if midi % 12 in pitch_classes]


def mapping_event_name(event_name):
    return "PostToolUse" if event_name == "PostToolUseFailure" else event_name
