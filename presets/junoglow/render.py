#!/usr/bin/env python3
"""
junoglow — sample renderer (per-voice reverb from preset.json).

Soft analog synth pads breathing dreamy and warm, a Juno chorus shimmering in
the sun. Warm Juno-style additive pads with gentle chorus shimmer and soft
bleeps; plush and bright, retro-warm and optimistic, never cold or dark.
A major pentatonic @ A=432, additive only, hall reverb, never dreary.

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


def _juno_chorus(f, t, depth=0.004, rate=0.83, voices=3):
    """Juno-style chorus: a few slightly-detuned, slowly-LFO'd sine copies of a
    pitch summed together for that shimmering, gently-beating analog warmth.
    Pure additive (sum of sines), no modulation buzz. Returns a mono signal."""
    out = np.zeros_like(t)
    # symmetric detune spread around the center pitch, each with its own slow LFO
    spreads = np.linspace(-1.0, 1.0, voices)
    for i, s in enumerate(spreads):
        # slow per-voice pitch wobble (the BBD chorus shimmer), tiny & smooth
        lfo = 1.0 + depth * s * (1.0 + 0.25 * np.sin(2*np.pi*(rate*(0.7+0.2*i))*t + i*1.7))
        out += np.sin(2*np.pi*f*lfo*t + i*0.6)
    return out / voices


# ---- bass (round analog sub-pad, soft warm fundamental with slow chorus) ----
def voice_bass(arg):
    """A round analog sub-pad — soft warm fundamental, the plush ground floor.
    Sine fundamental + a kiss of low harmonics for warmth, a gentle detuned
    twin for slow chorus 'breathing', wrapped in a soft pad attack. Near-dark
    on top (heavily low-passed) so it is felt as a warm floor, never harsh."""
    f = freq(int(arg))
    dur = 3.4
    n = int(dur * SR); t = t_axis(dur)

    body = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.26 * np.sin(2*np.pi*f*2*t) * np.exp(-t*2.2) +      # warmth, fades early
        0.08 * np.sin(2*np.pi*f*3*t) * np.exp(-t*4.0)        # tiny edge, gone fast
    )
    # slow analog chorus: two faint detuned twins, gently beating = "breathing"
    body += 0.22 * np.sin(2*np.pi*f*1.0045*t)
    body += 0.22 * np.sin(2*np.pi*f*0.9958*t)
    # subtle slow amplitude breathe so the floor feels alive
    breathe = 1.0 + 0.05 * np.sin(2*np.pi*0.9*t - np.pi/2)
    body = body * breathe

    # keep it round: roll off anything bright; bass should be plush, not heard up top
    body = lowpass_fft(body, 760.0, order=4)

    env = adsr(n, a=0.030, d=0.7, s_level=0.6, hold=0.8, r=1.4)
    out = body[:env.size] * env[:body.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead (Juno-pad lead with chorus shimmer, soft-attack swelling in) ----
def voice_lead(midi):
    """A Juno-pad lead — soft-attack additive tone that swells in and sings the
    dreamy melody, with chorus shimmer. A chorused fundamental plus sweet
    consonant partials (octave, fifth) for body, a gentle filter that opens as
    it swells, warm low-passed top. Bright and plush, never piercing. ~2.6s."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    chorus = _juno_chorus(f, t, depth=0.0045, rate=0.9, voices=3)
    sig = (
        1.00 * chorus +
        0.34 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*1.4) +    # sweet octave, fades
        0.16 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*2.6) +    # fifth-above-octave, soft
        0.16 * np.sin(2*np.pi*f*0.5*t)                       # warm sub halo for body
    )
    # gentle vibrato fading in after the note speaks (singing, not warbly)
    vib_depth = 0.0022 * np.clip((t - 0.4) / 0.7, 0.0, 1.0)
    sig = sig * (1.0 + vib_depth * np.sin(2*np.pi*5.2*t))

    # filter opens over the swell -> brightens as it blooms
    bright = sig - lowpass_fft(sig, 800.0, order=3)
    bodyl  = sig - bright
    open_env = np.clip(t / 1.4, 0, 1)
    sig = bodyl + bright * (0.30 + 0.70*open_env)

    sig = lowpass_fft(sig, 5200.0, order=3)
    env = adsr(n, a=0.045, d=0.9, s_level=0.55, r=1.1)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (brighter pluck-synth bleep, quick warm blip) ----
