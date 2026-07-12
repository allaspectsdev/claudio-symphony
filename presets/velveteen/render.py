#!/usr/bin/env python3
"""
velveteen — sample renderer (per-voice reverb from preset.json).

Warm bell-keys glowing through tape haze: a nostalgic celesta lullaby from a
half-remembered summer. Soft celesta bell-keys with gentle tape wow and warm
low-pass haze; Boards-of-Canada dreampop, hazy-bright like sunlight through old
film, tender and happy. A major pentatonic @ A=432, additive only, never dreary.

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


# ---- tape wow helper: a gentle slow pitch wobble (the warm flutter of old tape) ----
def _wow(t, depth=0.0035, rate=0.7, phase=0.0, flutter=0.0009, frate=6.3):
    """Returns a per-sample multiplier ~1.0 with slow 'wow' plus faint fast
    'flutter'. Keeps celesta keys feeling hazy and nostalgic, never static."""
    return (1.0
            + depth   * np.sin(2*np.pi*rate*t + phase)
            + flutter * np.sin(2*np.pi*frate*t + phase*1.7))


# ---- subkey (bass) — a soft tape-warm sub-key, round muffled fundamental w/ wow ----
def voice_subkey(arg):
    """A soft tape-warm sub-key: round muffled fundamental with gentle tape wow,
    hazy and grounding. Additive — a dominant sine fundamental, a kiss of 2nd
    harmonic for warmth (fades fast), a soft octave-under sub for body, all
    rolled off warm so it's felt low, not heard up top. Slow tape wow gives the
    'half-remembered' drift. Soft felt attack, no click. ~2.6s."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(arg) * 13 + 1)
    wow = _wow(t, depth=0.0040, rate=0.55, phase=rng.uniform(0, 6.28), flutter=0.0007)
    phase = 2*np.pi*f*np.cumsum(wow)/SR
    body = (
        1.00 * np.sin(phase) +
        0.20 * np.sin(2*phase) * np.exp(-t*2.2) +     # warmth, fades early
        0.06 * np.sin(3*phase) * np.exp(-t*5.0) +     # tiny edge, gone fast
        0.28 * np.sin(2*np.pi*f*0.5*t)                # soft sub for round body
    )
    # gentle slow breathe so the floor is alive, not static
    breathe = 1.0 + 0.05 * np.sin(2*np.pi*2.3*t - np.pi/2)
    body = body * breathe
    # soft felt-key attack puff (very low-passed, brief)
    puff = rng.standard_normal(n)
    puff = lowpass_fft(puff, 240.0, order=3) * np.exp(-t*20.0)
    body = body + 0.12 * puff
    # warm tape haze: round it off, kill anything bright
    body = lowpass_fft(body, 820.0, order=4)
    env = adsr(n, a=0.024, d=0.6, s_level=0.5, hold=0.5, r=1.2)
    out = body[:env.size] * env[:body.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- bellkey (lead) — celesta bell-key with tape flutter, singing a nostalgic tune ----
def voice_bellkey(midi):
    """A celesta bell-key with tape flutter: warm struck bell plus a soft 2.005x
    inharmonic partial, singing a nostalgic tune. Additive — a glowing
    fundamental, a clean octave that decays fast, a sweet 3x glass color, and a
    gentle inharmonic 2.005x bell shimmer with its OWN decay (the 'bell' color).
    Tape wow + faint flutter give the hazy nostalgia. Soft attack, warm
    low-pass. A-pentatonic-safe, no FM, nothing harsh above ~5x. ~2.4s."""
    f = freq(midi); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) * 31 + 5)
    wow = _wow(t, depth=0.0032, rate=0.85, phase=rng.uniform(0, 6.28))
    phase = 2*np.pi*f*np.cumsum(wow)/SR
    sig = (
        1.00 * np.sin(phase)               * np.exp(-t*1.2) +   # warm struck body
        0.42 * np.sin(2.0*phase)           * np.exp(-t*1.9) +   # clean octave
        0.16 * np.sin(3.0*phase)           * np.exp(-t*3.0) +   # sweet glass color
        0.05 * np.sin(4.0*phase)           * np.exp(-t*5.0)     # faint shimmer, fast
    )
    # the celesta 'bell' partial: soft inharmonic 2.005x, independent decay
    sig += 0.22 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.6)
    # warm chorus twin for tape-haze body
    sig += 0.12 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.3)
    env = adsr(n, a=0.012, d=1.8, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    # warm tape haze top — keep the bell sweet, not glassy
    out = lowpass_fft(out, 5200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- bellkey_hi (lead2) — a higher celesta key, brighter through haze, echoing dreamily ----
def voice_bellkey_hi(midi):
    """A higher celesta key, brighter through the haze, echoing the melody
    dreamily. Same bell-key family as the lead but lighter and quicker to fade,
    a touch more shimmer up top (still warm-rolled), with a slightly faster tape
    flutter for the 'higher' airy feel. ~2.0s."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) * 37 + 9)
    wow = _wow(t, depth=0.0030, rate=1.0, phase=rng.uniform(0, 6.28), flutter=0.0012, frate=7.1)
    phase = 2*np.pi*f*np.cumsum(wow)/SR
    sig = (
        1.00 * np.sin(phase)               * np.exp(-t*1.5) +
        0.38 * np.sin(2.0*phase)           * np.exp(-t*2.2) +
        0.14 * np.sin(3.0*phase)           * np.exp(-t*3.4) +
        0.06 * np.sin(4.0*phase)           * np.exp(-t*5.5)
    )
    sig += 0.18 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*2.0)   # bell color
    sig += 0.10 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*1.6)   # haze twin
    env = adsr(n, a=0.010, d=1.5, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6000.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- warmkey (tone) — a warm muffled bell-key, low-passed and sweet, tape-saturated middle ----
def voice_warmkey(midi):
    """A warm muffled bell-key, low-passed and sweet — the cozy tape-saturated
    middle. A sustained singing tone: clean fundamental, soft octave that fades
    early, a whisper of detune for body, slow tape wow, and a tender vibrato
    that only opens after the attack. Heavily warm low-passed so it's muffled
    and cozy, never bright. ~2.6s. Additive only, no FM."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) * 41 + 3)
    # tape wow + a vibrato that fades in (singing, not warbly)
    vib_depth = 0.0026 * np.clip((t - 0.4) / 0.6, 0.0, 1.0)
    wow = _wow(t, depth=0.0034, rate=0.65, phase=rng.uniform(0, 6.28))
    mod = wow * (1.0 + vib_depth * np.sin(2*np.pi*4.6*t))
    phase = 2*np.pi*f*np.cumsum(mod)/SR
    sig = (
        1.00 * np.sin(phase) +
        0.20 * np.sin(2*phase) * np.exp(-t*2.0) +     # soft octave, fades early
        0.05 * np.sin(3*phase) * np.exp(-t*4.5) +     # faint sweetener, gone fast
        0.10 * np.sin(2*np.pi*f*1.004*t)              # whisper of detune for body
    )
    # cozy muffled tape haze
    sig = lowpass_fft(sig, 2400.0, order=3)
    env = adsr(n, a=0.022, d=0.9, s_level=0.5, r=1.3)
    out = sig[:env.size] * env[:sig.size] * 0.46
    return out


# ---- glasskey (chime) — clear high celesta ping w/ soft shimmer, slightly detuned-warm ----
def voice_glasskey(midi):
    """A clear high celesta ping with soft shimmer, medium reverb, slightly
    detuned-warm. Additive bell: glowing fundamental, pure octave 'celeste
    doubling', a gentle 3x glass partial that decays fast, and a whisper of high
    sparkle that fades quickly. Two near-unison detunes give the warm shimmer.
    Soft 14ms attack (no click), tape wow for haze. Warm-rolled top. ~2.4s."""
    f = freq(midi); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) * 23 + 7)
    wow = _wow(t, depth=0.0028, rate=0.9, phase=rng.uniform(0, 6.28))
    phase = 2*np.pi*f*np.cumsum(wow)/SR
    sig = (
        1.00 * np.sin(phase)       * np.exp(-t*1.1) +     # warm body
        0.50 * np.sin(2.0*phase)   * np.exp(-t*1.7) +     # celeste octave
        0.18 * np.sin(3.0*phase)   * np.exp(-t*2.9) +     # sweet glass color
        0.06 * np.sin(4.0*phase)   * np.exp(-t*4.6)       # faint shimmer, fast
    )
    # warm shimmer: two near-unisons (the 'detuned-warm' glow)
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.2)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.2)
    env = adsr(n, a=0.014, d=2.0, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- glints (sparkle) — tiny high bell-keys glinting through haze, light delay echoes ----
def voice_glints(seed):
    """Tiny high bell-keys glinting through the haze, light delay echoes with
    tape wow. Seed picks a note from the HIGH pentatonic. A short, bright little
    celesta glint: fundamental + soft octave + a quick high glass ping that dies
    fast, plus tape wow so each glint shimmers. Warm-rolled top, soft attack,
    near-short. ~0.9s. The live delay (preset.json) makes the dreamy echoes."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]
    m = HIGH[int(rng.integers(0, len(HIGH)))]
    f = freq(m)
    dur = 0.9
    n = int(dur * SR); t = t_axis(dur)
    wow = _wow(t, depth=0.0030, rate=1.3, phase=rng.uniform(0, 6.28), flutter=0.0013, frate=7.7)
    phase = 2*np.pi*f*np.cumsum(wow)/SR
    sig = (
        1.00 * np.sin(phase)     * np.exp(-t*3.2) +     # quick warm body
        0.34 * np.sin(2.0*phase) * np.exp(-t*4.5) +     # octave glint
        0.10 * np.sin(3.0*phase) * np.exp(-t*7.0)       # tiny glass ping, gone fast
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*3.5)   # haze twin
    env = adsr(n, a=0.008, d=0.6, s_level=0.0, r=0.22)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7000.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.46 / peak)
    return out


# ---- hazebloom (bloom) — a warm synth-pad bloom under the keys, hazy low-passed swell ----
def voice_hazebloom(midi):
    """A warm synth-pad bloom under the keys: a hazy low-passed swell, lush and
    nostalgic. Additive — a clean fundamental with a chorus of faint detunes, a
    sweet just-major-third (5/4) and just-fifth (3/2), a soft octave halo, and a
    gentle sub for warmth. A moving low-pass 'opens' the bloom over a few
    seconds, then settles. Slow tape wow for the half-remembered drift.
    Everything heavily rolled off — round, nostalgic, never glassy. ~7s."""
    f = freq(midi)
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) * 19 + 11)
    wow = _wow(t, depth=0.0030, rate=0.42, phase=rng.uniform(0, 6.28), flutter=0.0005)
    vib = wow * (1.0 + 0.0014 * np.sin(2*np.pi*0.26*t))
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.45 * np.sin(2*np.pi*f*1.0035*t) +
        0.45 * np.sin(2*np.pi*f*0.9967*t)
    )
    third  = 0.38 * np.sin(2*np.pi*f*(5/4)*t*vib)
    fifth  = 0.32 * np.sin(2*np.pi*f*(3/2)*t*vib)
    octave = 0.20 * np.sin(2*np.pi*f*2.0*t)
    sub    = 0.28 * np.sin(2*np.pi*f*0.5*t)
    sig = fund + third + fifth + octave + sub
    # bloom opens the brightness over the first seconds, then settles
    low  = lowpass_fft(sig, 640.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve
    # warm haze ceiling
    sig = lowpass_fft(sig, 2400.0, order=3)
    env = adsr(n, a=1.6, d=1.0, s_level=0.85, hold=1.2, r=3.0)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- chimecloud (cluster) — a shimmering cluster of detuned bell-keys, warm chorus wash ----
def voice_chimecloud(arg):
    """A shimmering cluster of detuned bell-keys: warm chorus wash, dreamy. From
    the passed root midi we build a major-pentatonic-safe chord (root, +4, +7,
    +9, +12). Each note is a soft bell-key (fundamental + faint 2nd/3rd partials)
    with a slightly detuned twin for warm chorus shimmer, slow tape wow, and
    staggered swells so the cluster blooms open like an inhale. Warm low-passed —
    sits hazy under the keys with no harsh edge. ~7.2s."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.2
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    rng = np.random.default_rng(root * 29 + 13)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        wow = _wow(t, depth=0.0030, rate=0.4 + 0.06*i, phase=rng.uniform(0, 6.28), flutter=0.0006)
        ph = 2*np.pi*f*np.cumsum(wow)/SR
        partial = (np.sin(ph)
                   + 0.18*np.sin(2*ph)
                   + 0.07*np.sin(3*ph))
        detune = np.sin(2*np.pi*f*1.0035*t)
        voice = (0.85*partial + 0.35*detune)
        stagger = 0.18 * i
        env = adsr(n, a=1.8 + stagger, d=0.7, s_level=0.82, hold=1.6, r=2.6)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 2500, order=3)
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- tapegrain (texture) — a faint tape hiss-and-wow texture, near-dry, warm grain of old film ----
def voice_tapegrain(seed):
    """A faint tape hiss-and-wow texture: near-dry, the warm grain of old film.
    A very soft band-limited noise bed (warm, no harsh top) gently amplitude-
    modulated by a slow tape 'wow', with a tiny low pitched glow underneath so
    it sits in key rather than reading as pure hiss. Deliberately quiet — the
    nostalgic grain behind everything. Soft fade in/out, no click. ~1.4s."""
    rng = np.random.default_rng(int(seed))
    dur = 1.4
    n = int(dur * SR); t = t_axis(dur)
    # warm hiss: band-limited noise, no harsh top
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 1800.0, order=3)
    noise = noise - lowpass_fft(noise, 180.0, order=2)   # band: gentle grain
    # slow tape wow amplitude shimmer
    wow = 1.0 + 0.35 * np.sin(2*np.pi*0.8*t + rng.uniform(0, 6.28))
    grain = noise * wow
    # faint low pitched glow so it sits in key (very quiet)
    glow = 0.10 * np.sin(2*np.pi*freq(57)*t) * np.exp(-t*0.6)
    sig = 0.5 * grain + glow
    # soft fade in/out — no click
    env = adsr(n, a=0.06, d=0.3, s_level=0.7, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 2000.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.40 / peak)
    return out


