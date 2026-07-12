#!/usr/bin/env python3
"""
sunraga — sample renderer (per-voice reverb from preset.json).

A santoor shimmering in morning light: struck-string courses raining bright
major sunlight. Many close strings per course give the santoor its shimmer —
each course here is built additively as a small cluster of slightly-detuned
sine "strings" struck together, with quick mallet flutter from fast-decaying
inharmonic partials (all kept under ~5x and decayed fast, never buzzy, never
FM). A Lydian @ A=432, radiant and cascading, devotional joy, never heavy.

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


def _course(f, t, detunes, amp_decay, seed):
    """A santoor 'course': several slightly-detuned sine strings struck
    together. The micro-detunes beat against each other -> the shimmering
    many-string santoor body. Returns summed mono of the strings only."""
    rng = np.random.default_rng(seed)
    body = np.zeros_like(t)
    for k, det in enumerate(detunes):
        ph = rng.uniform(0, 2*np.pi)
        body += np.sin(2*np.pi*f*det*t + ph) * np.exp(-t*amp_decay)
    body /= max(1, len(detunes))
    return body


# ---- bass (a low santoor course struck deep, warm resonant strings, bright tail) ----
def voice_bass(midi):
    """A low santoor course struck deep: a warm, round, multi-string body with
    a bright struck tail. Several slightly-detuned low strings give the
    resonant shimmer; a couple of fast inharmonic partials are the mallet glint
    at the strike (gone in ~60 ms). The drone-ground of the raga — one struck
    note, never a continuous drone. ~2.6s."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    # warm low course: 3 detuned strings, slow decay = sustaining ground
    strings = _course(f, t, [0.9965, 1.0, 1.0035], amp_decay=1.1, seed=int(midi)*13+1)
    # gentle octave for solidity + a just-fifth shimmer above
    strings += 0.30 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*1.8)
    strings += 0.14 * np.sin(2*np.pi*f*(3/2)*t) * np.exp(-t*2.4)

    # bright struck tail: quick high glint so it reads "struck", not bowed
    glint = (
        0.10 * np.sin(2*np.pi*f*3.01*t) * np.exp(-t*9.0) +
        0.05 * np.sin(2*np.pi*f*4.02*t) * np.exp(-t*16.0)
    )
    sig = strings + glint

    # struck attack: ~8 ms (no click), long warm decay
    env = adsr(n, a=0.008, d=1.6, s_level=0.0, r=0.8)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 2600.0, order=3)  # warm, keep a little bright tail
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead (mid santoor course, bright mallet-strike, shimmering many-string) ----
def voice_lead(midi):
    """The mid santoor course raining the melody: a bright mallet strike on a
    many-string course. 4 detuned strings shimmer; bright but consonant
    partials (octave, just-fifth, double-octave) sparkle and decay independently;
    a quick inharmonic mallet glint at the very onset. Cascading, radiant. ~1.9s."""
    f = freq(midi); dur = 1.9
    n = int(dur * SR); t = t_axis(dur)

    strings = _course(f, t, [0.997, 0.9995, 1.0005, 1.003], amp_decay=3.2,
                      seed=int(midi)*17+3)
    sig = (
        1.00 * strings +
        0.45 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*4.5) +   # bright octave
        0.20 * np.sin(2*np.pi*f*(3/2)*t) * np.exp(-t*5.5) +   # sweet fifth shimmer
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*7.0) +   # high glint
        0.05 * np.sin(2*np.pi*f*4.21*t)  * np.exp(-t*36.0)    # mallet tick (~28ms)
    )
    env = adsr(n, a=0.006, d=1.2, s_level=0.0, r=0.55)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6800.0, order=2)   # keep it bright but not glassy
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead2 (higher course, quicker brighter flutter, ornamenting above) ----
def voice_lead2(midi):
    """A higher santoor course, quicker and brighter — the ornamenting flutter
    above the lead. Faster decay, a touch more high glint and a quick double-
    strike flutter (a tiny second mallet hit ~35 ms in) that makes it 'flutter'
    the way santoor ornaments do. Still soft-attacked, never piercing. ~1.4s."""
    f = freq(midi); dur = 1.4
    n = int(dur * SR); t = t_axis(dur)

    strings = _course(f, t, [0.9975, 1.0, 1.0025], amp_decay=4.6,
                      seed=int(midi)*19+5)
    # quick mallet flutter: a faint second strike a hair later
    t2 = np.maximum(t - 0.035, 0.0)
    flutter = 0.5 * _course(f, t2, [0.9985, 1.0015], amp_decay=5.2,
                            seed=int(midi)*19+9) * (t >= 0.035)
    sig = (
        1.00 * strings + flutter +
        0.40 * np.sin(2*np.pi*f*2.0*t)  * np.exp(-t*6.0) +
        0.16 * np.sin(2*np.pi*f*3.0*t)  * np.exp(-t*8.5) +
        0.06 * np.sin(2*np.pi*f*4.31*t) * np.exp(-t*40.0)   # bright flick, gone fast
    )
    env = adsr(n, a=0.005, d=0.95, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7400.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (softly-struck warm course, rounder shimmer, sweet resonant middle) ----
def voice_tone(midi):
    """A softly-struck warm santoor course — the sweet resonant middle. Rounder
    and slower than the lead: gentle detuned strings, a soft octave, no bright
    glint to speak of, and a slow chorusy shimmer. Lowpassed warm so it sings
    rather than rings. ~2.4s."""
    f = freq(midi); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)

    strings = _course(f, t, [0.9967, 1.0, 1.0033], amp_decay=2.0,
                      seed=int(midi)*23+7)
    sig = (
        1.00 * strings +
        0.30 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.6) +   # soft octave
        0.10 * np.sin(2*np.pi*f*(3/2)*t) * np.exp(-t*3.2)     # gentle fifth
    )
    # slow shimmer so the held middle breathes
    vib = 1.0 + 0.0022 * np.sin(2*np.pi*4.0*t)
    sig = sig * vib
    env = adsr(n, a=0.012, d=0.9, s_level=0.45, r=1.2)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4200.0, order=3)  # rounder, sweet
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chime (high single-string ping with bright glint, medium reverb) ----
def voice_chime(midi):
    """A high single-string santoor ping with a bright glint. Mostly one clean
    struck string (a single course string, only the faintest detune twin) with
    a sweet octave and a quick high sparkle that fades in ~40 ms. A radiant
    little drop of light. ~2.0s."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)          * np.exp(-t*2.2) +
        0.16 * np.sin(2*np.pi*f*1.003*t)    * np.exp(-t*2.4) +  # faint twin
        0.40 * np.sin(2*np.pi*f*2.0*t)      * np.exp(-t*3.2) +  # sweet octave
        0.14 * np.sin(2*np.pi*f*3.0*t)      * np.exp(-t*5.0) +  # glass color
        0.05 * np.sin(2*np.pi*f*4.0*t)      * np.exp(-t*9.0)    # tiny glint
    )
    env = adsr(n, a=0.010, d=1.6, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7200.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (fast mallet-flutter on top strings, cascading bright droplets) ----
def voice_sparkle(seed):
    """Fast mallet-flutter on the top strings: cascading bright droplets, each a
    tiny high santoor ping, sprinkled in a quick rising run from the HIGH Lydian
    set. Delay echoes (added live at playback) trail them. Additive sines only,
    soft-attacked, warm-topped. ~1.6s of cascade."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 80, 81, 85, 88]      # A Lydian, high register
    dur = 1.6
    n = int(dur * SR); t = t_axis(dur)
    out = np.zeros(n)
    # 5-6 droplets cascading upward, quick spacing -> mallet flutter
    count = int(rng.integers(5, 7))
    idxs = sorted(rng.choice(len(HIGH), size=count, replace=False))
    for k, ix in enumerate(idxs):
        m = HIGH[ix]
        f = freq(m)
        offset = int((0.02 + k*0.085 + rng.uniform(0, 0.02)) * SR)
        if offset >= n:
            break
        tt = t[:n-offset]
        drop = (
            np.sin(2*np.pi*f*tt)        * np.exp(-tt*7.0) +
            0.30*np.sin(2*np.pi*f*2.0*tt)*np.exp(-tt*9.0) +
            0.08*np.sin(2*np.pi*f*3.0*tt)*np.exp(-tt*14.0)
        )
        denv = adsr(len(tt), a=0.005, d=0.5, s_level=0.0, r=0.25)
        drop = drop[:denv.size] * denv[:drop.size]
        out[offset:offset+drop.size] += drop * (0.95 - 0.05*k)
    out = lowpass_fft(out, 7600.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- bloom (bowed-santoor swell of sympathetic strings ringing together) ----
def voice_bloom(midi):
    """A bowed-santoor swell — sympathetic strings ringing together into a lush
    blooming raga wash. From the root we ring a Lydian-safe chord (root, maj3,
    fifth, maj6/9, octave) as bowed, slowly-swelling detuned string pairs. A
    moving lowpass opens the brightness as it blooms, then settles. Warm, never
    glassy, never heavy. ~6.5s."""
    f0 = freq(midi)
    intervals = [0, 4, 7, 9, 12]   # Lydian-consonant raga stack
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(midi + iv)
        # bowed string pair: two faint detunes ringing sympathetically
        partial = (
            np.sin(2*np.pi*f*t) +
            0.5*np.sin(2*np.pi*f*1.0035*t) +
            0.5*np.sin(2*np.pi*f*0.9965*t)
        )
        partial += 0.18*np.sin(2*np.pi*f*2.0*t)   # soft octave halo
        vib = 1.0 + 0.0020*np.sin(2*np.pi*0.26*t + i*0.8)
        stagger = 0.22 * i
        env = adsr(n, a=1.4 + stagger, d=0.8, s_level=0.80, hold=1.2, r=2.6)
        sig += partial * vib * env[:n] * (1.0 - 0.09*i)
    sig /= len(intervals)
    low = lowpass_fft(sig, 650.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75*(0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.82), 1.0)))
    sig = low + high*open_curve
    sig = lowpass_fft(sig, 3000.0, order=3)   # warm ceiling, no glass
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- cluster (rapid santoor tremolo across courses, shimmering struck cloud) ----
def voice_cluster(midi):
    """A rapid santoor tremolo across courses — the shimmering struck-string
    cloud, radiant. From the root we voice a Lydian chord and re-strike each
    note in fast tremolo (the santoor's signature rolling mallets), the strikes
    staggered so it glitters like sun on water. Bright but warm-topped. ~6.0s."""
    intervals = [0, 4, 7, 9, 12]
    dur = 6.0
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi)*29 + 11)
    sig = np.zeros(n)
    trem_hz = 13.0   # rolling mallet rate
    for i, iv in enumerate(intervals):
        f = freq(midi + iv)
        # tremolo amplitude: raised-cosine pulses at trem_hz, never to zero
        trem = 0.55 + 0.45*np.abs(np.sin(2*np.pi*trem_hz*t + i*0.7))
        strings = (
            np.sin(2*np.pi*f*t) +
            0.4*np.sin(2*np.pi*f*1.003*t) +
            0.2*np.sin(2*np.pi*f*2.0*t)
        )
        # bright per-strike glint that rides the tremolo, kept under 5x, fast
        glint = 0.10*np.sin(2*np.pi*f*3.0*t)
        voice = (strings + glint) * trem
        # slow overall swell so the cloud blooms in and settles
        env = adsr(n, a=0.9 + 0.15*i, d=1.0, s_level=0.75, hold=1.4, r=2.2)
        sig += voice * env[:n] * (1.0 - 0.08*i)
    sig /= len(intervals)
    sig = lowpass_fft(sig, 5200.0, order=3)  # radiant but not harsh
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- tap (damped mallet tap on the bridge, near-dry wooden click, the pulse) ----
def voice_tap(seed):
    """A damped mallet tap on the santoor bridge — a near-dry little wooden
    click, the rhythmic pulse. A short tuned woody body (a couple of fast
    inharmonic partials near the bridge pitch) plus a soft band-limited noise
    contact, all damped in ~50 ms. Warm, dry, never a sharp click. ~0.16s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.16
    n = int(dur * SR); t = t_axis(dur)
    # bridge wood pitch, slight per-tap wobble so taps feel hand-played
    base = 660.0 * (2 ** (rng.uniform(-0.2, 0.2) / 12.0))
    body = (
        1.00 * np.sin(2*np.pi*base*t)        * np.exp(-t*55) +
        0.45 * np.sin(2*np.pi*base*1.51*t)   * np.exp(-t*80) +
        0.16 * np.sin(2*np.pi*base*2.43*t)   * np.exp(-t*120)
    )
    # soft contact: short band of warm noise (the felt mallet on the bridge)
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 2400.0, order=3) - lowpass_fft(noise, 300.0, order=2)
    nenv = adsr(n, a=0.0025, d=0.030, s_level=0.0, r=0.0)
    sig = 0.7*body + 0.45*noise*nenv
    benv = adsr(n, a=0.003, d=0.08, s_level=0.0, r=0.04)
    out = sig[:benv.size] * benv[:sig.size]
    out = lowpass_fft(out, 3800.0, order=4)   # keep it woody/dry
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chirp (bright top-string flick, a radiant little raga accent) ----
def voice_chirp(seed):
    """A bright top-string flick — a radiant little raga accent. A quick rising
    2-note blip from the HIGH Lydian set: a struck top string that lifts and
    settles, with a glassy octave sheen and a tiny mallet chiff at the onset.
    Additive sines, near-dry, ~0.4s. Cheerful, devotional, never piercing."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 80, 81, 85, 88]    # A Lydian high
    leaps = [2, 3, 4]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)         # smoothstep
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR
    sig = (
        np.sin(phase) +
        0.20 * np.sin(2*phase) +                 # glassy octave sheen
        0.06 * np.sin(3*phase) * np.exp(-t*16)   # mallet chiff at onset
    )
    sig = lowpass_fft(sig, 7000.0, order=3)
    env = adsr(n, a=0.010, d=0.12, s_level=0.5, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.62,
        "reverb": {"wet": 0.12, "decay": 1.8, "predelay_ms": 14, "brightness": 0.4},
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 63, 64, 66, 68, 69, 71, 73, 76],
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.2, "decay": 1.8, "predelay_ms": 20, "brightness": 0.6},
    },
    "lead2": {
        "kind": "midi",
        "midis": [64, 66, 68, 69, 71, 73, 75, 76, 78, 80, 81],
        "pans": [0.25, -0.2, 0.3, -0.25],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 1.9, "predelay_ms": 18, "brightness": 0.62},
    },
    "tone": {
        "kind": "midi",
        "midis": [57, 61, 63, 64, 68, 69, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 2.4, "predelay_ms": 22, "brightness": 0.5},
    },
    "chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 80, 81, 85, 88],
        "pans": [-0.4, 0.3, -0.2, 0.4, -0.3, 0.2, 0, 0.35],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.6},
    },
    "sparkle": {
        "kind": "seed",
        "count": 5,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.4, "decay": 3.4, "predelay_ms": 26, "brightness": 0.62},
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.2, "predelay_ms": 45, "brightness": 0.45},
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.8, "predelay_ms": 40, "brightness": 0.5},
    },
    "tap": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.25, 0.2, -0.1, 0.3],
        "target_peak": 0.7,
        "reverb": {"wet": 0.04, "decay": 0.6, "predelay_ms": 8, "brightness": 0.42},
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.78,
        "reverb": {"wet": 0.12, "decay": 1.6, "predelay_ms": 12, "brightness": 0.62},
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
    print("sunraga:", name)


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
