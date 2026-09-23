#!/usr/bin/env python3
"""
glassbright — sample renderer (per-voice reverb from preset.json).

Crystal singing bowls catching the sun, ringing pure and clear over still
water. Frictionless glassy sine-pure tones with a faint inharmonic glassy
shimmer that decays fast; ethereal yet wide-awake and joyful, never icy.
Long bell rings, no buzz, all light. A major pentatonic @ A=432, hall reverb,
additive only.

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


# ---- glassbottle (bass) ----
def voice_glassbottle(arg):
    """A rounded glass-bottle resonance — a soft sine fundamental with a
    breathy bottle-edge, grounding without weight. Pure low sine body with a
    kiss of 2nd/3rd harmonic for warmth, a faint breathy noise puff across the
    mouth of the bottle at the onset, and a slow amplitude breathe so the floor
    feels alive. Round, warm, near-dry. A-pentatonic LOW. ~2.6s."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    # round glass-bottle body — fundamental dominant, gentle low harmonics only
    body = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.20 * np.sin(2*np.pi*f*2*t)     * np.exp(-t*2.4) +   # warmth, fades early
        0.06 * np.sin(2*np.pi*f*3*t)     * np.exp(-t*5.0) +   # tiny edge, gone fast
        0.05 * np.sin(2*np.pi*f*1.004*t)                      # slow beat = glass life
    )
    # subtle slow breathe so the floor has movement
    breathe = 1.0 + 0.05 * np.sin(2*np.pi*2.4*t - np.pi/2)
    body = body * breathe

    # breathy bottle-edge: soft band of air across the mouth, short at onset
    rng = np.random.default_rng(int(arg) * 19 + 3)
    air = rng.standard_normal(n)
    air = lowpass_fft(air, 1100.0, order=3)
    air = air - lowpass_fft(air, 320.0, order=2)   # band: breathy mouth tone
    air_env = np.exp(-t * 9.0)
    body = body + 0.10 * air * air_env

    # keep it round — bottle is felt, not bright
    body = lowpass_fft(body, 1100.0, order=4)

    # soft glassy attack (18 ms), supportive sustain, gentle tail
    env = adsr(n, a=0.018, d=0.5, s_level=0.55, hold=0.6, r=1.2)
    out = body[:env.size] * env[:body.size]

    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- bowlsing (lead) ----
def voice_bowlsing(midi):
    """A rubbed crystal-bowl tone that swells in over ~30 ms, pure with one
    gentle 2.005x partial, singing the melody. Clean sine fundamental, a soft
    octave that fades early, one faint inharmonic glassy partial (2.005x) that
    decays fast for the crystal shimmer, and a whisper of vibrato that opens
    only after the note has spoken. Bright, singing, never icy. ~2.6s."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    # vibrato fades IN after the swell — singing, not warbly
    vib_depth = 0.0022 * np.clip((t - 0.45) / 0.6, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.0*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = (
        1.00 * np.sin(phase) +                                   # pure fundamental
        0.22 * np.sin(2*phase)        * np.exp(-t*1.8) +         # soft octave, fades early
        0.14 * np.sin(2.005*phase)    * np.exp(-t*3.5) +         # crystal glassy partial, quick
        0.05 * np.sin(3*phase)        * np.exp(-t*5.0) +         # faint sweetener, gone fast
        0.09 * np.sin(2*np.pi*f*1.004*t)                         # whisper of detune for body
    )
    # keep it sweet, tame any high edge
    sig = lowpass_fft(sig, 5200.0, order=3)
    # ~30 ms swell-in attack (no click)
    env = adsr(n, a=0.030, d=0.9, s_level=0.5, r=1.3)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- glassrim (lead2) ----
def voice_glassrim(midi):
    """A higher struck-glass rim — brighter and quicker, answering the lead in
    call-and-response. Pure sine with a clean octave glint and one fast glassy
    2.41x partial that pings then dies, a touch of high sparkle that fades in a
    blink. Quicker decay than the lead, bright and clear. ~1.8s."""
    f = freq(midi); dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)                              +  # pure body
        0.35 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.5)       +  # clean octave glint
        0.14 * np.sin(2*np.pi*f*2.41*t)  * np.exp(-t*7.0)       +  # struck-glass partial, quick
        0.06 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*9.0)       +  # bright ping
        0.05 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*22.0)      +  # tiny glint, gone in a blink
        0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*2.2)          # soft body bloom
    )
    # ~10 ms attack — quicker, brighter than lead, still click-free
    env = adsr(n, a=0.010, d=1.0, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=2)   # tame fizz, keep it bright
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- wineglass (tone) ----
def voice_wineglass(midi):
    """A warm wineglass hum — sweet and slightly breathy, filling the middle
    with rounded glass. A clean sine fundamental with a soft octave, a gentle
    just-fifth halo, a faint detune for body, and a whisper of breath that
    softens the onset. Rounded, sweet, A-pentatonic-safe. ~2.8s. Additive."""
    f = freq(midi); dur = 2.8
    n = int(dur * SR); t = t_axis(dur)

    # very slow breathing vibrato — calm hum
    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.4*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = (
        1.00 * np.sin(phase) +                                   # clean fundamental
        0.24 * np.sin(2*phase) * np.exp(-t*1.6) +                # soft octave, fades early
        0.16 * np.sin(2*np.pi*f*(3/2)*t) * np.exp(-t*1.4) +      # sweet just-fifth halo
        0.05 * np.sin(3*phase) * np.exp(-t*4.0) +                # faint sweetener
        0.10 * np.sin(2*np.pi*f*1.0035*t)                        # whisper of detune for body
    )
    # breathy onset: very soft band of air, short
    rng = np.random.default_rng(int(midi) * 13 + 7)
    air = rng.standard_normal(n)
    air = lowpass_fft(air, 2600.0, order=3)
    air = air - lowpass_fft(air, 700.0, order=2)
    air_env = np.exp(-t * 16.0)
    sig = sig + 0.06 * air * air_env

    sig = lowpass_fft(sig, 4600.0, order=3)
    env = adsr(n, a=0.022, d=0.9, s_level=0.5, r=1.4)
    out = sig[:env.size] * env[:sig.size] * 0.46
    return out


# ---- rimping (chime) ----
def voice_rimping(midi):
    """A fingertip-on-rim ping — pure sine plus a fast 2.76x glint, medium
    reverb, like a single clear bell. A glowing fundamental, a clean octave
    doubling, a quick inharmonic 2.76x glassy glint that decays fast, and a
    whisper of high sparkle. Soft 16 ms attack, no click. Pure and clear. ~2.6s."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.0)  +   # warm body
        0.45 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*1.5)  +   # clean octave doubling
        0.18 * np.sin(2*np.pi*f*2.76*t)   * np.exp(-t*4.5)  +   # glassy glint, fast
        0.07 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*6.0)  +   # faint shimmer
        0.04 * np.sin(2*np.pi*f*5.0*t)    * np.exp(-t*9.0)      # tiny glint, gone fast
    )
    # gentle chorus shimmer (two near-unisons) for a glowing bell warmth
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.2)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.2)
    env = adsr(n, a=0.016, d=2.0, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=3)
    peak = np.max(np.abs(out))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- droplet (sparkle) ----
