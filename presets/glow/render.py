#!/usr/bin/env python3
"""
glow — sample renderer.

A major pentatonic. Light reverb, clean attacks, no long pads.
Felt mallet for satisfaction, soft chime for resolution, wood tap for ticks,
short flourish (3 quick notes) instead of a dreary bloom.
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


def voice_mallet(midi):
    """Felt mallet on warm wood — satisfying thock, no harsh upper partials."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.5) +
        0.40 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.0) +
        0.12 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*5.0)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*1.6)
    sig = lowpass_fft(sig, 3500, order=3)
    env = adsr(n, a=0.012, d=1.0, s_level=0.0, r=1.4)
    return sig[:env.size] * env[:sig.size] * 0.55


def voice_chime(midi):
    """Soft glockenspiel-style chime — bright but polite."""
    f = freq(midi); dur = 3.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.0) +
        0.35 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.6) +
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.5)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.2)
    env = adsr(n, a=0.008, d=2.5, s_level=0.0, r=0.5)
    return sig[:env.size] * env[:sig.size] * 0.45


def voice_wood(seed):
    """Tiny dry wood-block tap. Pitched-noise overlay handled at trigger time."""
    rng = np.random.default_rng(seed)
    dur = 0.28; n = int(dur * SR); t = t_axis(dur)
    f = 1100
    body = np.sin(2*np.pi*f*t) * np.exp(-t*60)
    body += 0.30 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*100)
    noise = rng.standard_normal(n) * np.exp(-t*180) * 0.4
    noise = lowpass_fft(noise, 4500, order=2) - lowpass_fft(noise, 600, order=2)
    sig = body * 0.55 + noise * 0.45
    env = adsr(n, a=0.001, d=0.08, s_level=0.0, r=0.15)
    return sig[:env.size] * env[:sig.size] * 0.55


def voice_flourish(seed):
    """3-note ascending pentatonic, quick. Lasts ~1.5s. Replaces dreary bloom."""
    rng = np.random.default_rng(seed)
    pcs = [69, 73, 76, 78, 81]
    notes = sorted(rng.choice(pcs, size=3, replace=False))
    dur = 2.5; n = int(dur * SR)
    out = np.zeros(n + int(SR))
    for i, m in enumerate(notes):
        offset = int((0.05 + i*0.12) * SR)
        chime = voice_chime(int(m))
        end = min(offset + chime.size, out.size)
        out[offset:end] += chime[:end - offset] * 0.85
    return out


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("mallet", "chime", "wood", "flourish"):
        (OUT / sub).mkdir(exist_ok=True)

    # mallet — A pentatonic
    mallet_midis = [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81]
    for i, m in enumerate(mallet_midis):
        print(f"  mallet m{m}")
        st = reverb_stereo(voice_mallet(m), wet=0.18, decay_s=2.0,
                           predelay_ms=20, brightness=0.50)
        write_wav(OUT / "mallet" / f"{i:02d}_m{m}.wav", st, target_peak=0.78)

    # chime — A pentatonic upper octave
    chime_midis = [73, 76, 78, 81, 83, 85, 88, 90]
    for i, m in enumerate(chime_midis):
        print(f"  chime m{m}")
        st = reverb_stereo(voice_chime(m), wet=0.22, decay_s=2.5,
                           predelay_ms=30, brightness=0.55)
        write_wav(OUT / "chime" / f"{i:02d}_m{m}.wav", st, target_peak=0.72)

    # wood — bag mode, dry
    for i in range(3):
        print(f"  wood {i}")
        st = reverb_stereo(voice_wood(seed=10+i), wet=0.04, decay_s=0.7,
                           predelay_ms=8, brightness=0.45)
        write_wav(OUT / "wood" / f"{i:02d}.wav", st, target_peak=0.55)

    # flourish — 3 short variants
    for i in range(3):
        print(f"  flourish {i}")
        st = reverb_stereo(voice_flourish(seed=20+i), wet=0.30, decay_s=2.5,
                           predelay_ms=25, brightness=0.55)
        write_wav(OUT / "flourish" / f"{i:02d}.wav", st, target_peak=0.72)

    print("done.")


if __name__ == "__main__":
    gen_all()
