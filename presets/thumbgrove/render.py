#!/usr/bin/env python3
"""
thumbgrove — sample renderer (per-voice reverb from preset.json).

A warm kalimba grove at golden hour: plucked metal tines on a wooden gourd,
woody and earthy with a gentle characteristic buzz that decays fast. An
mbira/kalimba groove — hypnotic, joyful, African-sunlit, never harsh. A low
gourd-resonated bass heartbeat, interlocking lead tines in cross-rhythm, a
sweet muted tone, a bright chime ping, scattered seed-pod sparkles, a bowed-
gourd bloom, a hocketed tine cluster, a dry calabash knuckle tap, and a happy
buzzing chirp up top. A major pentatonic @ A=432, additive only, never dreary.

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


def _soft_buzz(t, f, amount, decay, seed=0):
    """A gentle, fast-decaying tine 'buzz/rattle' — the kalimba's signature
    woody buzz from the wire wrapped on the tine. NOT FM: it's a couple of
    inharmonic partials at a soft, quick-dying amplitude, kept low and tamed.
    amount scales it down; decay is high so it's GONE in tens of ms."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    p1 = 3.37 + rng.uniform(-0.05, 0.05)
    p2 = 4.62 + rng.uniform(-0.05, 0.05)
    buzz = (
        0.6 * np.sin(2*np.pi*f*p1*t) * np.exp(-t*decay) +
        0.4 * np.sin(2*np.pi*f*p2*t) * np.exp(-t*decay*1.4)
    )
    # amplitude-flutter so it reads as a soft rattle, not a clean partial
    flutter = 1.0 + 0.5*np.sin(2*np.pi*38.0*t)*np.exp(-t*decay)
    return amount * buzz * flutter


# ---- bass (low gourd-resonated tine — deep warm pluck with woody body thrum) ----
def voice_bass(arg):
    """A low gourd-resonated tine: a deep, warm plucked fundamental with a
    soft woody body thrum and a tiny gourd-resonance overtone. The grounding
    heartbeat of the grove. Additive only, rounded, near-dry. ~2.2s."""
    f = freq(int(arg))
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    # plucked tine body: fundamental dominant + low warmth harmonics that
    # fade fast. Pluck = quick-ish exponential decay, not a sustained drone.
    body = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.0) +
        0.34 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.8) +   # warm octave
        0.12 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*6.0) +   # woody color, gone fast
        0.07 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*1.6)     # slow beat = gourd 'life'
    )
    # gourd body thrum: a soft sub resonance just under the fundamental
    thrum = 0.20 * np.sin(2*np.pi*f*0.5*t) * np.exp(-t*2.6)

    # a whisper of woody pluck transient (low-passed noise puff at attack)
    rng = np.random.default_rng(int(arg) * 17 + 5)
    puff = lowpass_fft(rng.standard_normal(n), 320.0, order=3)
    puff = 0.10 * puff * np.exp(-t*30.0)

    sig = body + thrum + puff
    # keep it round and woody — bass is felt, not bright
    sig = lowpass_fft(sig, 1100.0, order=4)

    # soft felt pluck attack (~8 ms, no click), warm supportive tail
    env = adsr(n, a=0.008, d=0.6, s_level=0.30, hold=0.2, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead (mid kalimba tine — bright pluck with soft buzz-rattle, weaves melody) ----
def voice_lead(arg):
    """A mid kalimba tine: a bright plucked fundamental with a clean octave
    ping and a soft characteristic buzz-rattle that decays fast. The melody
    weaver. Additive only, sweet, ~1.4s. No FM, buzz is gone in ~80 ms."""
    f = freq(int(arg))
    dur = 1.4
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)                          +  # fundamental
        0.42 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*4.0)   +  # clean octave ping
        0.16 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*7.0)   +  # bright pluck color
        0.07 * np.sin(2*np.pi*f*4.02*t)  * np.exp(-t*22.0)  +  # tine 'tick', gone fast
        0.14 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*3.0)      # soft detune body
    )
    # gentle kalimba buzz-rattle — quick decay so it's a flavor, not a drone
    sig += _soft_buzz(t, f, amount=0.05, decay=34.0, seed=int(arg))

    # plucky soft attack (~6 ms), bright but click-free
    env = adsr(n, a=0.006, d=0.9, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6000.0, order=2)   # tame top, keep it sweet & woody
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (higher mbira tine — quicker, twangier, interlocks in cross-rhythm) ----
def voice_lead2(arg):
    """A higher mbira tine: quicker and twangier than the lead, a short bright
    pluck that interlocks with the lead in cross-rhythm. Additive only,
    snappier decay, a touch more buzz-twang. ~1.0s. No FM."""
    f = freq(int(arg))
    dur = 1.0
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.2)   +  # quick fundamental
        0.40 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*5.0)   +  # octave twang
        0.18 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*9.0)   +  # bright twang color
        0.08 * np.sin(2*np.pi*f*4.05*t)   * np.exp(-t*26.0)     # tine tick
    )
    # twangier buzz — slightly stronger but decays even faster (snappy mbira)
    sig += _soft_buzz(t, f, amount=0.06, decay=40.0, seed=int(arg) + 3)

    env = adsr(n, a=0.005, d=0.7, s_level=0.0, r=0.28)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (warm muted tine — round, buzz-free, the sweet woody middle) ----
