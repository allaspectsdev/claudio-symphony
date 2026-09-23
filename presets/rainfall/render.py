#!/usr/bin/env python3
"""
Rainfall preset — sample renderer.

Aesthetic: the developer is in a quiet room. Outside, far away, something
gentle is happening. Most of the time you don't hear anything. Then,
occasionally — a tiny pitched 'plip'. Once every minute or two, a slow
chord blooms in the distance and recedes.

Voices:
  drop   — tiny pitched FM pluck, 8 pitches A4..A5, very short decay
  tap    — almost subliminal noise pop with pitched resonance, 4 pitches
  swell  — 25 s pad swell, 3 chord variants, the rare droney event
  pulse  — small bell ping, 4 pitches A5..F#6
"""
import sys, math
from pathlib import Path
import numpy as np

# import shared DSP from top-level synth.py
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from synth import (
    SR, freq, t_axis, adsr, lowpass_fft,
    reverb_stereo, write_wav,
)

# === reverb_scale monkeypatch ===
# Reads top-level reverb_scale from this preset's preset.json (default 1.0)
# and multiplies every reverb_stereo() wet by it. Lets `claudio preset reverb`
# tune ALL voices' reverb in one shot without editing the call sites.
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
for sub in ("drop", "tap", "swell", "pulse"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)

# ---------- voices ----------

def voice_drop(midi):
    """Tiny pluck — pure sine with a brief glassy attack partial.
    ~250 ms total. Sounds like a single bead of water meeting a still
    pond — pitched, then gone. Additive (no FM buzz)."""
    f = freq(midi)
    dur = 0.7
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t) +
        # brief stretched-octave partial — gives the 'plip' character
        0.30 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*25) +
        # tiny inharmonic shimmer (only audible at attack)
        0.08 * np.sin(2*np.pi*f*2.76*t)  * np.exp(-t*40)
    )
    env = adsr(n, a=0.005, d=0.18, s_level=0.0, r=0.08)
    out = sig[:env.size] * env[:sig.size] * 0.35
    return out

def voice_tap(midi):
    """Filtered noise burst with a faint pitched resonance.
    Almost subliminal — used for the smallest events."""
    rng = np.random.default_rng(int(midi))
    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)
    f = freq(midi)
    noise = rng.standard_normal(n)
    # narrow bandpass-ish resonance via subtraction-of-LPs
    band = lowpass_fft(noise, f * 1.6, order=2) - lowpass_fft(noise, f * 0.6, order=2)
    # add a tiny pitched element
    pitched = 0.5 * np.sin(2*np.pi*f*t) * np.exp(-t * 25)
    sig = 0.7 * band + pitched
    env = adsr(n, a=0.002, d=0.06, s_level=0.0, r=0.04)
    out = sig[:env.size] * env[:sig.size] * 0.25
    return out

def voice_swell(chord_midis):
    """Slow 25 s pad swell. Slower attack and longer release than cathedral
    pad — this is the rare 'droney' event."""
    dur = 25.0
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for m in chord_midis:
        f = freq(m)
        # warm partials
        partials = np.zeros(n)
        for h in range(1, 6):
            partials += (1.0 / h) * np.sin(2*np.pi*f*h*t)
        partials *= 0.35
        sine = np.sin(2*np.pi*f*t)
        det = np.sin(2*np.pi*f*1.005*t)
        # slight slow vibrato on each note
        vib = 1 + 0.0025 * np.sin(2*np.pi*0.18*t + m*0.07)
        sig += (0.8*sine + 0.45*det + 0.45*partials) * vib
    sig /= max(1, len(chord_midis))
    sig = lowpass_fft(sig, 1100.0, order=3)
    # ADSR: 6 s attack, hold 6 s, release 13 s
    env = adsr(n, a=6.0, d=0.5, s_level=0.85, hold=6.0, r=13.0)
    out = sig[:env.size] * env[:sig.size] * 0.40
    return out

def voice_pulse(midi):
    """Small high bell — additive synthesis (no FM buzz). Same recipe as
    the meadow chime, slightly smaller / quicker decay."""
    f = freq(midi)
    dur = 3.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.9) +
        0.45 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.4) +
        0.16 * np.sin(2*np.pi*f*2.76*t)  * np.exp(-t*2.8) +
        0.05 * np.sin(2*np.pi*f*4.5*t)   * np.exp(-t*5.0)
    )
    env = adsr(n, a=0.014, d=2.0, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size] * 0.32
    return out

# ---------- generation ----------

def render_with_pan(mono, wet, decay_s, predelay_ms, brightness, pan=0.0):
    st = reverb_stereo(mono, wet=wet, decay_s=decay_s,
                       predelay_ms=predelay_ms, brightness=brightness)
    if pan != 0.0:
        pan = float(np.clip(pan, -1.0, 1.0))
        lg = math.cos((pan + 1) * math.pi / 4)
        rg = math.sin((pan + 1) * math.pi / 4)
        st = st.copy()
        st[:, 0] *= 2 * lg
        st[:, 1] *= 2 * rg
    return st

def gen_all():
    print("[rainfall] rendering...")

    # drop — light reverb so drops feel intimate, not echoed across a hall
    drop_midis = [69, 71, 73, 75, 76, 78, 80, 81]
    for i, m in enumerate(drop_midis):
        print(f"  drop m{m}")
        pan = (-0.4, -0.2, 0.0, 0.2, 0.4, 0.2, -0.2, 0.0)[i % 8]
        st = render_with_pan(voice_drop(m), wet=0.18, decay_s=1.2,
                             predelay_ms=15, brightness=0.45, pan=pan)
        write_wav(OUT / "drop" / f"{i:02d}_m{m}.wav", st, target_peak=0.78)

    # tap — DRY. Almost subliminal noise pop, no echo.
    tap_midis = [81, 85, 88, 90]
    for i, m in enumerate(tap_midis):
        print(f"  tap m{m}")
        pan = (-0.5, -0.2, 0.2, 0.5)[i]
        st = render_with_pan(voice_tap(m), wet=0.0, decay_s=0.5,
                             predelay_ms=0, brightness=0.55, pan=pan)
        write_wav(OUT / "tap" / f"{i:02d}_m{m}.wav", st, target_peak=0.55)

    # swell — KEEPS heavy reverb. This is the rare droney bloom event.
    chords = [
        [69, 76, 71],         # A4 E5 B4
        [69, 73, 78],         # A4 C#5 F#5
        [69, 75, 81],         # A4 D#5 A5  — the #4 voicing
    ]
    for i, c in enumerate(chords):
        print(f"  swell {i} {c}")
        st = render_with_pan(voice_swell(c), wet=0.52, decay_s=4.0,
                             predelay_ms=55, brightness=0.35, pan=0.0)
        write_wav(OUT / "swell" / f"{i:02d}.wav", st, target_peak=0.80)

    # pulse — medium reverb; high bells should ring but not haunt
    pulse_midis = [81, 85, 88, 90]
    for i, m in enumerate(pulse_midis):
        print(f"  pulse m{m}")
        pan = (-0.25, 0.0, 0.0, 0.25)[i]
        st = render_with_pan(voice_pulse(m), wet=0.38, decay_s=2.2,
                             predelay_ms=35, brightness=0.45, pan=pan)
        write_wav(OUT / "pulse" / f"{i:02d}_m{m}.wav", st, target_peak=0.70)

    print("[rainfall] done.")

if __name__ == "__main__":
    gen_all()
