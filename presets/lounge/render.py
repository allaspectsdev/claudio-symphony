#!/usr/bin/env python3
"""
lounge — sample renderer (per-voice reverb from preset.json).

A mellow vibraphone glowing in a cozy lamplit room: warm struck-metal bars
with a gentle motor tremolo, soft round mallets, a woody upright-bass thumb
pluck walking underneath, bright bell-bar pings, a bowed-vibe bloom, a soft
mallet-roll cluster, a muted time-keeping tap, and a happy little chirp.
A major pentatonic @ A=432, additive only, late-evening but sunlit-warm.

Per-voice REVERB lives in preset.json voices.<name>.reverb (baked here); per-voice
DELAY is a live playback echo handled by event.py.

Usage:  python3 render.py [voice ...]   (no args = all)
"""
import sys, math
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (SR, A4, freq, t_axis, adsr, soft_clip, lowpass_fft,
                    reverb_stereo, write_wav)

import json as _json
import synth as _synth
_PRESET_CFG = _json.loads(Path(__import__("os").environ.get("CLAUDIO_PRESET_CONFIG", str(HERE / "preset.json"))).read_text())
_REVERB_SCALE = float(_PRESET_CFG.get("reverb_scale", 1.0))
_orig_reverb_stereo = _synth.reverb_stereo
def reverb_stereo(mono, **kwargs):
    if "wet" in kwargs:
        kwargs["wet"] = max(0.0, min(1.0, float(kwargs["wet"]) * _REVERB_SCALE))
    return _orig_reverb_stereo(mono, **kwargs)

OUT = Path(__import__("os").environ.get("CLAUDIO_SAMPLES_DIR", str(HERE / "samples")))


# ---- bass (upright-bass thumb pluck — round, woody, walking under the bars) ----
def voice_bass(arg):
    """A soft upright-bass thumb pluck. A round sine fundamental with just a
    kiss of 2nd/3rd harmonic for woody warmth (all gone fast, nothing above
    3x), a tiny attack pitch-give like a finger releasing the string, and a
    soft felt 'thumb' transient (low-passed noise puff). Near-dry, warm, walks
    gently. A-pentatonic LOW. arg = midi."""
    f = freq(int(arg))
    dur = 2.0
    n = int(dur * SR); t = t_axis(dur)

    # tiny downward pitch give at the very attack (the string settling)
    give = 1.0 + 0.010 * np.exp(-t * 60.0)
    phase = 2*np.pi*f*np.cumsum(give)/SR

    body = (
        1.00 * np.sin(phase)                              +
        0.30 * np.sin(2*phase) * np.exp(-t*3.0)           +  # woody warmth, fades early
        0.10 * np.sin(3*phase) * np.exp(-t*6.0)           +  # tiny edge, gone fast
        0.05 * np.sin(2*np.pi*f*1.003*t)                     # slow beat = wood life
    )

    # soft thumb contact: low-passed noise puff, very short
    rng = np.random.default_rng(int(arg) * 17 + 3)
    puff = rng.standard_normal(n)
    puff = lowpass_fft(puff, 360.0, order=3)
    puff_env = np.exp(-t * 26.0)
    body = body + 0.16 * puff * puff_env

    # keep it round — bass is felt, not heard up top
    body = lowpass_fft(body, 1100.0, order=4)

    # warm plucked envelope: soft attack (~8 ms), quick body, gentle tail
    env = adsr(n, a=0.008, d=0.7, s_level=0.30, hold=0.1, r=0.9)
    out = body[:env.size] * env[:body.size]

    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- lead (vibraphone bar with slow motor tremolo — warm strike, carries the tune) ----
