#!/usr/bin/env python3
"""
clayround — sample renderer (per-voice reverb from preset.json).

A sweet ocarina singing round clay-flute melodies over a warm hill at
dusk-bright. Round hollow ocarina tones, pure and soft-edged with a warm
woody breath; sweet clay-whistle melodies, gentle and rounded, folk-bright
and tender, never thin. A major pentatonic @ A=432, additive only, room
reverb, never dreary.

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


def _breath_noise(n, t, cutoff, decay, seed):
    """A soft warm breath puff: band-limited noise, gently shaped. The 'air'
    of a clay flute. Never hissy — lowpassed warm, never a click."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, cutoff, order=3)
    noise = noise - lowpass_fft(noise, 180.0, order=2)  # band: airy, no rumble
    return noise * np.exp(-t * decay)


# ---- clayjug (bass) ----
def voice_clayjug(arg):
    """A low clay-jug tone — round breathy fundamental with a warm hollow body,
    the soft ground. Pure sine fundamental with a gentle just-fifth and a soft
    octave for hollow-jug body (all tamed fast, nothing harsh), a slow breathe
    so the floor feels alive, and a soft warm air-breath at the attack (no
    click). Round and dark-warm but bright-hearted, never gloomy. A-pent LOW."""
    f = freq(int(arg))
    dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    # Round hollow body: fundamental, soft fifth (hollow-jug resonance),
    # a kiss of octave. Upper partials fade fast so it stays a warm floor.
    body = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.20 * np.sin(2*np.pi*f*(3/2)*t) * np.exp(-t*2.4) +   # hollow fifth, fades
        0.14 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.2) +   # soft octave body
        0.05 * np.sin(2*np.pi*f*1.004*t)                      # slow beat = "clay" life
    )
    # gentle slow breathe — the jug has a soft pulse of warm air
    breathe = 1.0 + 0.05 * np.sin(2*np.pi*2.4*t - np.pi/2)
    body = body * breathe

    # soft warm breath at the attack: the air entering the jug mouth
    air = _breath_noise(n, t, 360.0, 20.0, int(arg) * 17 + 5)
    body = body + 0.16 * air

    # keep it round: roll off anything bright; bass is felt, not heard up top
    body = lowpass_fft(body, 820.0, order=4)

    # warm rounded envelope: soft breath attack (24 ms), long support, soft tail
    env = adsr(n, a=0.024, d=0.5, s_level=0.55, hold=0.6, r=1.2)
    out = body[:env.size] * env[:body.size]

    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- ocarina (lead) ----
