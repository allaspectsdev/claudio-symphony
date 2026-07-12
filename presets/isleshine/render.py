#!/usr/bin/env python3
"""
isleshine — sample renderer (per-voice reverb from preset.json).

Bright steel pans ringing on a sunny beach: a deep round low-pan boom under a
singing tenor-pan lead, a snappier ping-pan counter, a creamy double-second
harmony, fast-decaying high pan pings, scattered top-pan sparkle, a rolled-pan
bloom, a shimmering pan-roll cluster, a near-dry rim tap, and a bright island
chirp. A major pentatonic @ A=432, additive only, never dreary — pure summer joy.

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


# Steel-pan partial set: the characteristic ring of a pan comes from a small
# group of mostly-harmonic partials plus a couple of gently-stretched ones,
# each with its OWN decay so the bright top "glints" then fades fast while the
# warm body sustains. Kept additive, never FM, nothing harsh above ~5x.


# ---- pan_boom (bass) ----
def voice_pan_boom(arg):
    """Low bass-pan boom: a deep round steel note with warm sustain — the island
    groove floor. Strong sine fundamental, a soft octave for body, a gentle 3x
    that fades early, plus a slight metallic 2.8x glint gone in ~120 ms so it
    reads as a struck pan, not a pure sub. Slow ~3 Hz breathe keeps it alive.
    Soft 8 ms attack. A-pentatonic LOW. arg = midi."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)                              +  # round body
        0.40 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.0)       +  # octave warmth
        0.16 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*4.0)       +  # soft third
        0.10 * np.sin(2*np.pi*f*2.8*t)   * np.exp(-t*8.0)       +  # quick metallic glint
        0.06 * np.sin(2*np.pi*f*1.004*t)                           # slow beat = steel life
    )
    breathe = 1.0 + 0.05 * np.sin(2*np.pi*3.0*t - np.pi/2)
    sig = sig * breathe
    sig = lowpass_fft(sig, 1100.0, order=4)                    # keep it round/deep
    env = adsr(n, a=0.008, d=0.6, s_level=0.5, hold=0.5, r=1.2)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- pan_lead (lead) ----
