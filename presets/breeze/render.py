#!/usr/bin/env python3
"""
breeze — sample renderer.

Airy and bright. A Lydian. Crystal chimes, soft pluck, gentle wind breath.
Tiny delays for air movement. Cheerful and clean.
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (SR, A4, freq, t_axis, adsr, soft_clip, lowpass_fft,
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


def delay_line(x, delay_ms=240, feedback=0.20, mix=0.18):
    delay_n = int(delay_ms * SR / 1000)
    n_echoes = max(1, int(np.log(0.01) / np.log(max(feedback, 0.01))))
    total = len(x) + delay_n * (n_echoes + 1)
    wet = np.zeros(total)
    for i in range(1, n_echoes + 1):
        offset = delay_n * i
        gain = feedback ** i
        end = min(offset + len(x), total)
        wet[offset:end] += x[:end - offset] * gain
    dry = np.zeros(total); dry[:len(x)] = x
    return dry * (1 - mix) + wet * mix


def voice_crystal(midi):
    """Crystal glass / wineglass timbre — pure sine + 2nd partial."""
    f = freq(midi); dur = 3.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.7) +
        0.30 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.2) +
        0.05 * np.sin(2*np.pi*f*4.5*t)   * np.exp(-t*4.0)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.002*t) * np.exp(-t*0.9)
    env = adsr(n, a=0.012, d=3.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.40


def voice_soft_pluck(midi):
    """Felt-pluck like meadow's mallet but lighter."""
    f = freq(midi); dur = 2.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.6) +
        0.35 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.0) +
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*5.0)
    )
    sig += 0.08 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*1.8)
    sig = lowpass_fft(sig, 4000, order=3)
    env = adsr(n, a=0.010, d=1.0, s_level=0.0, r=0.8)
    dry = sig[:env.size] * env[:sig.size] * 0.50
    return delay_line(dry, delay_ms=240, feedback=0.18, mix=0.15)


def voice_wind(seed):
    """Soft filtered noise — gentle air. Pre-tool atmosphere."""
    rng = np.random.default_rng(seed)
    dur = 0.9; n = int(dur * SR); t = t_axis(dur)
    noise = rng.standard_normal(n)
    bp = lowpass_fft(noise, 3500, order=2) - lowpass_fft(noise, 800, order=2)
    env = adsr(n, a=0.10, d=0.3, s_level=0.4, r=0.4)
    return bp * env * 0.30


def voice_high_chime(midi):
    """Sparkly high chime — used for SessionStart / bigger moments."""
    f = freq(midi); dur = 4.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.7) +
        0.40 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.1) +
        0.15 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*2.5) +
        0.05 * np.sin(2*np.pi*f*5.5*t)   * np.exp(-t*5.0)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*0.9)
    env = adsr(n, a=0.010, d=3.5, s_level=0.0, r=0.4)
    dry = sig[:env.size] * env[:sig.size] * 0.45
    return delay_line(dry, delay_ms=380, feedback=0.30, mix=0.28)


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("crystal", "soft_pluck", "wind", "high_chime"):
        (OUT / sub).mkdir(exist_ok=True)

    # crystal — A Lydian high register
    crystal_midis = [76, 78, 80, 81, 83, 85, 87, 88]
    for i, m in enumerate(crystal_midis):
        print(f"  crystal m{m}")
        st = reverb_stereo(voice_crystal(m), wet=0.22, decay_s=2.5,
                           predelay_ms=22, brightness=0.60)
        write_wav(OUT / "crystal" / f"{i:02d}_m{m}.wav", st, target_peak=0.65)

    # soft_pluck — A Lydian mid range
    pluck_midis = [69, 71, 73, 75, 76, 78, 80, 81, 83, 85]
    for i, m in enumerate(pluck_midis):
        print(f"  soft_pluck m{m}")
        st = reverb_stereo(voice_soft_pluck(m), wet=0.20, decay_s=2.0,
                           predelay_ms=18, brightness=0.55)
        write_wav(OUT / "soft_pluck" / f"{i:02d}_m{m}.wav", st, target_peak=0.72)

    # wind — bag mode, mostly dry
    for i in range(3):
        print(f"  wind {i}")
        st = reverb_stereo(voice_wind(seed=70+i), wet=0.15, decay_s=1.4,
                           predelay_ms=12, brightness=0.50)
        write_wav(OUT / "wind" / f"{i:02d}.wav", st, target_peak=0.50)

    # high_chime — pitched, used sparingly
    chime_midis = [81, 85, 88]
    for i, m in enumerate(chime_midis):
        print(f"  high_chime m{m}")
        st = reverb_stereo(voice_high_chime(m), wet=0.25, decay_s=2.8,
                           predelay_ms=28, brightness=0.55)
        write_wav(OUT / "high_chime" / f"{i:02d}_m{m}.wav", st, target_peak=0.65)

    print("done.")


if __name__ == "__main__":
    gen_all()