def voice_ocarina(midi):
    """An ocarina pipe with breath-attack swelling in — pure round tone with
    soft air, singing the sweet melody. An ocarina is almost a pure sine with a
    gentle octave; the character is in the BREATH. A soft 35 ms swell-in (the
    player taking a breath), a whisper of vibrato that opens only after the note
    speaks, and a low breath-noise bed under the attack. Round, pure, tender,
    folk-bright. Additive only, no FM. ~2.2s. arg = midi."""
    f = freq(midi); dur = 2.2
    n = int(dur * SR); t = t_axis(dur)

    # vibrato fades IN after the note has spoken (singing, not warbly)
    vib_depth = 0.004 * np.clip((t - 0.35) / 0.7, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.2*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    # ocarina = near-pure sine + soft octave + tiny third for round body
    sig = (
        1.00 * np.sin(phase) +
        0.16 * np.sin(2*phase) * np.exp(-t*1.4) +              # soft octave, fades
        0.05 * np.sin(3*phase) * np.exp(-t*4.0) +              # faint sweetener
        0.07 * np.sin(2*np.pi*f*1.005*t)                       # whisper detune = body
    )

    # breath bed under the attack: soft air swelling with the note
    air = _breath_noise(n, t, 1600.0, 7.0, midi * 13 + 3)
    breath_env = np.clip(t / 0.18, 0.0, 1.0) * np.exp(-t*3.5)
    sig = sig + 0.10 * air * breath_env

    # keep it round and soft-edged — no thin top
    sig = lowpass_fft(sig, 3600.0, order=3)

    # breath swell-in attack (35 ms, no click), singing sustain, gentle release
    env = adsr(n, a=0.035, d=0.6, s_level=0.6, hold=0.2, r=0.9)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- whistle (lead2) ----
def voice_whistle(midi):
    """A higher clay-whistle, brighter and rounder, echoing a counter-line.
    Like the ocarina but lifted: a touch more octave shimmer and a hair more
    air so it reads as a sweeter, brighter clay-whistle answering the lead.
    Still rounded — lowpassed, soft attack, never thin or piercing. ~1.8s."""
    f = freq(midi); dur = 1.8
    n = int(dur * SR); t = t_axis(dur)

    vib_depth = 0.004 * np.clip((t - 0.3) / 0.6, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.6*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = (
        1.00 * np.sin(phase) +
        0.22 * np.sin(2*phase) * np.exp(-t*1.8) +              # brighter octave
        0.07 * np.sin(3*phase) * np.exp(-t*4.5) +              # sweet glass color
        0.06 * np.sin(2*np.pi*f*1.005*t)                       # body detune
    )

    air = _breath_noise(n, t, 2200.0, 9.0, midi * 19 + 7)
    breath_env = np.clip(t / 0.14, 0.0, 1.0) * np.exp(-t*4.5)
    sig = sig + 0.11 * air * breath_env

    sig = lowpass_fft(sig, 4600.0, order=3)

    env = adsr(n, a=0.028, d=0.5, s_level=0.55, hold=0.15, r=0.8)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- lowcarina (tone) ----
def voice_lowcarina(midi):
    """A warm low-ocarina tone — dark and round, the sweet hollow middle. A
    fuller, darker ocarina: fundamental with a soft fifth and octave for hollow
    woody warmth, a slow gentle vibrato, and a warm breath bed. Rolled off low
    so it sits as a round, tender middle voice — dark-toned but never gloomy,
    a warm sweetness. Additive only. ~2.6s."""
    f = freq(midi); dur = 2.6
    n = int(dur * SR); t = t_axis(dur)

    vib_depth = 0.003 * np.clip((t - 0.4) / 0.8, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*4.6*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    sig = (
        1.00 * np.sin(phase) +
        0.18 * np.sin(2*np.pi*f*(3/2)*t) * np.exp(-t*2.0) +    # hollow fifth, warm
        0.14 * np.sin(2*phase)           * np.exp(-t*2.6) +    # soft octave body
        0.05 * np.sin(3*phase)           * np.exp(-t*5.0) +    # faint color
        0.08 * np.sin(2*np.pi*f*1.004*t)                       # body detune
    )

    air = _breath_noise(n, t, 1100.0, 6.0, midi * 11 + 5)
    breath_env = np.clip(t / 0.2, 0.0, 1.0) * np.exp(-t*3.0)
    sig = sig + 0.09 * air * breath_env

    # darker, rounder — lower ceiling for the hollow warmth
    sig = lowpass_fft(sig, 2600.0, order=3)

    env = adsr(n, a=0.030, d=0.7, s_level=0.6, hold=0.3, r=1.1)
    out = sig[:env.size] * env[:sig.size] * 0.5
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- whistleping (chime) ----
def voice_whistleping(midi):
    """A high whistle-harmonic ping — flute-pure with soft air, medium-light
    reverb. A bright clay-whistle ping that melts in (no click), a pure
    fundamental with a clean octave and a whisper of a high glint that fades
    fast, plus a soft air-puff at the onset so it stays breathy and round, not
    glassy. Sweet and bright, tender. Additive, no FM, nothing past 4x. ~2.0s."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)       * np.exp(-t*1.3) +    # warm pure body
        0.40 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.0) +    # clean octave
        0.12 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*3.2) +    # sweet color
        0.05 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*5.0)      # tiny glint, gone fast
    )
    # gentle shimmer twin for a glowing whistle warmth
    sig += 0.14 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.5)

    # soft air at the onset — the breath of the whistle
    air = _breath_noise(n, t, 2600.0, 12.0, midi * 23 + 9)
    sig = sig + 0.08 * air * np.clip(t / 0.06, 0.0, 1.0)

    # soft attack — no click, the ping melts in
    env = adsr(n, a=0.012, d=1.6, s_level=0.0, r=0.4)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6200.0, order=3)  # round, no glassy top
    peak = np.max(np.abs(out))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- glint (sparkle) ----
def voice_glint(seed):
    """Tiny top whistle-flicks — round bright glints with light delay echoes.
    A single quick high whistle blip in the HIGH pentatonic: a short rising
    breath-flick, pure sine with a soft octave sheen, rounded warm so it
    sparkles without ever screeching. ~0.35s. Seed picks the pitch + a small
    upward lift so each glint is a fresh little bright drop."""
    rng = np.random.default_rng(int(seed))
    HIGH = [73, 76, 78, 81, 85, 88]
    start_i = int(rng.integers(0, 4))
    lift = int(rng.integers(1, 3))
    end_i = min(start_i + lift, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.35
    n = int(dur * SR); t = t_axis(dur)

    rise = np.clip(t / (dur * 0.5), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep, no zipper
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.16 * np.sin(2*phase) +                       # soft octave sheen
        0.04 * np.sin(3*phase) * np.exp(-t*16)         # tiny chiff at onset
    )
    # a breath of air at the very front so it's a whistle-flick, not a beep
    air = _breath_noise(n, t, 4000.0, 30.0, int(seed) * 7 + 1)
    sig = sig + 0.07 * air * np.clip(t / 0.04, 0.0, 1.0)

    sig = lowpass_fft(sig, 7000.0, order=3)   # round, no screech
    env = adsr(n, a=0.010, d=0.08, s_level=0.45, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


# ---- claybloom (bloom) ----
def voice_claybloom(midi):
    """A soft layered-ocarina swell — warm clay tones blooming open, lush room
    wash. Several detuned ocarina layers (fundamental + just major third + just
    fifth + soft octave) that bloom open via a slow opening lowpass, with a
    breathing chorus shimmer and a soft air bed. Round, warm, enveloping, sweet
    and bright — never glassy, never gloomy. Additive only. ~6.5s."""
    f = freq(midi)
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)

    # slow breathing vibrato — a calm warm exhale
    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.30*t)

    # layered ocarina body: fundamental with two faint detunes (chorus)
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.45 * np.sin(2*np.pi*f*1.0035*t) +
        0.45 * np.sin(2*np.pi*f*0.9967*t)
    )
    # consonant major-tone halo (just intonation: sweet, never beating)
    third  = 0.38 * np.sin(2*np.pi*f*(5/4)*t*vib)   # major third
    fifth  = 0.32 * np.sin(2*np.pi*f*(3/2)*t*vib)   # perfect fifth
    octave = 0.20 * np.sin(2*np.pi*f*2.0*t)         # soft octave halo
    sub    = 0.22 * np.sin(2*np.pi*f*0.5*t)         # tiny sub for warmth

    sig = fund + third + fifth + octave + sub

    # soft air bed swelling with the bloom
    air = _breath_noise(n, t, 1400.0, 1.0, midi * 29 + 11)
    sig = sig + 0.06 * air * np.clip(t / 1.0, 0.0, 1.0)

    # bloom: brightness opens over the first seconds then settles
    low  = lowpass_fft(sig, 700.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/(dur*0.85), 1.0)))
    sig = low + high * open_curve

    # final warmth ceiling — round, kill any residual fizz
    sig = lowpass_fft(sig, 2600.0, order=3)

    # slow swell-in, long gentle release
    env = adsr(n, a=1.5, d=1.0, s_level=0.85, hold=1.0, r=2.8)
    out = sig[:env.size] * env[:sig.size]
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- threewhistle (cluster) ----
def voice_threewhistle(arg):
    """A breathy chord of three whistles — round shimmering cloud, sweet and
    bright. From the passed root we build a major-pentatonic-safe chord:
    root, +4 (maj3), +7 (5th), +9 (maj6), +12 (octave). Each note is a soft
    ocarina-whistle (pure sine + faint octave + breath shimmer) with staggered
    swells so the chord blooms open like a shared breath. Warm low-passed so it
    sits sweet over the clay. ~6.8s. arg = root midi."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.8
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        # soft whistle body: fundamental + faint octave + soft third partial
        partial = (np.sin(2*np.pi*f*t)
                   + 0.16*np.sin(2*np.pi*2*f*t)
                   + 0.05*np.sin(2*np.pi*3*f*t))
        # subtle detune twin for warm movement
        detune = np.sin(2*np.pi*f*1.0035*t)
        # slow breathing vibrato, each voice phased differently
        vib = 1 + 0.0022*np.sin(2*np.pi*0.24*t + i*0.9)
        voice = (0.85*partial + 0.30*detune) * vib
        # staggered swell: upper notes bloom slightly later -> opening glow
        stagger = 0.16 * i
        env = adsr(n, a=1.6 + stagger, d=0.7, s_level=0.82, hold=1.4, r=2.6)
        gain = 1.0 - 0.10*i      # high voices a touch quieter, root grounded
        sig += voice * env[:n] * gain
    sig /= len(intervals)

    # soft breath cloud under the chord
    air = _breath_noise(n, t, 1800.0, 0.7, root * 31 + 13)
    sig = sig + 0.05 * air * np.clip(t / 1.4, 0.0, 1.0)

    # warm: tame anything bright, no harsh partials
    sig = lowpass_fft(sig, 2800, order=3)
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- claybreath (texture) ----
def voice_claybreath(seed):
    """A gentle clay-breath texture — near-dry soft air, the warmth of the
    flute. A soft slow swell of warm band-limited breath-noise with a faint
    tonal hum underneath (so it stays musical and in-key, never hissy). The
    'air in the pipe' between notes. Round, tender, near-dry. ~1.4s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 1.4
    n = int(dur * SR); t = t_axis(dur)

    # warm breath band: soft noise, lowpassed round, no rumble, no hiss
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 1300.0, order=3)
    noise = noise - lowpass_fft(noise, 240.0, order=2)

    # faint tonal hum so the breath sits in-key (very quiet ~A3)
    f = freq(57) * (1.0 + rng.uniform(-0.004, 0.004))
    hum = 0.18 * (np.sin(2*np.pi*f*t) + 0.3*np.sin(2*np.pi*f*1.5*t)) * np.exp(-t*1.2)

    sig = noise + hum

    # soft slow swell in and out — a gentle breath, no click
    env = adsr(n, a=0.12, d=0.4, s_level=0.5, hold=0.2, r=0.5)
    sig = sig[:env.size] * env[:sig.size]

    sig = lowpass_fft(sig, 2000.0, order=3)   # keep it warm and round
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.45 / peak)
    return sig


# ---- chirpflick (chirp) ----
def voice_chirpflick(seed):
    """A bright high whistle-flick — a sweet little birdlike accent. A quick
    two-note rising whistle blip in the HIGH pentatonic, pure sine with a soft
    octave sparkle and a tiny breath chiff, rounded warm so it's a cheerful
    little bird perching over the hill — bright, friendly, tender, never harsh.
    ~0.42s. Seed picks a starting note + a small upward leap."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]
    leaps = [2, 3, 4]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])

    dur = 0.42
    n = int(dur * SR); t = t_axis(dur)

    rise = np.clip(t / (dur * 0.55), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep — no zipper
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.18 * np.sin(2*phase) +                       # gentle octave sheen
        0.05 * np.sin(3*phase) * np.exp(-t*14)         # tiny chiff at onset
    )
    # breath flick at the very front
    air = _breath_noise(n, t, 3600.0, 26.0, int(seed) * 5 + 3)
    sig = sig + 0.08 * air * np.clip(t / 0.03, 0.0, 1.0)

    sig = lowpass_fft(sig, 6800.0, order=3)   # round warm top, never piercing
    env = adsr(n, a=0.012, d=0.10, s_level=0.5, r=0.24)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


PLAN = {
    "clayjug": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.10, "decay": 1.8, "predelay_ms": 14, "brightness": 0.3}
    },
    "ocarina": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76],
        "pans": [-0.15, 0.15, -0.1, 0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.28, "decay": 2.4, "predelay_ms": 24, "brightness": 0.5}
    },
    "whistle": {
        "kind": "midi",
        "midis": [64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.2, -0.2, 0.15, -0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.30, "decay": 2.4, "predelay_ms": 26, "brightness": 0.55}
    },
    "lowcarina": {
        "kind": "midi",
        "midis": [45, 49, 52, 57, 61, 64],
        "pans": [-0.12, 0.12, 0, -0.1],
        "target_peak": 0.8,
        "reverb": {"wet": 0.26, "decay": 2.6, "predelay_ms": 24, "brightness": 0.42}
    },
    "whistleping": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.4, -0.3, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.36, "decay": 3.0, "predelay_ms": 28, "brightness": 0.6}
    },
    "glint": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 2.0, "predelay_ms": 16, "brightness": 0.6}
    },
    "claybloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.52, "decay": 5.2, "predelay_ms": 46, "brightness": 0.48}
    },
    "threewhistle": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.50, "decay": 5.0, "predelay_ms": 44, "brightness": 0.5}
    },
    "claybreath": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.2, 0.2, -0.1, 0.15],
        "target_peak": 0.5,
        "reverb": {"wet": 0.06, "decay": 0.8, "predelay_ms": 10, "brightness": 0.35}
    },
    "chirpflick": {
        "kind": "seed",
        "count": 6,
        "pans": [0.4, -0.35, 0.3, -0.45, 0.2, -0.25],
        "target_peak": 0.8,
        "reverb": {"wet": 0.12, "decay": 1.6, "predelay_ms": 12, "brightness": 0.6}
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
    print("clayround:", name)


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
