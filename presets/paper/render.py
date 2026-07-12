#!/usr/bin/env python3
"""
paper — sample renderer.

Micro-tactile minimal. A major pentatonic. Tiny taps, music-box notes,
soft clicks, single chime. Almost no reverb, very dry.
The quietest preset by design.
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


def voice_music_box(midi):
    """Toy piano / music-box note. Bright fundamental, very short tail."""
    f = freq(midi); dur = 1.6
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*2.5) +
        0.40 * np.sin(2*np.pi*f*2.001*t) * np.exp(-t*4.0) +
        0.18 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*6.0) +
        0.06 * np.sin(2*np.pi*f*4.5*t)   * np.exp(-t*10.0)
    )
    sig += 0.08 * np.sin(2*np.pi*f*1.005*t) * np.exp(-t*3.0)
    env = adsr(n, a=0.005, d=1.2, s_level=0.0, r=0.3)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_tap(seed):
    """Tiny finger-on-paper tap. Pitched noise via tonal_anchor at trigger."""
    rng = np.random.default_rng(seed)
    dur = 0.18; n = int(dur * SR); t = t_axis(dur)
    f = 1800
    body = np.sin(2*np.pi*f*t) * np.exp(-t*120)
    noise = rng.standard_normal(n) * np.exp(-t*250) * 0.4
    noise = lowpass_fft(noise, 6000, order=2) - lowpass_fft(noise, 1000, order=2)
    sig = body * 0.5 + noise * 0.5
    env = adsr(n, a=0.001, d=0.05, s_level=0.0, r=0.08)
    return sig[:env.size] * env[:sig.size] * 0.50


def voice_click(seed):
    """Pure click — even smaller than tap."""
    rng = np.random.default_rng(seed)
    dur = 0.08; n = int(dur * SR); t = t_axis(dur)
    noise = rng.standard_normal(n) * np.exp(-t*400) * 0.4
    noise = lowpass_fft(noise, 8000, order=2) - lowpass_fft(noise, 2000, order=2)
    env = adsr(n, a=0.0005, d=0.03, s_level=0.0, r=0.04)
    return noise[:env.size] * env[:noise.size] * 0.55


def voice_single_chime(midi):
    """One clean chime, dry, bright."""
    f = freq(midi); dur = 2.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.9) +
        0.35 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*1.5) +
        0.12 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*2.5)
    )
    sig += 0.10 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*1.1)
    env = adsr(n, a=0.008, d=2.0, s_level=0.0, r=0.4)
    return sig[:env.size] * env[:sig.size] * 0.42


def gen_all():
    OUT.mkdir(exist_ok=True)
    for sub in ("music_box", "tap", "click", "single_chime"):
        (OUT / sub).mkdir(exist_ok=True)

    # music_box — A pentatonic upper register
    box_midis = [69, 71, 73, 76, 78, 81, 83, 85, 88, 90, 93]
    for i, m in enumerate(box_midis):
        print(f"  music_box m{m}")
        st = reverb_stereo(voice_music_box(m), wet=0.12, decay_s=1.4,
                           predelay_ms=12, brightness=0.55)
        write_wav(OUT / "music_box" / f"{i:02d}_m{m}.wav", st, target_peak=0.72)

    # tap — bag mode
    for i in range(3):
        print(f"  tap {i}")
        st = reverb_stereo(voice_tap(seed=40+i), wet=0.04, decay_s=0.5,
                           predelay_ms=5, brightness=0.50)
        write_wav(OUT / "tap" / f"{i:02d}.wav", st, target_peak=0.50)

    # click — bag mode
    for i in range(3):
        print(f"  click {i}")
        st = reverb_stereo(voice_click(seed=50+i), wet=0.02, decay_s=0.3,
                           predelay_ms=2, brightness=0.50)
        write_wav(OUT / "click" / f"{i:02d}.wav", st, target_peak=0.40)

    # single_chime — pitched, fewer than music_box
    chime_midis = [76, 81, 85, 88]
    for i, m in enumerate(chime_midis):
        print(f"  single_chime m{m}")
        st = reverb_stereo(voice_single_chime(m), wet=0.18, decay_s=1.8,
                           predelay_ms=18, brightness=0.50)
        write_wav(OUT / "single_chime" / f"{i:02d}_m{m}.wav", st, target_peak=0.62)

    print("done.")


if __name__ == "__main__":
    gen_all()
