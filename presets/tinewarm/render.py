#!/usr/bin/env python3
"""
tinewarm — sample renderer (per-voice reverb from preset.json).

A soft Rhodes electric piano glowing mellow and lo-fi cozy, tines humming in
lamplight. Warm tine-keys with a soft bell-like attack and a mellow body, a
gentle lo-fi haze laid over everything: plush, intimate, smiling, tender.
A major pentatonic @ A=432, additive only (no FM), never dreary.

The Rhodes "tine" sound here is built additively: a strong sine fundamental,
a warm octave, a soft bell-strike chime made of a few inharmonic partials with
INDEPENDENT fast decays (the metallic "ping" that dies away leaving warm body),
plus a whisper of detune for chorus shimmer and a touch of amp/tremolo. Tops
are always lowpassed so the bell never screeches — mellow, plush, cozy.

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


def _tine_strike(f, t, amp=0.10, fast=120.0, slow=42.0):
    """The soft bell-like ATTACK of a Rhodes tine: a couple of gentle
    inharmonic partials that ping at the strike and decay FAST (independent
    rates) so you hear a soft bell glint that melts into warm body, never a
    sustained metallic ring. All partials stay <=5x and decay quickly."""
    return (
        amp        * np.sin(2*np.pi*f*4.02*t) * np.exp(-t*fast) +   # bright tine ping, gone fast
        amp*0.55   * np.sin(2*np.pi*f*3.01*t) * np.exp(-t*slow) +   # softer bell color
        amp*0.30   * np.sin(2*np.pi*f*5.00*t) * np.exp(-t*(fast*1.6))  # tiny glint, dies first
    )


def _lofi_haze(sig, t, depth=0.04, rate=4.6):
    """Gentle lo-fi cozy haze: a slow amp tremolo (Rhodes/amp wobble) plus a
    very faint, slow pitch-wow feel via tremolo only (no harshness). Returns
    the signal multiplied by a soft tremolo envelope."""
    trem = 1.0 - depth + depth * np.sin(2*np.pi*rate*t - np.pi/2)
    return sig * trem


# ---- bass (A low Rhodes tine: round warm bark, soft bell-attack, plush ground) ----
def voice_bass(arg):
    """A low Rhodes tine — round, warm, plush. A dominant sine fundamental with
    a gentle octave and a kiss of 3x for warm 'bark', a soft fast-decaying bell
    strike for the tine attack, and a whisper of detune for life. Heavily
    lowpassed so it stays felt-warm under everything. Soft felt attack."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    body = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.34 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*2.6) +   # warm octave, settles
        0.12 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*4.5) +   # soft bark, fades
        0.06 * np.sin(2*np.pi*f*1.004*t)                    # slow detune beat = tine life
    )
    body += _tine_strike(f, t, amp=0.07, fast=90.0, slow=36.0)  # soft low bell-attack
    body = _lofi_haze(body, t, depth=0.05, rate=2.7)            # slow cozy amp breathe
    body = lowpass_fft(body, 1100.0, order=4)                   # plush, felt-warm
    env = adsr(n, a=0.014, d=0.6, s_level=0.5, hold=0.5, r=1.2)
    out = body[:env.size] * env[:body.size]
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead (mid Rhodes tine-key: soft bell-strike into warm sustain, gentle tremolo) ----
def voice_lead(arg):
    """The singing mid tine-key. A clean fundamental + warm octave that fades
    early, a soft fast-decaying bell strike at the attack, then warm sustain
    with a gentle Rhodes tremolo. A whisper of detune chorus. Mellow lowpass so
    it stays plush and intimate. ~2.6s. Additive, no FM."""
    f = freq(int(arg)); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.40 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*2.2) +   # octave, fades early
        0.10 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*4.0) +   # soft color
        0.12 * np.sin(2*np.pi*f*1.005*t)                    # detune chorus
    )
    sig += _tine_strike(f, t, amp=0.12, fast=110.0, slow=40.0)  # soft bell-strike attack
    sig = _lofi_haze(sig, t, depth=0.06, rate=4.8)              # gentle tremolo
    sig = lowpass_fft(sig, 3400.0, order=3)                     # mellow, plush
    env = adsr(n, a=0.012, d=0.9, s_level=0.42, r=1.1)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 (higher tine-key: brighter bell-bark, mellow counter-line) ----
