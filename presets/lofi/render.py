#!/usr/bin/env python3
"""
lofi preset — dusty chill hip-hop kit renderer.

A warm, hazy kit for the Jukebox: a soft round kick, a laid-back rimshot, a
gentle hat, a round upright-ish BASS, a Rhodes-y electric-piano KEYS voice for
chords/melody, and a mellow PAD. A=432, major-pentatonic warmth. Pitched voices
every 3 semitones.

Voices:
  kick  — soft low sine thump, minimal click (2 variants)
  rim   — short woody rimshot click + tone (2 variants)
  hat   — soft short noise tick, closed / loose
  bass  — round sine+saw upright bass, A1..A3
  keys  — Rhodes-ish FM-ish electric piano, A2..A4
  pad   — mellow lowpassed pad, A2..A4
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from synth import SR, freq, t_axis, adsr, soft_clip, lowpass_fft, reverb_stereo, to_stereo, write_wav

import json as _json
import synth as _synth
_RS = float(_json.loads(Path(__import__("os").environ.get("CLAUDIO_PRESET_CONFIG", str(HERE / "preset.json"))).read_text()).get("reverb_scale", 1.0))
_orig = _synth.reverb_stereo
def reverb_stereo(mono, **kw):
    if "wet" in kw: kw["wet"] = max(0.0, min(1.0, float(kw["wet"]) * _RS))
    return _orig(mono, **kw)

OUT = Path(__import__("os").environ.get("CLAUDIO_SAMPLES_DIR", str(HERE / "samples")))
for s in ("kick", "rim", "hat", "bass", "keys", "pad"):
    (OUT / s).mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(4242)

BASS_MIDIS = [33, 36, 39, 42, 45, 48, 51, 54, 57]
KEYS_MIDIS = [45, 48, 51, 54, 57, 60, 63, 66, 69]
PAD_MIDIS  = [45, 48, 51, 54, 57, 60, 63, 66]


def saw(f0, t, n=20):
    out = np.zeros_like(t); k = 1
    while k * f0 < SR / 2 and k <= n:
        out += np.sin(2 * np.pi * k * f0 * t) / k; k += 1
    return out


def r_kick(v):
    t = t_axis(0.34)
    f = 44 + 80 * np.exp(-t / (0.022 + 0.006 * v))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)
    body = lowpass_fft(body, 2000)                      # soft, no harsh click
    return to_stereo(soft_clip(body * 0.95, drive=1.15))


def r_rim(v):
    t = t_axis(0.16)
    tone = (np.sin(2 * np.pi * 320 * t) + 0.5 * np.sin(2 * np.pi * 540 * t)) * np.exp(-t / 0.03)
    noise = rng.standard_normal(t.size) * np.exp(-t / (0.012 + 0.006 * v))
    noise -= lowpass_fft(noise, 2500)
    return to_stereo(soft_clip(0.7 * tone + 0.5 * noise, drive=1.1))


def r_hat(v):
    dur = (0.05, 0.13)[v]
    t = t_axis(dur)
    n = rng.standard_normal(t.size) * np.exp(-t / (dur * 0.4))
    n -= lowpass_fft(n, 7000)
    return to_stereo(n * 0.55)                          # gentle, sits back


def r_bass(m):
    t = t_axis(0.65); f0 = freq(m)
    x = np.sin(2 * np.pi * f0 * t) + 0.3 * saw(f0, t) + 0.2 * np.sin(2 * np.pi * 2 * f0 * t)
    x = lowpass_fft(x, max(180.0, f0 * 3))
    x *= adsr(t.size, 0.01, 0.22, 0.5, 0.2)
    return to_stereo(soft_clip(x * 0.7, drive=1.15))


def r_keys(m):
    t = t_axis(1.4); f0 = freq(m)
    # simple FM-ish tine: carrier + decaying modulator → Rhodes bark
    mod = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.4) * 2.2
    x = np.sin(2 * np.pi * f0 * t + mod) + 0.3 * np.sin(2 * np.pi * 2 * f0 * t) * np.exp(-t / 0.6)
    x = lowpass_fft(x, min(5000.0, f0 * 9))
    x *= adsr(t.size, 0.005, 0.5, 0.35, 0.6)
    return reverb_stereo(x * 0.7, wet=0.3, decay_s=1.8, predelay_ms=15, brightness=0.4)


def r_pad(m):
    t = t_axis(2.4)
    chord = [freq(m), freq(m + 7), freq(m + 12)]
    x = sum(saw(f, t, 14) + 0.6 * np.sin(2 * np.pi * f * t) for f in chord) / len(chord)
    x = lowpass_fft(x, min(3800.0, freq(m) * 6))        # darker, hazy
    x *= adsr(t.size, 0.5, 0.7, 0.7, 0.9)
    return reverb_stereo(x / 2.2, wet=0.5, decay_s=3.0, predelay_ms=28, brightness=0.38)


def main(only=None):
    def want(v): return only is None or v in only
    if want("kick"):
        for i in range(2): write_wav(OUT / "kick" / f"{i:02d}.wav", r_kick(i))
    if want("rim"):
        for i in range(2): write_wav(OUT / "rim" / f"{i:02d}.wav", r_rim(i))
    if want("hat"):
        for i in range(2): write_wav(OUT / "hat" / f"{i:02d}.wav", r_hat(i))
    for vname, midis, fn in (("bass", BASS_MIDIS, r_bass), ("keys", KEYS_MIDIS, r_keys),
                             ("pad", PAD_MIDIS, r_pad)):
        if want(vname):
            for i, m in enumerate(midis): write_wav(OUT / vname / f"{i:02d}_m{m}.wav", fn(m))
    print("lofi: rendered", "all" if only is None else ",".join(only))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
