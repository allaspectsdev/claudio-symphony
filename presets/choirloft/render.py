#!/usr/bin/env python3
"""
choirloft — sample renderer (per-voice reverb from preset.json).

Warm human voices singing oo and ah, angelic and bright, sunlight through
stained glass. Soft additive vocal pads with formant warmth and gentle
vibrato — ooh and ahh layered. Choir/angelic but joyful and major, radiant
and human, never mournful. A major @ A=432, additive only, never dreary.

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


# ---- formant helper -------------------------------------------------------
def _formant_gain(harm_f, formants):
    """Additive formant shaping: weight a partial by its proximity to vowel
    formant peaks. formants = list of (center_hz, bandwidth_hz, peak_gain).
    Returns a multiplicative gain (resonant-peak comb) that warms vowels."""
    g = 0.06  # small floor so partials never fully vanish
    for fc, bw, pk in formants:
        # gentle resonance bump (Lorentzian-ish), smooth and additive-safe
        g += pk / (1.0 + ((harm_f - fc) / (bw * 0.5)) ** 2)
    return g

# vowel formant tables (warm, rounded — not clinical): (center, bw, peak)
_VOWEL_OO = [(320.0, 110.0, 1.0), (760.0, 150.0, 0.32), (2400.0, 260.0, 0.08)]
_VOWEL_AH = [(700.0, 130.0, 1.0), (1180.0, 180.0, 0.55), (2600.0, 320.0, 0.16)]
_VOWEL_MM = [(280.0, 100.0, 1.0), (1100.0, 160.0, 0.18), (2200.0, 240.0, 0.05)]


def _voice_tone(f, t, vib, formants, n_harm=18, bright=1.0):
    """Build a warm additive vocal tone at frequency f over time axis t with a
    per-sample vibrato multiplier `vib`. Partials are shaped by vowel formants
    so it reads as a sung vowel, never a raw saw. Soft 1/n rolloff keeps it
    human and round; nothing harsh up top."""
    phase = 2 * np.pi * f * np.cumsum(vib) / SR
    sig = np.zeros_like(t)
    for h in range(1, n_harm + 1):
        hf = f * h
        if hf > 9000.0:
            break
        # natural vocal rolloff (slightly steeper than 1/n for warmth)
        amp = 1.0 / (h ** 1.18)
        amp *= _formant_gain(hf, formants)
        # high partials dimmed unless bright asked for them
        if h > 6:
            amp *= bright
        sig += amp * np.sin(h * phase)
    return sig


# ---- bass : low bass-voice ooh, round warm formant fundamental ------------
def voice_choir_bass(midi):
    """A low bass-voice ooh — round warm formant fundamental with soft breath,
    the grounding hum. Slow gentle vibrato fading in, soft breath intake at the
    attack, deeply rounded (lowpassed) so it is felt as a warm floor."""
    f = freq(midi)
    dur = 3.2
    n = int(dur * SR); t = t_axis(dur)
    # gentle vibrato that opens after the note speaks (singing, not warbly)
    vib_depth = 0.004 * np.clip((t - 0.5) / 0.8, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2 * np.pi * 4.6 * t)
    sig = _voice_tone(f, t, vib, _VOWEL_OO, n_harm=14, bright=0.5)
    # soft breath intake at onset
    rng = np.random.default_rng(int(midi) * 31 + 3)
    breath = rng.standard_normal(n)
    breath = lowpass_fft(breath, 700.0, order=2) - lowpass_fft(breath, 180.0, order=2)
    breath_env = np.exp(-t * 9.0) * np.clip(t / 0.03, 0, 1)
    sig = sig + 0.10 * breath * breath_env
    # round, warm — bass should be felt, not bright
    sig = lowpass_fft(sig, 1600.0, order=3)
    env = adsr(n, a=0.030, d=0.7, s_level=0.6, hold=0.6, r=1.3)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead : soprano ooh swelling in, warm formant + gentle vibrato --------
def voice_soprano_ooh(midi):
    """A soprano ooh-voice swelling in over 30ms, warm formant with gentle
    vibrato, singing the radiant melody. Soft swell attack, vibrato fades in,
    a whisper of detune chorus for a human bloom."""
    f = freq(midi)
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    vib_depth = 0.006 * np.clip((t - 0.35) / 0.6, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2 * np.pi * 5.4 * t)
    sig = _voice_tone(f, t, vib, _VOWEL_OO, n_harm=18, bright=0.85)
    # whisper of detune twin for a human, breathing bloom
    vib2 = 1.0035 + vib_depth * np.sin(2 * np.pi * 5.4 * t + 0.7)
    sig += 0.40 * _voice_tone(f, t, vib2, _VOWEL_OO, n_harm=14, bright=0.7)
    sig = lowpass_fft(sig, 5200.0, order=3)
    env = adsr(n, a=0.030, d=0.7, s_level=0.6, hold=0.4, r=1.1)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lead2 : alto ahh, brighter open formant, counter-line ----------------
def voice_alto_ahh(midi):
    """An alto ahh-voice, brighter open formant, harmonizing a counter-line.
    Open 'ah' vowel (bright formants), gentle vibrato, warm but radiant."""
    f = freq(midi)
    dur = 2.4
    n = int(dur * SR); t = t_axis(dur)
    vib_depth = 0.006 * np.clip((t - 0.3) / 0.55, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2 * np.pi * 5.0 * t)
    sig = _voice_tone(f, t, vib, _VOWEL_AH, n_harm=20, bright=0.95)
    vib2 = 0.9968 + vib_depth * np.sin(2 * np.pi * 5.0 * t + 1.1)
    sig += 0.34 * _voice_tone(f, t, vib2, _VOWEL_AH, n_harm=14, bright=0.8)
    sig = lowpass_fft(sig, 6000.0, order=3)
    env = adsr(n, a=0.026, d=0.6, s_level=0.58, hold=0.35, r=1.0)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- tone : warm tenor mmm, rounded and breath-soft -----------------------
def voice_tenor_mmm(midi):
    """A warm tenor mmm, rounded and breath-soft, the sweet vocal middle.
    Closed-mouth hum: dark rounded formant, very soft, a touch of breath."""
    f = freq(midi)
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)
    vib_depth = 0.0045 * np.clip((t - 0.4) / 0.7, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2 * np.pi * 4.8 * t)
    sig = _voice_tone(f, t, vib, _VOWEL_MM, n_harm=12, bright=0.4)
    sig = lowpass_fft(sig, 2600.0, order=3)   # closed-mouth = darker, rounder
    env = adsr(n, a=0.028, d=0.8, s_level=0.55, hold=0.4, r=1.2)
    out = sig[:env.size] * env[:sig.size] * 0.9
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.46 / peak)
    return out


# ---- chime : high boy-soprano ping-tone, pure with soft air ---------------
def voice_boy_ping(midi):
    """A high boy-soprano ping-tone, pure with soft air, medium-full reverb.
    Nearly pure fundamental with a soft octave, a breath of air at the onset,
    soft attack (no click) — an angelic little bell-like voice."""
    f = freq(midi)
    dur = 2.2
    n = int(dur * SR); t = t_axis(dur)
    vib_depth = 0.003 * np.clip((t - 0.25) / 0.5, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2 * np.pi * 5.6 * t)
    phase = 2 * np.pi * f * np.cumsum(vib) / SR
    sig = (
        1.00 * np.sin(phase) * np.exp(-t * 0.7) +
        0.30 * np.sin(2 * phase) * np.exp(-t * 1.4) +   # soft octave, fades early
        0.08 * np.sin(3 * phase) * np.exp(-t * 2.6)     # faint sweetener
    )
    # soft air at the onset — a breath behind the ping
    rng = np.random.default_rng(int(midi) * 13 + 9)
    air = rng.standard_normal(n)
    air = lowpass_fft(air, 5000.0, order=2) - lowpass_fft(air, 1500.0, order=2)
    air_env = np.exp(-t * 16.0) * np.clip(t / 0.02, 0, 1)
    sig = sig + 0.06 * air * air_env
    sig = lowpass_fft(sig, 7000.0, order=3)
    env = adsr(n, a=0.018, d=1.6, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- sparkle : tiny high vocal flutters, bright breathy glints ------------
def voice_vocal_sparkle(seed):
    """Tiny high vocal flutters, bright breathy glints with light delay echoes.
    A short rising vocal 'ee' blip in the high register with breathy air,
    cheerful and bright. Seed picks a high pentatonic-safe note and a tiny
    upward lift so each flutter is a different little angelic glint."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]      # A major, high register
    start_i = int(rng.integers(0, 4))
    end_i = min(start_i + int(rng.integers(1, 3)), len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.5
    n = int(dur * SR); t = t_axis(dur)
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2 * rise)   # smoothstep
    f_t = f0 + (f1 - f0) * rise
    # gentle flutter vibrato
    vib = 1.0 + 0.006 * np.sin(2 * np.pi * 7.0 * t)
    phase = 2 * np.pi * np.cumsum(f_t * vib) / SR
    sig = (
        np.sin(phase) +
        0.16 * np.sin(2 * phase) +
        0.05 * np.sin(3 * phase) * np.exp(-t * 12)
    )
    # breathy air glint
    air = rng.standard_normal(n)
    air = lowpass_fft(air, 6500.0, order=2) - lowpass_fft(air, 2500.0, order=2)
    air_env = np.exp(-t * 20.0) * np.clip(t / 0.012, 0, 1)
    sig = sig + 0.10 * air * air_env
    sig = lowpass_fft(sig, 7500.0, order=3)
    env = adsr(n, a=0.014, d=0.12, s_level=0.5, r=0.28)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


