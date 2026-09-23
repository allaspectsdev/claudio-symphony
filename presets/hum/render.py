#!/usr/bin/env python3
"""
hum — sample renderer.

A major pentatonic. Hand-bell ensemble warmth. Polite, calming.
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


def voice_hand_bell(midi):
    """Warm hand-bell — clear, polite, modest decay."""
    f = freq(midi); dur = 3.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.85) +
        0.42 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.4) +
        0.16 * np.sin(2*np.pi*f*2.76*t)  * np.exp(-t*2.4) +
        0.05 * np.sin(2*np.pi*f*4.5*t)   * np.exp(-t*4.5)
    )
    sig += 0.12 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.0)
    env = adsr(n, a=0.012, d=3.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.46


def voice_soft_pluck(midi):
    """Light mallet — very gentle satisfaction."""
    f = freq(midi); dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.6) +
        0.35 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.0) +
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*5.0)
    )
    sig += 0.08 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*1.8)
    sig = lowpass_fft(sig, 3800, order=3)
    env = adsr(n, a=0.010, d=1.0, s_level=0.0, r=0.6)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_brush(seed):
    """Soft noise brush — pre-tool tick, near-silent."""
    rng = np.random.default_rng(seed)
    dur = 0.18; n = int(dur * SR)
    noise = rng.standard_normal(n)
    bp = lowpass_fft(noise, 4500, order=2) - lowpass_fft(noise, 1200, order=2)
    env = adsr(n, a=0.001, d=0.07, s_level=0.0, r=0.10)
    return bp[:env.size] * env[:bp.size] * 0.40


def voice_bell_pair(seed):
    """Two-bell flourish — interval of a 3rd or 5th."""
    rng = np.random.default_rng(seed)
    pcs = [76, 78, 81, 83, 85]
    a = int(rng.choice(pcs))
    b = a + int(rng.choice([3, 4, 7]))
    n = int(3.5 * SR)
    out = np.zeros(n + int(SR))
    for i, m in enumerate([a, b]):
        offset = int((0.05 + i*0.18) * SR)
        bell = voice_hand_bell(int(m))
        end = min(offset + bell.size, out.size)
        out[offset:end] += bell[:end - offset] * 0.85
    return out


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("hand_bell", "soft_pluck", "brush", "bell_pair"):
        (OUT / sub).mkdir(exist_ok=True)

    bell_midis = [69, 71, 73, 76, 78, 81, 83, 85, 88]
    for i, m in enumerate(bell_midis):
        print(f"  hand_bell m{m}")
        st = reverb_stereo(voice_hand_bell(m), wet=0.25, decay_s=2.5,
                           predelay_ms=22, brightness=0.50)
        write_wav(OUT / "hand_bell" / f"{i:02d}_m{m}.wav", st, target_peak=0.70)

    pluck_midis = [69, 71, 73, 76, 78, 81, 83, 85]
    for i, m in enumerate(pluck_midis):
        print(f"  soft_pluck m{m}")
        st = reverb_stereo(voice_soft_pluck(m), wet=0.20, decay_s=1.8,
                           predelay_ms=18, brightness=0.50)
        write_wav(OUT / "soft_pluck" / f"{i:02d}_m{m}.wav", st, target_peak=0.72)

    for i in range(3):
        print(f"  brush {i}")
        st = reverb_stereo(voice_brush(seed=130+i), wet=0.05, decay_s=0.6,
                           predelay_ms=6, brightness=0.45)
        write_wav(OUT / "brush" / f"{i:02d}.wav", st, target_peak=0.45)

    for i in range(3):
        print(f"  bell_pair {i}")
        st = reverb_stereo(voice_bell_pair(seed=140+i), wet=0.25, decay_s=2.5,
                           predelay_ms=25, brightness=0.50)
        write_wav(OUT / "bell_pair" / f"{i:02d}.wav", st, target_peak=0.70)

    print("done.")


if __name__ == "__main__":
    gen_all()
