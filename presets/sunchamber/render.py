#!/usr/bin/env python3
"""
sunchamber — sample renderer (per-voice reverb from preset.json).

Bright chamber strings: pizzicato sparkling and soft arco glowing, sunlit and
gentle. A small string ensemble both plucked (dry bouncy) and bowed (warm soft
swell) — elegant, warm-bright, tender, never severe. A major @ A=432, additive
only, hall reverb character, never dreary.

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


# ---- bass (low double-bass pizzicato — round woody pluck, warm body) ----
def voice_bass(arg):
    """A low double-bass pizzicato: a round woody pluck with warm body, the
    gentle chamber ground. Additive string partials (1,2,3,4,5) with a soft
    pluck transient and natural per-partial decay; the higher partials die
    fast so it reads as a warm round 'thoom-pluck', never a buzz. A tiny
    finger-on-string noise puff at the onset gives the pizz contact. Near-dry,
    warm-lowpassed. arg = midi (LOW)."""
    f = freq(int(arg))
    dur = 1.6
    n = int(dur * SR); t = t_axis(dur)

    # string partials: amplitude falls with partial number, decay rises -> warm
    sig = (
        1.00 * np.sin(2*np.pi*f*1*t)   * np.exp(-t*3.0) +
        0.55 * np.sin(2*np.pi*f*2*t)   * np.exp(-t*5.0) +
        0.26 * np.sin(2*np.pi*f*3*t)   * np.exp(-t*8.0) +
        0.12 * np.sin(2*np.pi*f*4*t)   * np.exp(-t*12.0) +
        0.05 * np.sin(2*np.pi*f*5*t)   * np.exp(-t*18.0)
    )
    # gentle detune twin for woody body life
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*3.0)

    # pizz contact: short low-passed noise puff (finger releasing the string)
    rng = np.random.default_rng(int(arg) * 19 + 3)
    puff = rng.standard_normal(n)
    puff = lowpass_fft(puff, 600.0, order=3)
    puff_env = np.exp(-t * 90.0)
    sig = sig + 0.14 * puff * puff_env

    # warm round: keep it dark and woody, no harsh top
    sig = lowpass_fft(sig, 1400.0, order=4)

    # soft pluck attack (~6 ms, no click), natural decay tail
    env = adsr(n, a=0.006, d=0.7, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- lead (violin arco — warm bowed tone, soft vibrato, sings the melody) ----
def voice_lead(arg):
    """A violin arco swelling in over ~30 ms, warm bowed tone with soft vibrato,
    singing the sunlit melody. Additive sawtooth-ish bowed body (harmonics with
    gentle 1/n falloff, all tamed by a warm lowpass) + a vibrato that fades in
    after the bow speaks, so it sings rather than warbles. ~2.2s. arg = midi."""
    f = freq(int(arg)); dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    # vibrato fades in after the attack (singing, not wobbly)
    vib_depth = 0.004 * np.clip((t - 0.25) / 0.5, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.5*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    # bowed body: gentle harmonic series, soft 1/n falloff (warm, not buzzy)
    sig = np.zeros(n)
    amps = [1.0, 0.55, 0.34, 0.20, 0.12, 0.07]
    for k, a in enumerate(amps, start=1):
        sig += a * np.sin(k * phase)
    # faint detune twin = the warmth of bow hair / ensemble shimmer
    sig += 0.16 * np.sin(2*np.pi*f*1.004 * np.cumsum(np.ones(n)) / SR)

    # warm the tone so harmonics glow, never rasp
    sig = lowpass_fft(sig, 3600.0, order=3)

    # soft 30 ms swell-in, singing sustain, smooth release
    env = adsr(n, a=0.030, d=0.5, s_level=0.6, hold=0.3, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (viola pizzicato — dry bouncy pluck, dancing counter-line) ----
def voice_lead2(arg):
    """A viola pizzicato: a dry bouncy pluck dancing a counter-line under the
    bow. Additive string partials with quick natural decay (medium register,
    rounder/darker than violin), a short pizz contact tick, light reverb. The
    pluck is bouncy but warm — partials above ~5x die almost instantly. ~1.1s.
    arg = midi."""
    f = freq(int(arg)); dur = 1.1
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*1*t)   * np.exp(-t*5.0) +
        0.50 * np.sin(2*np.pi*f*2*t)   * np.exp(-t*7.5) +
        0.24 * np.sin(2*np.pi*f*3*t)   * np.exp(-t*11.0) +
        0.11 * np.sin(2*np.pi*f*4*t)   * np.exp(-t*16.0) +
        0.05 * np.sin(2*np.pi*f*5*t)   * np.exp(-t*26.0)
    )
    sig += 0.08 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*5.0)

    # pizz contact tick (finger release), short and warm
    rng = np.random.default_rng(int(arg) * 23 + 11)
    tick = rng.standard_normal(n)
    tick = lowpass_fft(tick, 2400.0, order=3)
    sig = sig + 0.16 * tick * np.exp(-t * 140.0)

    sig = lowpass_fft(sig, 4200.0, order=4)
    # soft pluck attack (~5 ms), natural bouncy decay
    env = adsr(n, a=0.005, d=0.5, s_level=0.0, r=0.35)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.03, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (cello arco struck soft — round warm bow, sweet glowing middle) ----
def voice_tone(arg):
    """A cello arco struck soft: a round warm bow, the sweet glowing middle.
    Additive bowed harmonics with a soft attack and a warm low-passed body, a
    slow gentle vibrato fading in. Rounder and darker than the violin lead —
    the cello sits in the chest of the ensemble. ~2.6s. arg = midi."""
    f = freq(int(arg)); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    vib_depth = 0.0032 * np.clip((t - 0.35) / 0.6, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*4.6*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = np.zeros(n)
    amps = [1.0, 0.50, 0.28, 0.15, 0.08]
    for k, a in enumerate(amps, start=1):
        sig += a * np.sin(k * phase)
    # warm detune body
    sig += 0.14 * np.sin(2*np.pi*f*1.003 * np.cumsum(np.ones(n)) / SR)

    # cello is round and warm — roll off the top more than the violin
    sig = lowpass_fft(sig, 2600.0, order=3)

    env = adsr(n, a=0.040, d=0.7, s_level=0.6, hold=0.4, r=1.1)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- chime (high violin harmonic — flute-pure bell tone, light shimmer) ----
def voice_chime(arg):
    """A high violin harmonic: a flute-pure bell tone with light shimmer. Almost
    a pure sine fundamental (a played natural harmonic) with only a whisper of
    octave and a faint airy partial that fades in late as a shimmer. Sweet, glassy
    but never harsh, medium reverb. ~2.4s. arg = midi (HIGH)."""
    f = freq(int(arg)); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)

    # very gentle shimmer vibrato (bow on the harmonic node)
    vib = 1.0 + 0.0018 * np.clip((t - 0.3) / 0.6, 0, 1) * np.sin(2*np.pi*5.2*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = (
        1.00 * np.sin(phase) +
        0.16 * np.sin(2*phase) * np.exp(-t*1.4) +     # faint octave glow
        0.06 * np.sin(3*phase) * np.exp(-t*2.6)       # tiny sweetener, gone fast
    )
    # airy high shimmer that fades IN late then drifts (the harmonic 'ring')
    shimmer = np.clip((t - 0.5) / 1.2, 0, 1) * np.exp(-np.maximum(t-1.6, 0)/1.4)
    sig += 0.10 * np.sin(2*np.pi*f*2.005*t) * shimmer

    sig = lowpass_fft(sig, 6500.0, order=3)
    env = adsr(n, a=0.018, d=1.0, s_level=0.5, hold=0.2, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- sparkle (tiny top-string pizzicato flicks — sparkling, light delay) ----
def voice_sparkle(seed):
    """Tiny top-string pizzicato flicks sparkling, with light delay echoes (the
    echo is the live playback delay in preset.json). A quick bright high pluck:
    short additive string partials decaying very fast, a tiny contact tick, near
    the top of the register. Seed picks a HIGH pentatonic note so each flick
    sparkles at a slightly different pitch. ~0.5s, bright but rounded."""
    rng = np.random.default_rng(int(seed))
    HIGH = [76, 78, 81, 85, 88]
    m = HIGH[int(rng.integers(0, len(HIGH)))]
    f = freq(m)
    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)

    sig = (
        1.00 * np.sin(2*np.pi*f*1*t)   * np.exp(-t*9.0) +
        0.42 * np.sin(2*np.pi*f*2*t)   * np.exp(-t*14.0) +
        0.18 * np.sin(2*np.pi*f*3*t)   * np.exp(-t*22.0) +
        0.07 * np.sin(2*np.pi*f*4*t)   * np.exp(-t*34.0)
    )
    # tiny bright pizz tick
    tick = rng.standard_normal(n)
    tick = lowpass_fft(tick, 5000.0, order=3)
    sig = sig + 0.14 * tick * np.exp(-t * 220.0)

    sig = lowpass_fft(sig, 6500.0, order=3)
    env = adsr(n, a=0.004, d=0.25, s_level=0.0, r=0.18)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.03, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (full arco-ensemble swell — warm bowed strings blooming open) ----
def voice_bloom(arg):
    """A full arco-ensemble swell: warm bowed strings blooming open, a lush
    sunlit hall wash. Additive: a fundamental with just-major-third and fifth
    above (5/4, 3/2 — sweet, consonant, A-major-safe), a soft octave halo, and
    a warm sub for body. Several slightly-detuned copies give the breathing
    ensemble shimmer. A moving lowpass 'opens' the brightness over the swell.
    ~7s, lush. arg = midi."""
    f = freq(int(arg)); dur = 7.0
    n = int(dur * SR); t = t_axis(dur)

    vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.3*t)

    # ensemble fundamental: a few faint detunes (warm chorus, the section)
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.42 * np.sin(2*np.pi*f*1.0035*t) +
        0.42 * np.sin(2*np.pi*f*0.9967*t) +
        0.22 * np.sin(2*np.pi*f*1.0061*t)
    )
    third  = 0.42 * np.sin(2*np.pi*f*(5/4)*t*vib)
    fifth  = 0.36 * np.sin(2*np.pi*f*(3/2)*t*vib)
    octave = 0.24 * np.sin(2*np.pi*f*2.0*t)
    sub    = 0.26 * np.sin(2*np.pi*f*0.5*t)

    sig = fund + third + fifth + octave + sub

    # bloom: brightness opens over the swell (moving lowpass blend)
    low  = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    # warm ceiling — keep it round and sunlit, no rasp
    sig = lowpass_fft(sig, 3000.0, order=3)

    env = adsr(n, a=1.4, d=1.0, s_level=0.85, hold=1.2, r=3.0)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- cluster (shimmering tremolo-bowed chord — gentle string cloud) ----
def voice_cluster(arg):
    """A shimmering tremolo-bowed chord: a gentle warm-bright string cloud. From
    the passed root we build an A-major-safe chord (root, +4 maj3, +7 fifth,
    +9 maj6, +12 octave). Each note is bowed-additive with a fast tremolo
    amplitude flutter (the bow shimmering) and a slow swell. Warm low-passed so
    the cloud glows over the room without harshness. ~7s. arg = root midi."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        # bowed body: fundamental + soft 2nd/3rd partials
        partial = (np.sin(2*np.pi*f*t)
                   + 0.30*np.sin(2*np.pi*2*f*t)
                   + 0.12*np.sin(2*np.pi*3*f*t))
        # tremolo shimmer: gentle fast amplitude flutter, phased per voice
        trem = 1.0 + 0.18 * np.sin(2*np.pi*(6.0 + 0.4*i)*t + i*1.3)
        # slow breathing detune twin
        detune = np.sin(2*np.pi*f*1.0035*t)
        voice = (0.85*partial + 0.32*detune) * trem
        stagger = 0.16 * i
        env = adsr(n, a=1.6 + stagger, d=0.7, s_level=0.82, hold=1.4, r=2.6)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 3000.0, order=3)
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- tap (muted col-legno tap — near-dry woody bow-click, rhythmic pulse) ----
def voice_tap(seed):
    """A muted col-legno tap: a near-dry woody bow-click, the rhythmic pulse.
    The wood of the bow tapped on the string — a short tuned woody body (a
    couple of fast-decaying mid partials around a fixed tap pitch) plus a soft
    band-limited noise contact transient. Short, dry, warm — a soft tactile
    'tock', never a sharp click (>=2.5 ms attack). ~0.16s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.16
    n = int(dur * SR); t = t_axis(dur)

    # tuned woody body around a mid tap pitch, tiny per-tap wobble
    base = 430.0 * (2 ** (rng.uniform(-0.2, 0.2) / 12.0))
    body = np.zeros(n)
    for mult, amp, dec in ((1.0, 1.0, 0.040), (2.01, 0.42, 0.026), (3.04, 0.16, 0.016)):
        ph = rng.uniform(0, 2*np.pi)
        body += amp * np.sin(2*np.pi*base*mult*t + ph) * np.exp(-t/dec)
    body /= 1.58

    # col-legno contact: short band-limited noise (wood on string)
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 3000.0, order=3)
    noise = noise - lowpass_fft(noise, 400.0, order=2)
    n_env = adsr(n, 0.0025, 0.022, 0.0, 0.0)
    click = noise * n_env * 0.5

    b_env = adsr(n, 0.003, 0.05, 0.0, 0.0)
    body = body * b_env

    out = body + click
    out = lowpass_fft(out, 4200.0, order=4)
    out = soft_clip(out, 1.08)
    peak = np.max(np.abs(out)) + 1e-9
    out = out * (0.50 / peak)
    return out.astype(np.float32)


# ---- chirp (bright high pizzicato flick — a tender little chamber accent) ----
def voice_chirp(seed):
    """A bright high pizzicato flick: a tender little chamber accent. A quick
    sweet two-note rising pizz blip in the high register — a short bright pluck
    that leaps up a pentatonic step. Additive string partials decaying fast,
    near-dry, friendly. Seed picks the starting note and the leap so each accent
    is a cheerful little flick. ~0.42s."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85]
    start_i = int(rng.integers(0, 3))
    leap = int(rng.choice([1, 2, 3]))
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.42
    n = int(dur * SR); t = t_axis(dur)

    # quick rising glide, smoothstepped (no zipper)
    rise = np.clip(t / (dur * 0.45), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    # pizz body: fast-decaying string partials
    amp_env = np.exp(-t * 7.0)
    sig = (
        np.sin(phase) * amp_env +
        0.34 * np.sin(2*phase) * np.exp(-t*11.0) +
        0.14 * np.sin(3*phase) * np.exp(-t*18.0)
    )
    # tiny bright contact tick
    tick = rng.standard_normal(n)
    tick = lowpass_fft(tick, 5200.0, order=3)
    sig = sig + 0.12 * tick * np.exp(-t * 240.0)

    sig = lowpass_fft(sig, 6500.0, order=3)
    env = adsr(n, a=0.005, d=0.2, s_level=0.0, r=0.16)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.03, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


PLAN = {
    "bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.12, "decay": 1.6, "predelay_ms": 14, "brightness": 0.3}
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 62, 64, 66, 68, 69, 71, 73, 76],
        "pans": [-0.12, 0.12, -0.08, 0.1],
        "target_peak": 0.82,
        "reverb": {"wet": 0.3, "decay": 2.6, "predelay_ms": 24, "brightness": 0.55}
    },
    "lead2": {
        "kind": "midi",
        "midis": [52, 54, 56, 57, 59, 61, 64, 66, 69],
        "pans": [0.18, -0.16, 0.12, -0.1],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 1.6, "predelay_ms": 16, "brightness": 0.5}
    },
    "tone": {
        "kind": "midi",
        "midis": [45, 49, 52, 56, 57, 61, 64],
        "pans": [-0.15, 0.15],
        "target_peak": 0.82,
        "reverb": {"wet": 0.3, "decay": 2.8, "predelay_ms": 26, "brightness": 0.45}
    },
    "chime": {
        "kind": "midi",
        "midis": [73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.4, -0.3, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.38, "decay": 3.2, "predelay_ms": 28, "brightness": 0.6}
    },
    "sparkle": {
        "kind": "seed",
        "count": 5,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.2, "decay": 1.8, "predelay_ms": 14, "brightness": 0.6}
    },
    "bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.2, "predelay_ms": 45, "brightness": 0.5}
    },
    "cluster": {
        "kind": "midi",
        "midis": [57, 62, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 42, "brightness": 0.52}
    },
    "tap": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.22, 0.2, -0.1, 0.16],
        "target_peak": 0.85,
        "reverb": {"wet": 0.04, "decay": 0.5, "predelay_ms": 8, "brightness": 0.4}
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4],
        "target_peak": 0.8,
        "reverb": {"wet": 0.14, "decay": 1.6, "predelay_ms": 12, "brightness": 0.6}
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
    print("sunchamber:", name)


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
