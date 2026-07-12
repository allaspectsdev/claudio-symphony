#!/usr/bin/env python3
"""
Koto preset — sample renderer.

Aesthetic: Japanese koto (plucked silk strings) + temple bowl + mokugyo
(small wooden fish-drum). Three voices only — cohesion through limitation.

Tonal world: A In sen scale (A B♭ C E F). The iconic "Japanese melancholy"
pentatonic — internally consonant, deliberately a different emotional space
from cathedral/meadow/rainfall (which are A Lydian / A pentatonic-major).

Voices:
  koto    — plucked silk string. Bright attack, long warm decay,
            characteristic metallic-detuned partials. Light reverb for
            presence — the koto already has natural sustain.
  bowl    — temple/Tibetan singing bowl. Slow fundamental + close-spaced
            second tone produces audible beating. Long warm decay.
            Medium reverb (it should ring but not haunt).
  mokugyo — small wooden fish-drum tap. Hollow body resonance, very brief.
            DRY — should feel right next to you in the room.
"""
import sys, math
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (
    SR, A4, freq, t_axis, adsr, soft_clip, lowpass_fft,
    reverb_stereo, to_stereo, write_wav,
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
for sub in ("koto", "bowl", "mokugyo"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)

# A In sen scale (A B♭ C E F) — pitch classes 9, 10, 0, 4, 5
# Across octaves 3-5: A3, B♭3, C4, E4, F4, A4, B♭4, C5, E5, F5, A5
INSEN_PITCHES = [57, 58, 60, 64, 65, 69, 70, 72, 76, 77, 81]

# Bowl voices: high register, fewer pitches
BOWL_PITCHES = [69, 72, 76, 81]   # A4, C5, E5, A5

# ---------- voices ----------

def voice_koto(midi):
    """Plucked silk string. Karplus-Strong-flavored timbre faked with
    sum of partials in slightly-inharmonic ratios (silk strings are NOT
    perfectly harmonic — they have a characteristic stretched tuning).

    The 'bend' of a real koto comes from left-hand pressure on the string —
    here we add a tiny sub-cent pitch glide at attack to suggest the same
    physical compliance. Long warm decay because silk is dampened slowly."""
    f = freq(midi)
    dur = 4.5
    n = int(dur * SR); t = t_axis(dur)
    rng = np.random.default_rng(int(midi) + 31)

    # Stretched-octave partials (typical of a real plucked string)
    # 1.0, 2.003, 3.012, 4.04, 5.10 ratios — sounds 'real string' not 'pure synth'
    body = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.1) +
        0.55 * np.sin(2*np.pi*f*2.003*t) * np.exp(-t*1.6) +
        0.32 * np.sin(2*np.pi*f*3.012*t) * np.exp(-t*2.4) +
        0.18 * np.sin(2*np.pi*f*4.04*t)  * np.exp(-t*3.5) +
        0.10 * np.sin(2*np.pi*f*5.10*t)  * np.exp(-t*5.0)
    )
    # Tiny detune layer for shimmer / 'two strings' feel
    body += 0.18 * np.sin(2*np.pi*f*1.0025*t) * np.exp(-t*1.2)

    # Pluck attack: short bright noise burst
    pluck = rng.standard_normal(n) * np.exp(-t*180) * 0.05
    pluck_band = lowpass_fft(pluck, max(f*5, 1500), order=2) - lowpass_fft(pluck, f*1.2, order=2)

    # Subtle attack pitch glide (left hand 'gives' against the string)
    pitch_env = 1 - 0.001 * np.exp(-t * 50)
    body = body * pitch_env

    sig = body + pluck_band
    # ADSR: very fast attack, mostly decay
    env = adsr(n, a=0.003, d=2.5, s_level=0.0, r=2.0)
    out = sig[:env.size] * env[:sig.size] * 0.55
    return out