def voice_droplet(midi):
    """Tiny high glass droplets — a pure sine with a quick 4.5x shimmer that
    decays in a blink, scattered with light delay echoes. A bright little
    pinprick of glass: clean fundamental + clean octave + a fast inharmonic
    4.5x glint that dies almost instantly. Short, bright, dry-ish. ~0.7s."""
    f = freq(midi); dur = 0.7
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*4.5)  +   # bright pure body
        0.30 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*7.0)  +   # clean octave
        0.10 * np.sin(2*np.pi*f*4.5*t)    * np.exp(-t*40.0) +   # 4.5x shimmer, blink-fast
        0.05 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*5.0)      # faint body shimmer
    )
    env = adsr(n, a=0.008, d=0.4, s_level=0.0, r=0.25)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8000.0, order=2)   # tame fizz, keep the glint
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- crystalbloom (bloom) ----
def voice_crystalbloom(midi):
    """A slow crystal swell — a bowed-glass pad of stacked pure partials
    blooming open, lush and lit from within. Clean fundamental + just-major-
    third + just-fifth + soft octave halo + a gentle sub for body. Two faint
    detunes give a breathing chorus shimmer. A moving lowpass OPENS over the
    swell so it 'blooms' lit from within, never harsh. ~7s. Additive only."""
    f = freq(midi)
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)

    # slow breathing vibrato — calm bowed glass
    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.26*t)

    # warm chorus on the fundamental: two faint detunes
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.45 * np.sin(2*np.pi*f*1.0035*t) +
        0.45 * np.sin(2*np.pi*f*0.9967*t)
    )
    # consonant pure halo above (just intonation: sweet, never beating)
    third  = 0.38 * np.sin(2*np.pi*f*(5/4)*t*vib)   # major third
    fifth  = 0.34 * np.sin(2*np.pi*f*(3/2)*t*vib)   # perfect fifth
    octave = 0.24 * np.sin(2*np.pi*f*2.0*t)         # soft octave halo
    sub    = 0.26 * np.sin(2*np.pi*f*0.5*t)         # tiny sub for body

    sig = fund + third + fifth + octave + sub

    # bloom: brightness opens over the first seconds then settles
    low  = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.30 + 0.70 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    # final warmth ceiling — lit from within, kill residual fizz
    sig = lowpass_fft(sig, 3200.0, order=3)

    # slow swell-in, long gentle release
    env = adsr(n, a=1.5, d=1.0, s_level=0.85, hold=1.2, r=3.0)
    out = sig[:env.size] * env[:sig.size]

    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- sunripple (cluster) ----