def voice_lead2(arg):
    """A higher tine-key answering the lead — a touch brighter bell-bark but
    still mellow. Fundamental + octave + a slightly stronger soft bell strike,
    gentle tremolo, warm top. ~2.2s. Additive, no FM."""
    f = freq(int(arg)); dur = 2.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.36 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*2.6) +
        0.09 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*4.4) +
        0.11 * np.sin(2*np.pi*f*0.996*t)                    # detune chorus (other way)
    )
    sig += _tine_strike(f, t, amp=0.15, fast=120.0, slow=44.0)  # brighter bell-bark
    sig = _lofi_haze(sig, t, depth=0.05, rate=5.2)
    sig = lowpass_fft(sig, 4000.0, order=3)
    env = adsr(n, a=0.010, d=0.8, s_level=0.38, r=0.95)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone (soft-struck warm tine: dark and creamy, the sweet plush middle) ----
def voice_tone(arg):
    """A soft-struck warm tine — dark, creamy, the sweet plush middle. Almost
    no bell glint; mostly fundamental + a soft octave + a whisper of detune.
    Slow gentle tremolo, dark mellow lowpass. The cozy heart. ~2.8s."""
    f = freq(int(arg)); dur = 2.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.30 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*1.8) +   # creamy octave
        0.10 * np.sin(2*np.pi*f*1.004*t) +                  # detune body
        0.08 * np.sin(2*np.pi*f*0.997*t)                    # second detune for warmth
    )
    sig += _tine_strike(f, t, amp=0.05, fast=80.0, slow=30.0)  # barely-there soft strike
    sig = _lofi_haze(sig, t, depth=0.05, rate=3.6)
    sig = lowpass_fft(sig, 2400.0, order=3)                    # dark & creamy
    env = adsr(n, a=0.018, d=1.0, s_level=0.5, r=1.2)
    out = sig[:env.size] * env[:sig.size] * 0.5
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- chime (high Rhodes bell-tine ping with soft shimmer, medium-light reverb) ----
def voice_chime(arg):
    """A high Rhodes bell-tine ping with soft shimmer. A glowing fundamental,
    a pure celeste octave, the soft bell strike a touch more present (it IS the
    chime), and a gentle chorus shimmer. Warm lowpass keeps the bell sweet not
    glassy. Soft 16ms attack, no click. ~2.4s. No FM, nothing past 5x."""
    f = freq(int(arg)); dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)      * np.exp(-t*1.2) +   # warm body
        0.50 * np.sin(2*np.pi*f*2.0*t)  * np.exp(-t*1.7) +   # celeste octave
        0.18 * np.sin(2*np.pi*f*3.0*t)  * np.exp(-t*2.8)     # sweet glass color
    )
    sig += _tine_strike(f, t, amp=0.18, fast=70.0, slow=26.0)  # the bell ping itself
    # gentle chorus shimmer for the glowing tine warmth
    sig += 0.16 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.4)
    sig += 0.12 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.4)
    env = adsr(n, a=0.016, d=1.9, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=3)                    # sweet, never glassy
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle (tiny high tine-flicks glinting soft, light delay echoes, lo-fi haze) ----
def voice_sparkle(seed):
    """Tiny high tine-flicks glinting soft. A quick single high pentatonic ping
    with a soft bell glint that dies fast, leaving a brief warm shimmer. Seed
    picks the note from the HIGH pentatonic. Light delay echoes added live by
    the player; here just a short cozy flick. ~0.6s. Additive, lo-fi-warm."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]
    m = HIGH[int(rng.integers(0, len(HIGH)))]
    f = freq(m)
    dur = 0.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)     * np.exp(-t*5.0) +    # quick warm body
        0.40 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*8.0)      # octave glint
    )
    sig += _tine_strike(f, t, amp=0.20, fast=100.0, slow=44.0)  # soft tine glint
    sig += 0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*6.0)    # tiny shimmer
    sig = _lofi_haze(sig, t, depth=0.05, rate=5.5)             # lo-fi haze
    sig = lowpass_fft(sig, 7000.0, order=3)                    # soft top, no screech
    env = adsr(n, a=0.008, d=0.30, s_level=0.0, r=0.22)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- bloom (sustained Rhodes-pad swell with tremolo, warm tines blooming, lush room) ----
def voice_bloom(arg):
    """A sustained Rhodes-pad swell — warm tines blooming open. A clean
    fundamental + just-major-third (5/4) + just-fifth (3/2) + soft octave halo,
    a gentle sub for body, two faint detunes for chorus, and a Rhodes tremolo
    that breathes through it. A moving lowpass OPENS the bloom then settles —
    warm, never glassy. Slow swell-in, long release. ~6.8s. Additive, no FM."""
    f = freq(int(arg))
    dur = 6.8
    n = int(dur * SR); t = t_axis(dur)

    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.26*t)   # slow breathe
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.45 * np.sin(2*np.pi*f*1.0035*t) +
        0.45 * np.sin(2*np.pi*f*0.9967*t)
    )
    third  = 0.38 * np.sin(2*np.pi*f*(5/4)*t*vib)
    fifth  = 0.32 * np.sin(2*np.pi*f*(3/2)*t*vib)
    octave = 0.20 * np.sin(2*np.pi*f*2.0*t)
    sub    = 0.28 * np.sin(2*np.pi*f*0.5*t)
    sig = fund + third + fifth + octave + sub

    # soft Rhodes tremolo (amp wobble) — the cozy electric-piano breathing
    sig = _lofi_haze(sig, t, depth=0.07, rate=4.4)

    # bloom: brightness opens over the first seconds then settles
    low  = lowpass_fft(sig, 650.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    sig = lowpass_fft(sig, 2700.0, order=3)       # warm ceiling, round
    env = adsr(n, a=1.5, d=1.0, s_level=0.85, hold=1.1, r=2.9)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- cluster (soft chord of detuned tines, mellow shimmering cloud, cozy) ----
def voice_cluster(arg):
    """A soft chord of detuned Rhodes tines — a mellow shimmering cloud, cozy
    and warm. From the passed root we build a major-pentatonic-safe chord:
    root, +4, +7, +9, +12. Each note is a warm tine (fundamental + soft octave
    + a gentle bell strike) with a detune twin and slow staggered swells so the
    chord blooms open. Tremolo breathing. Warm lowpass. ~7s. Additive, no FM."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        partial = (np.sin(2*np.pi*f*t)
                   + 0.22*np.sin(2*np.pi*2*f*t) * np.exp(-t*1.6)
                   + 0.07*np.sin(2*np.pi*3*f*t) * np.exp(-t*3.0))
        partial += _tine_strike(f, t, amp=0.06, fast=70.0, slow=28.0)
        detune = np.sin(2*np.pi*f*1.0035*t)
        vib = 1 + 0.0022*np.sin(2*np.pi*0.22*t + i*0.9)
        voice = (0.85*partial + 0.32*detune) * vib
        stagger = 0.18 * i
        env = adsr(n, a=1.6 + stagger, d=0.7, s_level=0.82, hold=1.6, r=2.6)
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = _lofi_haze(sig, t, depth=0.05, rate=4.0)     # mellow shimmer breathe
    sig = lowpass_fft(sig, 2700.0, order=3)            # warm cloud
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- texture (faint lo-fi tape-warm texture, near-dry, the cozy hum of the amp) ----
def voice_texture(seed):
    """A faint lo-fi tape-warm texture — the cozy hum of the amp idling in
    lamplight. A very soft low tonal hum (anchored low in key) + a breath of
    warm filtered tape noise, both heavily lowpassed and quiet. Near-dry. A
    slow tremolo gives the gentle amp wobble. ~0.7s, almost subliminal."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.7
    n = int(dur * SR); t = t_axis(dur)
    # soft low hum anchored near A2/A3, gentle drift per seed
    f0 = freq(45) * (2 ** (rng.uniform(-0.5, 0.5) / 12.0))
    hum = (
        np.sin(2*np.pi*f0*t) +
        0.30 * np.sin(2*np.pi*f0*2.0*t) +
        0.10 * np.sin(2*np.pi*f0*1.004*t)
    )
    hum = hum * np.exp(-t*1.2)
    # warm tape breath
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 900.0, order=3)
    noise = noise - lowpass_fft(noise, 120.0, order=2)   # band: soft amp hiss
    nz = 0.18 * noise * np.exp(-t*2.0)
    sig = 0.85 * hum + nz
    sig = _lofi_haze(sig, t, depth=0.06, rate=3.2)        # amp wobble
    sig = lowpass_fft(sig, 1400.0, order=4)               # tape-warm, dark
    env = adsr(n, a=0.020, d=0.2, s_level=0.4, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.40 / peak)                          # quiet, subliminal
    return out


# ---- chirp (bright high tine-flick, a tender little cozy accent) ----
def voice_chirp(seed):
    """A bright high tine-flick — a tender little cozy accent. A quick rising
    two-note blip in the high pentatonic with a soft bell glint, bright but
    warm (lowpassed so never piercing). Seed picks the start note and a small
    upward leap. ~0.45s, near-dry. Additive, no FM."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]
    leaps = [2, 3, 4]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.45
    n = int(dur * SR); t = t_axis(dur)
    rise = np.clip(t / (dur * 0.6), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR
    sig = (
        np.sin(phase) +
        0.22 * np.sin(2*phase) +                          # octave sheen
        0.06 * np.sin(3*phase) * np.exp(-t*14)            # tiny chiff onset
    )
    # soft tine glint at the strike (uses the end note's bell)
    sig += _tine_strike(f1, t, amp=0.12, fast=120.0, slow=50.0)
    sig = lowpass_fft(sig, 6800.0, order=3)               # warm top, never piercing
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
        "target_peak": 0.6,
        "reverb": {"wet": 0.1, "decay": 1.8, "predelay_ms": 12, "brightness": 0.3},
    },
    "lead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73],
        "pans": [-0.15, 0.15, -0.1, 0.12],
        "target_peak": 0.82,
        "reverb": {"wet": 0.2, "decay": 2.2, "predelay_ms": 22, "brightness": 0.5},
    },
    "lead2": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.18, -0.15, 0.12, -0.1],
        "target_peak": 0.82,
        "reverb": {"wet": 0.2, "decay": 2.0, "predelay_ms": 20, "brightness": 0.55},
    },
    "tone": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73],
        "pans": [-0.12, 0.12, 0],
        "target_peak": 0.82,
        "reverb": {"wet": 0.18, "decay": 2.4, "predelay_ms": 22, "brightness": 0.42},
    },
    "chime": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85],
        "pans": [-0.35, 0.3, -0.2, 0.4, -0.25, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.2, "predelay_ms": 28, "brightness": 0.58},
    },
    "sparkle": {
        "kind": "seed",
        "count": 5,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 2.0, "predelay_ms": 16, "brightness": 0.6},
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
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.48, "decay": 4.8, "predelay_ms": 42, "brightness": 0.42},
    },
    "texture": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.1, 0.1, 0, 0.05],
        "target_peak": 0.45,
        "reverb": {"wet": 0.04, "decay": 0.7, "predelay_ms": 8, "brightness": 0.3},
    },
    "chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.3, -0.25, 0.4, -0.35],
        "target_peak": 0.78,
        "reverb": {"wet": 0.12, "decay": 1.6, "predelay_ms": 12, "brightness": 0.58},
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
    print("tinewarm:", name)


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
