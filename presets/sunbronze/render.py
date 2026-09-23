#!/usr/bin/env python3
"""
sunbronze — sample renderer (per-voice reverb from preset.json).

A major-tuned gamelan shimmering in tropical sunlight: bronze bells beating
golden. Struck bronze metallophone bars with bright inharmonic partials and
the characteristic paired-tuning shimmer-beat (two slightly-detuned strikes
producing a slow golden amplitude beat). Sunny major gamelan — radiant,
interlocking, joyful. A major @ A=432, additive only, never dreary.

Per-voice REVERB lives in preset.json voices.<name>.reverb (baked here);
per-voice DELAY is a live playback echo handled by event.py.

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


# --- shared bronze helper: a struck metallophone bar with inharmonic partials
# and paired-tuning shimmer-beat. Two near-unison copies (detuned a few cents)
# give the slow golden beating that defines gamelan bronze. All partials decay
# independently; nothing harsh above ~5x survives long. ---
def _bronze_bar(f, t, partials, beat_cents=7.0, beat_mix=0.9):
    """partials: list of (ratio, amp, decay_rate). Returns mono bronze tone.
    beat_cents: detune of the paired strike (the shimmer-beat)."""
    det = 2 ** (beat_cents / 1200.0)
    sig = np.zeros_like(t)
    for ratio, amp, dec in partials:
        sig += amp * np.sin(2*np.pi*f*ratio*t) * np.exp(-t*dec)
        # paired-tuning twin, slightly detuned -> slow beating shimmer
        sig += beat_mix * amp * np.sin(2*np.pi*f*ratio*det*t) * np.exp(-t*dec)
    return sig


# ---- bass (gong-bar — a low bronze gong-bar struck deep, the golden ground) ----
def voice_gongbar(arg):
    """A low gong-bar struck deep: warm bronze boom with a shimmering beat and
    a long golden tail, the ground the whole gamelan stands on. A round low
    fundamental, a soft octave and a gentle gong-ish inharmonic (2.7x) that
    dies fast, plus the paired-tuning shimmer-beat slow and wide. Felt low,
    never harsh, never dark. arg = midi (LOW)."""
    f = freq(int(arg))
    dur = 4.2
    n = int(dur * SR); t = t_axis(dur)
    partials = [
        (1.00, 1.00, 0.7),    # deep round fundamental, long tail
        (2.00, 0.30, 1.4),    # soft octave shimmer
        (2.70, 0.12, 3.2),    # gong inharmonic, gone fast (the 'boom' edge)
        (3.92, 0.05, 5.0),    # faint high glint, dies quick
    ]
    sig = _bronze_bar(f, t, partials, beat_cents=5.0, beat_mix=0.85)
    # slow breathing so the golden ground feels alive
    sig = sig * (1.0 + 0.05*np.sin(2*np.pi*0.5*t))
    env = adsr(n, a=0.012, d=2.0, s_level=0.30, hold=0.5, r=1.6)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 1600.0, order=4)   # keep it round/warm, bronze not bright
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead (saron-bar — bright bronze strike ringing the interlocking melody) ----
def voice_saron(arg):
    """A saron-bar strike: bright bronze tone with the paired-tuning shimmer-beat,
    ringing out the interlocking melody. Strong fundamental, a clean octave, a
    bright inharmonic gamelan partial (~2.4x) and a quick mallet glint that dies
    in ~30ms. The detuned twin gives the golden beating. Bright but rounded —
    lowpassed so it sings, never screeches. arg = midi."""
    f = freq(int(arg))
    dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    partials = [
        (1.00, 1.00, 1.6),    # singing fundamental
        (2.00, 0.42, 2.4),    # clean octave
        (2.41, 0.22, 4.0),    # bronze inharmonic gamelan color, decays fast
        (3.84, 0.08, 7.0),    # mallet glint, gone quick
        (4.92, 0.04, 11.0),   # faint top shimmer, dies in ~30ms
    ]
    sig = _bronze_bar(f, t, partials, beat_cents=8.0, beat_mix=0.85)
    # soft strike, no click; bright bouncy decay
    env = adsr(n, a=0.006, d=1.2, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (peking-bar — brighter, quicker, ornamenting above in fast interlock) ----
def voice_peking(arg):
    """A higher peking-bar: brighter and quicker than the saron, ornamenting
    above in fast interlock. Shorter ring, snappier bronze inharmonics, the
    shimmer-beat a touch faster (wider detune). Quick decay so it reads as a
    crisp interlocking ornament. arg = midi (upper register)."""
    f = freq(int(arg))
    dur = 1.3
    n = int(dur * SR); t = t_axis(dur)
    partials = [
        (1.00, 1.00, 2.6),    # snappy fundamental
        (2.00, 0.40, 3.8),    # octave
        (2.41, 0.20, 6.0),    # bronze inharmonic
        (3.84, 0.07, 10.0),   # glint, fast
        (4.92, 0.03, 16.0),   # tiny top, instant
    ]
    sig = _bronze_bar(f, t, partials, beat_cents=10.0, beat_mix=0.8)
    env = adsr(n, a=0.005, d=0.8, s_level=0.0, r=0.3)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (demung-bar — struck soft, rounder bronze shimmer, sweet golden middle) ----
def voice_demung(arg):
    """A demung-bar struck soft: rounder, warmer bronze shimmer, the sweet
    golden middle of the gamelan. Mellower than the saron — the high inharmonics
    are gentler and the tone is lowpassed warm, with a slow wide shimmer-beat
    that breathes. Sustains sweetly. arg = midi (mid register)."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    partials = [
        (1.00, 1.00, 0.9),    # warm sustaining fundamental
        (2.00, 0.34, 1.8),    # soft octave
        (2.41, 0.12, 3.6),    # gentle bronze color, fades
        (3.00, 0.07, 4.5),    # soft consonant sweetener
    ]
    sig = _bronze_bar(f, t, partials, beat_cents=6.0, beat_mix=0.9)
    env = adsr(n, a=0.012, d=1.0, s_level=0.40, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4000.0, order=3)   # rounder, sweeter than the leads
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- chime (gender-bar — high bronze ping with bright beating glint) ----
def voice_gender(arg):
    """A high gender-bar ping: a bright bronze chime with a beating glint, the
    sparkling high voice of the gamelan. Clear fundamental, an octave celeste
    doubling, sweet bronze inharmonics that decay independently, and the
    paired-tuning shimmer-beat giving that glinting golden flutter. Soft 14ms
    attack — no click. arg = midi (high)."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    partials = [
        (1.00, 1.00, 1.2),    # clear bell body
        (2.00, 0.52, 1.7),    # octave celeste doubling
        (2.76, 0.18, 3.0),    # bronze bell inharmonic, sweet
        (3.00, 0.10, 3.6),    # consonant glass color
        (4.80, 0.05, 6.0),    # tiny high glint, gone fast
    ]
    sig = _bronze_bar(f, t, partials, beat_cents=9.0, beat_mix=0.9)
    env = adsr(n, a=0.014, d=1.8, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (top-bar flicks shimmering, scattered with delay echoes) ----
def voice_topflick(arg):
    """Tiny top-bar flicks: little high bronze flecks shimmering with the beat,
    scattered (event.py adds delay echoes). Short, bright, beating glints of
    bronze. A quick high ping with fast-decaying inharmonics and a wide
    shimmer-beat. Soft attack, no click. arg = midi (top register)."""
    f = freq(int(arg))
    dur = 0.9
    n = int(dur * SR); t = t_axis(dur)
    partials = [
        (1.00, 1.00, 4.0),    # bright quick ping
        (2.00, 0.40, 6.0),    # octave
        (2.76, 0.14, 9.0),    # bronze glint
        (4.80, 0.05, 14.0),   # top fleck, instant
    ]
    sig = _bronze_bar(f, t, partials, beat_cents=11.0, beat_mix=0.85)
    env = adsr(n, a=0.006, d=0.5, s_level=0.0, r=0.25)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 8000.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (a swell of overlapping bronze tails beating together) ----
def voice_bronzebloom(arg):
    """A swell of overlapping bronze tails beating together: a lush blooming
    gamelan wash. From the passed root we build a soft major chord of struck
    bars (root, maj3, 5th, octave) whose long tails overlap and shimmer-beat
    into a golden haze. Slow swell-in (no click), brightness opens as it blooms,
    lush long tail. arg = midi (mid root)."""
    root = int(arg)
    intervals = [0, 4, 7, 12]
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partials = [
            (1.00, 1.00, 0.6),
            (2.00, 0.28, 1.2),
            (2.41, 0.08, 2.6),
        ]
        voice = _bronze_bar(f, t, partials, beat_cents=6.0 + 1.5*i, beat_mix=0.9)
        # staggered swell so tails layer into a bloom
        stagger = 0.4 * i
        env = adsr(n, a=1.4 + stagger, d=1.2, s_level=0.6, hold=1.0, r=2.6)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    # brightness opens as it blooms
    low = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.30 + 0.70 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 3000.0, order=3)   # round golden ceiling
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.50 / peak)
    return sig


# ---- cluster (imbal — interlocking hocketed bronze cloud, radiant) ----
def voice_imbal(arg):
    """An interlocking imbal pattern: a shimmering hocketed bronze cloud,
    radiant and welcoming. From the root we build a bright major-pentatonic
    spray of struck bars (root, +4, +7, +9, +12) but each enters at a
    staggered, slightly-offset onset so they interlock like two players
    hocketing — a radiant golden cloud that blooms open. All shimmer-beating.
    arg = midi (root)."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    onsets = [0.0, 0.22, 0.10, 0.34, 0.16]   # interlocking hocket offsets (s)
    dur = 7.2
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partials = [
            (1.00, 1.00, 1.0),
            (2.00, 0.34, 2.0),
            (2.41, 0.12, 3.6),
            (3.00, 0.06, 4.5),
        ]
        voice = _bronze_bar(f, t, partials, beat_cents=7.0 + 1.0*i, beat_mix=0.88)
        # interlocking entrance: shift this bar's strike later in time
        shift = int(onsets[i] * SR)
        v = np.zeros(n)
        if shift < n:
            v[shift:] = voice[:n - shift]
        env = adsr(n, a=1.2 + 0.18*i, d=0.8, s_level=0.7, hold=1.4, r=2.4)
        gain = 1.0 - 0.08*i
        sig += v * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 3200.0, order=3)   # radiant but warm
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.50 / peak)
    return sig


