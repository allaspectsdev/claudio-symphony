#!/usr/bin/env python3
"""
Claudio Symphony — MIDI song import + sequencer.

Drop in a Standard MIDI File (e.g. the Sonic 2 themes) and have hook
events play through its melody one note at a time instead of using the
Markov-weighted picker. Also exposes a master quantization grid (BPM +
subdivision) so triggers snap to the beat.

Resolution of which song plays for an event (highest priority first):
  1. session pin       — sessions.json[session].song_pinned
  2. preset's default  — preset.json["song"]
  3. global default    — state/song.json["global"]

Each song has its own position pointer so switching back and forth keeps
your place. A song may be reduced to a single MIDI channel ("lead"
auto-detected by default) so polyphonic files don't smear into mush.

Pure stdlib — small SMF parser inside, no external deps.
"""
import json, struct, time
from pathlib import Path
import stateio

HERE = Path(__file__).resolve().parent
SONGS = HERE / "songs"
STATE = HERE / "state"
CONFIG = HERE / "config.json"


# ---------- atomic JSON ----------

def _load(p, default):
    return stateio.load_json(p, default)


def _save(p, d):
    stateio.save_json(p, d, indent=2, newline=False)


# ---------- SMF parser (Type 0/1, ticks-per-quarter only) ----------

def _read_varlen(data, i):
    val = 0
    while True:
        b = data[i]; i += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i


def parse_midi(path):
    """Parse a Standard MIDI File. Returns
        {bpm, ppq, notes: [{midi, beat, velocity, channel}, ...]}
    Drum channel (10 / index 9) is skipped. Notes sorted by beat then pitch.
    """
    data = Path(path).read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File (missing MThd)")
    hlen = struct.unpack(">I", data[4:8])[0]
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("SMPTE timing not supported (only ticks-per-quarter)")
    ppq = division if division else 480
    i = 8 + hlen
    initial_tempo_us = None
    notes = []  # (abs_tick, midi, vel, channel)

    for _ in range(ntracks):
        if i + 8 > len(data) or data[i:i+4] != b"MTrk":
            break
        tlen = struct.unpack(">I", data[i+4:i+8])[0]
        i += 8
        end = min(i + tlen, len(data))
        abs_tick = 0
        running = None
        while i < end:
            delta, i = _read_varlen(data, i)
            abs_tick += delta
            if i >= end:
                break
            b = data[i]
            if b & 0x80:
                status = b; i += 1
                if status < 0xF0:
                    running = status
            else:
                status = running
                if status is None:
                    i += 1
                    continue
            if status == 0xFF:  # meta
                if i >= end: break
                mtype = data[i]; i += 1
                mlen, i = _read_varlen(data, i)
                if mtype == 0x51 and mlen == 3 and i + 3 <= end:
                    tempo_us = (data[i] << 16) | (data[i+1] << 8) | data[i+2]
                    if initial_tempo_us is None and abs_tick == 0:
                        initial_tempo_us = tempo_us
                i += mlen
            elif status in (0xF0, 0xF7):  # sysex
                slen, i = _read_varlen(data, i)
                i += slen
            else:
                hi = status & 0xF0
                ch = status & 0x0F
                if hi in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    if i + 2 > end: break
                    p1, p2 = data[i], data[i+1]; i += 2
                    if hi == 0x90 and p2 > 0 and ch != 9:
                        notes.append((abs_tick, p1, p2, ch))
                elif hi in (0xC0, 0xD0):
                    if i + 1 > end: break
                    i += 1
        i = end

    notes.sort(key=lambda n: (n[0], -n[1]))
    bpm = 60_000_000 / initial_tempo_us if initial_tempo_us else 120.0
    return {
        "bpm": round(bpm, 3),
        "ppq": ppq,
        "notes": [
            {"midi": m, "beat": round(t / ppq, 6), "velocity": v, "channel": ch}
            for (t, m, v, ch) in notes
        ],
    }


