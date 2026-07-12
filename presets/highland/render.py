#!/usr/bin/env python3
"""
highland — sample renderer (per-voice reverb from preset.json).

A pan flute breathing across a sunlit mountain meadow: round hollow breathy
pipe tones with soft air-noise and gentle overblow. Highland/Andean calm —
open, airy, peaceful but bright and uplifted, never lonely, never dreary.
A major pentatonic @ A=432, additive only, hall reverb.

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


def _breath(n, t, cutoff_lo, cutoff_hi, seed):
    """A soft band of air-noise — the breath that lives inside every pipe.
    Band-limited (rolled off top, lows removed) so it's airy, never hissy."""
    rng = np.random.default_rng(seed)
    nz = rng.standard_normal(n)
    nz = lowpass_fft(nz, cutoff_hi, order=3)
    nz = nz - lowpass_fft(nz, cutoff_lo, order=2)
    return nz


# ---- pipe_ground (bass) ----
def voice_pipe_ground(arg):
    """A low breathy bamboo tone — soft round fundamental with an airy body,
    the gentle ground of the meadow. Mostly fundamental + a soft octave and a
    quiet third partial (hollow pipe color), wrapped in a slow breath swell and
    a low cushion of air-noise that fades after the attack. Round, warm, never
    dark. arg = midi (LOW)."""
    f = freq(int(arg))
    dur = 3.0
    n = int(dur * SR); t = t_axis(dur)

    # very slow breathe so the floor feels alive (a calm exhale)
    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.30*t)
    phase = 2*np.pi*f*np.cumsum(vib)/SR

    body = (
        1.00 * np.sin(phase) +
        0.30 * np.sin(2*phase) * np.exp(-t*1.2) +     # soft octave, fades early
        0.10 * np.sin(3*phase) * np.exp(-t*2.6) +     # quiet hollow color
        0.06 * np.sin(2*np.pi*f*1.004*t)              # whisper detune = bamboo life
    )

    # airy breath cushion, low and warm, strongest at the attack
    air = _breath(n, t, 120.0, 900.0, int(arg)*13+1)
    air_env = 0.10 + 0.18*np.exp(-t*3.0)
    body = body + 0.16 * air * air_env

    body = lowpass_fft(body, 1400.0, order=4)         # keep it round, bamboo-soft

    env = adsr(n, a=0.030, d=0.6, s_level=0.6, hold=0.6, r=1.3)
    out = body[:env.size] * env[:body.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


def _panpipe(f, dur, n, t, seed, breath_amt=0.20, overblow=0.05, attack=0.020):
    """Shared pan-flute pipe core: hollow harmonic stack (fundamental strong,
    a soft octave, a quiet 3x, a faint 4x that decays fast) with a breath-attack
    chiff swelling in, plus a gentle vibrato that opens after the note speaks."""
    # vibrato fades in after the breath-attack settles -> singing, not warbly
    vib_depth = 0.004 * np.clip((t - 0.18) / 0.5, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.2*t)
    phase = 2*np.pi*f*np.cumsum(vib)/SR

    sig = (
        1.00 * np.sin(phase) +
        0.28 * np.sin(2*phase) * np.exp(-t*1.4) +     # soft octave
        0.12 * np.sin(3*phase) * np.exp(-t*2.4) +     # hollow pipe color
        0.05 * np.sin(4*phase) * np.exp(-t*4.5)       # faint top, gone fast
    )
    # gentle overblow: a quiet octave-up that blooms a touch then settles
    if overblow > 0:
        ob_env = np.clip((t-0.05)/0.4, 0, 1) * np.exp(-np.maximum(t-0.6, 0)*1.2)
        sig += overblow * np.sin(2*phase) * ob_env

    # breath-attack chiff: a puff of air at the onset (the swell-in)
    air = _breath(n, t, 200.0, 4200.0, seed)
    chiff_env = np.exp(-t*16.0) * np.clip(t/0.012, 0, 1)   # quick airy onset
    body_air = 0.5 + 0.5*np.exp(-t*6.0)                    # air thins as tone speaks
    sig += air * (0.9*chiff_env + breath_amt*0.5*body_air) * breath_amt

    return sig


# ---- pan_lead (lead) ----
def voice_pan_lead(midi):
    """The highland melody pipe — a pan-flute with a breath-attack swelling in
    over ~20ms, hollow and pure with soft overblow. Carries the tune, bright and
    calm. arg = midi."""
    f = freq(int(midi)); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = _panpipe(f, dur, n, t, int(midi)*7+11,
                   breath_amt=0.22, overblow=0.06, attack=0.020)
    sig = lowpass_fft(sig, 5200.0, order=3)            # warm, no piercing top
    env = adsr(n, a=0.020, d=0.5, s_level=0.55, hold=0.2, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- whistle_pipe (lead2) ----
def voice_whistle_pipe(midi):
    """A higher whistle-pipe, brighter and breezier, echoing across the valley.
    Same pipe family as the lead but airier and a touch quicker, sitting an
    octave up in feel. arg = midi (higher register)."""
    f = freq(int(midi)); dur = 1.7
    n = int(dur * SR); t = t_axis(dur)
    sig = _panpipe(f, dur, n, t, int(midi)*5+29,
                   breath_amt=0.28, overblow=0.05, attack=0.015)
    sig = lowpass_fft(sig, 6200.0, order=3)            # brighter than lead, still warm
    env = adsr(n, a=0.016, d=0.45, s_level=0.5, hold=0.15, r=0.8)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- low_pipe (tone) ----
def voice_low_pipe(midi):
    """A warm low-pipe tone — round and woody-hollow, the sweet airy middle.
    A singing sustained pipe with a softer breath and rounder top than the lead;
    the cushion the melody rests on. arg = midi."""
    f = freq(int(midi)); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    sig = _panpipe(f, dur, n, t, int(midi)*9+3,
                   breath_amt=0.16, overblow=0.04, attack=0.024)
    # a touch of extra warmth: a soft sub-fifth-free body detune
    sig += 0.10 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.0)
    sig = lowpass_fft(sig, 3800.0, order=3)            # rounder, woodier
    env = adsr(n, a=0.024, d=0.7, s_level=0.58, hold=0.3, r=1.1)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- pipe_ping (chime) ----
def voice_pipe_ping(midi):
    """A high pipe-harmonic ping — flute-pure with soft air, medium reverb like
    a distant call across the valley. A short breathy pipe blip: a clean
    fundamental + soft octave, a quick airy chiff, fading like a far-off whistle.
    arg = midi (high)."""
    f = freq(int(midi)); dur = 1.4
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t) * np.exp(-t*2.2) +
        0.30 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*3.4) +   # soft octave
        0.10 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*5.0)     # faint hollow glint
    )
    # airy chiff at the onset — the breath of a distant call
    air = _breath(n, t, 400.0, 5500.0, int(midi)*17+5)
    sig += 0.20 * air * np.exp(-t*22.0) * np.clip(t/0.010, 0, 1)
    sig = lowpass_fft(sig, 6500.0, order=3)
    env = adsr(n, a=0.014, d=0.6, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- breath_flick (sparkle) ----
def voice_breath_flick(seed):
    """Tiny top-octave breath-flicks — airy glints with light delay echoes
    drifting on the wind. A quick rising whistle-tick from the HIGH pentatonic,
    mostly breath with a thread of pure pipe pitch. Short, bright, friendly.
    Additive, near the top of the register."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]
    f = freq(int(HIGH[int(rng.integers(0, len(HIGH)))]))
    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)

    # tiny upward whistle lift
    rise = np.clip(t/(dur*0.4), 0, 1)
    rise = rise*rise*(3-2*rise)
    f_t = f * (2 ** ((-0.6*(1-rise)) / 12.0))
    phase = 2*np.pi*np.cumsum(f_t)/SR

    tone = np.sin(phase) + 0.16*np.sin(2*phase)
    air = _breath(n, t, 800.0, 7000.0, int(seed)*3+7)
    air_env = np.exp(-t*9.0) * np.clip(t/0.008, 0, 1)

    sig = 0.55*tone*np.exp(-t*5.0) + 0.55*air*air_env
    sig = lowpass_fft(sig, 7500.0, order=3)
    env = adsr(n, a=0.010, d=0.12, s_level=0.35, r=0.30)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.46 / peak)
    return out


# ---- breath_bloom (bloom) ----
def voice_breath_bloom(midi):
    """A soft breath-pad swell — layered airy pipes blooming open, a lush
    meadow wash. A clean fundamental with consonant just-major third & fifth and
    a soft octave halo, two faint detunes for a breathing chorus, wrapped in a
    bed of slow air that opens with the swell. Round, never glassy. ~6.5s.
    arg = midi."""
    f = freq(int(midi)); dur = 6.5
    n = int(dur * SR); t = t_axis(dur)

    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.26*t)
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.42*np.sin(2*np.pi*f*1.0035*t) +
        0.42*np.sin(2*np.pi*f*0.9967*t)
    )
    third  = 0.34 * np.sin(2*np.pi*f*(5/4)*t*vib)
    fifth  = 0.30 * np.sin(2*np.pi*f*(3/2)*t*vib)
    octave = 0.20 * np.sin(2*np.pi*f*2.0*t)
    sig = fund + third + fifth + octave

    # breath bed: a wide band of air that swells in with the pad
    air = _breath(n, t, 200.0, 4500.0, int(midi)*11+13)
    air_swell = np.clip(t/2.0, 0, 1) * (0.6 + 0.4*np.exp(-np.maximum(t-3.5,0)*0.6))
    sig += 0.22 * air * air_swell

    # bloom: brightness opens over the first seconds via a moving lowpass blend
    low  = lowpass_fft(sig, 700.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75*(0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85),1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 3000.0, order=3)

    env = adsr(n, a=1.5, d=1.0, s_level=0.82, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    pk = float(np.max(np.abs(out)))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- pipe_cluster (cluster) ----
def voice_pipe_cluster(arg):
    """A breathy chord of three pipes — a shimmering airy cloud, open and bright.
    From the passed root we build a major-pentatonic chord: root, +4, +7, +9, +12.
    Each note is a soft pipe with a faint breath, gentle detune, slow breathing
    vibrato and staggered swells so the chord blooms open like an inhale on the
    wind. Warm low-passed, no harsh edge. arg = root midi."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.8
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partial = (np.sin(2*np.pi*f*t)
                   + 0.22*np.sin(2*np.pi*2*f*t)*np.exp(-t*1.4)
                   + 0.08*np.sin(2*np.pi*3*f*t)*np.exp(-t*2.6))
        detune = np.sin(2*np.pi*f*1.0035*t)
        vib = 1 + 0.0022*np.sin(2*np.pi*0.24*t + i*0.8)
        voice = (0.85*partial + 0.30*detune) * vib
        stagger = 0.16 * i
        env = adsr(n, a=1.5 + stagger, d=0.7, s_level=0.80, hold=1.2, r=2.4)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)

    # a soft airy cloud over the whole chord
    air = _breath(n, t, 250.0, 4000.0, root*7+19)
    air_swell = np.clip(t/2.2, 0, 1) * 0.8
    sig += 0.16 * air * air_swell

    sig = lowpass_fft(sig, 3000.0, order=3)
    peak = float(np.max(np.abs(sig))) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- wind_breath (texture) ----