def voice_pan_lead(arg):
    """Tenor-pan strike: bright ringing tone with shimmering 2x and a quick
    metallic glint, singing the calypso tune. Additive — fundamental, a bright
    octave that decays medium-fast for the 'shimmer', a 3x bell color, a
    stretched 4.05x glint that dies in ~80 ms (the pan 'ting'), and a soft
    detune body bloom. Fast ~6 ms strike attack. ~1.8s. arg = midi."""
    f = freq(int(arg))
    dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.4)      +  # singing body
        0.52 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.0)      +  # bright shimmer 2x
        0.22 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*5.0)      +  # bell color
        0.10 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*8.0)      +  # sparkle, fades
        0.07 * np.sin(2*np.pi*f*4.05*t)   * np.exp(-t*12.0)     +  # metallic glint, gone fast
        0.16 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*1.8)         # detune bloom
    )
    env = adsr(n, a=0.006, d=1.0, s_level=0.0, r=0.55)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=2)                   # tame top fizz, stay sweet
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- pan_ping (lead2) ----
def voice_pan_ping(arg):
    """Higher ping-pan: brighter and snappier than the lead, answering with a
    sunny counter-melody. Shorter decay, a touch more 2x/3x sparkle, a fast
    inharmonic 4.1x glint. ~1.3s, bright but rounded. arg = midi."""
    f = freq(int(arg))
    dur = 1.3
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.0)      +  # snappy body
        0.58 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.6)      +  # bright octave
        0.26 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*6.0)      +  # ping color
        0.10 * np.sin(2*np.pi*f*4.1*t)    * np.exp(-t*14.0)     +  # fast glint
        0.12 * np.sin(2*np.pi*f*1.005*t)  * np.exp(-t*2.4)         # tiny bloom
    )
    env = adsr(n, a=0.006, d=0.7, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7600.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- pan_double (tone) ----
def voice_pan_double(arg):
    """Double-second pan: warm mellow steel, the creamy mid harmony. Rounder
    than the leads — fundamental dominant, a soft octave, a gentle 3x that
    fades early, light detune chorus. Less bright top so it sits as the warm
    filler. ~2.2s sustained. arg = midi."""
    f = freq(int(arg))
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.1)      +  # warm body
        0.34 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*2.4)      +  # soft octave
        0.12 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*5.0)      +  # gentle color, early
        0.14 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*1.4)      +  # detune chorus
        0.10 * np.sin(2*np.pi*f*0.997*t)  * np.exp(-t*1.4)         # second detune
    )
    env = adsr(n, a=0.010, d=0.9, s_level=0.45, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 5200.0, order=3)                   # mellow, creamy
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- pan_chime (chime) ----
def voice_pan_chime(arg):
    """High pan ping with bright shimmer that decays fast. Additive bell-ish:
    fundamental + bright 2x + a 3x and a gentle stretched 4.2x glint, all with
    quick independent decays so it sparkles then clears. Soft 10 ms attack.
    Medium reverb voice. ~1.6s. arg = midi."""
    f = freq(int(arg))
    dur = 1.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.2)      +  # bright body
        0.50 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.4)      +  # shimmer
        0.22 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*5.5)      +  # glass color
        0.09 * np.sin(2*np.pi*f*4.2*t)    * np.exp(-t*10.0)     +  # quick glint
        0.10 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*2.4)         # tiny shimmer twin
    )
    env = adsr(n, a=0.010, d=1.0, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7800.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sunflick (sparkle) ----
def voice_sunflick(seed):
    """Tiny top-pan flicks scattering like sun on waves — light delay echoes.
    A quick high pan ping in the HIGH pentatonic, very short and bright, with a
    fast metallic glint at onset. Seed picks the note so a run scatters across
    the top. ~0.5s, additive, soft 8 ms attack. Light-delay voice."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]               # A maj pentatonic, high register
    m = HIGH[int(rng.integers(0, len(HIGH)))]
    f = freq(m)
    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*6.0)      +  # quick body
        0.46 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*9.0)      +  # bright flick
        0.16 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*14.0)     +  # sparkle
        0.07 * np.sin(2*np.pi*f*4.1*t)    * np.exp(-t*26.0)        # tiny glint, gone fast
    )
    env = adsr(n, a=0.008, d=0.18, s_level=0.0, r=0.22)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8200.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- pan_bloom (bloom) ----
def voice_pan_bloom(arg):
    """Rolled-pan swell: sustained shimmering steel blooming warm — a lush
    tropical wash. A fundamental with a just major-third (5/4) and just fifth
    (3/2) halo, a soft octave, and a slow breathing chorus. A moving lowpass
    opens the brightness over the first few seconds so it 'blooms' open without
    any harsh top. Slow swell-in, long release. ~6.5s. arg = midi."""
    f = freq(int(arg))
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.3*t)
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.42 * np.sin(2*np.pi*f*1.0035*t) +
        0.42 * np.sin(2*np.pi*f*0.9967*t)
    )
    third  = 0.36 * np.sin(2*np.pi*f*(5/4)*t*vib)    # major third
    fifth  = 0.30 * np.sin(2*np.pi*f*(3/2)*t*vib)    # perfect fifth
    octave = 0.24 * np.sin(2*np.pi*f*2.0*t)          # soft octave halo (steel shimmer)
    sub    = 0.20 * np.sin(2*np.pi*f*0.5*t)          # warm body
    sig = fund + third + fifth + octave + sub
    low  = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.28 + 0.72 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.82), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 3200.0, order=3)          # warm ceiling, keeps shimmer but no fizz
    env = adsr(n, a=1.4, d=1.0, s_level=0.82, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- pan_roll (cluster) ----
def voice_pan_roll(arg):
    """Fast pan-roll tremolo on three notes — a shimmering steel cloud, sunny.
    From the root midi build a major-pentatonic chord (root, +4, +7), each note
    a struck pan voice modulated by a fast ~16 Hz tremolo (the roll) that fades
    so it reads as a sustained shimmer. Staggered swells so the cluster blooms
    open. Warm low-passed, additive only. ~6.5s. arg = root midi."""
    root = int(arg)
    intervals = [0, 4, 7, 12]                 # pentatonic-safe steel cloud
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partial = (np.sin(2*np.pi*f*t)
                   + 0.30*np.sin(2*np.pi*2*f*t) * np.exp(-t*1.0)   # steel shimmer
                   + 0.10*np.sin(2*np.pi*3*f*t) * np.exp(-t*2.5))
        detune = np.sin(2*np.pi*f*1.0035*t)
        # the "roll": fast tremolo that eases off so it becomes a smooth shimmer
        roll_rate = 16.0
        tremolo = 1.0 - (0.45 * np.exp(-t*0.7)) * (0.5 + 0.5*np.sin(2*np.pi*roll_rate*t + i*1.1))
        vib = 1 + 0.0022*np.sin(2*np.pi*0.24*t + i*0.9)
        voice = (0.82*partial + 0.34*detune) * vib * tremolo
        stagger = 0.16 * i
        env = adsr(n, a=1.2 + stagger, d=0.7, s_level=0.8, hold=1.4, r=2.6)
        gain = 1.0 - 0.09*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 3400.0, order=3)          # warm steel cloud, no harsh top
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- rim_tap (tap) ----
def voice_rim_tap(arg):
    """Muted pan-rim tap: a near-dry metallic click, the rhythmic pulse. A short
    tuned high-mid body (a couple of fast inharmonic partials ~ the rim ping)
    plus a soft filtered-noise contact transient. Very short, dry, rounded —
    >=2.5 ms soft attack so it's a tap, never a raw click. arg = midi (anchor)."""
    f = freq(int(arg))
    dur = 0.14
    n = int(dur * SR); t = t_axis(dur)
    # tuned rim body: fundamental + a stretched metallic partial, fast decay
    body = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*55) +
        0.45 * np.sin(2*np.pi*f*2.01*t)   * np.exp(-t*75) +
        0.18 * np.sin(2*np.pi*f*3.4*t)    * np.exp(-t*110)      # quick metallic glint
    )
    rng = np.random.default_rng(int(arg) * 13 + 5)
    noise = rng.standard_normal(n)
    contact = lowpass_fft(noise, 3600.0, order=3) - lowpass_fft(noise, 700.0, order=2)
    c_env = adsr(n, a=0.0025, d=0.020, s_level=0.0, r=0.0)
    contact = contact * c_env
    sig = body * 0.7 + contact * 0.4
    sig = lowpass_fft(sig, 5200.0, order=4)           # warm, roll off harsh top
    env = adsr(n, a=0.003, d=0.05, s_level=0.0, r=0.05)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- pan_chirp (chirp) ----
