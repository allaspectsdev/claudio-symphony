---
name: claudio
description: Use when the user wants to control or understand Claudio Symphony — the ambient music that plays on Claude Code hook events. Covers opening the live web console, switching the sound "preset"/room, muting, recording a clip, jamming with the mic, and troubleshooting silence. Triggers on "claudio", "the music", "change the sound", "open the console", "mute the sounds".
---

# Claudio Symphony

Claudio turns Claude Code hook events into soft, in-key ambient music. It's installed as a plugin (hooks already wired) or via `bin/claudio install` from a clone. When the plugin is active, `claudio` is on the PATH of *your* (Claude's) Bash tool only — not the user's own terminal. So run `claudio …` commands for the user; if they want to run things themselves, give them the full path (`<plugin-or-repo>/bin/claudio …`, or `python3 <plugin-or-repo>/cli.py …`). For first-time setup, run `claudio setup` for them (or they can run `python3 <plugin-or-repo>/install.py`).

## Most common things people ask for

- **Open the visual console** (the thing to look at): `claudio web` — a live constellation of glowing "voices" with 5 physics view modes, preset browser, mic-jam, and recording. Runs locally at `http://127.0.0.1:8788`.
- **Change the sound / vibe**: `claudio preset use <name>` (e.g. `meadow`, `cathedral`, `rainfall`, `koto`, `studio`). List them with `claudio preset list`; hear them with `claudio audition`.
- **Make it quieter / off**: `claudio volume 0.3`, or `claudio off` / `claudio on`.
- **Turn on the drone bed**: `claudio drone on` (only some presets have one — `cathedral` does). It follows the key live.
- **Record a clip to share**: `claudio record 30` (it prints the saved file's full path; `claudio record list` shows the folder), or hit **Rec** in `claudio web`.
- **Jam with it**: open `claudio web`, hit **🎤 Listen**, and hum — it re-keys to your note. Headphones + Options → Mic monitor lets you play through its reverb.

## If it's silent

Run **`claudio doctor`** first — it checks Python, numpy, the audio player, whether the active preset's sounds are rendered, and whether hooks are wired, and prints the exact fix for anything missing. `claudio doctor --fix` will render the active preset for you if that's the problem.

Common causes it surfaces:
- **numpy missing** (needed to synthesize sounds): `python3 -m pip install numpy`, then start a new session.
- **No sounds rendered yet** on a brand-new plugin install — `claudio doctor --fix` or `claudio regen` renders them. The plugin also renders the default room automatically on the first session.
- **No audio player** on Linux/Windows: install `ffmpeg` (see README requirements).
- **Muted / volume down**: `claudio on`, and raise master in `claudio web`.

## Full command reference

`claudio --help` prints every command (bare `claudio` prints status; `claudio <command> --help` prints just that command's lines) — per-voice tuning, event→sound mapping, scales, chord progressions, the MIDI jukebox, session replay, and directory routing rules. Prefer the web console (`claudio web`) for anything visual or exploratory.