# ---- tap (damped bar tap — near-dry mallet-on-bronze click, the pulse) ----
def voice_damptap(arg):
    """A damped bar tap: a near-dry mallet-on-bronze click, the rhythmic pulse.
    The bar is struck but immediately damped, so you hear the bright contact
    'tink' and only a flash of pitched bronze before it's choked. Short,
    crisp, in-the-room. Soft 2.5ms attack — tactile, never a raw click.
    arg = midi (anchored mid)."""
    f = freq(int(arg))
    dur = 0.16
    n = int(dur * SR); t = t_axis(dur)
    # very fast pitched flash (damped immediately)
    body = (
        1.00 * np.sin(2*np.pi*f*t)      * np.exp(-t*55) +
        0.45 * np.sin(2*np.pi*f*2.0*t)  * np.exp(-t*80) +
        0.18 * np.sin(2*np.pi*f*2.41*t) * np.exp(-t*120)
    )
    # bright contact transient: short band-limited noise 'tink'
    rng = np.random.default_rng(int(arg) * 31 + 11)
    noise = rng.standard_normal(n)
    tink = lowpass_fft(noise, 4200.0, order=3) - lowpass_fft(noise, 800.0, order=2)
    t_env = adsr(n, a=0.0025, d=0.020, s_level=0.0, r=0.004)
    tink = tink * t_env
    b_env = adsr(n, a=0.0025, d=0.045, s_level=0.0, r=0.01)
    body = body * b_env
    out = body * 0.7 + tink * 0.4
    out = lowpass_fft(out, 5500.0, order=3)
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chirp (bright top-bar flick — a golden little gamelan accent) ----
def voice_goldchirp(seed):
    """A bright top-bar flick — a golden little gamelan accent. A quick struck
    high bronze flick that picks a note from the HIGH A-major register and adds
    a tiny upward neighbor grace, shimmer-beating, cheerful. Additive, near-dry,
    ~0.5s. Seed picks the note + grace so each accent is a fresh little glint."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]      # A major, high register
    i = int(rng.integers(0, len(HIGH)))
    m = HIGH[i]
    f = freq(m)
    grace = freq(m + int(rng.choice([2, 3, 4])))   # small upward neighbor
    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)
    # quick grace-into-note: brief lower onset bending up
    rise = np.clip(t / 0.04, 0.0, 1.0)
    rise = rise*rise*(3 - 2*rise)
    f_t = grace + (f - grace) * rise
    det = 2 ** (10.0/1200.0)
    phase = 2*np.pi*np.cumsum(f_t)/SR
    sig = (
        np.sin(phase) +
        0.9*np.sin(phase*det) +              # shimmer-beat twin
        0.30*np.sin(2*phase) * np.exp(-t*6) +    # octave glint
        0.10*np.sin(2.76*phase) * np.exp(-t*12)  # bronze inharmonic, gone fast
    )
    sig = lowpass_fft(sig, 8000.0, order=3)
    env = adsr(n, a=0.006, d=0.30, s_level=0.0, r=0.16)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "gongbar": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.62,
        "reverb": {"wet": 0.30, "decay": 4.0, "predelay_ms": 35, "brightness": 0.30},
    },
    "saron": {
        "kind": "midi",
        "midis": [57, 59, 61, 62, 64, 66, 69, 71, 73, 74, 76],
        "pans": [-0.2, 0.2, -0.1, 0.15, 0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 3.4, "predelay_ms": 26, "brightness": 0.55},
    },
    "peking": {
        "kind": "midi",
        "midis": [69, 71, 73, 74, 76, 78, 80, 81],
        "pans": [0.25, -0.2, 0.3, -0.25, 0.15, -0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.32, "decay": 2.8, "predelay_ms": 22, "brightness": 0.6},
    },
    "demung": {
        "kind": "midi",
        "midis": [52, 57, 59, 61, 64, 66, 69],
        "pans": [-0.12, 0.12, 0, -0.1, 0.1],
        "target_peak": 0.82,
        "reverb": {"wet": 0.30, "decay": 3.2, "predelay_ms": 24, "brightness": 0.42},
    },
    "gender": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.4, 0.3, -0.2, 0.4, -0.3, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.40, "decay": 3.4, "predelay_ms": 28, "brightness": 0.62},
    },
    "topflick": {
        "kind": "midi",
        "midis": [76, 78, 81, 85, 88],
        "pans": [-0.4, 0.4, -0.25, 0.3, 0],
        "target_peak": 0.78,
        "reverb": {"wet": 0.38, "decay": 2.6, "predelay_ms": 20, "brightness": 0.62},
    },
    "bronzebloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.4, "predelay_ms": 45, "brightness": 0.45},
    },
    "imbal": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.50, "decay": 5.0, "predelay_ms": 42, "brightness": 0.48},
    },
    "damptap": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [-0.2, 0.2, -0.1, 0.15, 0],
        "target_peak": 0.82,
        "reverb": {"wet": 0.06, "decay": 0.6, "predelay_ms": 8, "brightness": 0.45},
    },
    "goldchirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.8,
        "reverb": {"wet": 0.16, "decay": 1.8, "predelay_ms": 14, "brightness": 0.62},
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
    print("sunbronze:", name)


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