def voice_pan_chirp(seed):
    """Bright high pan flick — a beaming little island accent. A quick rising
    two-note pan blip in the HIGH pentatonic with a bright octave sheen and a
    tiny onset glint. Seed picks the start note and an upward leap so each chirp
    is a cheerful little lift. ~0.42s, additive, soft 10 ms attack, near-dry."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]           # A maj pentatonic, high
    leaps = [1, 2, 3]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.42
    n = int(dur * SR); t = t_axis(dur)
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)          # smoothstep glide
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR
    sig = (
        np.sin(phase) * np.exp(-t*3.0) +
        0.30 * np.sin(2*phase) * np.exp(-t*5.0) +       # bright pan octave sheen
        0.10 * np.sin(3*phase) * np.exp(-t*9.0) +       # sparkle color
        0.05 * np.sin(4.1*phase) * np.exp(-t*18.0)      # tiny onset glint
    )
    sig = lowpass_fft(sig, 8200.0, order=2)
    env = adsr(n, a=0.010, d=0.12, s_level=0.5, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.50
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "pan_boom": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.65,
        "reverb": {"wet": 0.1, "decay": 1.6, "predelay_ms": 12, "brightness": 0.32}
    },
    "pan_lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.18, 0.18, -0.1, 0.12, 0, -0.15, 0.15, -0.08, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.2, "decay": 1.8, "predelay_ms": 18, "brightness": 0.6}
    },
    "pan_ping": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.2, -0.2, 0.12, -0.12, 0.18, -0.15, 0.1, -0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.2, "decay": 1.7, "predelay_ms": 18, "brightness": 0.62}
    },
    "pan_double": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.12, 0.12, -0.08, 0.08, 0, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.18, "decay": 2.2, "predelay_ms": 22, "brightness": 0.5}
    },
    "pan_chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.62}
    },
    "sunflick": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.45, -0.4, 0.3, -0.3],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 1.8, "predelay_ms": 14, "brightness": 0.62}
    },
    "pan_bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 45, "brightness": 0.5}
    },
    "pan_roll": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.8, "predelay_ms": 42, "brightness": 0.5}
    },
    "rim_tap": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81],
        "pans": [-0.25, 0.2, -0.15, 0.25, 0],
        "target_peak": 0.82,
        "reverb": {"wet": 0.04, "decay": 0.5, "predelay_ms": 8, "brightness": 0.45}
    },
    "pan_chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.25],
        "target_peak": 0.8,
        "reverb": {"wet": 0.12, "decay": 1.5, "predelay_ms": 12, "brightness": 0.62}
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
    print("isleshine:", name)


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
