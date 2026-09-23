#!/usr/bin/env python3
"""
shimmerwire — sample renderer (per-voice reverb from preset.json).

A hammered dulcimer cascading bright struck-wire shimmer, like rain on a tin
sunroof at noon. Rapid struck-wire dulcimer tones, bright and ringing with
overlapping metallic decay; cascading and shimmering, folk-bright and tumbling,
pure daylit sparkle. A major pentatonic @ A=432, additive only, never dreary.

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


# A hammered-dulcimer "course" is a pair (or more) of nearly-identical strings
# struck together. The shimmer comes from two near-unison wires beating against
# each other plus a clean, fast-decaying set of harmonic partials. We model that
# directly: a small detuned chorus of partials, each partial with its OWN decay
# (high partials die fast -> bright struck attack that mellows to a ringing tone).
def _struck_course(f, t, partials, detune=0.0030, ring=1.0, bright=1.0):
    """Additive struck-wire course.
    partials: list of (mult, amp, decay_rate). decay_rate scaled by `ring`
    (smaller ring = longer tail). `detune` sets the two-wire beating shimmer."""
    sig = np.zeros_like(t)
    for mult, amp, dec in partials:
        a = amp * bright if mult >= 3.0 else amp
        d = dec * ring
        # two near-unison wires per course -> gentle shimmering beat
        sig += a * np.sin(2*np.pi*f*mult*(1.0 + detune)*t) * np.exp(-t*d)
        sig += a * np.sin(2*np.pi*f*mult*(1.0 - detune)*t) * np.exp(-t*d)
    return sig * 0.5


# ---- wirefloor (bass — low bass-course struck soft, warm ringing wire, long tail) ----
def voice_wirefloor(midi):
    """A low dulcimer bass-course struck soft. Warm round fundamental with a
    gentle octave and a kiss of fifth, two near-unison wires giving a slow
    shimmering beat, long ringing tail. The cascade floor — never dark, just
    deep and warm. Additive only, soft 8 ms attack, lowpassed round. ~3.2s."""
    f = freq(int(midi))
    dur = 3.2
    n = int(dur * SR); t = t_axis(dur)
    sig = _struck_course(f, t, [
        (1.00, 1.00, 1.1),     # round fundamental, long tail
        (2.00, 0.34, 1.8),     # warm octave
        (3.00, 0.12, 3.0),     # soft fifth-above-octave color, fades
        (4.00, 0.05, 5.0),     # tiny glint, gone fast
    ], detune=0.0022, ring=1.0)
    # soft felt of the padded hammer at the strike
    rng = np.random.default_rng(int(midi) * 31 + 5)
    puff = lowpass_fft(rng.standard_normal(n), 320.0, order=3) * np.exp(-t*26)
    sig = sig + 0.10 * puff
    sig = lowpass_fft(sig, 1600.0, order=3)   # keep it warm/round, bass felt not heard up top
    env = adsr(n, a=0.008, d=1.4, s_level=0.32, hold=0.3, r=1.3)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- hammerbright (lead — mid hammered course, bright struck attack + 2x wire shimmer) ----
def voice_hammerbright(midi):
    """The mid hammered course that tumbles the melody. A bright struck attack
    (fast-decaying high partials = the hammer 'ping') settling into a ringing
    fundamental, with a shimmering 2x wire-resonance that sings on. Two
    near-unison wires beat for that classic dulcimer shimmer. ~2.0s."""
    f = freq(int(midi))
    dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = _struck_course(f, t, [
        (1.00, 1.00, 2.0),     # ringing fundamental
        (2.00, 0.55, 2.6),     # the shimmering wire-resonance octave, sings on
        (3.00, 0.26, 5.0),     # bright struck color, mellows quick
        (4.00, 0.13, 9.0),     # hammer ping, gone in ~110ms
        (5.30, 0.06, 16.0),    # tiny metallic glint, dies fast (read as 'struck')
    ], detune=0.0034, ring=1.0)
    env = adsr(n, a=0.006, d=1.2, s_level=0.0, r=0.7)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=2)   # tame fizz, keep bright sparkle
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- hammerhigh (lead2 — higher course, quicker & brighter, cascading counter-line) ----
def voice_hammerhigh(midi):
    """A higher dulcimer course, quicker and brighter, cascading a counter-line
    down over the lead. Shorter ring, snappier struck attack, more top sparkle
    but all high partials decay fast so it stays sweet, never harsh. ~1.4s."""
    f = freq(int(midi))
    dur = 1.4
    n = int(dur * SR); t = t_axis(dur)
    sig = _struck_course(f, t, [
        (1.00, 1.00, 3.0),     # snappier fundamental
        (2.00, 0.48, 4.0),     # bright octave shimmer
        (3.00, 0.22, 7.0),     # struck brightness
        (4.00, 0.10, 12.0),    # ping, quick
        (5.20, 0.05, 20.0),    # glint, gone fast
    ], detune=0.0040, ring=1.0)
    env = adsr(n, a=0.005, d=0.85, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8200.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.49 / peak)
    return out


# ---- sweetcourse (tone — soft-hammered warm course, rounder shimmer, sweet middle) ----
def voice_sweetcourse(midi):
    """A soft-hammered warm course — the sweet ringing middle. Rounder shimmer:
    a strong fundamental, gentle octave, very little high struck-edge (felt
    hammer), a whisper of detune body for bloom. Sings warm and sweet. ~2.4s."""
    f = freq(int(midi))
    dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    sig = _struck_course(f, t, [
        (1.00, 1.00, 1.4),     # warm singing fundamental
        (2.00, 0.40, 2.2),     # rounded octave shimmer
        (3.00, 0.13, 4.5),     # gentle color, fades
        (4.00, 0.04, 8.0),     # tiny soft glint
    ], detune=0.0028, ring=1.0)
    # soft vibrato that opens after the note speaks (singing, not warbly)
    vib_depth = 0.0022 * np.clip((t - 0.45) / 0.6, 0.0, 1.0)
    sig = sig * (1.0 + vib_depth * np.sin(2*np.pi*4.8*t))
    sig = lowpass_fft(sig, 4600.0, order=3)   # round, sweet, no glassy top
    env = adsr(n, a=0.012, d=1.0, s_level=0.42, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- glintping (chime — high single-wire ping, bright glint, decays fast) ----
def voice_glintping(midi):
    """A high single-wire ping with a bright glint that decays fast — one wire,
    not a course, so less beating, more pure sparkle. A clear fundamental, a
    pure octave, a quick high glint that's gone in ~80ms. Medium reverb. ~1.6s."""
    f = freq(int(midi))
    dur = 1.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*3.2) +   # clear ping body
        0.42 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*4.5) +   # pure octave glint
        0.18 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*8.0) +   # bright color, quick
        0.08 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*14.0) +  # glint, gone fast
        0.10 * np.sin(2*np.pi*f*1.003*t)  * np.exp(-t*3.4)     # whisper detune shimmer
    )
    env = adsr(n, a=0.006, d=0.9, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8500.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.49 / peak)
    return out