def voice_lead(midi):
    """A medium-mallet vibraphone bar. Warm struck-metal: a fundamental with a
    soft 2x partial (mellow, fades) and a faint inharmonic 4x glint that dies
    fast for the mallet 'strike'. A slow ~5.5 Hz motor tremolo (amplitude, the
    rotating vane) opens after the attack so it breathes. Soft round mallet
    (~9 ms attack), low-passed warm. A-pentatonic. arg = midi."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)                          +  # fundamental
        0.42 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*1.8)   +  # mellow octave partial
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*4.0)   +  # soft third-ish color
        0.06 * np.sin(2*np.pi*f*4.01*t)  * np.exp(-t*30.0)  +  # mallet strike glint, gone ~30ms
        0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.4)      # gentle body bloom
    )

    # slow motor tremolo: amplitude vane, fades in after the strike speaks
    trem_depth = 0.22 * np.clip((t - 0.12) / 0.4, 0.0, 1.0)
    trem = 1.0 - trem_depth * (0.5 - 0.5*np.cos(2*np.pi*5.5*t))
    sig = sig * trem

    sig = lowpass_fft(sig, 5200.0, order=3)   # warm, no glassy top
    env = adsr(n, a=0.009, d=1.4, s_level=0.0, r=0.8)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (harder-mallet bar an octave up — brighter, crisper, trading licks) ----
def voice_lead2(midi):
    """A harder-mallet vibraphone bar, brighter and crisper than the lead. A
    fundamental with a stronger 2x partial and a quick 3x sparkle plus a tiny
    inharmonic glint at the strike. A faster, slightly shallower motor tremolo
    (~6 Hz) gives a livelier flutter. Soft round attack (~7 ms), low-passed but
    a touch brighter. A-pentatonic. arg = midi."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)                          +  # fundamental
        0.52 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.2)   +  # brighter octave
        0.18 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*4.5)   +  # crisp sparkle
        0.07 * np.sin(2*np.pi*f*4.02*t)  * np.exp(-t*34.0)  +  # hard-mallet strike glint
        0.08 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.6)      # body bloom
    )

    trem_depth = 0.16 * np.clip((t - 0.10) / 0.35, 0.0, 1.0)
    trem = 1.0 - trem_depth * (0.5 - 0.5*np.cos(2*np.pi*6.0*t))
    sig = sig * trem

    sig = lowpass_fft(sig, 6200.0, order=3)
    env = adsr(n, a=0.007, d=1.1, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (soft-felt-mallet bar — dark, creamy, no tremolo, the chord cushion) ----
def voice_tone(midi):
    """A soft-felt-mallet vibraphone bar: dark and creamy, the sweet cushion of
    the chord. A clean fundamental with a gentle octave that fades early and a
    whisper of detune for body — NO tremolo, just a still warm sustain. Soft
    felt attack (~20 ms), low-passed dark. A-pentatonic. arg = midi."""
    f = freq(midi); dur = 2.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)                          +  # clean fundamental
        0.24 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.0)   +  # soft octave, fades early
        0.06 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*5.0)   +  # faint sweetener, gone fast
        0.10 * np.sin(2*np.pi*f*1.004*t)                       # whisper of detune for body
    )
    sig = lowpass_fft(sig, 3400.0, order=3)   # dark, creamy
    env = adsr(n, a=0.020, d=0.9, s_level=0.50, r=1.4)
    out = sig[:env.size] * env[:sig.size] * 0.48
    return out


