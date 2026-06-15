#!/usr/bin/env python3
"""
dnb preset — Drum & Bass kit renderer.

A full, song-ready breakbeat kit for the Jukebox: punchy kick, cracking snare,
tight hats, a pure sine SUB, a growling detuned REESE bass, a minor STAB, and an
airy PAD. Dark and fast — minor-leaning, A-rooted at 432 Hz. Pitched voices are
sampled every 3 semitones so playback shifts stay tiny.

Voices:
  kick   — short sine pitch-drop thump with a click (2 variants)
  snare  — tone body + bright noise crack (2 variants)
  hat    — high-passed noise tick, closed / mid / open
  sub    — pure sine sub bass (A0..A2 region)
  reese  — detuned stacked saws, lowpassed growl (A1..A3 region)
  stab   — short minor7 saw stab (mid)
  pad    — slow airy pad swell (mid-high)
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from synth import SR, freq, t_axis, adsr, soft_clip, lowpass_fft, reverb_stereo, to_stereo, write_wav

# reverb_scale monkeypatch (same contract as every preset)
import json as _json
import synth as _synth
_RS = float(_json.loads((HERE / "preset.json").read_text()).get("reverb_scale", 1.0))
_orig = _synth.reverb_stereo
def reverb_stereo(mono, **kw):
    if "wet" in kw: kw["wet"] = max(0.0, min(1.0, float(kw["wet"]) * _RS))
    return _orig(mono, **kw)

OUT = HERE / "samples"
for s in ("kick", "snare", "hat", "sub", "reese", "stab", "pad"):
    (OUT / s).mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(1773)

SUB_MIDIS   = [21, 24, 27, 30, 33, 36, 39, 42, 45]   # A0..A2-ish
REESE_MIDIS = [33, 36, 39, 42, 45, 48, 51, 54]       # A1..F#3
STAB_MIDIS  = [45, 48, 51, 54, 57, 60, 63, 66, 69]   # A2..A4
PAD_MIDIS   = [57, 60, 63, 66, 69, 72, 75, 78]       # A3..F#5


def saw(f0, t, n=28):
    out = np.zeros_like(t); k = 1
    while k * f0 < SR / 2 and k <= n:
        out += np.sin(2 * np.pi * k * f0 * t) / k; k += 1
    return out


def r_kick(v):
    t = t_axis(0.36)
    f = 48 + 120 * np.exp(-t / (0.018 + 0.004 * v))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11)
    click = rng.standard_normal(int(0.0025 * SR)) * 0.6
    body[:click.size] += click * np.linspace(1, 0, click.size)
    return to_stereo(soft_clip(body, drive=1.5))


def r_snare(v):
    t = t_axis(0.26)
    body = (np.sin(2 * np.pi * 210 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * np.exp(-t / 0.05)
    noise = rng.standard_normal(t.size) * np.exp(-t / (0.07 + 0.02 * v))
    noise -= lowpass_fft(noise, 2200)
    return to_stereo(soft_clip(0.5 * body + 1.0 * noise, drive=1.3))


def r_hat(v):
    dur = (0.04, 0.09, 0.3)[v]
    t = t_axis(dur)
    n = rng.standard_normal(t.size) * np.exp(-t / (dur * 0.4))
    n -= lowpass_fft(n, 7500)
    return to_stereo(n * 0.9)


def r_sub(m):
    t = t_axis(0.7); f0 = freq(m)
    x = np.sin(2 * np.pi * f0 * t) + 0.15 * np.sin(2 * np.pi * 2 * f0 * t)
    x *= adsr(t.size, 0.008, 0.2, 0.7, 0.18)
    return to_stereo(soft_clip(x * 0.9, drive=1.2))


def r_reese(m):
    t = t_axis(0.8); f0 = freq(m)
    x = saw(f0 * 0.992, t) + saw(f0 * 1.008, t) + saw(f0 * 1.0, t)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 5.5 * t)
    x = lowpass_fft(x, max(220.0, f0 * (3 + 3 * lfo).mean()))
    x *= adsr(t.size, 0.01, 0.25, 0.6, 0.2)
    return to_stereo(soft_clip(x / 3 * 1.4, drive=1.3))


def r_stab(m):
    t = t_axis(0.5)
    chord = [freq(m), freq(m + 3), freq(m + 7), freq(m + 10)]   # minor7
    x = sum(saw(f, t, 20) for f in chord) / len(chord)
    x = lowpass_fft(x, min(6000.0, freq(m) * 8))
    x *= adsr(t.size, 0.004, 0.12, 0.25, 0.3)
    return reverb_stereo(x, wet=0.25, decay_s=1.6, predelay_ms=12, brightness=0.5)


def r_pad(m):
    t = t_axis(2.4)
    chord = [freq(m), freq(m + 7), freq(m + 12)]
    x = sum(saw(f, t, 16) + 0.5 * np.sin(2 * np.pi * f * t) for f in chord) / len(chord)
    x = lowpass_fft(x, min(5000.0, freq(m) * 7))
    x *= adsr(t.size, 0.5, 0.6, 0.7, 0.9)
    return reverb_stereo(x / 2.2, wet=0.5, decay_s=3.2, predelay_ms=30, brightness=0.45)


def main(only=None):
    def want(v): return only is None or v in only
    if want("kick"):
        for i in range(2): write_wav(OUT / "kick" / f"{i:02d}.wav", r_kick(i))
    if want("snare"):
        for i in range(2): write_wav(OUT / "snare" / f"{i:02d}.wav", r_snare(i))
    if want("hat"):
        for i in range(3): write_wav(OUT / "hat" / f"{i:02d}.wav", r_hat(i))
    for vname, midis, fn in (("sub", SUB_MIDIS, r_sub), ("reese", REESE_MIDIS, r_reese),
                             ("stab", STAB_MIDIS, r_stab), ("pad", PAD_MIDIS, r_pad)):
        if want(vname):
            for i, m in enumerate(midis): write_wav(OUT / vname / f"{i:02d}_m{m}.wav", fn(m))
    print("dnb: rendered", "all" if only is None else ",".join(only))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
