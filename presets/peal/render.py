#!/usr/bin/env python3
"""
peal — sample renderer (per-voice reverb from preset.json).

A carillon of handbells ringing out joyously over a sunny village square.
Bright ringing handbells in ensemble — struck and resonant with rich additive
partials and long bright tails. A low bourdon bell grounds the toll; mid and
high handbells peal the melody and descant; a warm bell sings the sweet middle;
tower-bell chimes ping; tiny top handbells flick and scatter with delay echoes;
overlapping bell-tails bloom into a lush carillon wash; a change-ringing tumble
shimmers; a damped tap pulses; a bright treble-bell chirps. A major @ A=432,
additive only, hall reverb, jubilant and never dreary.

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


# ---- bourdon (bass) — a low bourdon bell, deep warm strike, long bright tail ----
def voice_bourdon(arg):
    """The grounding toll. A deep warm bourdon bell: a strong low fundamental,
    a gentle hum partial an octave below for body, plus the characteristic bell
    'tierce' and 'quint' inharmonic partials (each decaying at its own rate) that
    give a bell its shimmer without harshness. Long bright tail, soft struck
    attack (~6 ms). Additive only, lowpassed warm. arg = midi (LOW)."""
    f = freq(int(arg))
    dur = 5.0
    n = int(dur * SR); t = t_axis(dur)
    # Bell partials: (ratio, amp, decay). Independent decays = living shimmer.
    parts = [
        (0.50, 0.40, 0.6),    # hum partial (octave below) — warm body
        (1.00, 1.00, 0.9),    # prime / fundamental toll
        (2.00, 0.45, 1.3),    # nominal octave, rings bright
        (2.40, 0.30, 1.9),    # minor-tierce inharmonic shimmer (decays its own way)
        (3.01, 0.20, 2.6),    # quint, soft
        (4.02, 0.10, 3.6),    # bright tail partial, low and quick-ish
    ]
    sig = np.zeros(n)
    for ratio, amp, dec in parts:
        sig += amp * np.sin(2*np.pi*f*ratio*t) * np.exp(-t / dec)
    # gentle detune twin on fundamental for a slow living beat
    sig += 0.16 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t / 1.4)
    # soft struck attack, no click; bell rings out and fades long
    env = adsr(n, a=0.006, d=4.0, s_level=0.0, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 3200.0, order=3)   # warm, no harsh top on the toll
    out = soft_clip(out * 1.02, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- handbell (lead) — mid handbell, clear strike + 2.005x and fast 2.76x partials ----
def voice_handbell(arg):
    """Pealing the melody bright. A mid handbell: clear ringing fundamental,
    a near-octave 2.005x partial (the bell's bright nominal, slightly stretched),
    a fast 2.76x inharmonic 'strike tone' that flashes at the attack and dies in
    ~0.3s, plus a soft 4x glint that vanishes quickly. Long bright tail. Soft
    struck attack (~5 ms). Additive only. arg = midi."""
    f = freq(int(arg))
    dur = 3.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)         * np.exp(-t*0.95) +   # ringing prime
        0.50 * np.sin(2*np.pi*f*2.005*t)   * np.exp(-t*1.3)  +   # bright nominal
        0.22 * np.sin(2*np.pi*f*2.76*t)    * np.exp(-t*8.0)  +   # strike-tone flash
        0.12 * np.sin(2*np.pi*f*3.01*t)    * np.exp(-t*2.2)  +   # quint, soft
        0.06 * np.sin(2*np.pi*f*4.0*t)     * np.exp(-t*5.0)      # tiny glint, gone fast
    )
    # living detune twin for handbell shimmer
    sig += 0.14 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.1)
    env = adsr(n, a=0.005, d=2.6, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- descant (lead2) — higher handbell, brighter and quicker tail, ringing the descant ----
def voice_descant(arg):
    """Ringing the descant line above. A higher handbell: brighter and quicker
    in the tail than the lead, with a crisper strike. Clear fundamental, bright
    stretched-octave 2.01x, a fast 2.76x strike flash, and a delicate 5x glint
    that decays fast. Shorter, sparklier tail. Soft attack (~5 ms). arg = midi."""
    f = freq(int(arg))
    dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)         * np.exp(-t*1.4) +    # ringing prime
        0.46 * np.sin(2*np.pi*f*2.01*t)    * np.exp(-t*1.9) +    # bright nominal
        0.20 * np.sin(2*np.pi*f*2.76*t)    * np.exp(-t*9.0) +    # strike flash
        0.08 * np.sin(2*np.pi*f*4.0*t)     * np.exp(-t*5.0) +    # glint
        0.05 * np.sin(2*np.pi*f*5.0*t)     * np.exp(-t*8.0)      # tiny sparkle, gone fast
    )
    sig += 0.12 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.6)
    env = adsr(n, a=0.005, d=1.9, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- warmbell (tone) — a warm mid bell rung soft, rounder partials, sweet middle ----
def voice_warmbell(arg):
    """The sweet resonant middle. A warm mid bell rung soft: rounder, gentler
    partials than the lead — no sharp strike flash, just a glowing fundamental,
    a soft octave, a quiet just-fifth and a whisper of detune. Mellow and
    singing, lowpassed round. Soft attack (~12 ms). ~3s. arg = midi."""
    f = freq(int(arg))
    dur = 3.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*0.9) +     # warm prime
        0.34 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*1.5) +     # soft octave
        0.16 * np.sin(2*np.pi*f*(3/2)*t)  * np.exp(-t*1.8) +     # sweet just-fifth
        0.08 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*3.0)       # faint sweetener
    )
    # gentle chorus shimmer for the rounded glow
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.0)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.0)
    # soft attack, mellow ring
    env = adsr(n, a=0.012, d=2.2, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4200.0, order=3)   # rounder partials, sweet middle
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- towerbell (chime) — a high tower-bell ping with bright shimmer ----
def voice_towerbell(arg):
    """A high tower-bell ping. Bright shimmer: a clear ringing fundamental with
    a stretched-octave nominal, a quick bright strike at 2.76x, and a high glassy
    5x glint that fades in ~50 ms so you only catch it as a sparkle at the onset.
    Bright but never glassy — lowpassed. Soft attack (~10 ms). ~2.6s. arg = midi."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.1) +    # warm body
        0.50 * np.sin(2*np.pi*f*2.01*t)   * np.exp(-t*1.6) +    # bright nominal
        0.22 * np.sin(2*np.pi*f*2.76*t)   * np.exp(-t*7.0) +    # bright strike ping
        0.10 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*4.0) +    # shimmer
        0.06 * np.sin(2*np.pi*f*5.0*t)    * np.exp(-t*6.0)      # high glint, gone fast
    )
    sig += 0.15 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.2)
    env = adsr(n, a=0.010, d=2.1, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7000.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- topbell (sparkle) — tiny top handbells flicking bright, scattered peals ----
def voice_topbell(seed):
    """Tiny top handbells flicking bright — scattered peals (delay echoes added
    live). Seed picks a note from the HIGH register and a quick partner a
    pentatonic step away, so each flick is a cheerful little two-bell glint.
    Very bright but rounded (lowpassed), short sparkling tail. Soft attack
    (~6 ms). Additive sines only. ~0.7s."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]           # A major, high register
    i = int(rng.integers(0, len(HIGH) - 2))
    step = int(rng.integers(1, 3))
    f0 = freq(HIGH[i])
    f1 = freq(HIGH[min(i + step, len(HIGH) - 1)])
    dur = 0.7
    n = int(dur * SR); t = t_axis(dur)
    # first tiny bell
    b0 = (np.sin(2*np.pi*f0*t) * np.exp(-t*6.5) +
          0.30*np.sin(2*np.pi*f0*2.01*t) * np.exp(-t*9.0) +
          0.10*np.sin(2*np.pi*f0*2.76*t) * np.exp(-t*16.0))
    # second bell, flicked ~60 ms later
    t2 = np.maximum(t - 0.06, 0.0)
    gate = (t >= 0.06).astype(float)
    b1 = gate * (np.sin(2*np.pi*f1*t2) * np.exp(-t2*7.0) +
                 0.28*np.sin(2*np.pi*f1*2.01*t2) * np.exp(-t2*10.0))
    sig = b0 + 0.85 * b1
    env = adsr(n, a=0.006, d=0.5, s_level=0.0, r=0.18)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- carillon_bloom (bloom) — a swell of overlapping bell-tails ringing together ----
def voice_carillon_bloom(arg):
    """A lush blooming carillon wash. From the passed root we ring a major chord
    of overlapping bell-tails (root, +4 maj3, +7 fifth, +12 octave), each a soft
    bell partial-stack with its own slow swell and staggered entry, so the chord
    blooms open like many bells overlapping in a tower. Warm, lowpassed, long
    lush tail. ~7s. arg = midi (root)."""
    root = int(arg)
    intervals = [0, 4, 7, 12]
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        # soft bell stack: prime + octave + gentle just-fifth, no strike flash
        bell = (np.sin(2*np.pi*f*t)
                + 0.30*np.sin(2*np.pi*f*2.0*t)
                + 0.12*np.sin(2*np.pi*f*(3/2)*t))
        # detune twin for shimmer
        bell += 0.30*np.sin(2*np.pi*f*1.0035*t)
        # slow breathing vibrato, each voice phased differently
        vib = 1.0 + 0.0020*np.sin(2*np.pi*0.24*t + i*0.8)
        bell = bell * vib
        # staggered slow swell: upper bells bloom slightly later
        stagger = 0.22 * i
        env = adsr(n, a=1.4 + stagger, d=0.9, s_level=0.78, hold=1.2, r=2.8)
        gain = 1.0 - 0.10*i
        sig += bell * env[:n] * gain
    sig /= len(intervals)
    # opening brightness over the bloom (moving lowpass feel)
    low = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.3 + 0.7 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 3000.0, order=3)   # warm, round, never glassy
    peak = float(np.max(np.abs(sig)) + 1e-9)
    sig = sig / peak * 0.50
    return sig


# ---- change_ring (cluster) — a change-ringing tumble of bells, shimmering interlocked ----
def voice_change_ring(arg):
    """A change-ringing tumble — joyous interlocked peal. From the root we take
    a rising pentatonic run (root, +2, +4, +7, +9, +12) and strike each bell in
    a quick staggered cascade, the way change-ringers tumble through a row, so
    the bells shimmer and overlap into one bright glow. Each strike is a small
    bell stack with a soft attack and bright tail. Warm lowpassed. ~6.5s.
    arg = midi (root)."""
    root = int(arg)
    steps = [0, 2, 4, 7, 9, 12]
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    stride = 0.16   # seconds between successive bell strikes in the row
    for i, iv in enumerate(steps):
        f = freq(root + iv)
        onset = i * stride
        on = int(onset * SR)
        if on >= n:
            break
        m = n - on
        tt = t[:m]
        bell = (1.00 * np.sin(2*np.pi*f*tt)      * np.exp(-tt*1.3) +
                0.42 * np.sin(2*np.pi*f*2.01*tt)  * np.exp(-tt*1.8) +
                0.16 * np.sin(2*np.pi*f*2.76*tt)  * np.exp(-tt*8.0) +
                0.06 * np.sin(2*np.pi*f*4.0*tt)   * np.exp(-tt*5.0))
        bell += 0.12 * np.sin(2*np.pi*f*1.004*tt) * np.exp(-tt*1.4)
        benv = adsr(m, a=0.006, d=1.6, s_level=0.0, r=0.4)
        sig[on:on+m] += bell[:benv.size] * benv[:bell.size]
    sig = lowpass_fft(sig, 6500.0, order=3)
    peak = float(np.max(np.abs(sig)) + 1e-9)
    sig = sig / peak * 0.50
    return sig


# ---- handtap (tap) — a damped handbell tap, near-dry mallet-on-bell click ----
def voice_handtap(seed):
    """The rhythmic pulse. A damped handbell tap — a bell struck and immediately
    damped, so it's a near-dry mallet-on-bell click with just a flash of pitched
    ring. A short pitched body (a couple of fast-decaying bell partials around a
    fixed mid pitch, tiny per-tap detune) plus a soft filtered-noise contact
    transient. Short, near-dry, warm. Soft attack (~3 ms). ~0.2s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.20
    n = int(dur * SR); t = t_axis(dur)
    # fixed mid handbell pitch (~A4) with a tiny per-tap wobble
    f0 = freq(69) * (2 ** (rng.uniform(-0.2, 0.2) / 12.0))
    body = (
        1.00 * np.sin(2*np.pi*f0*t)       * np.exp(-t*42) +    # quick pitched flash
        0.40 * np.sin(2*np.pi*f0*2.01*t)  * np.exp(-t*60) +    # bright nominal, gone fast
        0.16 * np.sin(2*np.pi*f0*2.76*t)  * np.exp(-t*90)      # tiny strike color
    )
    # mallet contact: short band-limited noise burst, soft (not instant) attack
    noise = rng.standard_normal(n)
    tap = lowpass_fft(noise, 2600.0, order=3)
    tap = tap - lowpass_fft(tap, 300.0, order=2)
    t_env = adsr(n, a=0.003, d=0.030, s_level=0.0, r=0.01)
    tap = tap * t_env
    sig = body + 0.32 * tap
    env = adsr(n, a=0.003, d=0.10, s_level=0.0, r=0.06)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4200.0, order=4)   # keep it warm, no harsh tick
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- treblechirp (chirp) — a bright tiny treble-bell flick, jubilant accent up top ----
def voice_treblechirp(seed):
    """A jubilant little accent up top. A bright tiny treble-bell flick: a single
    quick rising two-bell blip in the HIGH register — a bell pinged, then its
    partner a pentatonic step above, like a happy little 'ting-ting'. Pure bell
    partials, bright but rounded (lowpassed), near-dry, ~0.45s. Soft attack."""
    rng = np.random.default_rng(int(seed))
    HIGH = [78, 81, 85, 88]                    # very high A major bells
    i = int(rng.integers(0, len(HIGH) - 1))
    f0 = freq(HIGH[i])
    f1 = freq(HIGH[min(i + 1, len(HIGH) - 1)])
    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)
    # first ping
    b0 = (np.sin(2*np.pi*f0*t) * np.exp(-t*9.0) +
          0.28*np.sin(2*np.pi*f0*2.01*t) * np.exp(-t*13.0))
    # second ping ~70 ms later, a step up
    t2 = np.maximum(t - 0.07, 0.0)
    gate = (t >= 0.07).astype(float)
    b1 = gate * (np.sin(2*np.pi*f1*t2) * np.exp(-t2*10.0) +
                 0.26*np.sin(2*np.pi*f1*2.01*t2) * np.exp(-t2*14.0))
    sig = b0 + 0.9 * b1
    sig = lowpass_fft(sig, 8500.0, order=3)   # bright but never piercing
    env = adsr(n, a=0.006, d=0.30, s_level=0.0, r=0.12)
    out = sig[:env.size] * env[:sig.size] * 0.50
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "handtap": {
        "kind": "seed",
        "count": 5,
        "pans": [-0.2, 0.2, -0.1, 0.15, 0.0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.06, "decay": 0.7, "predelay_ms": 8, "brightness": 0.4}
    },
    "handbell": {
        "kind": "midi",
        "midis": [57, 59, 61, 62, 64, 66, 68, 69, 71, 73, 76],
        "pans": [-0.18, 0.18, -0.1, 0.12, 0.0, -0.15, 0.15],
        "target_peak": 0.78,
        "reverb": {"wet": 0.34, "decay": 3.0, "predelay_ms": 26, "brightness": 0.6}
    },
    "descant": {
        "kind": "midi",
        "midis": [66, 68, 69, 71, 73, 74, 76, 78, 81],
        "pans": [-0.3, 0.3, -0.2, 0.25, -0.1, 0.15, 0.0],
        "target_peak": 0.78,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.62}
    },
    "warmbell": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.32, "decay": 2.8, "predelay_ms": 26, "brightness": 0.5}
    },
    "towerbell": {
        "kind": "midi",
        "midis": [69, 71, 73, 76, 78, 81, 85, 88],
        "pans": [-0.4, 0.3, -0.2, 0.4, -0.3, 0.2, 0.0],
        "target_peak": 0.78,
        "reverb": {"wet": 0.40, "decay": 3.4, "predelay_ms": 30, "brightness": 0.62}
    },
    "topbell": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.38, "decay": 2.6, "predelay_ms": 18, "brightness": 0.66}
    },
    "carillon_bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0.0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.5, "predelay_ms": 45, "brightness": 0.5}
    },
    "change_ring": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0.0, -0.2, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 5.0, "predelay_ms": 42, "brightness": 0.55}
    },
    "treblechirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.5, -0.45, 0.3, -0.25],
        "target_peak": 0.78,
        "reverb": {"wet": 0.30, "decay": 2.2, "predelay_ms": 16, "brightness": 0.64}
    },
    "bourdon": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "target_peak": 0.62,
        "reverb": {"wet": 0.22, "decay": 3.0, "predelay_ms": 20, "brightness": 0.35}
    }
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
    print("peal:", name)


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