# ---- raindroplets (sparkle — rapid top-course hammer-rolls, cascading droplets) ----
def voice_raindroplets(seed):
    """Rapid top-course hammer-rolls: a quick cascade of 3-5 bright struck-wire
    droplets tumbling DOWN the high pentatonic, each a tiny pinging course.
    Cascading bright droplets (delay echoes added live). Seed picks the run.
    Additive, sweet, ~1.1s of tumbling sparkle."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]          # A maj pentatonic, high
    dur = 1.1
    n = int(dur * SR); t = t_axis(dur)
    out = np.zeros(n)
    # a tumbling DOWN cascade: start high, step down the scale
    n_drops = int(rng.integers(4, 6))
    start_i = int(rng.integers(len(HIGH) - 1, len(HIGH)))
    idx = start_i
    step = 0.085   # ~85ms between droplets = rapid roll
    for k in range(n_drops):
        idx = max(0, idx - int(rng.integers(1, 3)))
        m = HIGH[idx]
        f = freq(m)
        onset = k * step + rng.uniform(-0.008, 0.008)
        s = int(max(0, onset) * SR)
        avail = n - s
        if avail <= 0:
            break
        tt = t[:avail]
        drop = (
            1.00 * np.sin(2*np.pi*f*tt)      * np.exp(-tt*9.0) +
            0.40 * np.sin(2*np.pi*f*2.0*tt)  * np.exp(-tt*13.0) +
            0.16 * np.sin(2*np.pi*f*3.0*tt)  * np.exp(-tt*22.0)
        )
        denv = adsr(avail, a=0.004, d=0.18, s_level=0.0, r=0.05)
        drop = drop * denv
        gain = 0.95 ** k   # each droplet a touch softer -> tumbling away
        out[s:s+avail] += drop * gain
    out = lowpass_fft(out, 8800.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- wirebloom (bloom — tremolo-roll swell across courses, lush blooming wash) ----
def voice_wirebloom(midi):
    """A tremolo-roll swell across courses ringing together — a lush blooming
    wire wash. From the root we ring a major-pentatonic chord (root, +4, +7,
    +12) of soft struck courses, with a tremolo amplitude shimmer (the rapid
    hammer-roll) and a slow bloom-open filter. Warm, lush, never harsh. ~6.0s."""
    root = int(midi)
    intervals = [0, 4, 7, 12]
    dur = 6.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        voice = _struck_course(f, t, [
            (1.00, 1.00, 0.5),
            (2.00, 0.34, 0.8),
            (3.00, 0.10, 1.6),
        ], detune=0.0030 + 0.0006*i, ring=1.0)
        # slow staggered swell so courses bloom open like a roll spreading
        env = adsr(n, a=1.2 + 0.25*i, d=1.0, s_level=0.7, hold=0.8, r=2.2)
        sig += voice * env[:n] * (1.0 - 0.08*i)
    sig /= len(intervals)
    # tremolo roll: a soft, fairly quick amplitude shimmer = the ringing hammer-roll
    tremolo = 1.0 + 0.16 * (0.5 - 0.5*np.cos(2*np.pi*7.5*t))
    sig = sig * tremolo
    # bloom-open filter: dark-ish onset -> bright bloom -> settle (smooth)
    low = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.30 + 0.70 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.8), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 4200.0, order=3)   # lush warm ceiling, no fizz
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- shimmercloud (cluster — fast two-hammer roll on three courses, struck cloud) ----
def voice_shimmercloud(midi):
    """A fast two-hammer roll on three courses — a shimmering struck-wire cloud,
    tumbling. Three pentatonic-safe courses (root, +4, +7) struck rapidly with
    a tremolo-roll amplitude shimmer and slight per-course phase so it churns
    and tumbles. Bright but warm-capped. ~5.5s welcome cloud."""
    root = int(midi)
    intervals = [0, 4, 7]
    dur = 5.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        voice = _struck_course(f, t, [
            (1.00, 1.00, 0.7),
            (2.00, 0.42, 1.1),
            (3.00, 0.16, 2.2),
            (4.00, 0.06, 4.0),
        ], detune=0.0034 + 0.0008*i, ring=1.0)
        # fast two-hammer roll: a quick tremolo, phased per course = churning cloud
        roll = 1.0 + 0.22 * (0.5 - 0.5*np.cos(2*np.pi*9.0*t + i*1.7))
        voice = voice * roll
        env = adsr(n, a=1.0 + 0.2*i, d=0.8, s_level=0.72, hold=1.2, r=2.2)
        sig += voice * env[:n] * (1.0 - 0.09*i)
    sig /= len(intervals)
    # bloom-open so the cloud brightens as it gathers
    low = lowpass_fft(sig, 900.0, order=3)
    high = sig - low
    open_curve = 0.35 + 0.65 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.8), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 5200.0, order=3)   # warm cap, keep shimmer, no screech
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- frametap (tap — damped hammer tap on wood frame, near-dry click, the pulse) ----
def voice_frametap(seed):
    """A damped hammer tap on the wooden frame of the dulcimer — a near-dry
    woody click, the rhythmic pulse. A couple of fast-decaying mid-wood partials
    + a short soft filtered-noise contact transient. Soft ~3ms attack (no raw
    edge), short and dry. ~0.16s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.16
    n = int(dur * SR); t = t_axis(dur)
    # woody body: a fixed mid pitch with tiny per-tap wobble so taps feel real
    base = 430.0 * (2 ** (rng.uniform(-0.2, 0.2) / 12.0))
    body = np.zeros(n)
    for mult, amp, dec in ((1.0, 1.0, 55.0), (2.01, 0.40, 90.0), (3.1, 0.16, 140.0)):
        ph = rng.uniform(0, 2*np.pi)
        body += amp * np.sin(2*np.pi*base*mult*t + ph) * np.exp(-t*dec)
    body /= 1.56
    # contact transient: short band-limited noise = the hammer-on-wood click
    noise = lowpass_fft(rng.standard_normal(n), 2600.0, order=3)
    noise = noise - lowpass_fft(noise, 300.0, order=2)
    nenv = adsr(n, a=0.003, d=0.024, s_level=0.0, r=0.0)
    click = noise * nenv * 0.55
    benv = adsr(n, a=0.003, d=0.05, s_level=0.0, r=0.0)
    out = body * benv + click
    out = lowpass_fft(out, 3800.0, order=4)   # warm, woody, no harsh top
    out = soft_clip(out, 1.1)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- flickchirp (chirp — bright top-course flick, a sparkling little folk accent) ----
