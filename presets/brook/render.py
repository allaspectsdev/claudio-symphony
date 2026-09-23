#!/usr/bin/env python3
"""
brook — sample renderer.

A major pentatonic. Pitched bubbles (short pluck w/ slight rate sweep), wood
pops, soft chimes, tiny 3-note ascending swell.
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (SR, freq, t_axis, adsr, lowpass_fft,
                    reverb_stereo, write_wav)

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


def voice_bubble(midi):
    """Pitched bubble — short tone with subtle attack pitch glide upward."""
    f = freq(midi); dur = 0.9
    n = int(dur * SR); t = t_axis(dur)
    # gentle upward chirp at attack — gives the watery 'pop into pitch' quality
    pitch_env = 1.0 - 0.06 * np.exp(-t * 35)
    sig = (
        np.sin(2*np.pi*f*t * pitch_env)              * np.exp(-t*3.5) +
        0.30 * np.sin(2*np.pi*f*2.0*t * pitch_env)   * np.exp(-t*6.0)
    )
    sig += 0.08 * np.sin(2*np.pi*f*1.005*t)
    env = adsr(n, a=0.005, d=0.5, s_level=0.0, r=0.3)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_pop(seed):
    """Tiny dry wood pop — pitched-noise overlay handled at trigger."""
    rng = np.random.default_rng(seed)
    dur = 0.20; n = int(dur * SR); t = t_axis(dur)
    f = 1300
    body = np.sin(2*np.pi*f*t) * np.exp(-t*80)
    noise = rng.standard_normal(n) * np.exp(-t*200) * 0.4
    noise = lowpass_fft(noise, 5000, order=2) - lowpass_fft(noise, 700, order=2)
    sig = body * 0.5 + noise * 0.5
    env = adsr(n, a=0.001, d=0.06, s_level=0.0, r=0.10)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_soft_chime(midi):
    """Light bell — polite, no harshness."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.0) +
        0.32 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.5) +
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.5)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.2)
    env = adsr(n, a=0.008, d=2.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.42


def voice_small_swell(seed):
    """3-note ascending pentatonic flourish — lasts ~1.8s. Replaces dreary blooms."""
    rng = np.random.default_rng(seed)
    pcs = [73, 76, 78, 81, 83, 85]
    notes = sorted(rng.choice(pcs, size=3, replace=False))
    n = int(2.5 * SR)
    out = np.zeros(n + int(SR))
    for i, m in enumerate(notes):
        offset = int((0.05 + i*0.13) * SR)
        chime = voice_soft_chime(int(m))
        end = min(offset + chime.size, out.size)
        out[offset:end] += chime[:end - offset] * 0.85
    return out


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("bubble", "pop", "soft_chime", "small_swell"):
        (OUT / sub).mkdir(exist_ok=True)

    bub_midis = [69, 71, 73, 76, 78, 81, 83, 85, 88]
    for i, m in enumerate(bub_midis):
        print(f"  bubble m{m}")
        st = reverb_stereo(voice_bubble(m), wet=0.20, decay_s=1.5,
                           predelay_ms=15, brightness=0.55)
        write_wav(OUT / "bubble" / f"{i:02d}_m{m}.wav", st, target_peak=0.72)

    for i in range(3):
        print(f"  pop {i}")
        st = reverb_stereo(voice_pop(seed=80+i), wet=0.05, decay_s=0.6,
                           predelay_ms=6, brightness=0.50)
        write_wav(OUT / "pop" / f"{i:02d}.wav", st, target_peak=0.50)

    chime_midis = [76, 81, 85, 88]
    for i, m in enumerate(chime_midis):
        print(f"  soft_chime m{m}")
        st = reverb_stereo(voice_soft_chime(m), wet=0.20, decay_s=1.8,
                           predelay_ms=18, brightness=0.50)
        write_wav(OUT / "soft_chime" / f"{i:02d}_m{m}.wav", st, target_peak=0.65)

    for i in range(3):
        print(f"  small_swell {i}")
        st = reverb_stereo(voice_small_swell(seed=90+i), wet=0.25, decay_s=2.2,
                           predelay_ms=22, brightness=0.55)
        write_wav(OUT / "small_swell" / f"{i:02d}.wav", st, target_peak=0.70)

    print("done.")


if __name__ == "__main__":
    gen_all()
