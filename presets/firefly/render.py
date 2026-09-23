#!/usr/bin/env python3
"""
firefly — sample renderer.

A Lydian, very high. Tiny upper-register sparkles with soft delay echoes,
gentle high-glow chime, micro click, 3-note ascending lift.
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


def delay_line(x, delay_ms=280, feedback=0.30, mix=0.28):
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


def voice_spark(midi):
    """Tiny upper-register pluck with delay echoes."""
    f = freq(midi); dur = 0.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*4.0) +
        0.32 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*7.0)
    )
    env = adsr(n, a=0.005, d=0.4, s_level=0.0, r=0.3)
    dry = sig[:env.size] * env[:sig.size] * 0.42
    return delay_line(dry, delay_ms=260, feedback=0.28, mix=0.25)


def voice_glow_chime(midi):
    """Soft high chime — used as the resolution voice."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.9) +
        0.30 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.4) +
        0.08 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*3.0)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.0)
    env = adsr(n, a=0.010, d=2.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.40


def voice_click(seed):
    """Pure tiny click."""
    rng = np.random.default_rng(seed)
    dur = 0.07; n = int(dur * SR); t = t_axis(dur)
    noise = rng.standard_normal(n) * np.exp(-t*350) * 0.4
    noise = lowpass_fft(noise, 8000, order=2) - lowpass_fft(noise, 2200, order=2)
    env = adsr(n, a=0.001, d=0.02, s_level=0.0, r=0.04)
    return noise[:env.size] * env[:noise.size] * 0.50


def voice_lift(seed):
    """4-note rapid ascending sparkle — like a firefly catching light."""
    rng = np.random.default_rng(seed)
    pcs = [83, 85, 87, 88, 90, 92, 93]
    notes = sorted(rng.choice(pcs, size=4, replace=False))
    n = int(2.5 * SR)
    out = np.zeros(n + int(SR))
    for i, m in enumerate(notes):
        offset = int((0.04 + i*0.10) * SR)
        sp = voice_spark(int(m))
        end = min(offset + sp.size, out.size)
        out[offset:end] += sp[:end - offset] * 0.85
    return out


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("spark", "glow_chime", "click", "lift"):
        (OUT / sub).mkdir(exist_ok=True)

    spark_midis = [83, 85, 87, 88, 90, 92, 93, 95, 97]
    for i, m in enumerate(spark_midis):
        print(f"  spark m{m}")
        st = reverb_stereo(voice_spark(m), wet=0.18, decay_s=1.5,
                           predelay_ms=15, brightness=0.60)
        write_wav(OUT / "spark" / f"{i:02d}_m{m}.wav", st, target_peak=0.60)

    chime_midis = [85, 88, 90, 93]
    for i, m in enumerate(chime_midis):
        print(f"  glow_chime m{m}")
        st = reverb_stereo(voice_glow_chime(m), wet=0.20, decay_s=2.0,
                           predelay_ms=18, brightness=0.55)
        write_wav(OUT / "glow_chime" / f"{i:02d}_m{m}.wav", st, target_peak=0.62)

    for i in range(3):
        print(f"  click {i}")
        st = reverb_stereo(voice_click(seed=150+i), wet=0.04, decay_s=0.4,
                           predelay_ms=4, brightness=0.55)
        write_wav(OUT / "click" / f"{i:02d}.wav", st, target_peak=0.42)

    for i in range(3):
        print(f"  lift {i}")
        st = reverb_stereo(voice_lift(seed=160+i), wet=0.20, decay_s=1.8,
                           predelay_ms=18, brightness=0.55)
        write_wav(OUT / "lift" / f"{i:02d}.wav", st, target_peak=0.65)

    print("done.")


if __name__ == "__main__":
    gen_all()
