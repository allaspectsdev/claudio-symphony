#!/usr/bin/env python3
"""
chapelbright — sample renderer (per-voice reverb from preset.json).

Tubular bells ringing chapel-bright at high noon, chiming clear with no shadow.
Bell-forward tubular chimes, struck and bright with clean harmonic partials and
long shining tails, deliberately NO drone; chapel-bright and bell-led, clear and
joyous, all light. A major @ A=432, additive only, never dreary.

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


# Tubular-bell partial set: a real chime's most musical partials, gently tuned
# toward harmonic so it reads as a clear major bell (no minor/clashing strike
# tone). Each partial gets its OWN decay; high partials die fast so the tail is
# pure and warm, never buzzy. All <= ~4x amplitude-significant.
# (ratio, amp, decay_rate)
_TUBE = [
    (1.000, 1.00, 0.9),   # warm fundamental — the shining ground tone
    (2.005, 0.55, 1.4),   # bright struck octave-ish partial (the "ping")
    (3.01,  0.22, 2.6),   # sweet upper color, fades early
    (4.02,  0.10, 4.5),   # fast glint at the strike, gone quick
]


# ---- bell_ground (bass) ----
def voice_bell_ground(midi):
    """A low tubular chime struck soft — warm round bell-fundamental with a long
    shining tail. The bell-ground: single strikes, never continuous. Additive:
    a dominant fundamental, a soft octave-ish partial, and a kiss of upper color
    that fades fast so the long tail stays round and warm. Soft mallet attack,
    no click. A-major LOW."""
    f = freq(midi); dur = 5.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*0.55) +   # round shining ground
        0.40 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*1.0)  +   # soft struck octave
        0.12 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*2.4)  +   # gentle upper color
        0.05 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*0.5)      # tiny detune bloom
    )
    # soft round mallet attack, long shining tail
    env = adsr(n, a=0.010, d=2.4, s_level=0.0, r=2.6)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 2400.0, order=4)   # keep it round and warm, no top fizz
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- chime_lead (lead) ----
def voice_chime_lead(midi):
    """A mid tubular bell — clear mallet-strike plus 2.005x and a fast 4x partial,
    chiming the bright melody forward. The lead voice: a strong shining
    fundamental, a bright struck octave-ish partial, a quick sweet 3x, and a fast
    4x glint that lives only at the strike. Additive, no FM. Soft attack, bright
    singing tail. ~3s."""
    f = freq(midi); dur = 3.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.1)  +   # shining fundamental
        0.52 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*1.7)  +   # bright struck partial
        0.20 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*3.2)  +   # sweet upper color
        0.09 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*8.0)      # fast glint at strike
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.0)    # whisper detune for body
    env = adsr(n, a=0.008, d=1.6, s_level=0.0, r=1.1)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=3)   # sweet, no harsh top
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- chime_descant (lead2) ----
def voice_chime_descant(midi):
    """A higher chime — brighter and with a quicker tail, ringing the descant
    above the lead. Same tubular family, shifted bright: a clear fundamental, a
    bright 2.005x, a quick 3x, and a tiny fast 4x sparkle. Shorter shining tail
    so it stays light and quick on top. ~2.2s. Additive only."""
    f = freq(midi); dur = 2.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.6)  +
        0.50 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*2.4)  +
        0.18 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*4.0)  +
        0.07 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*9.0)
    )
    env = adsr(n, a=0.006, d=1.1, s_level=0.0, r=0.8)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chime_sweet (tone) ----
def voice_chime_sweet(midi):
    """A warm mid chime struck soft — rounder partials, the sweet ringing middle.
    Softer mallet, the upper partials kept quieter and decaying earlier so it
    reads as the rounded, mellow heart of the bell family. A glowing fundamental,
    a gentle octave partial, a faint 3x. Slightly slower attack. ~2.8s."""
    f = freq(midi); dur = 2.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.0)  +   # glowing round body
        0.36 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*2.0)  +   # soft octave, mellow
        0.12 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*4.5)      # faint sweetener
    )
    sig += 0.12 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.0)    # warm detune body
    env = adsr(n, a=0.014, d=1.5, s_level=0.0, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4600.0, order=3)   # rounder, mellow top
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tube_ping (chime) ----
def voice_tube_ping(midi):
    """A high small-tube ping with bright shimmer. A short bright bell ping: a
    clear fundamental, a bright struck partial, and a quick high glint, with a
    faint chorus shimmer for the 'small glass tube' glow. Medium-full reverb.
    ~1.8s shining tail. Additive only, no partials past ~4x ringing long."""
    f = freq(midi); dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.0)  +
        0.46 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*3.0)  +
        0.16 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*5.0)  +
        0.06 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*10.0)
    )
    # bright shimmer: two faint near-unisons
    sig += 0.12 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*2.2)
    sig += 0.10 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*2.2)
    env = adsr(n, a=0.006, d=0.9, s_level=0.0, r=0.7)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7800.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- topflick (sparkle) ----
def voice_topflick(seed):
    """Tiny top-tube flicks ringing bright, scattered with delay echoes. A short
    high bell flick on a random HIGH A-major note: a clear fundamental + bright
    partial + a tiny fast glint, quick shining decay. Additive sines only. Soft
    attack (no click), near-bright top tamed so it sparkles without screech.
    ~0.7s — the live delay scatters the echoes."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    HIGH = [69, 73, 76, 78, 81, 85, 88]
    m = int(HIGH[rng.integers(0, len(HIGH))])
    f = freq(m)
    dur = 0.7
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*4.5)  +
        0.42 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*6.0)  +
        0.10 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*9.0)  +
        0.05 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*14.0)
    )
    sig += 0.08 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*5.0)
    env = adsr(n, a=0.005, d=0.35, s_level=0.0, r=0.30)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- chapel_bloom (bloom) ----