# ---- chime (high bell-bar ping — quick metallic glint, decays fast) ----
def voice_chime(midi):
    """A high bell-bar ping with a quick metallic glint that decays fast. A
    glowing fundamental with a pure octave celeste doubling, a gentle bell
    partial at 3x and a whisper of 4x sparkle that fades in ~50 ms so it reads
    as a glint at the onset. Soft 14 ms attack (no click), low-passed sweet.
    No partials past 5x. A-pentatonic HIGH. arg = midi."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.6)  +  # warm body
        0.50 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*2.4)  +  # celeste octave
        0.18 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*3.6)  +  # sweet bell color
        0.06 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*6.0)      # tiny glint, gone fast
    )
    # gentle chorus shimmer for the glowing bell warmth
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.8)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.8)
    env = adsr(n, a=0.014, d=1.6, s_level=0.0, r=0.40)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7000.0, order=3)
    peak = np.max(np.abs(out))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (tiny brushed-bar shimmer up top — motor flutter, light delay) ----
def voice_sparkle(midi):
    """A tiny brushed-bar shimmer up top with a motor-vane flutter. A light
    high fundamental with a soft octave and a quick 3x glint, wrapped in a
    faster ~7 Hz tremolo flutter (the motor vane) so it shimmers like a wink.
    Short, bright but rounded (low-passed), soft 8 ms attack. A-pentatonic
    HIGH. arg = midi."""
    f = freq(midi); dur = 1.4
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.2)  +  # bright body
        0.30 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.2)  +  # soft octave
        0.10 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*5.0)      # quick glint
    )
    # motor flutter — faster tremolo, opens fast
    trem_depth = 0.30 * np.clip((t - 0.05) / 0.2, 0.0, 1.0)
    trem = 1.0 - trem_depth * (0.5 - 0.5*np.cos(2*np.pi*7.0*t))
    sig = sig * trem
    sig = lowpass_fft(sig, 7200.0, order=3)
    env = adsr(n, a=0.008, d=0.9, s_level=0.0, r=0.35)
    out = sig[:env.size] * env[:sig.size]
    peak = np.max(np.abs(out))
    if peak > 1e-6:
        out = out * (0.48 / peak)
    return out


# ---- bloom (bowed-vibraphone swell — sustained warm metal, slow tremolo, lush) ----
def voice_bloom(midi):
    """A bowed-vibraphone swell: sustained warm metal blooming open, lush and
    lamplit. A clean fundamental with a consonant just-fifth and a soft octave
    halo, two faint detunes for a breathing chorus, and a slow ~4.5 Hz motor
    tremolo. The brightness opens over the swell (moving lowpass) then settles
    — round, never glassy. Slow swell-in (no click), long release. ~6.5s.
    A-pentatonic. arg = midi."""
    f = freq(midi); dur = 6.5
    n = int(dur * SR); t = t_axis(dur)

    # warm chorus on the fundamental
    fund = (
        np.sin(2*np.pi*f*t) +
        0.42 * np.sin(2*np.pi*f*1.0035*t) +
        0.42 * np.sin(2*np.pi*f*0.9967*t)
    )
    fifth  = 0.32 * np.sin(2*np.pi*f*(3/2)*t)   # consonant just fifth
    octave = 0.22 * np.sin(2*np.pi*f*2.0*t)     # soft octave halo
    sub    = 0.18 * np.sin(2*np.pi*f*0.5*t)     # gentle warmth
    sig = fund + fifth + octave + sub

    # slow motor tremolo across the whole bloom
    trem = 1.0 - 0.18 * (0.5 - 0.5*np.cos(2*np.pi*4.5*t))
    sig = sig * trem

    # bloom: brightness opens then settles
    low  = lowpass_fft(sig, 650.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    sig = lowpass_fft(sig, 2800.0, order=3)   # warm ceiling
    env = adsr(n, a=1.4, d=0.9, s_level=0.82, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- cluster (soft mallet-roll on three bars — blurred shimmering chord) ----
def voice_cluster(arg):
    """A soft mallet-roll on three vibe bars — a blurred, shimmering, cozy
    chord. From the passed root we build a pentatonic-safe triad-ish set:
    root, +4 (maj3), +7 (5th), +9 (maj6), +12 (octave). Pure additive sines
    with a faint octave shimmer, gentle detune, a slow motor tremolo and a
    soft 'roll' amplitude ripple so the mallets blur together. Warm low-passed
    so it sits cozy. ~6s. arg = root midi."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    # soft mallet-roll ripple: gentle amplitude shimmer ~9 Hz, blurred
    roll = 1.0 - 0.10 * (0.5 - 0.5*np.cos(2*np.pi*9.0*t))
    # slow motor tremolo over the whole chord
    motor = 1.0 - 0.14 * (0.5 - 0.5*np.cos(2*np.pi*4.5*t))
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partial = (np.sin(2*np.pi*f*t)
                   + 0.18*np.sin(2*np.pi*2*f*t)
                   + 0.06*np.sin(2*np.pi*3*f*t))
        detune = np.sin(2*np.pi*f*1.0035*t)
        voice = (0.85*partial + 0.32*detune)
        # staggered swell: upper notes bloom slightly later
        stagger = 0.14 * i
        env = adsr(n, a=1.2 + stagger, d=0.6, s_level=0.80, hold=1.2, r=2.2)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig = sig * roll * motor
    sig /= len(intervals)
    sig = lowpass_fft(sig, 2800, order=3)   # warm, cozy
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- tap (muted mallet-on-bar tap — near-dry pulse, keeping time) ----
def voice_tap(midi):
    """A muted mallet-on-bar tap: the click of the keeping-time. A short
    pitched body (fundamental + a quiet octave) that decays in ~30 ms so it
    reads as a muted tap, not a tone, plus a soft band-limited noise contact
    for the mallet touch. Near-dry, warm, soft 3 ms attack (no raw edge).
    A-pentatonic. arg = midi."""
    f = freq(midi)
    dur = 0.22
    n = int(dur * SR); t = t_axis(dur)

    body = (
        1.00 * np.sin(2*np.pi*f*t)      * np.exp(-t*36.0) +  # muted pitched body
        0.30 * np.sin(2*np.pi*f*2.0*t)  * np.exp(-t*55.0) +  # quiet octave
        0.10 * np.sin(2*np.pi*f*3.01*t) * np.exp(-t*80.0)    # tiny color, gone fast
    )

    # soft mallet contact: short band-limited noise burst
    rng = np.random.default_rng(int(midi) * 31 + 9)
    noise = rng.standard_normal(n)
    contact = lowpass_fft(noise, 2000.0, order=3)
    contact = contact - lowpass_fft(contact, 240.0, order=2)
    c_env = adsr(n, a=0.003, d=0.025, s_level=0.0, r=0.005)
    contact = contact * c_env

    sig = body + 0.22 * contact
    sig = lowpass_fft(sig, 3600.0, order=4)   # warm, rounded
    env = adsr(n, a=0.003, d=0.10, s_level=0.0, r=0.08)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- chirp (bright high bar flick — a happy little grace note, quick) ----