# ---- bloom : full choir-swell, layered ooh and ahh ------------------------
def voice_choir_bloom(midi):
    """A full choir-swell, layered ooh and ahh blooming open, lush angelic
    wash. Several detuned voices (a small section) on ooh and ahh, a soft
    octave halo, slow breathing vibrato, and a brightness that OPENS over the
    swell like sun through stained glass. Round and warm, never harsh."""
    f = freq(midi)
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) * 7 + 1)
    # slow breathing vibrato
    vib_slow = 1.0 + 0.0018 * np.sin(2 * np.pi * 0.30 * t)
    sig = np.zeros(n)
    # a small section: detuned ooh + ahh voices for a human choir width
    detunes = [-0.004, -0.0015, 0.0, 0.0018, 0.0042]
    for i, dt in enumerate(detunes):
        ft = f * (1.0 + dt)
        vow = _VOWEL_OO if i % 2 == 0 else _VOWEL_AH
        vib = vib_slow + 0.003 * np.sin(2 * np.pi * (4.4 + 0.3 * i) * t + i)
        v = _voice_tone(ft, t, vib, vow, n_harm=14, bright=0.7)
        sig += v * (1.0 - 0.08 * i)
    # soft octave halo + warm sub for body
    sig += 0.30 * np.sin(2 * np.pi * f * 2.0 * t * vib_slow)
    sig += 0.22 * np.sin(2 * np.pi * f * 0.5 * t)
    sig /= len(detunes)
    # brightness opens over the swell (stained-glass light)
    low = lowpass_fft(sig, 800.0, order=3)
    high = sig - low
    open_curve = 0.20 + 0.80 * (0.5 - 0.5 * np.cos(2 * np.pi * np.minimum(t / (dur * 0.85), 1.0)))
    sig = low + high * open_curve
    sig = lowpass_fft(sig, 4200.0, order=3)   # warm ceiling, no fizz
    env = adsr(n, a=1.4, d=1.0, s_level=0.82, hold=1.1, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- cluster : stacked vocal chord shimmering with chorused voices --------
def voice_vocal_cluster(arg):
    """A stacked vocal chord shimmering with chorused voices, radiant cloud.
    From the passed root midi build a major-safe stacked chord: root, +4
    (maj3), +7 (5th), +9 (maj6), +12 (octave), each a chorused ooh/ahh voice
    with breathing vibrato and staggered swells so the chord blooms open."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.8
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        vow = _VOWEL_OO if i % 2 == 0 else _VOWEL_AH
        vib = 1.0 + 0.0026 * np.sin(2 * np.pi * (0.24 + 0.05 * i) * t + i * 0.8)
        v = _voice_tone(f, t, vib, vow, n_harm=12, bright=0.65)
        # chorused detune twin for shimmer
        vib2 = 1.0035 + 0.0026 * np.sin(2 * np.pi * (0.24 + 0.05 * i) * t + i * 0.8 + 1.0)
        v += 0.35 * _voice_tone(f, t, vib2, vow, n_harm=10, bright=0.55)
        stagger = 0.16 * i
        env = adsr(n, a=1.5 + stagger, d=0.7, s_level=0.82, hold=1.4, r=2.4)
        gain = 1.0 - 0.10 * i   # upper voices a touch quieter
        sig += v * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 4000.0, order=3)
    peak = float(np.max(np.abs(sig))) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- texture : soft choral-breath texture, near-dry intake of air ---------
def voice_choral_breath(seed):
    """A soft choral-breath texture, near-dry intake of air, the room of
    voices. A gentle filtered-noise inhale with a faint vocal-formant color,
    soft swell in and out — the breath of a choir before they sing. No pitch,
    no click; the softest texture in the family."""
    rng = np.random.default_rng(int(seed))
    dur = 1.1
    n = int(dur * SR); t = t_axis(dur)
    noise = rng.standard_normal(n)
    # voiced-air band: warm, no hiss top, no rumble bottom
    air = lowpass_fft(noise, 3200.0, order=3) - lowpass_fft(noise, 350.0, order=2)
    # faint formant color so it reads as a *vocal* breath (ooh-ish)
    air_oo = lowpass_fft(noise, 900.0, order=2) - lowpass_fft(noise, 240.0, order=2)
    sig = 0.8 * air + 0.5 * air_oo
    # soft inhale swell: rise then settle (no click, no edge)
    env = adsr(n, a=0.18, d=0.3, s_level=0.4, hold=0.1, r=0.45)
    sig = sig[:env.size] * env[:sig.size]
    sig = lowpass_fft(sig, 3600.0, order=3)
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.42 / peak)
    return sig


# ---- chirp : bright high vocal flick, a joyful little angelic accent ------
def voice_angel_chirp(seed):
    """A bright high vocal flick, a joyful little angelic accent. A quick
    rising two-note vocal blip in the high register on a bright 'ah', cheerful
    and friendly, near-dry. Seed picks a high major-safe note and a small
    upward leap so each accent is its own happy little flick."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]      # A major, high register
    start_i = int(rng.integers(0, 3))
    leap = int(rng.integers(2, 5))
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.42
    n = int(dur * SR); t = t_axis(dur)
    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2 * rise)
    f_t = f0 + (f1 - f0) * rise
    vib = 1.0 + 0.005 * np.sin(2 * np.pi * 6.5 * t)
    phase = 2 * np.pi * np.cumsum(f_t * vib) / SR
    # bright open 'ah' color via a couple of formant-weighted partials
    sig = (
        1.00 * np.sin(phase) +
        0.45 * np.sin(2 * phase) +       # bright open vowel
        0.18 * np.sin(3 * phase) +
        0.05 * np.sin(4 * phase) * np.exp(-t * 10)
    )
    sig = lowpass_fft(sig, 7000.0, order=3)
    env = adsr(n, a=0.012, d=0.10, s_level=0.5, r=0.24)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


