#!/usr/bin/env python3
"""
wisp — sample renderer.

Barely-there A Lydian. Pure sines with delay tails, tiny noise pops,
soft breath wash, rare bell.
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


def delay_line(x, delay_ms=440, feedback=0.35, mix=0.32):
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


def voice_sine(midi):
    """Pure sine + tiny harmonic for character. Long delay tail."""
    f = freq(midi); dur = 1.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.sin(2*np.pi*f*t) * np.exp(-t*2.5)
    sig += 0.12 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*4.0)
    env = adsr(n, a=0.008, d=1.0, s_level=0.0, r=0.4)
    dry = sig[:env.size] * env[:sig.size] * 0.42
    return delay_line(dry, delay_ms=460, feedback=0.32, mix=0.30)


def voice_pop(seed):
    """Smallest possible noise pop — barely there."""
    rng = np.random.default_rng(seed)
    dur = 0.10; n = int(dur * SR); t = t_axis(dur)
    noise = rng.standard_normal(n) * np.exp(-t*220) * 0.35
    noise = lowpass_fft(noise, 6000, order=2) - lowpass_fft(noise, 1500, order=2)
    env = adsr(n, a=0.001, d=0.04, s_level=0.0, r=0.05)
    return noise[:env.size] * env[:noise.size] * 0.45


def voice_breath(seed):
    """Soft filtered noise wash — quiet."""
    rng = np.random.default_rng(seed)
    dur = 0.8; n = int(dur * SR)
    noise = rng.standard_normal(n)
    bp = lowpass_fft(noise, 2500, order=2) - lowpass_fft(noise, 700, order=2)
    env = adsr(n, a=0.10, d=0.3, s_level=0.4, r=0.4)
    return bp * env * 0.25


def voice_rare_bell(midi):
    """Single soft bell — used on SessionStart / Stop only."""
    f = freq(midi); dur = 4.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.7) +
        0.30 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.1) +
        0.08 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*2.5)
    )
    env = adsr(n, a=0.012, d=3.5, s_level=0.0, r=0.5)
    dry = sig[:env.size] * env[:sig.size] * 0.40
    return delay_line(dry, delay_ms=560, feedback=0.40, mix=0.30)


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("sine", "pop", "breath", "rare_bell"):
        (OUT / sub).mkdir(exist_ok=True)

    sine_midis = [76, 78, 80, 81, 83, 85, 87, 88, 90]
    for i, m in enumerate(sine_midis):
        print(f"  sine m{m}")
        st = reverb_stereo(voice_sine(m), wet=0.15, decay_s=1.5,
                           predelay_ms=15, brightness=0.55)
        write_wav(OUT / "sine" / f"{i:02d}_m{m}.wav", st, target_peak=0.55)

    for i in range(3):
        print(f"  pop {i}")
        st = reverb_stereo(voice_pop(seed=110+i), wet=0.05, decay_s=0.5,
                           predelay_ms=5, brightness=0.50)
        write_wav(OUT / "pop" / f"{i:02d}.wav", st, target_peak=0.40)

    for i in range(3):
        print(f"  breath {i}")
        st = reverb_stereo(voice_breath(seed=120+i), wet=0.15, decay_s=1.5,
                           predelay_ms=15, brightness=0.45)
        write_wav(OUT / "breath" / f"{i:02d}.wav", st, target_peak=0.40)

    bell_midis = [81, 85, 88]
    for i, m in enumerate(bell_midis):
        print(f"  rare_bell m{m}")
        st = reverb_stereo(voice_rare_bell(m), wet=0.20, decay_s=2.5,
                           predelay_ms=25, brightness=0.55)
        write_wav(OUT / "rare_bell" / f"{i:02d}_m{m}.wav", st, target_peak=0.55)

    print("done.")


if __name__ == "__main__":
    gen_all()