def voice_chapel_bloom(midi):
    """A swell of overlapping chime-tails shining together — a lush blooming
    chapel wash. Several tuned bell partials (root + just major third + fifth +
    octave) each as a soft sine, with a slow chorus shimmer and a lowpass that
    OPENS over the swell so it brightens like sun filling a nave. No strike,
    no drone — a long blooming ring of overlapping tails. ~6.5s. Additive only."""
    f = freq(midi); dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    # slow breathing shimmer
    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.3*t)
    # consonant bell-tail stack (just intonation, sweet major, A-safe)
    sig = (
        1.00 * np.sin(2*np.pi*f*t*vib) +
        0.42 * np.sin(2*np.pi*f*(5/4)*t*vib) +   # major third
        0.36 * np.sin(2*np.pi*f*(3/2)*t*vib) +   # perfect fifth
        0.26 * np.sin(2*np.pi*f*2.0*t)           # octave halo
    )
    # warm chorus twins on the fundamental
    sig += 0.30 * np.sin(2*np.pi*f*1.0035*t)
    sig += 0.30 * np.sin(2*np.pi*f*0.9967*t)
    # bloom: brightness opens then settles
    low  = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.30 + 0.70 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 4200.0, order=3)   # bright but never harsh
    env = adsr(n, a=1.3, d=1.0, s_level=0.80, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    pk = float(np.max(np.abs(out)))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- chime_cloud (cluster) ----
def voice_chime_cloud(arg):
    """A cascade of struck tubes — a shimmering interlocked chime cloud, joyous.
    From the passed root we build a bright major chime chord (root, +4 maj3,
    +7 fifth, +9 maj6, +12 octave). Each note is a soft tubular sine stack with
    its own staggered strike so they cascade open like a peal of bells, glowing
    and interlocked. Warm-bright, low-passed, no harsh edge. ~7s."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        # tubular bell sine stack
        partial = (np.sin(2*np.pi*f*t)
                   + 0.40*np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.4)
                   + 0.14*np.sin(2*np.pi*f*3.01*t)  * np.exp(-t*2.8))
        detune = np.sin(2*np.pi*f*1.0035*t)
        vib = 1 + 0.0020*np.sin(2*np.pi*0.26*t + i*0.8)
        voice = (0.85*partial + 0.30*detune) * vib
        # staggered strike: each tube rings in a touch later -> cascading peal
        stagger = 0.22 * i
        env = adsr(n, a=0.012 + stagger, d=2.0, s_level=0.55,
                   hold=0.8, r=2.4)
        gain = 1.0 - 0.09*i      # upper tubes a touch quieter
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 4200.0, order=3)   # joyous bright, no harsh top
    peak = float(np.max(np.abs(sig))) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- chime_tap (tap) ----
def voice_chime_tap(midi):
    """A damped chime mallet-tap — a near-dry click, the rhythmic pulse. A very
    short struck tube that is immediately damped: a quick pitched body (a couple
    of fast-decaying tubular partials) plus a tiny soft mallet-contact noise, all
    rolled off warm. Soft >=2.5ms attack so there is no raw edge. ~0.22s, dry."""
    f = freq(midi); dur = 0.22
    n = int(dur * SR); t = t_axis(dur)
    body = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*30) +
        0.40 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*42) +
        0.14 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*60)
    )
    # soft felt mallet contact (damped, warm)
    rng = np.random.default_rng(int(midi) * 13 + 5)
    noise = rng.standard_normal(n)
    tap = lowpass_fft(noise, 2600.0, order=3)
    t_env = adsr(n, a=0.0025, d=0.020, s_level=0.0, r=0.0)
    tap = tap * t_env
    sig = body + 0.20 * tap
    env = adsr(n, a=0.003, d=0.08, s_level=0.0, r=0.06)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4200.0, order=4)
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- treble_flick (chirp) ----
def voice_treble_flick(seed):
    """A bright tiny treble-tube flick — a clear little chapel accent. A single
    very short, very bright bell ping on a high A-major note: clean fundamental,
    a bright struck partial, and a tiny glint, ringing for just a moment. Soft
    attack, warm-tamed top so it's clear and friendly, never piercing. ~0.45s,
    near-dry."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    TOP = [76, 78, 81, 85, 88]
    m = int(TOP[rng.integers(0, len(TOP))])
    f = freq(m)
    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*7.0)  +
        0.40 * np.sin(2*np.pi*f*2.005*t)  * np.exp(-t*9.0)  +
        0.10 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*14.0) +
        0.04 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*20.0)
    )
    env = adsr(n, a=0.006, d=0.20, s_level=0.0, r=0.18)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8800.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


