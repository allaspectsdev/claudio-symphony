#!/usr/bin/env python3
"""
courtly — sample renderer (per-voice reverb from preset.json).

A concert harp cascading through a sunlit hall while pizzicato strings dance
underneath. Plucked strings both soft (harp, round and shimmering) and short
(pizzicato, dry and bouncy) — elegant, cascading, regal but playful and bright,
all sparkle and grace. A major @ A=432, additive only, never dreary.

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


# ---- harp_bass (bass) ----
def voice_harp_bass(arg):
    """A low harp string plucked deep — long warm decay with a gentle string
    'buzz' that grounds the cascade. Additive: a round sine fundamental that
    decays slowly, soft octave + fifth-above-octave that fade earlier for the
    plucked bloom, a quiet sub for body, and a brief soft-noise 'string buzz'
    transient (low-passed, gone in ~40ms) for the felt-pluck contact. Soft
    ~9 ms attack — no click. Warm and rounded, never dark. arg = midi (LOW)."""
    f = freq(int(arg))
    dur = 3.0
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.4) +   # round body, long decay
        0.34 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.0) +   # plucked octave bloom
        0.14 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*5.5) +   # gentle string color
        0.30 * np.sin(2*np.pi*f*0.5*t)    * np.exp(-t*1.2) +   # quiet sub for body
        0.06 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*1.4)     # slow beat = string "life"
    )

    # soft string-buzz transient: low-passed noise puff, the pluck contact
    rng = np.random.default_rng(int(arg) * 19 + 3)
    buzz = rng.standard_normal(n)
    buzz = lowpass_fft(buzz, 1400.0, order=3)
    buzz_env = np.exp(-t * 60.0)                  # ~30 ms felt buzz, gone fast
    sig = sig + 0.10 * buzz * buzz_env

    # keep it warm and round — bass is felt, not bright
    sig = lowpass_fft(sig, 1600.0, order=4)

    env = adsr(n, a=0.009, d=1.2, s_level=0.0, r=1.4)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- harp_lead (lead) ----
def voice_harp_lead(arg):
    """A mid harp pluck — bright attack into a singing sustain, rolling through
    the melody like a glissando fragment. Additive: a clean fundamental with a
    sweet octave and a soft fifth-above-octave that ping bright at the onset and
    decay into a singing body, a faint high glint that dies in ~30 ms for the
    plucked 'attack', and a whisper of detune for bloom. ~12 ms soft attack,
    no click. Bright and graceful. arg = midi."""
    f = freq(int(arg))
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.6) +   # singing body
        0.46 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.2) +   # sweet octave, bright onset
        0.18 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*5.0) +   # fifth color, plucked ping
        0.06 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*9.0) +   # high glint, gone fast
        0.16 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*2.0)     # soft detune bloom
    )

    env = adsr(n, a=0.012, d=1.4, s_level=0.0, r=0.7)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=2)       # tame any fizz, keep it sweet
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- pizz_violin (lead2) ----
def voice_pizz_violin(arg):
    """A pizzicato violin — short dry snap with a quick body resonance, dancing
    a counter-line. Additive: a fundamental with bright string partials (octave,
    fifth) that decay FAST so it reads as a plucked 'snap', a tiny inharmonic
    glint for the fingertip pluck, plus a short band-limited noise 'pluck' burst.
    Quick smooth attack (~6 ms), dry and bouncy. arg = midi."""
    f = freq(int(arg))
    dur = 0.7
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*8.0)  +  # snappy body
        0.50 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*11.0) +  # bright octave snap
        0.22 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*16.0) +  # string color, quick
        0.08 * np.sin(2*np.pi*f*4.05*t)   * np.exp(-t*30.0)    # tiny pluck glint
    )

    # pluck contact: short band of noise, the fingertip snap
    rng = np.random.default_rng(int(arg) * 23 + 7)
    pluck = rng.standard_normal(n)
    pluck = lowpass_fft(pluck, 3200.0, order=3)
    pluck_env = np.exp(-t * 140.0)                # ~12 ms snap
    sig = sig + 0.12 * pluck * pluck_env

    sig = lowpass_fft(sig, 5200.0, order=3)       # warm, no glassy top
    env = adsr(n, a=0.006, d=0.45, s_level=0.0, r=0.18)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- pizz_cello (tone) ----
def voice_pizz_cello(arg):
    """A soft cello pizzicato — round and warm, the sweet low-mid pulse.
    Additive: a round fundamental with a gentle octave and a touch of fifth,
    all decaying medium-fast for a plucked-but-warm body, plus a soft low
    noise 'thumb' puff for the felt-pluck contact. Quick soft attack (~7 ms),
    rounded and dark-free. arg = midi."""
    f = freq(int(arg))
    dur = 1.3
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*3.2) +   # round plucked body
        0.32 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*5.5) +   # warm octave
        0.12 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*8.0) +   # gentle fifth color
        0.10 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*3.0)     # whisper of bloom
    )

    rng = np.random.default_rng(int(arg) * 29 + 5)
    thumb = rng.standard_normal(n)
    thumb = lowpass_fft(thumb, 1100.0, order=3)
    thumb_env = np.exp(-t * 90.0)
    sig = sig + 0.09 * thumb * thumb_env

    sig = lowpass_fft(sig, 3200.0, order=3)       # round, warm low-mid
    env = adsr(n, a=0.007, d=0.7, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- harp_harmonic (chime) ----
def voice_harp_harmonic(arg):
    """A high harp harmonic — a flute-pure bell tone with light shimmer.
    Additive: a near-pure fundamental (harmonics are almost sinusoidal) with a
    very soft octave that fades early, a faint fifth-above for glass color that
    dies fast, and a gentle chorus shimmer from two near-unisons. Soft ~16 ms
    attack — no click, melts in. Pure, sweet, bell-like. arg = midi (HIGH)."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.0) +   # flute-pure body
        0.22 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*2.0) +   # soft octave, fades early
        0.07 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*3.5)     # faint glass color, gone fast
    )
    # gentle chorus shimmer for the "harmonic" glow
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.2)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.2)

    env = adsr(n, a=0.016, d=2.1, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7000.0, order=3)       # keep it pure, no harsh top
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- harp_droplets (sparkle) ----
def voice_harp_droplets(arg):
    """A tiny top-octave harp flick cascade — bright droplets tumbling down,
    meant to ring out into delay echoes. Additive: a sequence of 3-4 quick
    pure plucks descending a pentatonic fragment from a high seed note, each a
    sine + soft octave with a fast plucked decay. Bright, light, sparkling.
    Soft per-droplet attack (~5 ms), near-dry here (echoes added live)."""
    rng = np.random.default_rng(int(arg))
    HIGH = [76, 78, 81, 85, 88, 90]               # A major, high register
    start_i = int(rng.integers(2, len(HIGH)))     # start high, cascade down
    ndrops = int(rng.integers(3, 5))

    dur = 0.95
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)

    gap = 0.085                                    # tumbling spacing
    idx = start_i
    for d in range(ndrops):
        idx = max(0, idx - int(rng.integers(1, 3)))   # step down the scale
        f = freq(HIGH[idx])
        start = int(d * gap * SR)
        if start >= n:
            break
        seg_t = t[:n - start]
        drop = (
            np.sin(2*np.pi*f*seg_t) * np.exp(-seg_t*9.0) +
            0.30 * np.sin(2*np.pi*f*2.0*seg_t) * np.exp(-seg_t*13.0)
        )
        denv = adsr(seg_t.size, a=0.005, d=0.18, s_level=0.0, r=0.06)
        drop = drop[:denv.size] * denv[:drop.size]
        amp = 1.0 - 0.12 * d                       # gently softening cascade
        sig[start:start + drop.size] += drop * amp

    sig = lowpass_fft(sig, 7500.0, order=3)        # bright but not piercing
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.48 / peak)
    return sig