def voice_lead2(midi):
    """A brighter pluck-synth bleep — quick warm blip answering the pad with
    playful counter-notes. A fast-decaying chorused body + a clean octave
    sparkle that pings at the attack, soft 9ms attack so it's plucky but
    click-free. Bright but rounded (low-passed), A-pentatonic safe. ~1.0s."""
    f = freq(midi); dur = 1.0
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*t) * np.exp(-t*4.5) +        # plucky body
        0.40 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*7.0) +    # clean octave ping
        0.12 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*12.0)     # bright blip top, gone fast
    )
    # light chorus twins for warm Juno sheen
    sig += 0.30 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*4.5)
    sig += 0.30 * np.sin(2*np.pi*f*0.996*t) * np.exp(-t*4.5)

    sig = lowpass_fft(sig, 6200.0, order=3)
    env = adsr(n, a=0.009, d=0.5, s_level=0.0, r=0.35)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (warm sustained pad-tone, mellow and chorused, plush middle) ----
def voice_tone(midi):
    """A warm sustained pad-tone — mellow and chorused, the sweet plush middle.
    A chorused fundamental with a soft octave that fades early and a whisper of
    fifth for body. Mellow low-passed top so it sits warm under the lead. A
    gentle breathing tremolo. ~2.8s. Additive only, no FM."""
    f = freq(midi); dur = 2.8
    n = int(dur * SR); t = t_axis(dur)

    chorus = _juno_chorus(f, t, depth=0.0040, rate=0.7, voices=3)
    sig = (
        1.00 * chorus +
        0.20 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*1.8) +    # soft octave, fades early
        0.10 * np.sin(2*np.pi*f*1.5*t) * np.exp(-t*2.4) +    # gentle fifth color
        0.12 * np.sin(2*np.pi*f*0.5*t)                       # warm sub for plush body
    )
    # slow breathing tremolo
    sig = sig * (1.0 + 0.05 * np.sin(2*np.pi*0.55*t))

    sig = lowpass_fft(sig, 3800.0, order=3)
    env = adsr(n, a=0.035, d=0.9, s_level=0.55, hold=0.3, r=1.3)
    out = sig[:env.size] * env[:sig.size] * 0.5
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- chime (soft synth-bell ping, pure with gentle shimmer) ----
def voice_chime(midi):
    """A soft synth-bell ping — pure with gentle shimmer, medium reverb.
    A glowing fundamental with a pure octave doubling and a couple of soft
    inharmonic bell partials, each with INDEPENDENT decay so it shimmers and
    settles to pure. Gentle chorus twins for the Juno glow. Soft 16ms attack,
    no click. No partials past 5x, all decay fast. ~2.4s."""
    f = freq(midi); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.3) +     # warm body
        0.50 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*1.8) +     # pure octave doubling
        0.18 * np.sin(2*np.pi*f*2.76*t)   * np.exp(-t*3.6) +     # soft bell color, fast decay
        0.08 * np.sin(2*np.pi*f*4.2*t)    * np.exp(-t*5.5)       # tiny shimmer, gone fast
    )
    # gentle chorus shimmer twins
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.4)
    sig += 0.13 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.4)

    env = adsr(n, a=0.016, d=2.0, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6800.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (tiny high synth-blips arpeggiating, bright droplets) ----
def voice_sparkle(midi):
    """Tiny high synth-blips — bright droplets with delay echoes (live echo in
    event.py). A short, sweet sine droplet with a clean octave glint and a fast
    chorus shimmer, soft 8ms attack, quick decay so each blip is a glassy
    droplet. Warm-topped so it stays sweet, never piercing. ~0.6s."""
    f = freq(midi); dur = 0.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t) * np.exp(-t*6.0) +
        0.30 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*9.0) +   # octave glint
        0.08 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*16.0)    # tiny top, gone fast
    )
    sig += 0.22 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*6.0)   # chorus shimmer twin
    sig = lowpass_fft(sig, 7000.0, order=3)
    env = adsr(n, a=0.008, d=0.30, s_level=0.0, r=0.22)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (big chorused pad swell, layered warm analog blooming open) ----