def voice_bowl(midi):
    """Clean singing bowl — two close-tuned fundamentals create the
    natural ~5 Hz beating that gives a real Tibetan bowl its meditative
    quality. NO harsh high inharmonic partials (the previous version had
    a 5.40x and 8.93x partial that sounded screechy at higher pitches).

    Just: two fundamentals beating + stretched octave for body + one warm
    pure 3x partial for presence. Slow swell attack, very long decay."""
    f = freq(midi)
    dur = 9.0
    n = int(dur * SR); t = t_axis(dur)

    # Two close fundamentals — 5 Hz beat regardless of pitch
    detune = 5.0 / f
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.35) +
        np.sin(2*np.pi*f*(1+detune)*t)   * np.exp(-t*0.35) * 0.90
    )
    # Stretched octave — natural body without harshness
    sig += 0.42 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*0.7)
    # Single warm pure-octave-plus-fifth partial (3.0x = pure consonance)
    sig += 0.15 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*1.6)

    # Slow swelling attack — the bowl warms up rather than barks
    env = adsr(n, a=0.10, d=5.5, s_level=0.0, r=3.0)
    out = sig[:env.size] * env[:sig.size] * 0.55
    return out

def voice_mokugyo(seed):
    """Small wooden fish-drum tap. Hollow body resonance from a filtered
    noise burst + low pitched ringing element. DRY — wants to feel right
    next to you in the room, not in a temple hall."""
    rng = np.random.default_rng(seed)
    dur = 0.4
    n = int(dur * SR); t = t_axis(dur)

    # Noise burst, woody mid-band
    noise = rng.standard_normal(n)
    band = lowpass_fft(noise, 1800, order=2) - lowpass_fft(noise, 500, order=2)
    band_env = np.exp(-t * 60)

    # Hollow body resonance (~140 Hz, a small wooden box)
    ring_freq = 140 + rng.uniform(-15, 15)
    ring = np.sin(2*np.pi*ring_freq*t) * np.exp(-t*22)
    ring2 = np.sin(2*np.pi*ring_freq*2.6*t) * np.exp(-t*40) * 0.4

    sig = 0.7 * band * band_env + 0.5 * ring + 0.2 * ring2
    env = adsr(n, a=0.001, d=0.08, s_level=0.0, r=0.05)
    out = sig[:env.size] * env[:sig.size] * 0.45
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
    print("[koto] rendering...")

    # koto — 11 pitches in In sen, light reverb (the koto already sustains).
    # Slight pan rotation — feel of multiple strings across the instrument.
    pan_pattern = (-0.4, -0.25, -0.1, 0.05, 0.2, 0.35, 0.2, 0.05, -0.1, -0.25, -0.4)
    for i, m in enumerate(INSEN_PITCHES):
        print(f"  koto m{m}")
        st = render_with_pan(voice_koto(m), wet=0.20, decay_s=2.0,
                             predelay_ms=25, brightness=0.50, pan=pan_pattern[i % 11])
        write_wav(OUT / "koto" / f"{i:02d}_m{m}.wav", st, target_peak=0.85)

    # bowl — 4 pitches, medium reverb. The bowl's natural beating is the
    # main effect; reverb adds room not character.
    for i, m in enumerate(BOWL_PITCHES):
        print(f"  bowl m{m}")
        pan = (-0.15, 0.0, 0.0, 0.15)[i]
        st = render_with_pan(voice_bowl(m), wet=0.40, decay_s=3.5,
                             predelay_ms=40, brightness=0.40, pan=pan)
        write_wav(OUT / "bowl" / f"{i:02d}_m{m}.wav", st, target_peak=0.80)

    # mokugyo — DRY. 3 variants of the wooden tap.
    for i in range(3):
        print(f"  mokugyo {i}")
        pan = (-0.20, 0.0, 0.20)[i]
        st = render_with_pan(voice_mokugyo(seed=400 + i), wet=0.0, decay_s=0.3,
                             predelay_ms=0, brightness=0.4, pan=pan)
        write_wav(OUT / "mokugyo" / f"{i:02d}.wav", st, target_peak=0.65)

    print("[koto] done.")

if __name__ == "__main__":
    gen_all()
