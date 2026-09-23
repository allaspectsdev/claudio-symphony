#!/usr/bin/env python3
"""
toybox — sample renderer.

Playful and bright. A major pentatonic. Toy piano with delay (music-box
winding feel), glockenspiel, soft wood block, hand-bell.
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


def delay_line(x, delay_ms=320, feedback=0.28, mix=0.25):
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


def voice_toy_piano(midi):
    """Toy piano — bright pluck with quick decay, clean attack."""
    f = freq(midi); dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*2.0) +
        0.50 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*3.5) +
        0.22 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*5.5) +
        0.08 * np.sin(2*np.pi*f*4.5*t)   * np.exp(-t*9.0)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*2.2)
    env = adsr(n, a=0.005, d=1.3, s_level=0.0, r=0.4)
    dry = sig[:env.size] * env[:sig.size] * 0.50
    return delay_line(dry, delay_ms=320, feedback=0.25, mix=0.22)


def voice_glock(midi):
    """Glockenspiel — bright bell, polite."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.0) +
        0.42 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.5) +
        0.15 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.5)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.2)
    env = adsr(n, a=0.006, d=2.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.45


def voice_block(seed):
    """Wood-block tap — bright resonant body."""
    rng = np.random.default_rng(seed)
    dur = 0.32; n = int(dur * SR); t = t_axis(dur)
    f = 1400
    body = np.sin(2*np.pi*f*t) * np.exp(-t*55)
    body += 0.40 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*90)
    noise = rng.standard_normal(n) * np.exp(-t*180) * 0.4
    noise = lowpass_fft(noise, 5000, order=2) - lowpass_fft(noise, 700, order=2)
    sig = body * 0.55 + noise * 0.45
    env = adsr(n, a=0.001, d=0.10, s_level=0.0, r=0.16)
    return sig[:env.size] * env[:sig.size] * 0.55


def voice_hand_bell(midi):
    """Hand-bell — clear, polite, no sustained tail."""
    f = freq(midi); dur = 3.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.8) +
        0.40 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.2) +
        0.18 * np.sin(2*np.pi*f*2.76*t)  * np.exp(-t*2.0) +
        0.06 * np.sin(2*np.pi*f*4.5*t)   * np.exp(-t*4.0)
    )
    sig += 0.12 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.0)
    env = adsr(n, a=0.010, d=3.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.48


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("toy_piano", "glock", "block", "hand_bell"):
        (OUT / sub).mkdir(exist_ok=True)

    # toy_piano — A pentatonic
    tp_midis = [69, 71, 73, 76, 78, 81, 83, 85, 88, 90]
    for i, m in enumerate(tp_midis):
        print(f"  toy_piano m{m}")
        st = reverb_stereo(voice_toy_piano(m), wet=0.20, decay_s=1.8,
                           predelay_ms=18, brightness=0.55)
        write_wav(OUT / "toy_piano" / f"{i:02d}_m{m}.wav", st, target_peak=0.72)

    # glock — A pentatonic upper octave
    glock_midis = [76, 78, 81, 83, 85, 88, 90]
    for i, m in enumerate(glock_midis):
        print(f"  glock m{m}")
        st = reverb_stereo(voice_glock(m), wet=0.22, decay_s=2.0,
                           predelay_ms=20, brightness=0.55)
        write_wav(OUT / "glock" / f"{i:02d}_m{m}.wav", st, target_peak=0.68)

    # block — bag mode, dry
    for i in range(3):
        print(f"  block {i}")
        st = reverb_stereo(voice_block(seed=60+i), wet=0.05, decay_s=0.7,
                           predelay_ms=8, brightness=0.50)
        write_wav(OUT / "block" / f"{i:02d}.wav", st, target_peak=0.55)

    # hand_bell — pitched, fewer pitches, used sparingly
    bell_midis = [76, 81, 85, 88]
    for i, m in enumerate(bell_midis):
        print(f"  hand_bell m{m}")
        st = reverb_stereo(voice_hand_bell(m), wet=0.25, decay_s=2.5,
                           predelay_ms=25, brightness=0.50)
        write_wav(OUT / "hand_bell" / f"{i:02d}_m{m}.wav", st, target_peak=0.68)

    print("done.")


if __name__ == "__main__":
    gen_all()