# ---- arco_bloom (bloom) ----
def voice_arco_bloom(arg):
    """A soft arco-string swell — a gentle bowed pad blooming warm under the
    plucks, a lush hall wash. Additive only: a clean fundamental with a sweet
    just-major-third (5/4) and just-fifth (3/2) above, a soft octave halo and a
    quiet sub, two faint detunes for a breathing bowed shimmer. A slow moving
    lowpass opens the brightness over the swell so it 'blooms' without harshness.
    Slow ~1.4 s attack, long gentle release. ~6.5s. arg = midi."""
    f = freq(int(arg))
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)

    # slow breathing vibrato — a calm bowed exhale
    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.30*t)

    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.42 * np.sin(2*np.pi*f*1.0035*t) +
        0.42 * np.sin(2*np.pi*f*0.9967*t)
    )
    third  = 0.38 * np.sin(2*np.pi*f*(5/4)*t*vib)
    fifth  = 0.32 * np.sin(2*np.pi*f*(3/2)*t*vib)
    octave = 0.20 * np.sin(2*np.pi*f*2.0*t)
    sub    = 0.26 * np.sin(2*np.pi*f*0.5*t)

    sig = fund + third + fifth + octave + sub

    # bloom: brightness opens over the first seconds, then settles
    low  = lowpass_fft(sig, 700.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    sig = lowpass_fft(sig, 2800.0, order=3)        # round, warm bowed wash
    env = adsr(n, a=1.4, d=1.0, s_level=0.85, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out / peak * 0.50
    return out


# ---- rolled_chord (cluster) ----
def voice_rolled_chord(arg):
    """A rolled harp chord — a shimmering arpeggiated wash of strings, elegant
    and bright. From the passed root midi we build a major chord: root, +4
    (maj3), +7 (5th), +9 (maj6), +12 (octave), +16 (maj3 up top). Each note is
    a pure additive harp pluck (sine + soft octave) and they are ROLLED in
    sequence (staggered onsets) like a harpist's hand sweeping up, blooming into
    a glowing chord. Warm low-passed, bright but never harsh. arg = root midi."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12, 16]
    dur = 4.2
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)

    roll = 0.065                                   # harp roll spacing per note
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        start = int(i * roll * SR)
        if start >= n:
            break
        seg_t = t[:n - start]
        # plucked harp body: fundamental + soft octave + faint fifth, detune bloom
        note = (
            np.sin(2*np.pi*f*seg_t)        * np.exp(-seg_t*1.3) +
            0.34 * np.sin(2*np.pi*f*2.0*seg_t) * np.exp(-seg_t*2.6) +
            0.12 * np.sin(2*np.pi*f*3.0*seg_t) * np.exp(-seg_t*4.0) +
            0.12 * np.sin(2*np.pi*f*1.004*seg_t) * np.exp(-seg_t*1.6)
        )
        nenv = adsr(seg_t.size, a=0.010, d=1.6, s_level=0.0, r=0.8)
        note = note[:nenv.size] * nenv[:note.size]
        gain = 1.0 - 0.07 * i                      # top notes a touch softer
        sig[start:start + note.size] += note * gain

    sig = lowpass_fft(sig, 6000.0, order=3)        # shimmering but warm
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- muted_pizz (tap) ----
def voice_muted_pizz(arg):
    """A muted string pizzicato tap — a near-dry bounce, a light fingertip
    pulse. Additive: a couple of very fast-decaying low-mid sine partials (the
    muted, damped string body) anchored in key, plus a short soft band-limited
    noise 'fingertip' transient. Very short and dry — the lightest plucked tick.
    Soft ~3 ms attack, no raw edge. ~0.22s. arg = seed."""
    rng = np.random.default_rng(int(arg) & 0xffffffff)
    dur = 0.22
    n = int(dur * SR); t = t_axis(dur)

    # muted body: tuned near A3, tiny per-tap pitch wobble = real fingers
    f0 = freq(57) * (1.0 + rng.uniform(-0.010, 0.010))
    body = (
        1.00 * np.sin(2*np.pi*f0*t)       * np.exp(-t*28.0) +   # damped fundamental
        0.40 * np.sin(2*np.pi*f0*2.0*t)   * np.exp(-t*40.0) +   # muted octave, gone fast
        0.16 * np.sin(2*np.pi*f0*3.01*t)  * np.exp(-t*55.0)     # faint string color
    )

    # fingertip contact: short band of noise
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 2400.0, order=3)
    noise = noise - lowpass_fft(noise, 260.0, order=2)
    n_env = adsr(n, a=0.0025, d=0.030, s_level=0.0, r=0.01)
    noise = noise * n_env

    sig = body + 0.32 * noise
    sig = lowpass_fft(sig, 3400.0, order=4)         # rounded, dry pluck
    env = adsr(n, a=0.003, d=0.10, s_level=0.0, r=0.06)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- harp_ping (chirp) ----
def voice_harp_ping(arg):
    """A bright harp harmonic ping at the very top — a sparkling courtly
    flourish. One sweet single high pluck in A major: a near-pure sine with a
    soft octave glint and a tiny chiff at the onset, picked from the HIGH
    register by seed. Bright & friendly, ~0.5s, near-dry. Soft ~6 ms attack,
    no click. arg = seed."""
    rng = np.random.default_rng(int(arg))
    HIGH = [78, 81, 85, 88, 90, 93]                # A major, very high
    note = HIGH[int(rng.integers(0, len(HIGH)))]
    f = freq(note)

    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        np.sin(2*np.pi*f*t) * np.exp(-t*4.5) +
        0.22 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*7.5) +   # bright octave glint
        0.06 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*16.0)    # tiny chiff at onset
    )
    sig = lowpass_fft(sig, 7500.0, order=3)         # bright but never piercing
    env = adsr(n, a=0.006, d=0.22, s_level=0.0, r=0.18)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "harp_bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.12, "decay": 1.8, "predelay_ms": 14, "brightness": 0.32}
    },
    "harp_lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 62, 64, 66, 68, 69, 71, 73, 76],
        "pans": [-0.18, 0.18, -0.1, 0.14, -0.05, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.2, "decay": 1.8, "predelay_ms": 20, "brightness": 0.6}
    },
    "pizz_violin": {
        "kind": "midi",
        "midis": [61, 64, 66, 68, 69, 71, 73, 76, 78, 81],
        "pans": [0.28, -0.24, 0.32, -0.18, 0.2, -0.3],
        "target_peak": 0.82,
        "reverb": {"wet": 0.16, "decay": 1.2, "predelay_ms": 14, "brightness": 0.55}
    },
    "pizz_cello": {
        "kind": "midi",
        "midis": [45, 49, 52, 57, 61, 64],
        "pans": [-0.15, 0.15, -0.08, 0.1],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 1.6, "predelay_ms": 18, "brightness": 0.42}
    },
    "harp_harmonic": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88, 90],
        "pans": [-0.35, 0.3, -0.2, 0.4, -0.3, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.2, "predelay_ms": 28, "brightness": 0.62}
    },
    "harp_droplets": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.78,
        "reverb": {"wet": 0.3, "decay": 2.6, "predelay_ms": 22, "brightness": 0.64}
    },
    "arco_bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.0, "predelay_ms": 45, "brightness": 0.44}
    },
    "rolled_chord": {
        "kind": "midi",
        "midis": [45, 50, 52, 57],
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 4.8, "predelay_ms": 40, "brightness": 0.5}
    },
    "muted_pizz": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.22, 0.18, -0.1, 0.24],
        "target_peak": 0.5,
        "reverb": {"wet": 0.04, "decay": 0.6, "predelay_ms": 8, "brightness": 0.42}
    },
    "harp_ping": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.5, -0.45],
        "target_peak": 0.8,
        "reverb": {"wet": 0.18, "decay": 1.8, "predelay_ms": 14, "brightness": 0.62}
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
    print("courtly:", name)


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
