#!/usr/bin/env python3
"""
droplet — sample renderer.

A Lydian, sparse, with feedback delay on the drop voice for the
"stone in still water" ripple effect. No long sustained pads.
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


def delay_line(x, delay_ms=380, feedback=0.32, mix=0.30):
    """Soft feedback delay. Mix is the wet level (0=dry, 1=all wet).
    Tail extends the input by enough echoes to fall below -40dB."""
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


def voice_drop(midi):
    """Tiny single-pluck drop. With delay = ripples that fade."""
    f = freq(midi); dur = 1.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*4.0) +
        0.30 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*7.0)
    )
    env = adsr(n, a=0.005, d=0.7, s_level=0.0, r=0.3)
    dry = sig[:env.size] * env[:sig.size] * 0.50
    return delay_line(dry, delay_ms=420, feedback=0.30, mix=0.32)


def voice_ring(midi):
    """Light bell — softer and shorter than meadow's bell."""
    f = freq(midi); dur = 4.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.85) +
        0.32 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.4) +
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.5)
    )
    sig += 0.12 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.0)
    env = adsr(n, a=0.010, d=3.5, s_level=0.0, r=0.5)
    return sig[:env.size] * env[:sig.size] * 0.42


def voice_tap(seed):
    """Tiny dry tap — pitched-noise via tonal_anchor at trigger time."""
    rng = np.random.default_rng(seed)
    dur = 0.20; n = int(dur * SR); t = t_axis(dur)
    f = 1500
    body = np.sin(2*np.pi*f*t) * np.exp(-t*100)
    noise = rng.standard_normal(n) * np.exp(-t*220) * 0.35
    noise = lowpass_fft(noise, 5500, order=2) - lowpass_fft(noise, 700, order=2)
    sig = body * 0.5 + noise * 0.5
    env = adsr(n, a=0.001, d=0.06, s_level=0.0, r=0.10)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_glow_bell(midi):
    """Single high bell with delay echoes — heard once at session start."""
    f = freq(midi); dur = 4.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.7) +
        0.40 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.1) +
        0.12 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*2.5)
    )
    env = adsr(n, a=0.010, d=3.8, s_level=0.0, r=0.5)
    dry = sig[:env.size] * env[:sig.size] * 0.45
    return delay_line(dry, delay_ms=520, feedback=0.40, mix=0.35)


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("drop", "ring", "tap", "glow_bell"):
        (OUT / sub).mkdir(exist_ok=True)

    # drop — A Lydian high register
    drop_midis = [69, 71, 73, 75, 76, 78, 80, 81, 83, 85, 88]
    for i, m in enumerate(drop_midis):
        print(f"  drop m{m}")
        st = reverb_stereo(voice_drop(m), wet=0.20, decay_s=1.8,
                           predelay_ms=15, brightness=0.55)
        write_wav(OUT / "drop" / f"{i:02d}_m{m}.wav", st, target_peak=0.70)

    # ring — fewer pitches, more sparing
    ring_midis = [76, 78, 81, 83, 85]
    for i, m in enumerate(ring_midis):
        print(f"  ring m{m}")
        st = reverb_stereo(voice_ring(m), wet=0.25, decay_s=2.5,
                           predelay_ms=25, brightness=0.50)
        write_wav(OUT / "ring" / f"{i:02d}_m{m}.wav", st, target_peak=0.70)

    # tap — bag mode
    for i in range(3):
        print(f"  tap {i}")
        st = reverb_stereo(voice_tap(seed=30+i), wet=0.05, decay_s=0.8,
                           predelay_ms=8, brightness=0.45)
        write_wav(OUT / "tap" / f"{i:02d}.wav", st, target_peak=0.55)

    # glow_bell — pitched, used on SessionStart only (long MIOI)
    glow_midis = [81, 85, 88]
    for i, m in enumerate(glow_midis):
        print(f"  glow_bell m{m}")
        st = reverb_stereo(voice_glow_bell(m), wet=0.28, decay_s=3.0,
                           predelay_ms=30, brightness=0.55)
        write_wav(OUT / "glow_bell" / f"{i:02d}_m{m}.wav", st, target_peak=0.65)

    print("done.")


if __name__ == "__main__":
    gen_all()