def voice_tone(arg):
    """A warm muted tine: round and completely buzz-free, the sweet woody
    middle of the grove. A clean fundamental with a soft octave that fades
    early and a whisper of detune for body. Muted = warm lowpass, gentle
    sustain. Additive only, ~1.8s. No FM, no buzz."""
    f = freq(int(arg))
    dur = 1.8
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)                          +  # clean fundamental
        0.22 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.0)   +  # soft octave, fades early
        0.06 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*6.0)   +  # faint sweetener
        0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*2.0)      # whisper of detune body
    )
    # muted: roll off bright top so it's round and woody, never glassy
    sig = lowpass_fft(sig, 2600.0, order=3)

    # gentle pluck-to-sing attack, soft sustain & release
    env = adsr(n, a=0.010, d=0.7, s_level=0.40, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- chime (high bright tine ping with a touch of shimmer, medium reverb) ----
def voice_chime(midi):
    """A high bright tine ping with a touch of shimmer. Additive, sweet,
    ~2.0s. Soft 14ms attack (no click), a glowing fundamental with a clean
    octave doubling, a gentle tine partial at 3x that decays fast, and a
    whisper of shimmer from two near-unisons. No FM, no partials past 5x."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)       * np.exp(-t*1.3)  +  # warm ping body
        0.50 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.0)  +  # octave doubling
        0.18 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*3.4)  +  # sweet tine color
        0.06 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*5.5)  +  # faint glint
        0.04 * np.sin(2*np.pi*f*5.0*t)   * np.exp(-t*7.0)     # tiny shimmer, gone fast
    )
    # gentle chorus shimmer (two near-unisons) for the golden-hour glow
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.4)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.4)
    env = adsr(n, a=0.014, d=1.6, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (tiny top tines flicking with soft buzz, scattered seed-pods) ----
def voice_sparkle(seed):
    """Tiny top tines flicking, scattered like seed-pods. Seed picks a high
    pentatonic note and a quick 2-note flick. Very short, bright, light. A
    soft buzz-flick at the onset (gone in ~30ms) for the seed-pod rattle.
    Additive only, ~0.45s. No FM."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85, 88]
    start_i = int(rng.integers(0, len(HIGH) - 1))
    step = int(rng.integers(1, 3))
    end_i = min(start_i + step, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)

    # quick little flick: rise from f0 to f1 over the first ~40%, then hold
    rise = np.clip(t / (dur * 0.4), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) * np.exp(-t*3.0) +
        0.20 * np.sin(2*phase) * np.exp(-t*5.0) +     # glassy sheen
        0.06 * np.sin(3*phase) * np.exp(-t*9.0)       # tiny tine glint
    )
    # soft seed-pod buzz at the very onset, gone fast
    sig += _soft_buzz(t, f0, amount=0.05, decay=46.0, seed=int(seed) + 11)
    sig = lowpass_fft(sig, 7000.0, order=3)

    env = adsr(n, a=0.006, d=0.18, s_level=0.18, r=0.22)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (bowed-gourd swell — warm wooden pad blooming softly under the grove) ----
