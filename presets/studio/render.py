#!/usr/bin/env python3
"""
Studio preset — sample renderer.

The MIDI demo kit: drums, bass and synth, made for the Jukebox. Where every
other preset is an ambient room, this one is a band — kick/snare/hat that hit
like a kit, a round sub-ish bass, and a soft detuned synth lead. Pitched
voices are A-rooted like everything else (A=432), sampled every 3 semitones so
playback shifts stay tiny.

Voices:
  kick  — sine pitch-drop thump with a tiny click transient
  snare — triangle body + bright noise crack
  hat   — short high-passed noise tick (3 lengths)
  bass  — band-limited saw, lowpassed round, A1..F#2 region
  synth — two detuned saws, soft pluck envelope, A3..F#5 region
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (
    SR, freq, t_axis, adsr, soft_clip, lowpass_fft,
    reverb_stereo, to_stereo, write_wav,
)

# === reverb_scale monkeypatch (same contract as every preset) ===
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
for sub in ("kick", "snare", "hat", "bass", "synth"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(432)

BASS_MIDIS = [33, 36, 39, 42, 45, 48, 51, 54]    # A1 .. F#2-ish, every 3 semis
SYNTH_MIDIS = [57, 60, 63, 66, 69, 72, 75, 78]   # A3 .. F#5-ish


def saw(f0, t):
    """Band-limited-ish saw: summed harmonics below Nyquist (capped at 30)."""
    out = np.zeros_like(t)
    k = 1
    while k * f0 < SR / 2 and k <= 30:
        out += np.sin(2 * np.pi * k * f0 * t) / k
        k += 1
    return out


def r_kick(variant):
    dur = 0.40
    t = t_axis(dur)
    # pitch drop 150→45 Hz over ~70 ms (phase-integrated so there's no click)
    f = 45 + 105 * np.exp(-t / (0.022 + 0.006 * variant))
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t / 0.13)
    click = rng.standard_normal(int(0.003 * SR)) * 0.5
    body[:click.size] += click * np.linspace(1, 0, click.size)
    return to_stereo(soft_clip(body, drive=1.4))


def r_snare(variant):
    dur = 0.30
    t = t_axis(dur)
    body = (np.sin(2 * np.pi * 196 * t) + 0.5 * np.sin(2 * np.pi * 286 * t)) * np.exp(-t / 0.055)
    noise = rng.standard_normal(t.size) * np.exp(-t / (0.075 + 0.02 * variant))
    noise = noise - lowpass_fft(noise, 1800)          # high-pass the crack
    return to_stereo(soft_clip(0.6 * body + 0.9 * noise, drive=1.2))


def r_hat(variant):
    dur = (0.06, 0.12, 0.28)[variant]                 # closed / mid / open
    t = t_axis(dur)
    n = rng.standard_normal(t.size) * np.exp(-t / (dur * 0.45))
    n = n - lowpass_fft(n, 6500)                      # keep only the sizzle
    return to_stereo(n)


def r_bass(midi):
    dur = 0.55
    t = t_axis(dur)
    f0 = freq(midi)
    x = saw(f0, t)
    x = lowpass_fft(x, max(180.0, f0 * 3.2))          # round it off
    x *= adsr(t.size, 0.006, 0.18, 0.55, 0.16)
    return to_stereo(soft_clip(x, drive=1.1))


def r_synth(midi):
    dur = 0.9
    t = t_axis(dur)
    f0 = freq(midi)
    x = saw(f0 * 0.9965, t) + saw(f0 * 1.0035, t)     # ±6-cent detune
    x = lowpass_fft(x, min(7000.0, f0 * 9))
    x *= adsr(t.size, 0.012, 0.30, 0.45, 0.35)
    return reverb_stereo(x / 2.0, wet=0.18, decay_s=1.6, predelay_ms=15, brightness=0.5)


def main(only=None):
    def want(v): return only is None or v in only
    if want("kick"):
        for i in range(3): write_wav(OUT / "kick" / f"{i:02d}.wav", r_kick(i))
    if want("snare"):
        for i in range(3): write_wav(OUT / "snare" / f"{i:02d}.wav", r_snare(i))
    if want("hat"):
        for i in range(3): write_wav(OUT / "hat" / f"{i:02d}.wav", r_hat(i))
    if want("bass"):
        for i, m in enumerate(BASS_MIDIS): write_wav(OUT / "bass" / f"{i:02d}_m{m}.wav", r_bass(m))
    if want("synth"):
        for i, m in enumerate(SYNTH_MIDIS): write_wav(OUT / "synth" / f"{i:02d}_m{m}.wav", r_synth(m))
    print("studio: rendered", "all" if only is None else ",".join(only))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