# ---- flicker (chirp) — a bright high celesta flick, a tender little nostalgic accent ----
def voice_flicker(seed):
    """A bright high celesta flick: a tender little nostalgic accent. Seed picks
    a note (and a small upward pentatonic leap) from the HIGH register, giving a
    quick rising 2-note celesta blip — fundamental + soft octave sparkle + a tiny
    onset chiff, with tape wow so it shimmers. Warm-rolled top so it's tender,
    never piercing. Soft attack, near-dry-ish. ~0.45s."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]
    leaps = [1, 2, 3]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)          # smoothstep
    f_t = f0 + (f1 - f0) * rise
    wow = _wow(t, depth=0.0024, rate=1.4, phase=rng.uniform(0, 6.28), flutter=0.0012, frate=7.5)
    phase = 2*np.pi*np.cumsum(f_t * wow)/SR
    sig = (
        np.sin(phase) +
        0.20 * np.sin(2*phase) * np.exp(-t*3.0) +       # gentle octave sheen
        0.05 * np.sin(3*phase) * np.exp(-t*16)          # tiny chiff at onset
    )
    sig = lowpass_fft(sig, 6500.0, order=3)
    env = adsr(n, a=0.010, d=0.12, s_level=0.5, r=0.24)
    out = sig[:env.size] * env[:sig.size] * 0.48
    return out


PLAN = {
    "subkey": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.08, "decay": 1.8, "predelay_ms": 12, "brightness": 0.28},
    },
    "bellkey": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.18, 0.18, -0.1, 0.14, -0.06, 0.1, 0, -0.12, 0.12],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 2.6, "predelay_ms": 26, "brightness": 0.55},
    },
    "bellkey_hi": {
        "kind": "midi",
        "midis": [69, 71, 73, 76, 78, 81, 85],
        "pans": [0.2, -0.2, 0.12, -0.14, 0.16, -0.1, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 2.8, "predelay_ms": 28, "brightness": 0.58},
    },
    "warmkey": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.14, 0.14, -0.08, 0.08, 0, -0.12, 0.12],
        "target_peak": 0.82,
        "reverb": {"wet": 0.2, "decay": 2.2, "predelay_ms": 22, "brightness": 0.42},
    },
    "glasskey": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.38, "decay": 3.2, "predelay_ms": 30, "brightness": 0.6},
    },
    "glints": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.45, -0.4, 0.3, -0.3],
        "target_peak": 0.78,
        "reverb": {"wet": 0.32, "decay": 2.4, "predelay_ms": 22, "brightness": 0.6},
    },
    "hazebloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.0, "predelay_ms": 45, "brightness": 0.4},
    },
    "chimecloud": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18, -0.12, 0.12],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 4.8, "predelay_ms": 42, "brightness": 0.45},
    },
    "tapegrain": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.45,
        "reverb": {"wet": 0.06, "decay": 0.8, "predelay_ms": 10, "brightness": 0.32},
    },
    "flicker": {
        "kind": "seed",
        "count": 6,
        "pans": [0.3, -0.28, 0.4, -0.35, 0.25, -0.22],
        "target_peak": 0.78,
        "reverb": {"wet": 0.18, "decay": 1.8, "predelay_ms": 14, "brightness": 0.58},
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
    print("velveteen:", name)


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
