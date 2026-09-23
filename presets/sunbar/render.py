#!/usr/bin/env python3
"""
sunbar — sample renderer (per-voice reverb from preset.json).

Marimba and xylophone dancing in full sunshine: warm round rosewood bars
(marimba) and crisp bright bars (xylophone) tumbling over each other. A deep
bouncy marimba bass floor, a tumbling soft-mallet lead, a quick crisp counter
line, a creamy woody tone, fast bright xylophone pings and flicks, a warm
mallet-roll bloom, a shimmering wood-and-bar cluster, a near-dry woody tap, and
a bouncy bright accent. A major pentatonic @ A=432, additive only, pure daylight.

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


# A real marimba/xylophone bar has a strong inharmonic partial near 4x (the
# rectangular-bar mode). Marimba resonators reinforce the fundamental and the
# octave -> warm and round. Xylophone leaves the 3x/4x ringing -> bright snap.
# All additive sines with INDEPENDENT decay rates, low-passed warm. No FM.


# ---- bass (low marimba bar — deep round rosewood boom + warm resonator) ----
def voice_bass(arg):
    """A low marimba bar: deep round rosewood boom with a warm tuned resonator.
    Strong sine fundamental + a fat octave (the resonator reinforcing) + the
    characteristic marimba ~4x bar partial kept low and decaying fast so it
    reads as woody attack, not a ring. A soft felt-mallet thud at the strike.
    Bouncy ground floor — short-ish round decay, near-dry. arg = midi (LOW)."""
    f = freq(int(arg))
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.2)  +   # round fundamental boom
        0.55 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*3.2)  +   # resonator octave (warm body)
        0.16 * np.sin(2*np.pi*f*3.98*t)   * np.exp(-t*14.0) +   # marimba bar partial -> woody tick
        0.08 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*1.8)      # slow detune = wood life
    )
    # subtle bounce: a gentle amplitude breathe so the floor feels alive
    sig = sig * (1.0 + 0.05 * np.sin(2*np.pi*3.0*t - np.pi/2))

    # soft felt-mallet thud at the strike: low-passed noise puff, very short
    rng = np.random.default_rng(int(arg) * 17 + 3)
    puff = rng.standard_normal(n)
    puff = lowpass_fft(puff, 320.0, order=3)
    sig = sig + 0.16 * puff * np.exp(-t * 30.0)

    # keep it round and warm — bass is felt, not heard up top
    sig = lowpass_fft(sig, 1100.0, order=4)

    env = adsr(n, a=0.006, d=0.7, s_level=0.0, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead (mid marimba bar — warm soft-mallet strike, tumbling the melody) ----
def voice_lead(midi):
    """A mid marimba bar: warm soft-mallet strike with the rounded marimba 4x
    bar partial that decays fast (woody, not metallic). Strong fundamental + a
    sweet octave + the bar partial + a soft body detune for bloom. This is the
    voice that tumbles the tune — bouncy, warm, ~1.6s. Additive only."""
    f = freq(int(midi))
    dur = 1.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)                            +   # warm fundamental
        0.42 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*4.0)    +   # round octave, fades
        0.20 * np.sin(2*np.pi*f*3.98*t)   * np.exp(-t*16.0)   +   # marimba bar partial -> mallet tick
        0.06 * np.sin(2*np.pi*f*9.2*t)    * np.exp(-t*55.0)   +   # tiny high glint, gone in ~18ms
        0.14 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*2.2)        # soft body bloom
    )
    # soft mallet attack (~7ms), round decay
    env = adsr(n, a=0.007, d=1.0, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6000.0, order=2)   # keep it warm rosewood
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (bright xylophone bar — crisp hard-mallet snap, quick counter-line) ----
def voice_lead2(midi):
    """A bright xylophone bar: crisp hard-mallet snap. The xylophone leaves its
    upper bar partials ringing a touch longer (3x, 4x) and decays FAST overall
    -> bright, dry, snappy. Fundamental + a present octave + the bright bar
    partials + a quick noise 'snap' transient at the hard-mallet strike. Dances
    a quick counter-line above the marimba. ~0.9s. Additive only."""
    f = freq(int(midi))
    dur = 0.9
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*5.0)   +   # crisp fundamental
        0.50 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*7.0)   +   # bright octave
        0.30 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*10.0)  +   # xylo bar color (bright)
        0.18 * np.sin(2*np.pi*f*3.98*t)   * np.exp(-t*13.0)  +   # bar partial snap
        0.05 * np.sin(2*np.pi*f*9.4*t)    * np.exp(-t*60.0)      # tiny glint at onset
    )
    # hard-mallet snap: short band of noise at the strike (warm, no screech)
    rng = np.random.default_rng(int(midi) * 53 + 11)
    snap = rng.standard_normal(n)
    snap = lowpass_fft(snap, 4200.0, order=3) - lowpass_fft(snap, 900.0, order=2)
    sig = sig + 0.10 * snap * np.exp(-t * 200.0)
    # crisp but click-free: ~5ms attack, fast bright decay
    env = adsr(n, a=0.005, d=0.55, s_level=0.0, r=0.25)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8000.0, order=2)   # bright but not glassy
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (soft-mallet marimba bar — dark creamy sweet woody middle) ----
def voice_tone(midi):
    """A soft-mallet marimba bar: dark and creamy, the sweet woody middle. Very
    soft mallet -> the bright bar partials are barely struck, so it's almost a
    pure warm sustained sine with a gentle octave and the faintest bar color.
    A whisper of vibrato opens after the attack so it sings. ~2.2s. Additive."""
    f = freq(int(midi))
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)
    # vibrato fades in after the note speaks (singing, not warbly)
    vib_depth = 0.0022 * np.clip((t - 0.35) / 0.6, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*4.6*t)
    phase = 2*np.pi*f*np.cumsum(vib)/SR
    sig = (
        1.00 * np.sin(phase)                              +   # creamy fundamental
        0.24 * np.sin(2*phase) * np.exp(-t*2.8)           +   # soft octave, fades early
        0.07 * np.sin(2*np.pi*f*3.98*t) * np.exp(-t*22.0) +   # faint bar tick, gone fast
        0.10 * np.sin(2*np.pi*f*1.004*t)                      # whisper detune for body
    )
    sig = lowpass_fft(sig, 3400.0, order=3)   # dark, creamy roll-off
    env = adsr(n, a=0.018, d=0.7, s_level=0.5, r=1.1)
    out = sig[:env.size] * env[:sig.size] * 0.46
    return out


# ---- chime (high xylophone ping — bright crisp glint, decays fast) ----
def voice_chime(midi):
    """A high xylophone ping: bright crisp glint that decays fast, medium
    reverb (baked from preset). A clean high fundamental + a sparkling octave +
    a quick bright bar partial that dies fast, plus a tiny glassy glint at the
    onset. Sweet, never piercing. ~1.4s. Additive, nothing harsh sustained."""
    f = freq(int(midi))
    dur = 1.4
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*3.4)   +   # bright body
        0.45 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*5.0)   +   # sparkling octave
        0.16 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*8.5)   +   # crisp glint
        0.06 * np.sin(2*np.pi*f*3.98*t)   * np.exp(-t*20.0)      # bar partial, gone fast
    )
    # faint chorus shimmer for a glowing ping
    sig += 0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*3.0)
    env = adsr(n, a=0.006, d=1.0, s_level=0.0, r=0.35)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8500.0, order=3)   # bright but rounded
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (tiny top xylophone flicks — scattering bright, light delay) ----
def voice_sparkle(seed):
    """Tiny top xylophone flicks scattering bright. From the HIGH pentatonic,
    each flick is a very short, bright two-partial ping (fundamental + octave)
    with a quick glassy onset glint. Very short decay so they scatter like
    sun-flecks; light delay echoes added live by event.py. ~0.5s. Additive."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]              # A maj pentatonic, top register
    m = HIGH[int(rng.integers(0, len(HIGH)))]
    f = freq(m) * (1.0 + rng.uniform(-0.004, 0.004))   # tiny per-flick wobble
    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*9.0)   +   # bright flick
        0.35 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*13.0)  +   # octave sparkle
        0.10 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*18.0)      # quick glint
    )
    env = adsr(n, a=0.005, d=0.30, s_level=0.0, r=0.14)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 9000.0, order=3)   # bright, no screech
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (marimba mallet-roll swell — sustained warm wood, lush wash) ----
def voice_bloom(midi):
    """A marimba mallet-roll swell: sustained warm wood blooming, lush room
    wash (baked reverb). A roll on a bar sustains the tone via rapid soft
    strikes -> modeled as a warm sustained body with a gentle amplitude tremolo
    (the roll) that swells open. Fundamental + just-octave + a soft consonant
    fifth + a low sub for body. All warm low-passed -> round, never glassy. ~6s."""
    f = freq(int(midi))
    dur = 6.0
    n = int(dur * SR); t = t_axis(dur)

    # the mallet-roll: a gentle, slightly irregular amplitude tremolo ~11 Hz
    roll = 0.85 + 0.15 * (0.5 + 0.5*np.sin(2*np.pi*11.0*t))
    # slow breathing vibrato underneath
    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.3*t)

    sig = (
        np.sin(2*np.pi*f*t*vib) +
        0.40 * np.sin(2*np.pi*f*2.0*t) +              # warm octave
        0.26 * np.sin(2*np.pi*f*(3/2)*t*vib) +        # consonant fifth
        0.28 * np.sin(2*np.pi*f*0.5*t) +              # sub for body
        0.40 * np.sin(2*np.pi*f*1.0035*t) +           # chorus shimmer
        0.40 * np.sin(2*np.pi*f*0.9967*t)
    )
    sig = sig * roll

    # bloom open: brightness opens over the first seconds then settles
    low  = lowpass_fft(sig, 650.0, order=3)
    high = sig - low
    open_curve = 0.30 + 0.70 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.8), 1.0)))
    sig = low + high * open_curve

    sig = lowpass_fft(sig, 2700.0, order=3)   # warm wood ceiling, round

    env = adsr(n, a=1.2, d=1.0, s_level=0.82, hold=1.0, r=2.6)
    out = sig[:env.size] * env[:sig.size]
    pk = float(np.max(np.abs(out)))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- cluster (fast mallet-roll on three bars — shimmering wood-and-bar cloud) ----