PLAN = {
    "bell_ground": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.62,
        "reverb": {"wet": 0.30, "decay": 3.2, "predelay_ms": 22, "brightness": 0.4}
    },
    "chime_lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 62, 64, 66, 68, 69, 71, 73, 76],
        "pans": [-0.18, 0.18, -0.1, 0.12, 0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 3.4, "predelay_ms": 26, "brightness": 0.58}
    },
    "chime_descant": {
        "kind": "midi",
        "midis": [69, 71, 73, 74, 76, 78, 80, 81],
        "pans": [-0.3, 0.25, -0.15, 0.3, -0.2, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.38, "decay": 3.2, "predelay_ms": 28, "brightness": 0.62}
    },
    "chime_sweet": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 3.0, "predelay_ms": 24, "brightness": 0.5}
    },
    "tube_ping": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.4, 0.3, -0.2, 0.4, -0.3, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.40, "decay": 3.0, "predelay_ms": 26, "brightness": 0.62}
    },
    "topflick": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.45, -0.4, 0.3, -0.3],
        "target_peak": 0.78,
        "reverb": {"wet": 0.32, "decay": 2.4, "predelay_ms": 18, "brightness": 0.62}
    },
    "chapel_bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.5, "predelay_ms": 45, "brightness": 0.5}
    },
    "chime_cloud": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.50, "decay": 5.0, "predelay_ms": 42, "brightness": 0.52}
    },
    "chime_tap": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.6,
        "reverb": {"wet": 0.06, "decay": 0.6, "predelay_ms": 8, "brightness": 0.4}
    },
    "treble_flick": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.25],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 1.8, "predelay_ms": 14, "brightness": 0.62}
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
    print("chapelbright:", name)


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