def voice_wind_breath(seed):
    """A gentle wind-breath texture — near-dry soft air, the mountain breeze
    itself. A slow swell of band-limited air-noise with a barely-there breathy
    pitch shimmer, rising and falling like a calm gust. Soft, warm, quiet."""
    rng = np.random.default_rng(int(seed))
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    air = _breath(n, t, 180.0, 2600.0, int(seed)*3+1)
    # slow gust swell: rise then fall, smooth (no edges)
    gust = 0.5 - 0.5*np.cos(2*np.pi*np.clip(t/dur, 0, 1))
    gust = gust ** 1.2

    # a barely-there breathy pitch — a soft pipe ghost hidden in the wind
    f = freq(57)
    ghost = (np.sin(2*np.pi*f*t) + 0.4*np.sin(2*np.pi*f*1.5*t)) * 0.06
    ghost *= (0.5 - 0.5*np.cos(2*np.pi*np.clip(t/dur,0,1)))

    sig = air * gust + ghost
    sig = lowpass_fft(sig, 2800.0, order=3)
    env = adsr(n, a=0.25, d=0.3, s_level=0.7, hold=0.4, r=0.7)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.42 / peak)
    return out


# ---- pipe_chirp (chirp) ----
def voice_pipe_chirp(seed):
    """A bright high pipe-flick — a happy little birdcall accent. A quick
    two-note rising whistle-blip from the HIGH pentatonic, pure pipe with a
    thread of breath, cheerful and friendly. ~0.4s, additive."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85]
    leaps = [2, 3]
    start_i = int(rng.integers(0, 3))
    end_i = min(start_i + leaps[int(rng.integers(0, len(leaps)))], len(HIGH)-1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)

    rise = np.clip(t/(dur*0.55), 0, 1)
    rise = rise*rise*(3-2*rise)
    f_t = f0 + (f1-f0)*rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (np.sin(phase)
           + 0.18*np.sin(2*phase)
           + 0.05*np.sin(3*phase)*np.exp(-t*14))
    # tiny breath chiff at the very onset
    air = _breath(n, t, 600.0, 6500.0, int(seed)*5+3)
    sig += 0.16 * air * np.exp(-t*26.0) * np.clip(t/0.008, 0, 1)
    sig = lowpass_fft(sig, 7000.0, order=3)
    env = adsr(n, a=0.012, d=0.10, s_level=0.5, r=0.22)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


PLAN = {
    "pipe_ground": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.18, "decay": 2.2, "predelay_ms": 18, "brightness": 0.32}
    },
    "pan_lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1, 0, -0.12, 0.12, -0.08, 0.08],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 3.2, "predelay_ms": 30, "brightness": 0.55}
    },
    "whistle_pipe": {
        "kind": "midi",
        "midis": [69, 71, 73, 76, 78, 81, 85],
        "pans": [0.2, -0.2, 0.25, -0.15, 0.3, -0.25, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.4, "predelay_ms": 32, "brightness": 0.6}
    },
    "low_pipe": {
        "kind": "midi",
        "midis": [52, 57, 61, 64, 66, 69],
        "pans": [-0.12, 0.12, -0.08, 0.08, 0, -0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.3, "decay": 3.0, "predelay_ms": 26, "brightness": 0.45}
    },
    "pipe_ping": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.4, -0.3, 0.25],
        "target_peak": 0.8,
        "reverb": {"wet": 0.4, "decay": 3.6, "predelay_ms": 30, "brightness": 0.6}
    },
    "breath_flick": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.45, -0.4, 0.3, -0.3],
        "target_peak": 0.78,
        "reverb": {"wet": 0.3, "decay": 2.4, "predelay_ms": 18, "brightness": 0.62}
    },
    "breath_bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.2, "predelay_ms": 45, "brightness": 0.5}
    },
    "pipe_cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 42, "brightness": 0.52}
    },
    "wind_breath": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.6,
        "reverb": {"wet": 0.08, "decay": 1.2, "predelay_ms": 10, "brightness": 0.4}
    },
    "pipe_chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 2.0, "predelay_ms": 14, "brightness": 0.6}
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
    print("highland:", name)


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