def voice_bloom(midi):
    """A big chorused pad swell — layered warm analog blooming open, a lush
    dreamy wash. A fat chorus of detuned fundamentals + consonant just-major
    third & fifth halo + soft octave + warm sub. A moving lowpass that OPENS
    over the swell so it blooms bright without harshness. Slow swell-in, long
    release. Round and plush, never glassy. ~7s."""
    f = freq(midi)
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)

    # very slow breathing vibrato
    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.26*t)

    # fat chorus on the fundamental: several faint detunes (the Juno glow)
    fund = _juno_chorus(f, t, depth=0.0055, rate=0.6, voices=5) * vib

    third  = 0.36 * np.sin(2*np.pi*f*(5/4)*t*vib)   # major third (just)
    fifth  = 0.30 * np.sin(2*np.pi*f*(3/2)*t*vib)   # perfect fifth (just)
    octave = 0.22 * np.sin(2*np.pi*f*2.0*t)         # soft octave halo
    sub    = 0.28 * np.sin(2*np.pi*f*0.5*t)         # warm body sub

    sig = fund + third + fifth + octave + sub

    # bloom: brightness opens over the first seconds then settles
    low  = lowpass_fft(sig, 700.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    sig = lowpass_fft(sig, 2800.0, order=3)
    env = adsr(n, a=1.5, d=1.0, s_level=0.85, hold=1.2, r=3.0)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- cluster (detuned-saw chord wash, shimmering chorused cloud) ----
def voice_cluster(arg):
    """A detuned-saw chord wash — a shimmering chorused cloud, plush and bright.
    From the passed root we build a major-pentatonic-safe chord (root, +4, +7,
    +9, +12). Each note is a SOFT band-limited additive 'saw' (a few harmonics
    that roll off, no harsh tops) with detuned chorus twins for that thick
    analog supersaw shimmer. Staggered swells bloom it open. Warm low-passed."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.2
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    # soft additive 'saw': harmonics 1..6 with 1/k amplitude, rolled off warm
    harms = [1, 2, 3, 4, 5, 6]
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        note = np.zeros(n)
        # three detuned chorus copies for the shimmering supersaw cloud
        for d in (-1.0, 0.0, 1.0):
            ff = f * (1.0 + 0.005 * d)
            saw = np.zeros(n)
            for k in harms:
                if k * ff > 5.2 * f:   # keep nothing harsh above ~5x of the note
                    continue
                saw += (1.0 / k) * np.sin(2*np.pi*ff*k*t)
            note += saw
        note /= 3.0
        # slow breathing vibrato, each voice phased differently
        vib = 1 + 0.0022 * np.sin(2*np.pi*0.2*t + i*0.9)
        note = note * vib
        # staggered swell: upper notes bloom slightly later -> opening glow
        stagger = 0.16 * i
        env = adsr(n, a=1.7 + stagger, d=0.7, s_level=0.82, hold=1.6, r=2.6)
        gain = 1.0 - 0.10*i        # high voices a touch quieter, root grounded
        sig += note * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 2800.0, order=3)   # warm: no harsh top on the cloud
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- texture (faint warm analog-noise texture, near-dry machine hiss) ----
def voice_texture(seed):
    """A faint warm analog-noise texture — the gentle hiss of the machine,
    near-dry. A soft band of low-passed noise (warm, no top hiss) with a slow
    swell so it breathes in and out, plus a very faint tonal hum anchored low
    in key for warmth. Deliberately quiet, soft attack, never harsh. ~2.2s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 1600.0, order=3)          # warm, roll off hiss top
    noise = noise - lowpass_fft(noise, 180.0, order=2)   # band: gentle machine air
    # slow breathing amplitude so it swells in/out, never a static drone
    breathe = 0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.5), 1.0)) * np.exp(-np.maximum(t-1.1,0)*1.4)

    # faint tonal hum anchored low in key for warmth (very quiet)
    fh = freq(45)
    hum = 0.12 * (np.sin(2*np.pi*fh*t) + 0.4*np.sin(2*np.pi*fh*1.004*t))
    hum = lowpass_fft(hum, 500.0, order=3)

    sig = 0.5 * noise * breathe + hum * breathe
    env = adsr(n, a=0.20, d=0.6, s_level=0.6, hold=0.3, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 2000.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.40 / peak)        # deliberately quiet texture
    return out