def voice_sunripple(arg):
    """A shimmering wash of three nearby glass tones beating gently, like
    sunlight rippling on a bowl of water. From the passed root we build a
    major-pentatonic-safe chord: root, +4 (maj3), +7 (5th), +9 (maj6), +12
    (octave). Pure additive sines with faint octaves, gentle detune, slow
    breathing vibrato and staggered swells so the chord blooms open like light
    spreading across water. Warm low-passed. ~7.2s."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.2
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partial = (np.sin(2*np.pi*f*t)
                   + 0.18*np.sin(2*np.pi*2*f*t)
                   + 0.06*np.sin(2*np.pi*3*f*t))
        # subtle detune twin for the gentle "beating" ripple
        detune = np.sin(2*np.pi*f*1.0035*t)
        vib = 1 + 0.0022*np.sin(2*np.pi*0.20*t + i*0.9)
        voice = (0.85*partial + 0.32*detune) * vib
        stagger = 0.18 * i
        env = adsr(n, a=1.7 + stagger, d=0.7, s_level=0.82,
                   hold=1.6, r=2.6)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 3000, order=3)
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- glassbreath (texture) ----
def voice_glassbreath(seed):
    """A faint glassy breath — the air just before a bowl sings, near-dry and
    intimate. A soft band of filtered noise shaped into a gentle swell-and-fade,
    with a barely-there pure sine 'pre-ring' that hints the bowl is about to
    speak. Very quiet, warm, near-dry. ~0.9s."""
    rng = np.random.default_rng(seed)
    dur = 0.9
    n = int(dur * SR); t = t_axis(dur)

    # breath: soft band-limited noise, warm (no hiss top), shaped as a swell
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 2400.0, order=3)
    noise = noise - lowpass_fft(noise, 500.0, order=2)   # band: airy breath
    breath_env = adsr(n, a=0.10, d=0.3, s_level=0.4, r=0.35)
    breath = noise * breath_env

    # barely-there pure pre-ring: a faint high sine hinting the bowl wakes up
    pre_f = 432.0 * (2 ** (rng.uniform(-1.0, 4.0) / 12.0))  # gentle drift, stays in air
    pre = 0.12 * np.sin(2*np.pi*pre_f*t) * adsr(n, a=0.15, d=0.4, s_level=0.2, r=0.3)

    sig = 0.85 * breath + pre
    sig = lowpass_fft(sig, 3000.0, order=3)   # keep it soft and rounded

    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.40 / peak)
    return sig


# ---- sunglint (chirp) ----
def voice_sunglint(seed):
    """A bright tiny glass flick at the top — a happy sun-glint accent, quick
    and dry-ish. One sweet rising glass-blip in A major pentatonic high
    register: a pure sine that lifts a pentatonic step or two with a tiny
    octave sheen, like a flick of light off a rim. ~0.4s, near-dry."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]          # A maj pentatonic, high register
    leaps = [1, 2, 3]                         # pentatonic steps up (indices)
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i])
    f1 = freq(HIGH[end_i])

    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)

    rise = np.clip(t / (dur * 0.5), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep — no zipper
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.20 * np.sin(2*phase) +                 # glassy octave sheen
        0.06 * np.sin(2.41*phase) * np.exp(-t*16) +  # tiny glass glint at onset
        0.04 * np.sin(3*phase) * np.exp(-t*18)       # tiny chiff
    )
    sig = lowpass_fft(sig, 8000.0, order=3)      # keep it from piercing

    env = adsr(n, a=0.010, d=0.10, s_level=0.5, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.48
    return out


PLAN = {
    "glassbottle": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.62,
        "reverb": {"wet": 0.10, "decay": 1.8, "predelay_ms": 14, "brightness": 0.32}
    },
    "bowlsing": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [-0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 3.4, "predelay_ms": 26, "brightness": 0.6}
    },
    "glassrim": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.18, -0.18, 0.1, -0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.30, "decay": 2.8, "predelay_ms": 22, "brightness": 0.62}
    },
    "wineglass": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.12, 0.12, 0],
        "target_peak": 0.82,
        "reverb": {"wet": 0.32, "decay": 3.0, "predelay_ms": 24, "brightness": 0.5}
    },
    "rimping": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.4, 0.3, -0.2, 0.4, -0.3, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.38, "decay": 3.4, "predelay_ms": 28, "brightness": 0.62}
    },
    "droplet": {
        "kind": "midi",
        "midis": [76, 78, 81, 85, 88],
        "pans": [0.4, -0.35, 0.3, -0.4, 0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.30, "decay": 2.4, "predelay_ms": 16, "brightness": 0.66}
    },
    "crystalbloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.2, "predelay_ms": 45, "brightness": 0.46}
    },
    "sunripple": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.2, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 45, "brightness": 0.48}
    },
    "glassbreath": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.5,
        "reverb": {"wet": 0.06, "decay": 0.8, "predelay_ms": 10, "brightness": 0.4}
    },
    "sunglint": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.78,
        "reverb": {"wet": 0.12, "decay": 1.8, "predelay_ms": 12, "brightness": 0.64}
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
    print("glassbright:", name)


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