def voice_cluster(arg):
    """A fast mallet-roll on three bars: a shimmering wood-and-bar cloud that
    tumbles and swells for a SessionStart welcome. From the root we build a
    major-pentatonic-safe triad-ish cloud: root, +4, +7, +9, +12. Each bar is a
    warm marimba body with a gentle roll tremolo (phased differently per bar)
    so the cloud shimmers and tumbles. Staggered swells -> blooms open. Warm
    low-passed, round and sunny."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.4
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        body = (np.sin(2*np.pi*f*t)
                + 0.30*np.sin(2*np.pi*2*f*t)
                + 0.10*np.sin(2*np.pi*(3/2)*f*t))     # consonant fifth color
        detune = np.sin(2*np.pi*f*1.0035*t)
        # per-bar roll tremolo, phased differently -> tumbling shimmer
        roll = 0.80 + 0.20 * (0.5 + 0.5*np.sin(2*np.pi*(10.0 + i*0.7)*t + i*1.1))
        vib = 1 + 0.0020*np.sin(2*np.pi*0.24*t + i*0.8)
        voice = (0.85*body + 0.30*detune) * vib * roll
        stagger = 0.16 * i
        env = adsr(n, a=1.4 + stagger, d=0.6, s_level=0.80, hold=1.4, r=2.4)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 2800.0, order=3)   # warm wood-and-bar, no harsh top
    peak = float(np.max(np.abs(sig))) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- tap (muted bar-tap — near-dry woody click, the rhythmic sunshine pulse) ----
def voice_tap(arg):
    """A muted bar-tap: a near-dry woody click, the rhythmic sunshine pulse. A
    mallet on a damped bar -> a very short tuned woody pip (fundamental + a
    quick bar partial) plus a soft filtered-noise contact transient. Bright-ish
    but rounded and short. >=2ms soft attack, no raw edge. ~0.16s. arg = midi."""
    f = freq(int(arg))
    dur = 0.16
    n = int(dur * SR); t = t_axis(dur)
    # muted pitched pip: fast decay so it reads as a tap, not a tone
    pip = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*40.0) +
        0.30 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*60.0) +
        0.16 * np.sin(2*np.pi*f*3.98*t)   * np.exp(-t*90.0)     # woody bar tick
    )
    # soft contact transient: short band of warm noise
    rng = np.random.default_rng(int(arg) * 31 + 7)
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 2600.0, order=3)
    tr_env = adsr(n, a=0.0025, d=0.025, s_level=0.0, r=0.0)
    transient = noise * tr_env * 0.40

    out = pip + transient
    out = lowpass_fft(out, 4200.0, order=4)   # warm, woody, no glassy top
    # overall soft shaping (>=2ms attack)
    soft = adsr(n, a=0.0025, d=0.04, s_level=0.0, r=0.04)
    out = out[:soft.size] * soft[:out.size]
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chirp (bright high xylophone flick — a bouncy little sunshine accent) ----
def voice_chirp(seed):
    """A bright high xylophone flick: a bouncy little sunshine accent. A quick
    rising two-note blip in the HIGH pentatonic — a xylophone bar tapped and
    lifted. Pure sines + tiny octave sheen, near-dry, ~0.4s. Each seed picks a
    starting note and a small upward pentatonic leap so each accent is a
    cheerful little rising bounce. Additive only, bright but never piercing."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]          # A maj pentatonic, high
    leaps = [1, 2, 3]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i])
    f1 = freq(HIGH[end_i])

    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)
    # smooth rising glide over the first ~55%, then hold -> a bouncy lift
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.20 * np.sin(2*phase) * np.exp(-t*4.0) +   # bright octave sheen
        0.06 * np.sin(3*phase) * np.exp(-t*16.0)    # tiny chiff at onset
    )
    sig = lowpass_fft(sig, 8500.0, order=3)   # bright, warm, not piercing
    env = adsr(n, a=0.008, d=0.12, s_level=0.5, r=0.20)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.08, "decay": 1.4, "predelay_ms": 12, "brightness": 0.32},
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [-0.18, 0.18, -0.1, 0.14, 0, -0.2, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.2, "decay": 1.6, "predelay_ms": 18, "brightness": 0.55},
    },
    "lead2": {
        "kind": "midi",
        "midis": [61, 64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.25, -0.2, 0.3, -0.25, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.18, "decay": 1.3, "predelay_ms": 16, "brightness": 0.6},
    },
    "tone": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.15, 0.15],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 2.2, "predelay_ms": 22, "brightness": 0.48},
    },
    "chime": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.4, -0.3, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.62},
    },
    "sparkle": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.2, -0.15],
        "target_peak": 0.78,
        "reverb": {"wet": 0.3, "decay": 2.4, "predelay_ms": 18, "brightness": 0.62},
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 45, "brightness": 0.45},
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.8, "predelay_ms": 42, "brightness": 0.46},
    },
    "tap": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [-0.22, 0.2, -0.1, 0.15, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.04, "decay": 0.5, "predelay_ms": 8, "brightness": 0.42},
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.3, -0.3, 0.4, -0.35],
        "target_peak": 0.8,
        "reverb": {"wet": 0.12, "decay": 1.4, "predelay_ms": 12, "brightness": 0.6},
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
    print("sunbar:", name)


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