# ---- chirp (bright tiny synth-blip, a happy retro accent up top) ----
def voice_chirp(seed):
    """A bright tiny synth-blip — a happy retro accent up top. One cheerful
    little 2-note rising blip in the HIGH pentatonic: a quick smooth pitch lift
    + a clean octave sparkle + a fast chorus shimmer. Soft 10ms attack, quick
    decay. Bright & friendly, warm-topped so it never pierces. ~0.4s."""
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
    rise = rise * rise * (3 - 2*rise)        # smoothstep
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.22 * np.sin(2*phase) +                 # clean octave sparkle
        0.06 * np.sin(3*phase) * np.exp(-t*12)   # tiny chiff at onset
    )
    # fast chorus shimmer twin
    sig += 0.18 * np.sin(phase * 1.004)
    sig = lowpass_fft(sig, 7000.0, order=3)
    env = adsr(n, a=0.010, d=0.12, s_level=0.5, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.50
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.7,
        "reverb": {"wet": 0.12, "decay": 1.8, "predelay_ms": 14, "brightness": 0.3}
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76, 78, 81],
        "pans": [-0.15, 0.15, -0.1, 0.1, 0, -0.18, 0.18, -0.08, 0.12],
        "target_peak": 0.7,
        "reverb": {"wet": 0.4, "decay": 3.6, "predelay_ms": 30, "brightness": 0.55}
    },
    "lead2": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.2, -0.2, 0.15, -0.15, 0.25, -0.1, 0.3, -0.25],
        "target_peak": 0.7,
        "reverb": {"wet": 0.2, "decay": 1.8, "predelay_ms": 18, "brightness": 0.6}
    },
    "tone": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.12, 0.12, -0.08, 0.08, 0, -0.15, 0.15],
        "target_peak": 0.7,
        "reverb": {"wet": 0.42, "decay": 3.8, "predelay_ms": 32, "brightness": 0.5}
    },
    "chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.4, 0.3, -0.2, 0.4, -0.3, 0.2, 0],
        "target_peak": 0.7,
        "reverb": {"wet": 0.38, "decay": 3.2, "predelay_ms": 28, "brightness": 0.6}
    },
    "sparkle": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88, 90],
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.2, 0.3],
        "target_peak": 0.7,
        "reverb": {"wet": 0.34, "decay": 2.8, "predelay_ms": 22, "brightness": 0.62}
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.7,
        "reverb": {"wet": 0.52, "decay": 5.2, "predelay_ms": 45, "brightness": 0.48}
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18, -0.1, 0.1],
        "target_peak": 0.7,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 42, "brightness": 0.52}
    },
    "texture": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.7,
        "reverb": {"wet": 0.06, "decay": 0.8, "predelay_ms": 10, "brightness": 0.35}
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.2],
        "target_peak": 0.7,
        "reverb": {"wet": 0.12, "decay": 1.6, "predelay_ms": 12, "brightness": 0.62}
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
    print("junoglow:", name)


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