PLAN = {
    "choir_bass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.30, "decay": 3.0, "predelay_ms": 25, "brightness": 0.3},
    },
    "soprano_ooh": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [-0.12, 0.12, -0.08, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.42, "decay": 4.2, "predelay_ms": 32, "brightness": 0.55},
    },
    "alto_ahh": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [0.15, -0.15, 0.1, -0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.40, "decay": 4.0, "predelay_ms": 30, "brightness": 0.58},
    },
    "tenor_mmm": {
        "kind": "midi",
        "midis": [45, 49, 52, 57, 61, 64, 66],
        "pans": [-0.1, 0.1, 0.0, -0.05],
        "target_peak": 0.78,
        "reverb": {"wet": 0.34, "decay": 3.4, "predelay_ms": 28, "brightness": 0.42},
    },
    "boy_ping": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2, 0.0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.40, "decay": 3.6, "predelay_ms": 30, "brightness": 0.6},
    },
    "vocal_sparkle": {
        "kind": "seed",
        "count": 5,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.2],
        "target_peak": 0.8,
        "reverb": {"wet": 0.30, "decay": 2.4, "predelay_ms": 18, "brightness": 0.62},
    },
    "choir_bloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0.0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.2, "predelay_ms": 45, "brightness": 0.5},
    },
    "vocal_cluster": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0.0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.50, "decay": 5.0, "predelay_ms": 42, "brightness": 0.5},
    },
    "choral_breath": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.5,
        "reverb": {"wet": 0.06, "decay": 0.8, "predelay_ms": 10, "brightness": 0.45},
    },
    "angel_chirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.3, -0.3, 0.45, -0.45, 0.15, -0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.14, "decay": 1.8, "predelay_ms": 12, "brightness": 0.62},
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
    print("choirloft:", name)


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
