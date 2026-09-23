#!/usr/bin/env python3
"""
courtyard — sample renderer (per-voice reverb from preset.json).

Fingerstyle nylon guitar warming a sunlit Spanish courtyard. Soft plucked
nylon strings with warm woody body resonance and gentle fingertip noise:
a round low bass string, a soft singing lead, a brighter counter-line,
a thumb-plucked tone, a flute-pure harmonic chime, tiny string-flick
sparkle, a strummed bloom, a rolled fingerstyle cluster, a soft body tap,
and a tender little harmonic chirp. A major @ A=432, additive only,
intimate and bright, never dreary.

Per-voice REVERB lives in preset.json voices.<name>.reverb (baked here);
per-voice DELAY is a live playback echo handled by event.py.

Usage:  python3 render.py [voice ...]   (no args = all)
"""
import sys, math
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (SR, freq, t_axis, adsr, soft_clip, lowpass_fft,
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


def _nylon_pluck(t, f, decay, *, partials, bright=0.0, body=0.18):
    """Shared nylon-string core: harmonic stack with independent decays so the
    top harmonics fade fast (warm, never glassy), a faint detune twin for the
    woody body bloom, and a low-passed bed. `partials` is a list of
    (multiple, amplitude, decay_rate)."""
    sig = np.zeros_like(t)
    for mult, amp, dec in partials:
        sig += amp * np.sin(2*np.pi*f*mult*t) * np.exp(-t*dec)
    # warm body bloom: faint detuned fundamental, slow decay
    sig += body * np.sin(2*np.pi*f*1.0035*t) * np.exp(-t*(decay*0.7))
    return sig


# ---- bass (A low nylon bass string — round warm pluck, deep woody body) ----
def voice_bass(midi):
    """A low nylon bass string: round warm pluck with deep woody body, the
    courtyard ground. Strong fundamental, gentle low harmonics that fade fast,
    a soft fingertip 'pad' transient (low-passed noise, no click), and a short
    woody knock at the very onset. Rounded, dark-warm, never boomy-dreary."""
    f = freq(midi); dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    sig = _nylon_pluck(
        t, f, decay=3.2,
        partials=[
            (1.0, 1.00, 2.6),     # fundamental, the round body
            (2.0, 0.30, 4.5),     # warmth, fades early
            (3.0, 0.12, 7.0),     # tiny edge, gone fast
            (4.0, 0.05, 11.0),    # faint string color
        ],
        body=0.16,
    )
    # soft fingertip contact: low-passed noise puff, very short -> the pad of
    # a finger on a wound string, never a click.
    rng = np.random.default_rng(int(midi) * 13 + 1)
    puff = rng.standard_normal(n)
    puff = lowpass_fft(puff, 900.0, order=3)
    puff_env = np.exp(-t * 60.0)               # ~16 ms fingertip pad
    sig = sig + 0.10 * puff * puff_env

    # keep it round and woody
    sig = lowpass_fft(sig, 1600.0, order=4)

    # soft pluck attack (~8 ms, no click), warm decay
    env = adsr(n, a=0.008, d=1.4, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead (mid nylon string — soft fingertip attack into warm sustain) ----
def voice_lead(midi):
    """A mid nylon string: soft fingertip attack into warm sustain, fingerpicking
    the melody. A clean fundamental with a sweet octave that fades, a soft fifth
    for body, a gentle nail 'chiff' at the onset, and the faintest vibrato that
    only opens after the note speaks. Bright, singing, tender. ~2.4s."""
    f = freq(midi); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)

    # vibrato fades in after the attack (singing finger vibrato, not warbly)
    vib_depth = 0.0028 * np.clip((t - 0.35) / 0.7, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.2*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = (
        1.00 * np.sin(phase)                              +  # fundamental
        0.36 * np.sin(2*phase) * np.exp(-t*2.4)           +  # sweet octave, fades
        0.16 * np.sin(3*phase) * np.exp(-t*4.0)           +  # soft fifth-color
        0.06 * np.sin(4*phase) * np.exp(-t*7.0)           +  # faint string sheen
        0.10 * np.sin(2*np.pi*f*1.0035*t) * np.exp(-t*1.8)   # body bloom detune
    )
    # nail 'chiff': tiny band of noise right at the pluck, gone in ~20ms
    rng = np.random.default_rng(int(midi) * 31 + 5)
    chiff = rng.standard_normal(n)
    chiff = lowpass_fft(chiff, 3800.0, order=3)
    chiff = chiff - lowpass_fft(chiff, 900.0, order=2)
    sig = sig + 0.07 * chiff * np.exp(-t * 80.0)

    # keep it warm over the wood
    sig = lowpass_fft(sig, 4600.0, order=3)
    env = adsr(n, a=0.010, d=1.0, s_level=0.40, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (higher nylon string — brighter pluck, weaving a counter-line) ----
def voice_lead2(midi):
    """A higher nylon string, brighter pluck, weaving a counter-line above the
    lead. Same nylon DNA but a touch brighter and shorter: more octave sparkle,
    a quicker decay so it dances over the melody. ~2.0s."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)

    sig = _nylon_pluck(
        t, f, decay=3.0,
        partials=[
            (1.0, 1.00, 2.8),
            (2.0, 0.44, 3.4),     # brighter octave sparkle
            (3.0, 0.20, 5.2),
            (4.0, 0.09, 8.0),
            (5.0, 0.04, 12.0),    # tiny glint, gone fast
        ],
        body=0.14,
    )
    # nail chiff, a touch brighter than the lead
    rng = np.random.default_rng(int(midi) * 41 + 9)
    chiff = rng.standard_normal(n)
    chiff = lowpass_fft(chiff, 5000.0, order=3)
    chiff = chiff - lowpass_fft(chiff, 1100.0, order=2)
    sig = sig + 0.06 * chiff * np.exp(-t * 90.0)

    sig = lowpass_fft(sig, 5600.0, order=3)
    env = adsr(n, a=0.008, d=1.2, s_level=0.0, r=0.7)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (muted thumb-plucked string — round and dark-warm) ----
def voice_tone(midi):
    """A muted thumb-plucked string (palm-mute): round and dark-warm, the sweet
    woody middle. Short, fat, very few harmonics — a soft 'dum' of the thumb on
    a damped string. Quick decay, heavily warmed. ~0.9s."""
    f = freq(midi); dur = 0.9
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)      * np.exp(-t*6.0) +   # fat damped body
        0.28 * np.sin(2*np.pi*f*2.0*t)  * np.exp(-t*10.0) +  # faint octave warmth
        0.08 * np.sin(2*np.pi*f*3.0*t)  * np.exp(-t*16.0)    # tiny, gone fast
    )
    sig += 0.14 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*5.0)  # body bloom

    # soft thumb contact: low-passed noise pad
    rng = np.random.default_rng(int(midi) * 23 + 3)
    thumb = rng.standard_normal(n)
    thumb = lowpass_fft(thumb, 1300.0, order=3)
    sig = sig + 0.09 * thumb * np.exp(-t * 70.0)

    # dark-warm: roll off hard
    sig = lowpass_fft(sig, 1900.0, order=4)
    env = adsr(n, a=0.007, d=0.5, s_level=0.0, r=0.3)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.03, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chime (natural guitar harmonic — flute-pure bell tone) ----
def voice_chime(midi):
    """A natural guitar harmonic (12th-fret touch): a flute-pure bell tone.
    Almost a pure sine with a soft octave 'bloom', a whisper of a higher
    partial that glints and dies, and a faint chorus shimmer. No nail attack —
    a harmonic 'speaks' softly. Sweet, glassy-but-warm, ~2.6s."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.0) +   # pure body
        0.34 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*1.7) +   # octave bloom
        0.10 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*3.0) +   # soft fifth color
        0.04 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*5.5)     # tiny glint, gone fast
    )
    # gentle chorus shimmer for the "flute" warmth
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.1)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.1)

    # very soft attack — a harmonic melts in, no click
    env = adsr(n, a=0.016, d=2.1, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (tiny high string-flicks and harmonics — bright droplets) ----
def voice_sparkle(seed):
    """Tiny high string-flicks and harmonics — bright little droplets with light
    delay echoes (delay lives in preset.json). A quick high pentatonic pluck:
    pure-ish sine + a soft octave glint, a tiny nail tick, fast decay. Each seed
    picks a different high note so the droplets scatter. ~0.45s."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]              # A major, high register
    f = freq(HIGH[int(rng.integers(0, len(HIGH)))])

    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)      * np.exp(-t*7.0) +    # bright droplet
        0.30 * np.sin(2*np.pi*f*2.0*t)  * np.exp(-t*11.0) +   # octave glint
        0.08 * np.sin(2*np.pi*f*3.0*t)  * np.exp(-t*18.0)     # tiny sparkle, gone fast
    )
    # tiny nail tick at the flick
    tick = rng.standard_normal(n)
    tick = lowpass_fft(tick, 5500.0, order=3)
    tick = tick - lowpass_fft(tick, 1500.0, order=2)
    sig = sig + 0.06 * tick * np.exp(-t * 140.0)

    sig = lowpass_fft(sig, 6800.0, order=3)
    env = adsr(n, a=0.006, d=0.30, s_level=0.0, r=0.12)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (soft strummed-and-sustained chord swell — warm nylon blooming) ----
def voice_bloom(midi):
    """A soft strummed-and-sustained chord swell — warm nylon blooming gently,
    lush room wash. From the root we build a sweet major triad-plus
    (root, just-third 5/4, fifth 3/2, octave) of nylon-string tones, gently
    arpeggio-staggered so the strum 'opens', then sustained into a warm pad.
    A moving lowpass blooms the brightness up. Round, lush, ~6.5s."""
    f = freq(midi); dur = 6.5
    n = int(dur * SR); t = t_axis(dur)

    ratios = [1.0, 5/4, 3/2, 2.0]            # root, maj3, fifth, octave (just)
    strum_gap = 0.045                         # ~45 ms between strings (a strum)
    sig = np.zeros(n)
    for i, r in enumerate(ratios):
        fr = f * r
        # nylon partials per string, top harmonics fade fast
        s = (
            1.00 * np.sin(2*np.pi*fr*t)      * np.exp(-t*0.9) +
            0.30 * np.sin(2*np.pi*fr*2.0*t)  * np.exp(-t*1.6) +
            0.10 * np.sin(2*np.pi*fr*3.0*t)  * np.exp(-t*3.0)
        )
        s += 0.12 * np.sin(2*np.pi*fr*1.0035*t) * np.exp(-t*1.0)  # body bloom
        # staggered strum onset, slow nylon swell-in, long warm tail
        a = 0.18 + strum_gap * i
        env = adsr(n, a=a, d=1.4, s_level=0.55, hold=0.8, r=2.6)
        gain = 1.0 - 0.10 * i                 # upper strings a touch softer
        sig += s * env[:n] * gain
    sig /= len(ratios)

    # bloom: brightness opens then settles -> the strum "blossoming"
    low = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.30 + 0.70 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.8), 1.0)))
    sig = low + high * open_curve

    # warm ceiling — round, never glassy
    sig = lowpass_fft(sig, 3000.0, order=3)
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- cluster (rolled fingerstyle arpeggio — shimmering cascade of plucks) ----
def voice_cluster(midi):
    """A rolled fingerstyle arpeggio — a shimmering cascade of nylon plucks,
    intimate. From the root we roll up a major pentatonic figure
    (root, +4, +7, +9, +12) as separate quick nylon plucks, each delayed a
    little so it cascades like a thumb-roll, then a soft sustained halo holds
    it together. Bright, sweet, rolling. ~5.0s."""
    intervals = [0, 4, 7, 9, 12]
    dur = 5.0
    n = int(dur * SR)
    roll = 0.085                               # ~85 ms between plucks (a roll)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        fr = freq(midi + iv)
        delay = int(roll * i * SR)
        if delay >= n:
            break
        tt = t_axis(dur)[:n - delay]
        pluck = (
            1.00 * np.sin(2*np.pi*fr*tt)      * np.exp(-tt*3.2) +
            0.36 * np.sin(2*np.pi*fr*2.0*tt)  * np.exp(-tt*4.6) +
            0.14 * np.sin(2*np.pi*fr*3.0*tt)  * np.exp(-tt*7.0)
        )
        pluck += 0.12 * np.sin(2*np.pi*fr*1.0035*tt) * np.exp(-tt*2.4)
        penv = adsr(pluck.size, a=0.008, d=1.6, s_level=0.0, r=0.7)
        pluck = pluck * penv
        gain = 1.0 - 0.07 * i
        sig[delay:delay + pluck.size] += pluck * gain
    sig /= 3.0
    # warm over the wood, keep the cascade sweet not glassy
    sig = lowpass_fft(sig, 5200.0, order=3)
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- tap (soft guitar-body tap — near-dry woody knock) ----
def voice_tap(seed):
    """A soft guitar-body tap (golpe) — a near-dry woody knock, the percussive
    courtyard pulse. A couple of fast-decaying low-mid sine 'body' partials
    (the hollow soundboard) plus a short soft band-limited noise transient for
    the fingertip contact. Short, dry, warm, soft attack. ~0.3s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.30
    n = int(dur * SR); t = t_axis(dur)

    # hollow soundboard body, small per-tap wobble so it feels hand-played
    f0 = 150.0 * (1.0 + rng.uniform(-0.04, 0.04))
    body = (
        1.00 * np.sin(2*np.pi*f0*t)      * np.exp(-t*24) +
        0.45 * np.sin(2*np.pi*f0*1.98*t) * np.exp(-t*34) +
        0.18 * np.sin(2*np.pi*f0*2.9*t)  * np.exp(-t*52)
    )
    # fingertip contact: short filtered noise, soft non-instant attack
    noise = rng.standard_normal(n)
    knock = lowpass_fft(noise, 1700.0, order=4)
    knock = knock - lowpass_fft(knock, 200.0, order=2)
    k_env = adsr(n, a=0.0035, d=0.040, s_level=0.0, r=0.02)
    knock = knock * k_env

    sig = body + 0.45 * knock
    env = adsr(n, a=0.003, d=0.16, s_level=0.0, r=0.10)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 2800.0, order=4)    # rounded, woody
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chirp (bright high harmonic flick — a tender little Spanish accent) ----
def voice_chirp(seed):
    """A bright high harmonic flick — a tender little Spanish accent. A quick
    rising two-note pentatonic blip on a high nylon harmonic: pure sine + a
    gentle octave sheen, a tiny chiff at the onset, soft and bright. Each seed
    picks a starting note and a small upward leap so each accent is a cheerful
    little lift. ~0.4s, near-dry."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]              # A major, high register
    start_i = int(rng.integers(0, 3))
    leap = [1, 2, 3][int(rng.integers(0, 3))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)
    # smooth rising glide then settle
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)         # smoothstep
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.20 * np.sin(2*phase) +              # gentle octave sheen
        0.05 * np.sin(3*phase) * np.exp(-t*16)   # tiny chiff at onset
    )
    sig = lowpass_fft(sig, 6800.0, order=3)
    env = adsr(n, a=0.010, d=0.10, s_level=0.50, r=0.20)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.12, "decay": 1.8, "predelay_ms": 12, "brightness": 0.3},
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 62, 64, 66, 69, 71, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.20, "decay": 2.0, "predelay_ms": 20, "brightness": 0.55},
    },
    "lead2": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.2, -0.2, 0.15, -0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.20, "decay": 1.8, "predelay_ms": 18, "brightness": 0.6},
    },
    "tone": {
        "kind": "midi",
        "midis": [45, 49, 52, 57, 61, 64],
        "pans": [-0.1, 0.1, 0, -0.08, 0.08, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.16, "decay": 1.4, "predelay_ms": 14, "brightness": 0.35},
    },
    "chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.2, "predelay_ms": 28, "brightness": 0.6},
    },
    "sparkle": {
        "kind": "seed",
        "count": 5,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.22, "decay": 1.8, "predelay_ms": 14, "brightness": 0.62},
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.0, "predelay_ms": 45, "brightness": 0.45},
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [-0.2, 0.2, -0.1, 0.1, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.4, "predelay_ms": 38, "brightness": 0.55},
    },
    "tap": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.14],
        "target_peak": 0.7,
        "reverb": {"wet": 0.06, "decay": 0.6, "predelay_ms": 8, "brightness": 0.35},
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.3, -0.4, 0.45, -0.3],
        "target_peak": 0.8,
        "reverb": {"wet": 0.12, "decay": 1.4, "predelay_ms": 12, "brightness": 0.62},
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
    print("courtyard:", name)


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
