#!/usr/bin/env python3
"""
synthwave preset — neon 80s kit renderer.

A complete retro-future kit for the Jukebox: a punchy kick, a big gated-reverb
snare, crisp hats, a fat analog saw BASS, a bright detuned LEAD, a plucky ARP,
and a warm POLY pad. A=432, minor-leaning. Pitched voices every 3 semitones.

Voices:
  kick  — tight sine-drop with click (2 variants)
  snare — body + noise into a gated reverb burst (2 variants)
  hat   — crisp high-passed tick, closed / open
  bass  — analog saw, lowpassed, A1..F#3
  lead  — two detuned saws + square, bright, A3..A5
  arp   — short saw pluck for arpeggios, A3..A5
  pad   — warm stacked-saw poly pad, A2..A4
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
_RS = float(_json.loads((HERE / "preset.json").read_text()).get("reverb_scale", 1.0))
_orig = _synth.reverb_stereo
def reverb_stereo(mono, **kw):
    if "wet" in kw: kw["wet"] = max(0.0, min(1.0, float(kw["wet"]) * _RS))
    return _orig(mono, **kw)

OUT = HERE / "samples"
for s in ("kick", "snare", "hat", "bass", "lead", "arp", "pad"):
    (OUT / s).mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(8084)

BASS_MIDIS = [33, 36, 39, 42, 45, 48, 51, 54]
LEAD_MIDIS = [57, 60, 63, 66, 69, 72, 75, 78, 81]
ARP_MIDIS  = [57, 60, 63, 66, 69, 72, 75, 78, 81]
PAD_MIDIS  = [45, 48, 51, 54, 57, 60, 63, 66]


def saw(f0, t, n=26):
    out = np.zeros_like(t); k = 1
    while k * f0 < SR / 2 and k <= n:
        out += np.sin(2 * np.pi * k * f0 * t) / k; k += 1
    return out

def square(f0, t, n=18):
    out = np.zeros_like(t); k = 1
    while (2 * k - 1) * f0 < SR / 2 and k <= n:
        out += np.sin(2 * np.pi * (2 * k - 1) * f0 * t) / (2 * k - 1); k += 1
    return out


def r_kick(v):
    t = t_axis(0.42)
    f = 46 + 110 * np.exp(-t / (0.02 + 0.005 * v))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.14)
    click = rng.standard_normal(int(0.003 * SR)) * 0.4
    body[:click.size] += click * np.linspace(1, 0, click.size)
    return to_stereo(soft_clip(body, drive=1.4))


def r_snare(v):
    t = t_axis(0.34)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    noise = rng.standard_normal(t.size) * np.exp(-t / (0.05 + 0.02 * v))
    noise -= lowpass_fft(noise, 1600)
    dry = 0.5 * body + 0.9 * noise
    return reverb_stereo(soft_clip(dry, drive=1.2), wet=0.42, decay_s=1.1, predelay_ms=8, brightness=0.6)


def r_hat(v):
    dur = (0.05, 0.26)[v]
    t = t_axis(dur)
    n = rng.standard_normal(t.size) * np.exp(-t / (dur * 0.4))
    n -= lowpass_fft(n, 6800)
    return to_stereo(n)


def r_bass(m):
    t = t_axis(0.6); f0 = freq(m)
    x = saw(f0, t) + 0.4 * square(f0, t)
    x = lowpass_fft(x, max(200.0, f0 * 4))
    x *= adsr(t.size, 0.006, 0.16, 0.6, 0.16)
    return to_stereo(soft_clip(x * 0.7, drive=1.25))


def r_lead(m):
    t = t_axis(1.0); f0 = freq(m)
    x = saw(f0 * 0.994, t) + saw(f0 * 1.006, t) + 0.5 * square(f0, t)
    x = lowpass_fft(x, min(8000.0, f0 * 10))
    x *= adsr(t.size, 0.01, 0.3, 0.55, 0.4)
    return reverb_stereo(x / 2.5, wet=0.3, decay_s=1.8, predelay_ms=18, brightness=0.55)


def r_arp(m):
    t = t_axis(0.45); f0 = freq(m)
    x = saw(f0, t) + 0.3 * square(f0 * 2, t)
    x = lowpass_fft(x, min(7000.0, f0 * 9))
    x *= adsr(t.size, 0.004, 0.1, 0.2, 0.28)
    return reverb_stereo(x, wet=0.28, decay_s=1.4, predelay_ms=10, brightness=0.55)


def r_pad(m):
    t = t_axis(2.6)
    chord = [freq(m), freq(m + 7), freq(m + 12)]
    x = sum(saw(f * 0.996, t, 18) + saw(f * 1.004, t, 18) for f in chord) / (2 * len(chord))
    x = lowpass_fft(x, min(5500.0, freq(m) * 7))
    x *= adsr(t.size, 0.55, 0.7, 0.7, 1.0)
    return reverb_stereo(x, wet=0.5, decay_s=3.4, predelay_ms=30, brightness=0.5)


def main(only=None):
    def want(v): return only is None or v in only
    if want("kick"):
        for i in range(2): write_wav(OUT / "kick" / f"{i:02d}.wav", r_kick(i))
    if want("snare"):
        for i in range(2): write_wav(OUT / "snare" / f"{i:02d}.wav", r_snare(i))
    if want("hat"):
        for i in range(2): write_wav(OUT / "hat" / f"{i:02d}.wav", r_hat(i))
    for vname, midis, fn in (("bass", BASS_MIDIS, r_bass), ("lead", LEAD_MIDIS, r_lead),
                             ("arp", ARP_MIDIS, r_arp), ("pad", PAD_MIDIS, r_pad)):
        if want(vname):
            for i, m in enumerate(midis): write_wav(OUT / vname / f"{i:02d}_m{m}.wav", fn(m))
    print("synthwave: rendered", "all" if only is None else ",".join(only))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