def voice_flickchirp(seed):
    """A bright top-course flick — a sparkling little folk accent. One quick
    struck high wire, optionally a tiny upward grace-note flick into it, bright
    and friendly, decays fast. Additive, near-dry-ish, ~0.45s."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]              # A maj pentatonic, high
    i = int(rng.integers(0, len(HIGH)))
    f = freq(HIGH[i])
    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)
    # tiny upward grace flick at the very onset (a quick pitch lift settling)
    flick = 2 ** ((0.6 * np.exp(-t * 90.0)) / 12.0)   # ~+60 cents, gone in ~30ms
    phase = 2*np.pi*f*np.cumsum(flick)/SR
    sig = (
        1.00 * np.sin(phase)              * np.exp(-t*6.0) +
        0.38 * np.sin(2*phase)            * np.exp(-t*9.0) +
        0.15 * np.sin(3*phase)            * np.exp(-t*16.0) +
        0.06 * np.sin(2*np.pi*f*1.003*t)  * np.exp(-t*6.0)   # shimmer twin
    )
    sig = lowpass_fft(sig, 8600.0, order=2)
    env = adsr(n, a=0.005, d=0.25, s_level=0.0, r=0.12)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.49 / peak)
    return out


PLAN = {
    "wirefloor": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.62,
        "reverb": {"wet": 0.20, "decay": 2.6, "predelay_ms": 18, "brightness": 0.32},
    },
    "hammerbright": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73],
        "pans": [-0.18, 0.18, -0.1, 0.14, -0.16, 0.12, 0, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.30, "decay": 3.4, "predelay_ms": 24, "brightness": 0.58},
    },
    "hammerhigh": {
        "kind": "midi",
        "midis": [69, 71, 73, 76, 78, 81, 85],
        "pans": [0.2, -0.2, 0.15, -0.15, 0.25, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.30, "decay": 3.2, "predelay_ms": 22, "brightness": 0.6},
    },
    "sweetcourse": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1, 0, -0.12, 0.12],
        "target_peak": 0.82,
        "reverb": {"wet": 0.26, "decay": 3.0, "predelay_ms": 22, "brightness": 0.5},
    },
    "glintping": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.38, "decay": 3.4, "predelay_ms": 26, "brightness": 0.62},
    },
    "raindroplets": {
        "kind": "seed",
        "count": 6,
        "pans": [-0.3, 0.25, -0.4, 0.35, -0.2, 0.4],
        "target_peak": 0.78,
        "reverb": {"wet": 0.40, "decay": 3.6, "predelay_ms": 24, "brightness": 0.62},
    },
    "wirebloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.50, "decay": 5.2, "predelay_ms": 42, "brightness": 0.48},
    },
    "shimmercloud": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18, -0.12, 0.12],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.4, "predelay_ms": 45, "brightness": 0.5},
    },
    "frametap": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.7,
        "reverb": {"wet": 0.04, "decay": 0.6, "predelay_ms": 8, "brightness": 0.4},
    },
    "flickchirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.25],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 2.4, "predelay_ms": 16, "brightness": 0.62},
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
    print("shimmerwire:", name)


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
