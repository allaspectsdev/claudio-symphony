#!/usr/bin/env python3
"""
felt — sample renderer.

A major pentatonic. Felt-piano single notes with mild tape muffle.
Soft, simple, never busy.
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


def voice_felt_note(midi):
    """Felt piano: warm fundamental + soft 2nd partial, low-passed for muffle."""
    f = freq(midi); dur = 3.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*1.4) +
        0.45 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.5) +
        0.15 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*4.5) +
        0.04 * np.sin(2*np.pi*f*4.0*t)   * np.exp(-t*7.0)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*1.6)
    sig = lowpass_fft(sig, 2400, order=3)   # tape-muffle
    sig = soft_clip(sig, 1.05)
    env = adsr(n, a=0.012, d=1.5, s_level=0.0, r=1.2)
    return sig[:env.size] * env[:sig.size] * 0.52


def voice_low_note(midi):
    """Low felt note — used on SessionEnd / PreCompact for grounding."""
    f = freq(midi); dur = 4.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.9) +
        0.50 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*1.5) +
        0.15 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.8)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.0)
    sig = lowpass_fft(sig, 1800, order=3)
    sig = soft_clip(sig, 1.05)
    env = adsr(n, a=0.020, d=2.5, s_level=0.0, r=1.8)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_soft_tap(seed):
    """Almost-inaudible felt tap. Pitched-noise overlay at trigger."""
    rng = np.random.default_rng(seed)
    dur = 0.22; n = int(dur * SR); t = t_axis(dur)
    f = 800
    body = np.sin(2*np.pi*f*t) * np.exp(-t*55)
    noise = rng.standard_normal(n) * np.exp(-t*170) * 0.3
    noise = lowpass_fft(noise, 3500, order=2) - lowpass_fft(noise, 400, order=2)
    sig = body * 0.5 + noise * 0.5
    env = adsr(n, a=0.002, d=0.08, s_level=0.0, r=0.12)
    return sig[:env.size] * env[:sig.size] * 0.45


def voice_warm_bell(midi):
    """Polite warm bell — no harsh upper partials."""
    f = freq(midi); dur = 3.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.8) +
        0.38 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.3) +
        0.12 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.5)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.0)
    env = adsr(n, a=0.010, d=2.8, s_level=0.0, r=0.5)
    return sig[:env.size] * env[:sig.size] * 0.45


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("felt_note", "low_note", "soft_tap", "warm_bell"):
        (OUT / sub).mkdir(exist_ok=True)

    note_midis = [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81]
    for i, m in enumerate(note_midis):
        print(f"  felt_note m{m}")
        st = reverb_stereo(voice_felt_note(m), wet=0.18, decay_s=2.0,
                           predelay_ms=18, brightness=0.45)
        write_wav(OUT / "felt_note" / f"{i:02d}_m{m}.wav", st, target_peak=0.78)

    low_midis = [45, 49, 52, 57, 61, 64]
    for i, m in enumerate(low_midis):
        print(f"  low_note m{m}")
        st = reverb_stereo(voice_low_note(m), wet=0.20, decay_s=2.5,
                           predelay_ms=25, brightness=0.40)
        write_wav(OUT / "low_note" / f"{i:02d}_m{m}.wav", st, target_peak=0.75)

    for i in range(3):
        print(f"  soft_tap {i}")
        st = reverb_stereo(voice_soft_tap(seed=100+i), wet=0.06, decay_s=0.8,
                           predelay_ms=8, brightness=0.40)
        write_wav(OUT / "soft_tap" / f"{i:02d}.wav", st, target_peak=0.45)

    bell_midis = [73, 76, 81, 85]
    for i, m in enumerate(bell_midis):
        print(f"  warm_bell m{m}")
        st = reverb_stereo(voice_warm_bell(m), wet=0.22, decay_s=2.2,
                           predelay_ms=22, brightness=0.50)
        write_wav(OUT / "warm_bell" / f"{i:02d}_m{m}.wav", st, target_peak=0.68)

    print("done.")


if __name__ == "__main__":
    gen_all()