def channel_summary(song):
    """Return a list of (channel, count, median_midi) sorted by count desc."""
    by_ch = {}
    for n in song.get("notes") or []:
        by_ch.setdefault(n["channel"], []).append(n["midi"])
    out = []
    for ch, midis in by_ch.items():
        midis.sort()
        med = midis[len(midis)//2]
        out.append((ch, len(midis), med))
    out.sort(key=lambda x: -x[1])
    return out


def lead_channel(song):
    """Heuristic: the 'lead melody' is the channel with the most notes whose
    median pitch is in the lead range (>= MIDI 60). Falls back to highest
    median pitch if nothing crosses the threshold."""
    summary = channel_summary(song)
    if not summary:
        return None
    candidates = [(ch, ct, med) for ch, ct, med in summary if med >= 60]
    if candidates:
        return max(candidates, key=lambda x: (x[1], x[2]))[0]
    return max(summary, key=lambda x: x[2])[0]


# ---------- song library ----------

def import_midi_file(src_path, name=None):
    SONGS.mkdir(exist_ok=True)
    src = Path(src_path).expanduser()
    if not src.exists():
        raise FileNotFoundError(src)
    parsed = parse_midi(src)
    if name is None:
        name = src.stem
    name = "".join(c for c in name if c.isalnum() or c in "-_") or "song"
    _save(SONGS / f"{name}.json", parsed)
    try:
        (SONGS / f"{name}.mid").write_bytes(src.read_bytes())
    except Exception:
        pass
    return name, parsed


def list_songs():
    if not SONGS.exists():
        return []
    return sorted(p.stem for p in SONGS.iterdir() if p.suffix == ".json")


def load_song(name):
    if name is None: return None
    return _load(SONGS / f"{name}.json", None)


def has_song(name):
    return name is not None and (SONGS / f"{name}.json").exists()


# ---------- runtime state ----------

STATE_FILE = STATE / "song.json"
# state shape:
#   {"global": "<name>" | null,
#    "positions": {"<name>": int, ...},
#    "channel": {"<name>": int | "all", ...} }

def _state(): return _load(STATE_FILE, {})
def _set(d): _save(STATE_FILE, d)


def global_song():
    return _state().get("global")


def set_global(name):
    if not has_song(name):
        return False
    def mutate(s):
        s["global"] = name
    stateio.update_json(STATE_FILE, {}, mutate)
    return True


def disable_global():
    def mutate(s):
        s.pop("global", None)
    stateio.update_json(STATE_FILE, {}, mutate)


def position(name):
    return int(_state().get("positions", {}).get(name, 0))


def set_position(name, pos):
    def mutate(s):
        s.setdefault("positions", {})[name] = int(pos)
    stateio.update_json(STATE_FILE, {}, mutate)


def reset_position(name):
    set_position(name, 0)


def get_channel(name):
    """Returns the configured channel for a song: int channel, "all", or
    None if not configured (caller should fall back to lead_channel)."""
    return _state().get("channel", {}).get(name)


def set_channel(name, channel):
    """channel: int | 'all' | 'lead' (auto) | None (clear)."""
    def mutate(s):
        chmap = s.setdefault("channel", {})
        if channel is None or channel == "lead":
            chmap.pop(name, None)
        elif channel == "all":
            chmap[name] = "all"
        else:
            chmap[name] = int(channel)
    stateio.update_json(STATE_FILE, {}, mutate)


def _filter_notes(song, channel):
    notes = song.get("notes") or []
    if channel is None or channel == "all":
        return notes
    return [n for n in notes if n["channel"] == channel]


def notes_for(name, channel=None):
    song = load_song(name)
    if not song: return []
    if channel is None:
        ch = get_channel(name)
        channel = lead_channel(song) if ch is None else ch
    return _filter_notes(song, channel)


def next_note(name):
    """Advance the pointer for `name` and return the next MIDI note, or
    None if no song is active or song has no notes after channel filter."""
    if not name:
        return None
    song = load_song(name)
    if not song:
        return None
    result = {"note": None}
    def mutate(s):
        configured = s.get("channel", {}).get(name)
        channel = lead_channel(song) if configured is None else configured
        notes = _filter_notes(song, channel)
        if not notes:
            return
        positions = s.setdefault("positions", {})
        pos = int(positions.get(name, 0))
        result["note"] = int(notes[pos % len(notes)]["midi"])
        positions[name] = (pos + 1) % len(notes)
    stateio.update_json(STATE_FILE, {}, mutate)
    return result["note"]


# ---------- quantization ----------
#
# Settings live in config.json under "quant":
#   {"enabled": bool, "bpm": float, "grid": float}
# `grid` is in beats (0.25 = 16th, 0.5 = 8th, 1.0 = quarter).

def quant_settings():
    cfg = _load(CONFIG, {})
    q = cfg.get("quant") or {}
    return {
        "enabled": bool(q.get("enabled", False)),
        "bpm": float(q.get("bpm", 120.0)),
        "grid": float(q.get("grid", 0.5)),
    }


def set_quant(enabled=None, bpm=None, grid=None):
    def mutate(cfg):
        q = cfg.get("quant") or {}
        if enabled is not None: q["enabled"] = bool(enabled)
        if bpm is not None:     q["bpm"] = max(20.0, min(300.0, float(bpm)))
        if grid is not None:    q["grid"] = max(0.0625, min(4.0, float(grid)))
        cfg["quant"] = q
    cfg = stateio.update_json(CONFIG, {}, mutate)
    q = cfg.get("quant") or {}
    return {"enabled": bool(q.get("enabled", False)), "bpm": float(q.get("bpm", 120.0)),
            "grid": float(q.get("grid", 0.5))}


def quant_delay():
    """Seconds until the next grid boundary using the global config quant
    settings, or 0 if quant is disabled. Aligns to wall-clock so independent
    triggers land on the same grid."""
    return quant_delay_for(quant_settings())


def quant_delay_for(q):
    """Same math as quant_delay() but with explicit settings — used for
    per-preset quant overrides where a preset.json carries its own
    {enabled, bpm, grid} block. Falls back gracefully on partial dicts."""
    if not q or not q.get("enabled"):
        return 0.0
    bpm = float(q.get("bpm", 120.0))
    grid = float(q.get("grid", 0.5))
    beat_s = 60.0 / bpm
    cell = beat_s * grid
    if cell <= 0:
        return 0.0
    now = time.time()
    phase = now % cell
    delay = cell - phase
    return 0.0 if delay < 0.005 else delay