def voice_chirp(seed):
    """A bright high bar flick — a happy little grace note, quick and present.
    Seed picks a starting note from the HIGH pentatonic and a small upward leap
    so each chirp is a cheerful 2-note rising blip. Additive (pure sines + a
    tiny octave sheen), low-passed warm, ~0.35s, near-dry. Like a wink up top."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]
    leaps = [2, 3, 4]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i])
    f1 = freq(HIGH[end_i])

    dur = 0.35
    n = int(dur * SR); t = t_axis(dur)

    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.20 * np.sin(2*phase) +                 # gentle octave sheen
        0.05 * np.sin(3*phase) * np.exp(-t*16)   # tiny chiff at onset
    )
    sig = lowpass_fft(sig, 6800.0, order=3)
    env = adsr(n, a=0.010, d=0.09, s_level=0.50, r=0.18)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.10, "decay": 1.4, "predelay_ms": 12, "brightness": 0.3},
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.18, 0.18, -0.1, 0.12, 0, -0.15, 0.15, -0.08, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.20, "decay": 1.8, "predelay_ms": 18, "brightness": 0.55},
    },
    "lead2": {
        "kind": "midi",
        "midis": [69, 71, 73, 76, 78, 81, 85],
        "pans": [0.18, -0.18, 0.1, -0.12, 0.15, -0.1, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.20, "decay": 1.6, "predelay_ms": 16, "brightness": 0.6},
    },
    "tone": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.15, 0.15, -0.08, 0.1, 0, -0.12, 0.12],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 2.2, "predelay_ms": 22, "brightness": 0.45},
    },
    "chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.6},
    },
    "sparkle": {
        "kind": "midi",
        "midis": [76, 78, 81, 85, 88],
        "pans": [0.4, -0.35, 0.45, -0.4, 0.3],
        "target_peak": 0.78,
        "reverb": {"wet": 0.30, "decay": 2.4, "predelay_ms": 20, "brightness": 0.62},
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.50, "decay": 5.0, "predelay_ms": 45, "brightness": 0.45},
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.6, "predelay_ms": 42, "brightness": 0.48},
    },
    "tap": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73],
        "pans": [-0.2, 0.2, -0.1, 0.15, 0, 0.1],
        "target_peak": 0.55,
        "reverb": {"wet": 0.05, "decay": 0.6, "predelay_ms": 8, "brightness": 0.4},
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.8,
        "reverb": {"wet": 0.12, "decay": 1.6, "predelay_ms": 12, "brightness": 0.6},
    },
}


def _voice_reverb(name):
    rv = dict(PLAN[name]["reverb"])
    cfg = (_PRESET_CFG.get("voices", {}).get(name, {}) or {}).get("reverb")
    if isinstance(cfg, dict):
        rv.update(cfg)
    return rv


def _render(mono, rv, pan, target_peak, path):
    st = reverb_stereo(mono, wet=rv.get("wet", 0.0), decay_s=rv.get("decay", 2.0),
                       predelay_ms=rv.get("predelay_ms", 20),
                       brightness=rv.get("brightness", 0.45))
    if pan != 0.0:
        pan = float(np.clip(pan, -1.0, 1.0))
        lg = math.cos((pan + 1) * math.pi / 4); rg = math.sin((pan + 1) * math.pi / 4)
        st = st.copy(); st[:, 0] *= 2 * lg; st[:, 1] *= 2 * rg
    write_wav(path, st, target_peak=target_peak)


def render_voice(name):
    fn = globals()["voice_" + name]
    spec = PLAN[name]; rv = _voice_reverb(name); pans = spec["pans"]
    (OUT / name).mkdir(parents=True, exist_ok=True)
    if spec["kind"] == "midi":
        for i, m in enumerate(spec["midis"]):
            _render(fn(m), rv, pans[i % len(pans)], spec["target_peak"],
                    OUT / name / f"{i:02d}_m{m}.wav")
    else:  # seed
        for i in range(spec["count"]):
            _render(fn(1000 + i * 7), rv, pans[i % len(pans)], spec["target_peak"],
                    OUT / name / f"{i:02d}.wav")
    print("lounge:", name)


def gen_all():
    OUT.mkdir(exist_ok=True)
    for name in PLAN:
        render_voice(name)
    print("done.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        OUT.mkdir(exist_ok=True)
        for v in sys.argv[1:]:
            if v in PLAN: render_voice(v)
            else: print("unknown voice:", v)
    else:
        gen_all()
