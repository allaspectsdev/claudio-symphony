#!/usr/bin/env python3
"""
whittle — sample renderer (per-voice reverb from preset.json).

A sunlit wooden desk that learned to sing: warm felt taps + knuckle knocks
(dry, in-the-room) answered by a singing mallet, sweet celeste chimes, a soft
bloom, a glowing pentatonic cluster, a bright chirp, and a breathing sub-bass.
A major pentatonic @ A=432, additive only, never dreary.

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

# ---- felt_hush (felt soft-tap — an almost-inaudible felt pad tap, the gentlest possible "tick") ----
def voice_felt_hush(seed):
    """K of Spades — the gentlest possible felt-pad tap. An almost-inaudible
    'tick': a felt mallet kissing a warm wooden surface. Built from a tiny
    fast-decaying low body pip + a short soft-noise transient, lowpassed warm.
    Very short, very dry, deliberately quiet. No click edge — soft attack."""
    rng = np.random.default_rng(seed)
    dur = 0.18
    n = int(dur * SR); t = t_axis(dur)

    # warm wooden body: low pip, slight pitch wobble per seed (stays felt-soft)
    body_f = 196.0 * (2 ** (rng.uniform(-1.5, 1.5) / 12.0))  # ~G3, gentle drift
    body = (
        np.sin(2*np.pi*body_f*t) * np.exp(-t*42) +
        0.30 * np.sin(2*np.pi*body_f*2.01*t) * np.exp(-t*70)
    )

    # felt contact transient: short band-limited noise burst, very brief
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 1400.0, order=2)          # warm, no hiss top
    noise = noise - lowpass_fft(noise, 220.0, order=2)   # band: felt 'pad' touch
    nz_env = np.exp(-t * 130)                             # ~8 ms of contact

    sig = 0.85 * body + 0.55 * noise * nz_env

    # soft overall envelope: >=2ms attack so there's never a raw sample-zero edge
    env = adsr(n, a=0.003, d=0.05, s_level=0.0, r=0.10)
    sig = sig[:env.size] * env[:sig.size]

    sig = lowpass_fft(sig, 2600.0, order=3)              # keep it rounded/woody

    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig * (0.48 / peak)
    return sig


# ---- felt_knock (felt-knock — a warm soft knuckle-on-wood knock) ----
def voice_felt_knock(seed):
    """Warm soft knuckle-on-wood knock. A couple of fast-decaying low-mid
    sine 'body' partials (anchored near A2 so it sits in key) plus a
    short, soft band-limited noise transient for the felt knuckle contact.
    Short and dry — 'in the room with you'. ~0.3s."""
    rng = np.random.default_rng(seed)
    dur = 0.34
    n = int(dur * SR); t = t_axis(dur)

    # Wood body: low-mid tuned thunk. Small per-knock pitch wobble so
    # repeated knocks feel like a real hand, not a loop.
    f0 = freq(45) * (1.0 + rng.uniform(-0.012, 0.012))   # ~A2, warm body
    body = (
        1.00 * np.sin(2*np.pi*f0*t)        * np.exp(-t*22) +   # fundamental thunk
        0.45 * np.sin(2*np.pi*f0*1.5*t)    * np.exp(-t*30) +   # fifth-ish wood overtone
        0.18 * np.sin(2*np.pi*f0*2.76*t)   * np.exp(-t*48)     # quick woody color, gone fast
    )

    # Knuckle contact: short filtered noise burst, soft (not instant) attack.
    noise = rng.standard_normal(n)
    knock = lowpass_fft(noise, 1900.0, order=4)               # roll off harsh top -> warm
    knock = knock - lowpass_fft(knock, 220.0, order=2)        # band-limit lows out of the tick
    k_env = adsr(n, a=0.004, d=0.045, s_level=0.0, r=0.02)    # soft transient, no raw edge
    knock = knock * k_env

    sig = body + 0.5 * knock

    # Overall soft envelope: short non-instant attack, smooth decay.
    env = adsr(n, a=0.003, d=0.18, s_level=0.0, r=0.12)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 3200.0, order=4)                  # keep it rounded/woody
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- rimstick (rim click / cross-stick — a short dry woody tick) ----
def voice_rimstick(arg):
    rng = np.random.default_rng(int(arg) & 0xffffffff)
    dur = 0.12
    n = int(dur * SR)
    t = np.arange(n) / SR

    # --- Woody body: a couple of fast-decaying tuned sines around a fixed
    # rim-tick pitch (mid-high wood "tock"), with tiny seed-driven detune. ---
    base = 540.0 * (2 ** (rng.uniform(-0.18, 0.18) / 12.0))  # ~C#5 woody tock
    body = np.zeros(n)
    for mult, amp, dec in ((1.0, 1.0, 0.045), (2.01, 0.45, 0.030), (3.02, 0.18, 0.020)):
        ph = rng.uniform(0, 2*np.pi)
        body += amp * np.sin(2*np.pi*base*mult*t + ph) * np.exp(-t/dec)
    body /= 1.63

    # --- Click transient: short filtered noise burst, the "stick on rim". ---
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 3200, order=3)
    # soft but quick attack (>=2ms) then fast decay -> tactile tick
    nenv = adsr(n, 0.0025, 0.022, 0.0, 0.0)
    click = noise * nenv * 0.6

    # body gets its own soft-attack envelope so no raw zero-edge
    benv = adsr(n, 0.003, 0.05, 0.0, 0.0)
    body = body * benv

    out = body + click
    out = lowpass_fft(out, 4200, order=4)   # keep it warm, roll off harsh top
    out = soft_clip(out, 1.1)

    peak = np.max(np.abs(out)) + 1e-9
    out = out * (0.50 / peak)
    return out.astype(np.float32)


# ---- hollow_knock (woodblock — a hollow tuned wooden knock with a clear quick pitch) ----
def voice_hollow_knock(midi):
    """A hollow tuned woodblock: a clear quick pitched body (just a couple of
    fast-decaying low-mid partials) + a soft filtered noise 'knock' transient.
    Short, dry, warm. arg = midi."""
    f = freq(midi)
    dur = 0.26
    n = int(dur * SR)
    t = t_axis(dur)

    # --- pitched hollow body: fundamental + a quiet hollow-ish overtone ---
    # very fast decay so it reads as a "knock", not a tone
    body_env = np.exp(-t * 34.0)
    # tiny pitch drop at the very start gives the woody "tock"
    pitch_drop = 1.0 + 0.06 * np.exp(-t * 220.0)
    phase = 2*np.pi*f*pitch_drop*t
    body = np.sin(phase) * body_env
    # hollow overtone (~2.76x, woodblock-ish, inharmonic but gentle) decays faster
    body += 0.32 * np.sin(2*np.pi*f*2.76*t) * np.exp(-t * 70.0)
    # quiet octave for solidity
    body += 0.18 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t * 50.0)

    # --- soft knock transient: short band-limited noise burst ---
    rng = np.random.default_rng(int(midi) * 101 + 7)
    noise = rng.standard_normal(n)
    # soft non-instant attack (~2.5 ms) + quick decay -> no raw zero-edge click
    knock_env = adsr(n, a=0.0025, d=0.030, s_level=0.0, r=0.001, hold=0.0)
    knock = noise * knock_env
    # keep it warm: roll off the harsh top, center it near the body pitch region
    knock = lowpass_fft(knock, 2200, order=4)

    out = body + 0.22 * knock

    # overall soft shaping: gentle attack so the body never starts on a hard edge
    soft = adsr(n, a=0.003, d=0.01, s_level=1.0, r=0.04, hold=dur*0.6)
    out = out * soft

    # warm the whole thing
    out = lowpass_fft(out, 4200, order=4)
    out = soft_clip(out, 1.05)

    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / peak * 0.50
    return out


# ---- temple_block (temple block — a rounded hollow wooden bonk, warm and tuned) ----
def voice_temple_block(midi):
    f = freq(midi)
    dur = 0.34
    n = int(dur * SR); t = t_axis(dur)[:n]
    # Hollow tuned body: fundamental plus a slightly stretched octave and a
    # quick mid partial that gives the rounded "bonk" knock. Fast decays so it
    # reads as a wooden temple-block, not a sustained pitch.
    body = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*14) +
        0.45 * np.sin(2*np.pi*f*2.01*t)   * np.exp(-t*26) +
        0.18 * np.sin(2*np.pi*f*3.02*t)   * np.exp(-t*42)
    )
    # Soft wooden transient: short filtered noise burst, warm (lowpassed),
    # decays in ~12 ms so it's the "tock" of the mallet, never a sharp click.
    rng = np.random.default_rng(int(midi) * 7 + 3)
    noise = rng.standard_normal(n)
    tock = lowpass_fft(noise, 2200.0, order=3) * np.exp(-t*180)
    sig = body + 0.30 * tock
    # gentle overall warmth roll-off
    sig = lowpass_fft(sig, 4200.0, order=4)
    # soft, non-instant attack (~3 ms) + smooth decay
    env = adsr(n, a=0.003, d=0.12, s_level=0.0, r=0.20)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- clave (clave — a bright dry hardwood click, two sticks meeting) ----
def voice_clave(seed):
    """Two hardwood sticks meeting — a bright dry resonant 'pock'.
    A clave's tone comes from a short tuned wooden cavity: a couple of
    close high partials (~1.5-2.4 kHz) that ring for only ~40 ms, plus a
    tiny filtered-noise 'contact' transient at the strike. Bright but
    rounded — lowpassed so there is no glassy top, and a >=2 ms attack so
    the strike is soft, never a raw sample-zero click."""
    rng = np.random.default_rng(seed)
    dur = 0.12; n = int(dur * SR); t = t_axis(dur)
    # slight per-hit tuning wobble so repeated taps feel like real wood
    f0 = 1480.0 * (1.0 + rng.uniform(-0.03, 0.03))
    # tuned wooden body: two close inharmonic partials, fast independent decay
    body = (
        1.00 * np.sin(2*np.pi*f0*t)        * np.exp(-t*70) +
        0.55 * np.sin(2*np.pi*f0*1.58*t)   * np.exp(-t*95) +
        0.22 * np.sin(2*np.pi*f0*2.42*t)   * np.exp(-t*130)
    )
    # contact transient: short band of noise, the 'click' of stick-on-stick
    noise = rng.standard_normal(n) * np.exp(-t*420)
    noise = lowpass_fft(noise, 5200, order=2) - lowpass_fft(noise, 900, order=2)
    sig = body * 0.55 + noise * 0.45
    # keep it warm: roll off the harsh top
    sig = lowpass_fft(sig, 5500, order=3)
    # soft strike: 3 ms attack (no raw edge), quick smooth decay
    env = adsr(n, a=0.003, d=0.05, s_level=0.0, r=0.06)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- cork_pop (cork-pop — a soft rounded little pop, friendly and bright) ----
def voice_cork_pop(seed):
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.12
    n = int(dur * SR)
    t = np.arange(n) / SR

    # tiny rate jitter so each pop is a slightly different little cork
    jit = 1.0 + (rng.random() - 0.5) * 0.14
    body_f = 320.0 * jit            # rounded woody body
    pop_f  = 760.0 * jit            # bright "pock" overtone

    # --- soft transient: a fast band of noise, smoothly shaped (no zero-edge) ---
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 2600.0, order=3)        # warm, no screech up top
    # short but non-instant attack (~3ms), quick smooth decay
    tr_env = adsr(n, 0.003, 0.030, 0.0, 0.0)
    transient = noise * tr_env * 0.55

    # --- rounded body: two fast-decaying low sines = the "round" of the pop ---
    b1_env = adsr(n, 0.0025, 0.060, 0.0, 0.0)
    b2_env = adsr(n, 0.0025, 0.035, 0.0, 0.0)
    body = (np.sin(2*np.pi*body_f*t) * b1_env * 0.9
            + np.sin(2*np.pi*pop_f*t)  * b2_env * 0.45)

    x = body + transient
    x = lowpass_fft(x, 3800.0, order=3)                # keep it soft & woody
    x = soft_clip(x, 1.1)

    peak = np.max(np.abs(x)) + 1e-9
    x = x / peak * 0.50
    return x.astype(np.float32)


# ---- felt_thump (soft thump — a low felt heartbeat/kick, round and warm) ----
def voice_felt_thump(seed):
    """Soft felt heartbeat/kick. A low rounded sine 'body' with a quick
    downward pitch drop (the felt-mallet 'give'), wrapped in a soft
    non-instant attack, plus a tiny breath of low-passed noise for the
    felt texture. Short, dry, warm. Unpitched-ish but anchored low."""
    rng = np.random.default_rng(seed)
    dur = 0.34
    n = int(dur * SR); t = t_axis(dur)

    # Body: low sine ~74 Hz settling to ~58 Hz — the round 'thump'.
    f0 = 74.0 + rng.uniform(-3.0, 3.0)
    f1 = 56.0 + rng.uniform(-2.0, 2.0)
    # exponential pitch glide from f0 down to f1 over ~60 ms
    drop = np.exp(-t * 28.0)
    inst_f = f1 + (f0 - f1) * drop
    phase = 2*np.pi*np.cumsum(inst_f)/SR
    body = np.sin(phase)
    body_env = np.exp(-t * 11.0)            # quick round decay
    body = body * body_env

    # gentle 2nd partial for a touch of wooden 'knock', decays fast
    knock = 0.18 * np.sin(2*phase) * np.exp(-t * 30.0)

    # Felt texture: very soft low-passed noise tick at the attack only
    noise = rng.standard_normal(n)
    noise = lowpass_fft(noise, 420.0, order=2)
    noise_env = np.exp(-t * 60.0)
    felt = 0.10 * noise * noise_env

    sig = body + knock + felt

    # Soft non-instant attack (~4 ms) so there's never a raw zero-edge click,
    # and a smooth release.
    env = adsr(n, a=0.004, d=0.10, s_level=0.0, r=0.20)
    sig = sig[:env.size] * env[:sig.size]

    # keep it warm — roll off anything bright/harsh
    sig = lowpass_fft(sig, 900.0, order=3)

    # land peak ~0.5
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-6:
        sig = sig * (0.50 / peak)
    return sig


# ---- dewspring (mallet) ----
def voice_dewspring(arg):
    """Bright playful glock/mallet — sweet, bouncy, clean. ~1.8s.
    Additive only: a strong sine fundamental, a clean 2x octave that decays
    fast, a soft 3x for a little 'sparkle' ping at the attack, and a tiny
    inharmonic 4.1x glint that dies in ~25ms so it reads as the mallet
    'tick' rather than a metallic ring. A gentle 1.004x detune body gives
    a touch of bloom. Fast soft attack (~7ms) keeps it bouncy but click-free.
    A-pentatonic safe; major family; no FM."""
    midi = int(arg)
    f = freq(midi)
    dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)                                +  # fundamental
        0.45 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*5.5)         +  # clean octave sparkle
        0.16 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*9.0)         +  # bright ping
        0.06 * np.sin(2*np.pi*f*4.1*t)   * np.exp(-t*40.0)        +  # mallet tick (gone in ~25ms)
        0.18 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*2.0)            # soft body bloom
    )
    env = adsr(n, a=0.007, d=1.1, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7000.0, order=2)  # tame any high fizz, keep it sweet
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- clearsong (tone) ----
def voice_clearsong(midi):
    """Pure sweet sustained TONE — a kalimba that decided to sing. One clean
    sine fundamental with a soft octave partial that fades early, a whisper of
    detune for body, and the gentlest vibrato that only opens after the attack.
    Bright, singing, A-pentatonic-safe. ~2.5s. Additive only, no FM."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    # vibrato that fades IN after the note has spoken (singing, not warbly)
    vib_depth = 0.0025 * np.clip((t - 0.4) / 0.6, 0.0, 1.0)
    vib = 1.0 + vib_depth * np.sin(2*np.pi*5.0*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR
    sig = (
        1.00 * np.sin(phase) +                                   # clean fundamental
        0.18 * np.sin(2*phase) * np.exp(-t*2.2) +                # soft octave, fades early
        0.05 * np.sin(3*phase) * np.exp(-t*5.0) +                # faint sweetener, gone fast
        0.10 * np.sin(2*np.pi*f*1.004*t)                         # whisper of detune for body
    )
    # tame any high edge so it stays sweet over wood
    sig = lowpass_fft(sig, 4200.0, order=3)
    env = adsr(n, a=0.020, d=0.8, s_level=0.55, r=1.3)
    out = sig[:env.size] * env[:sig.size] * 0.45
    return out


# ---- jewel_celeste (chime) ----
def voice_jewel_celeste(midi):
    """Warm celeste / glass chime. Additive, sweet, ~2.5s. A jewel that
    melts in: soft 18ms attack (no click), a glowing fundamental with a
    pure octave 'celeste doubling', a gentle tine-glass partial at 3x that
    decays fast, and a whisper of high glass sparkle that fades in ~50ms so
    you only catch it as a glint at the onset. No FM, no partials past 5x."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)                      * np.exp(-t*1.1)  +  # warm body
        0.55 * np.sin(2*np.pi*f*2.0*t)                  * np.exp(-t*1.6)  +  # celeste octave
        0.20 * np.sin(2*np.pi*f*3.0*t)                  * np.exp(-t*2.8)  +  # sweet glass color
        0.07 * np.sin(2*np.pi*f*4.0*t)                  * np.exp(-t*4.5)  +  # faint shimmer
        0.05 * np.sin(2*np.pi*f*5.0*t)                  * np.exp(-t*6.0)      # tiny glint, gone fast
    )
    # gentle chorus shimmer (two near-unisons) for the "glowing jewel" warmth
    sig += 0.18 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.2)
    sig += 0.14 * np.sin(2*np.pi*f*0.997*t) * np.exp(-t*1.2)
    # very soft attack — no click, jewel melts in
    env = adsr(n, a=0.018, d=2.0, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    # tame any harshness above the sweet range
    out = lowpass_fft(out, 7000.0, order=3)
    # land peak ~0.50
    peak = np.max(np.abs(out))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- sunlift (glow) ----
def voice_sunlift(arg):
    """A gentle bright SWELL — soft upward shimmer that lifts and opens.
    The Sun Card. Additive only: a fundamental + sweet octave + a fifth,
    plus a high airy sparkle that fades in late. A slow filter that OPENS
    over the swell makes it 'brighten' as it rises, like sun through a window.
    A subtle upward pitch glide (~+40 cents settling) gives the 'lift'.
    No FM, no harsh partials. Lands soft, blooms, releases long.
    arg = midi (HIGH)."""
    midi = int(arg)
    f = freq(midi)
    dur = 5.2
    n = int(dur * SR); t = t_axis(dur)

    # gentle upward glide: starts ~45 cents low, settles to pitch over ~1.8s.
    glide = np.exp(-t / 0.9)            # 1 -> 0
    bend = 2 ** ((-0.45 * glide) / 12.0)  # semitone fraction -> ratio
    phase = 2*np.pi*f*np.cumsum(bend)/SR

    # additive partials — all consonant (octave, fifth = pentatonic-safe)
    sig = (
        1.00 * np.sin(phase) +
        0.50 * np.sin(2.0*phase) +          # sweet octave
        0.22 * np.sin(3.0*phase) +          # fifth-above-octave, soft
        0.10 * np.sin(4.0*phase)            # gentle 2-oct, kept low
    )
    # high airy sparkle that fades IN late, then drifts away — the "glow"
    spark_env = np.clip((t - 0.6) / 1.6, 0, 1) * np.exp(-(np.maximum(t-2.2,0))/2.0)
    sig += 0.16 * np.sin(5.0*phase) * spark_env

    # very slow shimmer (chorus-like) on the body, tiny and slow -> warmth
    vib = 1 + 0.0025 * np.sin(2*np.pi*4.2*t)
    sig = sig * vib

    # FILTER OPENS over the swell: dark at onset -> bright at peak -> settle.
    # Do it as a 2-band blend so it stays smooth and cheap.
    bright = sig - lowpass_fft(sig, 700.0, order=3)
    body   = sig - bright
    open_env = np.clip(t / 2.4, 0, 1)        # 0 -> 1 as it lifts
    open_env = open_env * (1 - 0.25*np.clip((t-3.0)/2.2,0,1))  # gentle settle
    sig = body + bright * (0.18 + 0.82*open_env)

    # soft swell envelope: slow fade-in (no click), bloom, long release
    env = adsr(n, a=0.9, d=1.2, s_level=0.55, hold=0.4, r=2.4)
    out = sig[:env.size] * env[:sig.size]

    # tame any high-end fizz, keep it sweet
    out = lowpass_fft(out, 6500.0, order=4)

    peak = np.max(np.abs(out))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# ---- lovebird (chirp) ----
def voice_lovebird(seed):
    """Jack of Hearts — 'Sacrificial Love'. One sweet single chirp:
    a quick rising whistle-blip in A major pentatonic, bright & friendly.
    Additive (pure sines + tiny octave sparkle), ~0.4s, near-dry. Seed picks
    a starting note from the HIGH pentatonic and a small upward leap so each
    chirp is a cheerful little 2-note rising blip that perches over the wood."""
    rng = np.random.default_rng(int(seed))
    HIGH = [69, 73, 76, 78, 81, 85]          # A maj pentatonic, high register
    leaps = [2, 3, 4]                         # pentatonic steps up (indices)
    start_i = int(rng.integers(0, 3))        # keep room to leap upward
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i])
    f1 = freq(HIGH[end_i])

    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)

    # Smooth rising pitch glide: ease from f0 up to f1 over the first ~60%,
    # then hold — like a little whistle that lifts and settles.
    rise = np.clip(t / (dur * 0.6), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep — no zipper
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR

    sig = (
        np.sin(phase) +
        0.18 * np.sin(2*phase) +             # gentle octave for a glassy sheen
        0.05 * np.sin(3*phase) * np.exp(-t*14)  # tiny chiff at the very onset
    )
    # soft warm top so it never gets piercing over the wood
    sig = lowpass_fft(sig, 6500.0, order=3)

    env = adsr(n, a=0.012, d=0.10, s_level=0.55, r=0.22)
    out = sig[:env.size] * env[:sig.size] * 0.50
    return out


# ---- mother_bloom (bloom) ----
def voice_mother_bloom(midi):
    """Soft maternal pad bloom — a warm, enveloping major-tone swell that
    blooms open like arms and slowly closes again. Additive only.

    A clean fundamental + a gentle just-major-third + just-fifth above it
    (frequency ratios 5/4 and 3/2, sweet and consonant, A-pentatonic-safe)
    plus a soft octave halo. Two slightly-detuned copies of the fundamental
    give a breathing chorus shimmer. Everything low-passed so there is NO
    harsh upper partial — round and nurturing, never glassy. ~7s."""
    f = freq(midi)
    dur = 7.0
    n = int(dur * SR); t = t_axis(dur)

    # very slow breathing vibrato — like a calm exhale
    vib = 1.0 + 0.0016 * np.sin(2*np.pi*0.28*t)

    # warm chorus on the fundamental: two faint detunes
    fund = (
        np.sin(2*np.pi*f*t*vib) +
        0.45 * np.sin(2*np.pi*f*1.0035*t) +
        0.45 * np.sin(2*np.pi*f*0.9967*t)
    )

    # consonant major-tone halo above (just intonation: sweet, never beating)
    third  = 0.40 * np.sin(2*np.pi*f*(5/4)*t*vib)   # major third
    fifth  = 0.34 * np.sin(2*np.pi*f*(3/2)*t*vib)   # perfect fifth
    octave = 0.22 * np.sin(2*np.pi*f*2.0*t)         # soft octave halo
    # tiny sub for warmth/body
    sub    = 0.30 * np.sin(2*np.pi*f*0.5*t)

    sig = fund + third + fifth + octave + sub

    # bloom: the brightness opens up over the first few seconds then settles —
    # a moving lowpass gives the "swelling open" feeling without harshness.
    low  = lowpass_fft(sig, 700.0, order=3)
    high = sig - low
    open_curve = 0.25 + 0.75 * (0.5 - 0.5*np.cos(2*np.pi*np.minimum(t/ (dur*0.85),1.0)))
    sig = low + high * open_curve

    # final warmth ceiling — keep it round, kill any residual fizz
    sig = lowpass_fft(sig, 2600.0, order=3)

    # slow nurturing swell-in, long gentle release
    env = adsr(n, a=1.6, d=1.0, s_level=0.85, hold=1.2, r=3.0)
    out = sig[:env.size] * env[:sig.size]

    # normalize to a soft target peak
    pk = np.max(np.abs(out))
    if pk > 1e-9:
        out = out / pk * 0.50
    return out


# ---- communion (cluster) ----
def voice_communion(arg):
    """7 of Hearts - 'Spiritual Love'. A soft bright pentatonic chord
    CLUSTER that swells and glows for a SessionStart welcome. From the
    passed root midi we build a major-pentatonic-safe chord: root, +4
    (maj3), +7 (5th), +9 (maj6), +12 (octave). Pure additive sines with
    a faint shimmering octave, gentle detune, slow breathing vibrato and
    staggered swells so the chord blooms open like an inhale. Warm
    low-passed so it sits over wooden taps without any harsh edge."""
    root = int(arg)
    intervals = [0, 4, 7, 9, 12]
    dur = 7.2
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        # gentle additive body: fundamental + soft 2nd & 3rd partials only
        partial = (np.sin(2*np.pi*f*t)
                   + 0.18*np.sin(2*np.pi*2*f*t)
                   + 0.07*np.sin(2*np.pi*3*f*t))
        # subtle detune twin for warmth/movement
        detune = np.sin(2*np.pi*f*1.0035*t)
        # slow breathing vibrato, each voice phased differently
        vib = 1 + 0.0022*np.sin(2*np.pi*0.22*t + i*0.9)
        voice = (0.85*partial + 0.35*detune) * vib
        # staggered swell: upper notes bloom slightly later -> opening glow
        stagger = 0.18 * i
        env = adsr(n, a=1.8 + stagger, d=0.7, s_level=0.82,
                   hold=1.6, r=2.6)
        # high voices a touch quieter so the root stays grounded
        gain = 1.0 - 0.10*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    # warm: tame anything above ~5x of the root, no harsh partials
    sig = lowpass_fft(sig, 2600, order=3)
    peak = np.max(np.abs(sig)) + 1e-9
    sig = sig / peak * 0.50
    return sig


# ---- lowtide (low_bass) ----
def voice_lowtide(arg):
    """K of Spades — 'The Master Card'. A deep warm bass PULSE with a soft
    felt attack. Round sine fundamental + just a kiss of 2nd/3rd harmonic for
    warmth (all tamed fast, nothing above 3x). A gentle ~2.7 Hz amplitude
    'breathe' gives subtle movement so the floor feels alive, not static.
    Felt attack = slow 22 ms rise (no click), soft felt 'thud' transient that
    is a low-passed noise puff decaying in ~50 ms. Near-dry, A-pentatonic LOW."""
    f = freq(int(arg))
    dur = 2.5
    n = int(dur * SR); t = t_axis(dur)

    # Round body: fundamental dominant, gentle warmth from low harmonics only.
    body = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.22 * np.sin(2*np.pi*f*2*t) * np.exp(-t*2.5) +   # warmth, fades early
        0.07 * np.sin(2*np.pi*f*3*t) * np.exp(-t*5.0) +   # tiny edge, gone fast
        0.05 * np.sin(2*np.pi*f*1.004*t)                  # slow beat = "wood" life
    )
    # Subtle slow breathe so the floor has movement (a touch, ~2.7 Hz).
    breathe = 1.0 + 0.06 * np.sin(2*np.pi*2.7*t - np.pi/2)
    body = body * breathe

    # Soft FELT attack: low-passed noise puff, very short — the pad of a mallet
    # hitting felt, not a click.
    rng = np.random.default_rng(int(arg) * 17 + 5)
    puff = rng.standard_normal(n)
    puff = lowpass_fft(puff, 280.0, order=3)
    puff_env = np.exp(-t * 22.0)               # ~45 ms felt thud
    body = body + 0.18 * puff * puff_env

    # Keep it round: roll off anything bright; bass should be felt, not heard up top.
    body = lowpass_fft(body, 900.0, order=4)

    # Warm rounded envelope: felt attack (22 ms), long supportive sustain, soft tail.
    env = adsr(n, a=0.022, d=0.5, s_level=0.55, hold=0.6, r=1.1)
    out = body[:env.size] * env[:body.size]

    out = soft_clip(out * 1.05, 1.0)
    # land peak ~0.5
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out * (0.5 / peak)
    return out


PLAN = {
    "felt_hush": {
        "kind": "seed",
        "count": 4,
        "pans": [
            -0.25,
            0.2,
            -0.1,
            0.3
        ],
        "target_peak": 0.5,
        "reverb": {
            "wet": 0,
            "decay": 0.6,
            "predelay_ms": 8,
            "brightness": 0.35
        }
    },
    "felt_knock": {
        "kind": "seed",
        "count": 4,
        "pans": [
            -0.18,
            0.2,
            -0.1,
            0.14
        ],
        "target_peak": 0.85,
        "reverb": {
            "wet": 0.05,
            "decay": 0.6,
            "predelay_ms": 8,
            "brightness": 0.3
        }
    },
    "rimstick": {
        "kind": "seed",
        "count": 4,
        "pans": [
            -0.25,
            0,
            0.25,
            0.1
        ],
        "target_peak": 0.85,
        "reverb": {
            "wet": 0.02,
            "decay": 0.5,
            "predelay_ms": 8,
            "brightness": 0.4
        }
    },
    "hollow_knock": {
        "kind": "midi",
        "midis": [
            45,
            49,
            52,
            57,
            61,
            64
        ],
        "pans": [
            -0.25,
            0,
            0.25,
            -0.12,
            0.12,
            0
        ],
        "target_peak": 0.85,
        "reverb": {
            "wet": 0.05,
            "decay": 0.7,
            "predelay_ms": 8,
            "brightness": 0.5
        }
    },
    "temple_block": {
        "kind": "midi",
        "midis": [
            57,
            61,
            64,
            66,
            69,
            73,
            76
        ],
        "pans": [
            -0.2,
            0.2,
            -0.1,
            0.15
        ],
        "target_peak": 0.7,
        "reverb": {
            "wet": 0.05,
            "decay": 0.6,
            "predelay_ms": 8,
            "brightness": 0.35
        }
    },
    "clave": {
        "kind": "seed",
        "count": 4,
        "pans": [
            -0.3,
            0.25,
            -0.15,
            0.4
        ],
        "target_peak": 0.82,
        "reverb": {
            "wet": 0.05,
            "decay": 0.6,
            "predelay_ms": 8,
            "brightness": 0.4
        }
    },
    "cork_pop": {
        "kind": "seed",
        "count": 4,
        "pans": [
            -0.2,
            0.15,
            -0.05,
            0.25
        ],
        "target_peak": 0.5,
        "reverb": {
            "wet": 0.05,
            "decay": 0.6,
            "predelay_ms": 8,
            "brightness": 0.45
        }
    },
    "felt_thump": {
        "kind": "seed",
        "count": 4,
        "pans": [
            0,
            -0.1,
            0.1,
            0
        ],
        "target_peak": 0.6,
        "reverb": {
            "wet": 0.05,
            "decay": 0.6,
            "predelay_ms": 8,
            "brightness": 0.3
        }
    },
    "dewspring": {
        "kind": "midi",
        "midis": [
            57,
            59,
            61,
            64,
            66,
            69,
            71,
            73,
            76,
            78,
            81
        ],
        "pans": [
            -0.2,
            0.2,
            -0.1,
            0.15
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.18,
            "decay": 1.6,
            "predelay_ms": 18,
            "brightness": 0.6
        }
    },
    "clearsong": {
        "kind": "midi",
        "midis": [
            57,
            61,
            64,
            69,
            73,
            76
        ],
        "pans": [
            -0.15,
            0.15
        ],
        "target_peak": 0.82,
        "reverb": {
            "wet": 0.16,
            "decay": 2.4,
            "predelay_ms": 22,
            "brightness": 0.55
        }
    },
    "jewel_celeste": {
        "kind": "midi",
        "midis": [
            69,
            73,
            76,
            78,
            81,
            85,
            88
        ],
        "pans": [
            -0.4,
            0.3,
            -0.2,
            0.4,
            -0.3,
            0.2,
            0
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.36,
            "decay": 3.2,
            "predelay_ms": 28,
            "brightness": 0.62
        }
    },
    "sunlift": {
        "kind": "midi",
        "midis": [
            69,
            73,
            76,
            78,
            81,
            85,
            88
        ],
        "pans": [
            -0.15,
            0.15,
            -0.1,
            0.1,
            0,
            -0.2,
            0.2
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.46,
            "decay": 4.6,
            "predelay_ms": 38,
            "brightness": 0.62
        }
    },
    "lovebird": {
        "kind": "seed",
        "count": 6,
        "pans": [
            0.35,
            -0.3,
            0.45,
            -0.4
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.1,
            "decay": 1.6,
            "predelay_ms": 12,
            "brightness": 0.6
        }
    },
    "mother_bloom": {
        "kind": "midi",
        "midis": [
            57,
            61,
            64,
            66,
            69
        ],
        "pans": [
            0,
            -0.15,
            0.15
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.5,
            "decay": 5,
            "predelay_ms": 45,
            "brightness": 0.42
        }
    },
    "communion": {
        "kind": "midi",
        "midis": [
            57,
            61,
            64,
            66,
            69
        ],
        "pans": [
            0,
            -0.15,
            0.15
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.5,
            "decay": 5,
            "predelay_ms": 45,
            "brightness": 0.4
        }
    },
    "lowtide": {
        "kind": "midi",
        "midis": [
            33,
            36,
            40,
            45,
            49,
            52
        ],
        "pans": [
            0,
            0,
            0,
            0,
            0,
            0
        ],
        "target_peak": 0.6,
        "reverb": {
            "wet": 0.09,
            "decay": 1.6,
            "predelay_ms": 12,
            "brightness": 0.3
        }
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
    print("whittle:", name)


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