def voice_bloom(midi):
    """A bowed-gourd swell: a warm, earthy wooden pad that blooms softly open
    under the grove and slowly closes. Additive only. A clean fundamental with
    a just major-third and just-fifth halo, a soft octave and a warm sub, two
    faint detunes for a breathing chorus. Everything low-passed round — no
    harsh partial, lush and earthy. ~6.5s."""
    f = freq(midi)
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)

    # slow breathing vibrato — a calm exhale through the gourd
    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.26*t)

    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.45 * np.sin(2*np.pi*f*1.0035*t) +
        0.45 * np.sin(2*np.pi*f*0.9967*t)
    )
    third  = 0.38 * np.sin(2*np.pi*f*(5/4)*t*vib)   # sweet major third
    fifth  = 0.32 * np.sin(2*np.pi*f*(3/2)*t*vib)   # perfect fifth
    octave = 0.20 * np.sin(2*np.pi*f*2.0*t)         # soft octave halo
    sub    = 0.30 * np.sin(2*np.pi*f*0.5*t)         # warm earthy body

    sig = fund + third + fifth + octave + sub

    # bloom: brightness opens over the first seconds then settles (moving LP)
    low  = lowpass_fft(sig, 650.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    # final warmth ceiling — round and woody, no fizz
    sig = lowpass_fft(sig, 2400.0, order=3)

    env = adsr(n, a=1.5, d=1.0, s_level=0.85, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.48
    return out


# ---- cluster (interlocking tine roll — shimmering hocketed cloud of thumb-plucks) ----
def voice_cluster(arg):
    """A shimmering hocketed cloud of thumb-plucks: from the root we build a
    major-pentatonic chord (root, +4, +7, +9, +12) and pluck each tine as a
    staggered interlocking roll so it ripples open like a hypnotic mbira cycle.
    Pure additive plucks, soft buzz on the brighter tines, warm low-passed.
    A welcoming bloom-cloud. ~6.5s."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        # each tine is a soft pluck: fundamental + octave + a quick 3x color
        partial = (
            np.sin(2*np.pi*f*t) * np.exp(-t*1.4) +
            0.30 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*2.6) +
            0.10 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*4.5)
        )
        detune = 0.30 * np.sin(2*np.pi*f*1.0035*t) * np.exp(-t*1.6)
        # a faint buzz only on the brighter upper tines, gone fast
        buzz = _soft_buzz(t, f, amount=0.03 * (i / 4.0), decay=44.0, seed=root + i)
        voice = partial + detune + buzz
        # staggered onset = interlocking hocket roll (each tine enters later)
        stagger = 0.16 * i
        env = adsr(n, a=0.008 + stagger, d=1.2, s_level=0.50,
                   hold=1.2, r=2.2)
        gain = 1.0 - 0.10*i      # upper tines a touch quieter, root grounded
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    # warm: tame anything bright/harsh, keep it earthy
    sig = lowpass_fft(sig, 3000.0, order=3)
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- tap (gourd-body knuckle tap — dry woody knock, the calabash pulse) ----
def voice_tap(seed):
    """A gourd-body knuckle tap: a dry woody knock — knuckle on the calabash.
    A couple of fast-decaying low-mid sine 'body' partials (anchored near A2
    so it sits in key) plus a short soft band-limited noise contact transient.
    Short, near-dry, warm. The percussive pulse. ~0.3s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.30
    n = int(dur * SR); t = t_axis(dur)

    # gourd body: low-mid hollow thunk, small per-tap pitch wobble (real hand)
    f0 = freq(45) * (1.0 + rng.uniform(-0.014, 0.014))   # ~A2 calabash body
    body = (
        1.00 * np.sin(2*np.pi*f0*t)      * np.exp(-t*20) +    # fundamental knock
        0.42 * np.sin(2*np.pi*f0*1.5*t)  * np.exp(-t*28) +    # hollow fifth-ish overtone
        0.16 * np.sin(2*np.pi*f0*2.76*t) * np.exp(-t*44)      # woody color, gone fast
    )
    # knuckle contact: short filtered noise burst, soft (not instant) attack
    noise = rng.standard_normal(n)
    knock = lowpass_fft(noise, 1900.0, order=4)
    knock = knock - lowpass_fft(knock, 220.0, order=2)
    k_env = adsr(n, a=0.0035, d=0.040, s_level=0.0, r=0.02)
    knock = knock * k_env

    sig = body + 0.45 * knock
    env = adsr(n, a=0.003, d=0.16, s_level=0.0, r=0.10)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 3000.0, order=4)   # rounded, woody
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chirp (bright high tine flick — a happy buzzing grace note up top) ----
def voice_chirp(seed):
    """A bright high tine flick — a happy buzzing grace note up top. A quick
    rising 2-note blip in the high pentatonic with a tiny soft buzz at the
    onset (gone fast), bright & friendly. Additive (sines + octave sparkle),
    ~0.4s, near-dry. No FM."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]
    leaps = [2, 3, 4]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)

    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep — no zipper
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.18 * np.sin(2*phase) +                 # gentle octave glassy sheen
        0.05 * np.sin(3*phase) * np.exp(-t*14)   # tiny chiff at onset
    )
    # happy buzz grace at the very onset, gone fast
    sig += _soft_buzz(t, f0, amount=0.045, decay=50.0, seed=int(seed) + 7)
    sig = lowpass_fft(sig, 6800.0, order=3)

    env = adsr(n, a=0.010, d=0.10, s_level=0.50, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.1, "decay": 1.6, "predelay_ms": 12, "brightness": 0.3}
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.18, 0.16, -0.1, 0.12],
        "target_peak": 0.8,
        "reverb": {"wet": 0.18, "decay": 1.6, "predelay_ms": 16, "brightness": 0.58}
    },
    "lead2": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.22, -0.18, 0.14, -0.12],
        "target_peak": 0.8,
        "reverb": {"wet": 0.2, "decay": 1.5, "predelay_ms": 16, "brightness": 0.6}
    },
    "tone": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.12, 0.12],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 2.0, "predelay_ms": 20, "brightness": 0.5}
    },
    "chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.6}
    },
    "sparkle": {
        "kind": "seed",
        "count": 5,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25],
        "target_peak": 0.78,
        "reverb": {"wet": 0.3, "decay": 2.4, "predelay_ms": 22, "brightness": 0.62}
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5, "predelay_ms": 45, "brightness": 0.42}
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.8, "predelay_ms": 42, "brightness": 0.45}
    },
    "tap": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.18, 0.2, -0.1, 0.14],
        "target_peak": 0.85,
        "reverb": {"wet": 0.04, "decay": 0.6, "predelay_ms": 8, "brightness": 0.32}
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.8,
        "reverb": {"wet": 0.1, "decay": 1.6, "predelay_ms": 12, "brightness": 0.6}
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
    print("thumbgrove:", name)


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
