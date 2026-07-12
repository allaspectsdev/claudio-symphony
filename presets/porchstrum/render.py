#!/usr/bin/env python3
"""
porchstrum — sample renderer (per-voice reverb from preset.json).

Banjo and ukulele plinking bright and playful on a sunny front porch.
Plucked short-string folk tones: banjo (bright twangy ring) and ukulele
(soft warm plink). Bouncy, grinning, cheerful — pure good-time.
A major pentatonic @ A=432, additive only, never dreary.

Per-voice REVERB lives in preset.json voices.<name>.reverb (baked here); per-voice
DELAY is a live playback echo handled by event.py.

Usage:  python3 render.py [voice ...]   (no args = all)
"""
import sys, math
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (SR, A4, freq, t_axis, adsr, soft_clip, lowpass_fft,
                    reverb_stereo, write_wav)

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


def _plucked(f, t, partials, pluck_noise=0.0, noise_cut=4000.0, seed=0):
    """Additive plucked-string body. `partials` = list of
    (ratio, amp, decay_rate). A plucked string is a stack of nearly-harmonic
    partials each with its OWN decay rate (highs die first), giving the bright
    'twang' that mellows to a warm hum. Optional short filtered-noise pluck
    transient for the finger/nail contact."""
    sig = np.zeros(t.size)
    for ratio, amp, dec in partials:
        sig += amp * np.sin(2*np.pi*f*ratio*t) * np.exp(-t*dec)
    if pluck_noise > 0.0:
        rng = np.random.default_rng(int(seed) & 0xffffffff)
        n = t.size
        nz = rng.standard_normal(n)
        nz = lowpass_fft(nz, noise_cut, order=3)
        nz_env = np.exp(-t * 280.0)          # ~3.5 ms nail contact
        sig += pluck_noise * nz * nz_env
    return sig


# ---- banjobass (bass) ----
def voice_banjobass(arg):
    """A low banjo-bass pluck — round twangy thump with warm body, the
    bouncing porch ground. Strong sine fundamental + a quick-decaying octave
    twang and a soft 3rd for the 'pop', plus a low-passed pluck thump. The
    high partials die fast so it reads as a round plucked thump, not a buzz.
    arg = midi (LOW). ~1.4s, warm and near-dry."""
    f = freq(int(arg)); dur = 1.4
    n = int(dur * SR); t = t_axis(dur)
    sig = _plucked(f, t, [
        (1.00, 1.00, 3.0),     # round fundamental, hums on
        (2.00, 0.42, 7.0),     # octave twang, fades quick
        (3.00, 0.16, 12.0),    # the plucky 'pop', gone fast
        (1.004, 0.16, 2.6),    # slow-beat body for warm wood life
    ], pluck_noise=0.16, noise_cut=900.0, seed=int(arg)*13+1)
    # soft, slightly snappy pluck attack (~6 ms) — bouncy but click-free
    env = adsr(n, a=0.006, d=0.9, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 1500.0, order=4)   # keep it round & warm, no top fizz
    out = soft_clip(out * 1.04, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.52 / peak)
    return out


# ---- banjolead (lead) ----
def voice_banjolead(arg):
    """A bright banjo string — crisp twangy ring with quick metallic shimmer,
    rolling the melody. Bright nearly-harmonic stack with a fast 'shimmer'
    partial that dies in ~30ms (the twang), all decays independent so the
    string brightens then mellows. arg = midi. ~1.5s, light room."""
    f = freq(int(arg)); dur = 1.5
    n = int(dur * SR); t = t_axis(dur)
    sig = _plucked(f, t, [
        (1.00, 1.00, 3.2),     # singing fundamental
        (2.00, 0.50, 5.5),     # bright octave ring
        (3.00, 0.26, 8.0),     # twang sparkle
        (4.00, 0.12, 12.0),    # crisp shimmer, fades quick
        (5.02, 0.05, 30.0),    # tiny metallic glint, gone in ~30ms (no buzz)
        (1.003, 0.14, 2.6),    # detune body bloom
    ], pluck_noise=0.10, noise_cut=4500.0, seed=int(arg)*7+3)
    env = adsr(n, a=0.006, d=1.0, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 6500.0, order=3)   # tame harsh top, keep crisp
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- ukelead (lead2) ----
def voice_ukelead(arg):
    """A soft ukulele string — warm round plink, strumming a playful
    counter-line. Mellower than the banjo: strong fundamental, gentle octave,
    a soft 3rd that fades early. Rounded top so it's a sweet 'plink', not a
    twang. arg = midi. ~1.3s, light room."""
    f = freq(int(arg)); dur = 1.3
    n = int(dur * SR); t = t_axis(dur)
    sig = _plucked(f, t, [
        (1.00, 1.00, 3.4),     # warm round fundamental
        (2.00, 0.34, 6.0),     # soft octave, mellow
        (3.00, 0.12, 10.0),    # gentle plink color, fades fast
        (1.004, 0.16, 2.4),    # detune body for nylon warmth
    ], pluck_noise=0.08, noise_cut=3000.0, seed=int(arg)*11+5)
    env = adsr(n, a=0.007, d=0.85, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 4200.0, order=3)   # round & warm nylon plink
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.49 / peak)
    return out


# ---- mutedstring (tone) ----
def voice_mutedstring(midi):
    """A muted uke string — dark and warm plink, the sweet little middle.
    Palm-muted: very fast decay, mostly fundamental + a whisper of octave,
    strongly low-passed so it's a soft dark 'pud'. arg = midi. ~0.7s."""
    f = freq(int(midi)); dur = 0.7
    n = int(dur * SR); t = t_axis(dur)
    sig = _plucked(f, t, [
        (1.00, 1.00, 9.0),     # quick muted decay
        (2.00, 0.18, 16.0),    # tiny octave, gone fast
        (1.005, 0.12, 7.0),    # soft body
    ], pluck_noise=0.07, noise_cut=2000.0, seed=int(midi)*17+2)
    env = adsr(n, a=0.006, d=0.45, s_level=0.0, r=0.18)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 1800.0, order=4)   # dark & warm, muted
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- banjoping (chime) ----
def voice_banjoping(midi):
    """A high banjo harmonic ping — bright glint, sweet. Like touching the
    string at the 12th fret: a clear high fundamental with a pure octave
    and a faint, fast-fading 3rd for a glassy 'glint'. Additive, no buzz.
    arg = midi (HIGH). ~1.8s, medium-light reverb."""
    f = freq(int(midi)); dur = 1.8
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.8) +   # clear harmonic
        0.45 * np.sin(2*np.pi*f*2.0*t)    * np.exp(-t*2.6) +   # pure octave glint
        0.14 * np.sin(2*np.pi*f*3.0*t)    * np.exp(-t*4.5) +   # faint glassy color
        0.05 * np.sin(2*np.pi*f*4.0*t)    * np.exp(-t*8.0) +   # tiny shimmer, gone fast
        0.12 * np.sin(2*np.pi*f*1.004*t)  * np.exp(-t*1.6)     # soft detune halo
    )
    env = adsr(n, a=0.010, d=1.4, s_level=0.0, r=0.45)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7000.0, order=3)   # sweet, no harsh top
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.49 / peak)
    return out


# ---- topflick (sparkle) ----
def voice_topflick(seed):
    """Tiny top-string flicks scattering bright twang. A very short, bright
    plucked blip from the HIGH pentatonic — a quick nail-flick on the top
    string. Additive sines + a tiny chiff. Seed picks the pitch so flicks
    scatter playfully. ~0.5s, light delay echoes (handled live)."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    HIGH = [76, 78, 81, 85, 88]
    f = freq(HIGH[int(rng.integers(0, len(HIGH)))])
    dur = 0.5; n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)       * np.exp(-t*7.0) +    # bright blip
        0.32 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*11.0) +   # twang octave
        0.10 * np.sin(2*np.pi*f*3.0*t)   * np.exp(-t*18.0)     # tiny sparkle, fades fast
    )
    # short nail-flick chiff
    nz = lowpass_fft(rng.standard_normal(n), 6000.0, order=3) * np.exp(-t*240.0)
    sig += 0.10 * nz
    env = adsr(n, a=0.005, d=0.32, s_level=0.0, r=0.14)
    out = sig[:env.size] * env[:sig.size]
    out = lowpass_fft(out, 7500.0, order=3)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.48 / peak)
    return out


# ---- ukebloom (bloom) ----
def voice_ukebloom(midi):
    """A rolled-and-sustained uke chord swell — warm folk blooming gently,
    lush room wash. From the root we build a major-pentatonic chord (root,
    maj3, 5th, maj6, octave), each note a soft sustained nylon tone that
    STRUMS in staggered (the roll) and blooms open. Warm low-passed, lush.
    arg = root midi. ~6.5s."""
    root = int(midi)
    intervals = [0, 4, 7, 9, 12]
    dur = 6.5
    n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for i, iv in enumerate(intervals):
        f = freq(root + iv)
        body = (
            np.sin(2*np.pi*f*t) +
            0.30 * np.sin(2*np.pi*f*2.0*t) * np.exp(-t*2.0) +   # soft octave, fades
            0.10 * np.sin(2*np.pi*f*3.0*t) * np.exp(-t*4.0)     # gentle color
        )
        detune = 0.32 * np.sin(2*np.pi*f*1.0035*t)             # warm chorus
        vib = 1.0 + 0.0018 * np.sin(2*np.pi*0.26*t + i*0.8)    # slow breathe
        voice = (0.85*body + detune) * vib
        # rolled strum: each higher note enters a touch later
        roll = 0.09 * i
        env = adsr(n, a=0.9 + roll, d=1.0, s_level=0.78, hold=1.2, r=2.4)
        gain = 1.0 - 0.08*i
        sig += voice * env[:n] * gain
    sig /= len(intervals)
    sig = lowpass_fft(sig, 2600.0, order=3)   # warm folk, no harsh edge
    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- banjoroll (cluster) ----
def voice_banjoroll(arg):
    """A fast banjo-roll arpeggio — shimmering twangy cascade, bouncy and
    bright. From the root we play a quick rolling pentatonic arpeggio (a
    classic banjo roll), each pluck a short bright string. Notes cascade up
    then ring together into a shimmering chord. arg = root midi. ~4.0s."""
    root = int(arg)
    # pentatonic roll pattern (semitone offsets within A maj pentatonic)
    steps = [0, 4, 7, 12, 7, 9, 12, 16, 12, 16, 19, 21]
    dur = 4.0
    n = int(dur * SR); t = t_axis(dur)
    out = np.zeros(n)
    note_dt = 0.085   # bouncy roll spacing
    note_len = 1.1
    nl = int(note_len * SR)
    for i, st in enumerate(steps):
        f = freq(root + st)
        start = int(i * note_dt * SR)
        if start >= n:
            break
        seg = min(nl, n - start)
        tt = t[:seg]
        pluck = (
            1.00 * np.sin(2*np.pi*f*tt)      * np.exp(-tt*3.6) +
            0.42 * np.sin(2*np.pi*f*2.0*tt)  * np.exp(-tt*6.0) +
            0.18 * np.sin(2*np.pi*f*3.0*tt)  * np.exp(-tt*9.0) +
            0.05 * np.sin(2*np.pi*f*5.02*tt) * np.exp(-tt*30.0)   # tiny glint
        )
        penv = adsr(seg, a=0.005, d=0.6, s_level=0.0, r=0.4)
        gain = 0.95 - 0.02*i
        out[start:start+seg] += pluck[:penv.size] * penv[:pluck.size] * gain
    out = lowpass_fft(out, 6500.0, order=3)   # bright but tamed top
    out = soft_clip(out, 1.05)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- strumtap (tap) ----
def voice_strumtap(seed):
    """A muted string-mute tap — near-dry chunky click, the rhythmic
    strum-pulse. A palm hitting muted strings: a short low-mid thud body +
    a soft band-limited 'chunk' of muted-string noise. Warm, dry, percussive.
    >=2ms soft attack, never a raw click. ~0.16s."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    dur = 0.16; n = int(dur * SR); t = t_axis(dur)
    # muted-string body: low-mid thud near A2, tiny per-hit wobble
    f0 = freq(45) * (1.0 + rng.uniform(-0.02, 0.02))
    body = (
        1.00 * np.sin(2*np.pi*f0*t)       * np.exp(-t*36) +
        0.40 * np.sin(2*np.pi*f0*1.5*t)   * np.exp(-t*55) +
        0.16 * np.sin(2*np.pi*f0*2.4*t)   * np.exp(-t*80)
    )
    # muted-string chunk: filtered noise burst (the strings buzzing dead)
    nz = rng.standard_normal(n)
    chunk = lowpass_fft(nz, 2200.0, order=3) - lowpass_fft(nz, 300.0, order=2)
    c_env = adsr(n, a=0.0025, d=0.040, s_level=0.0, r=0.02)
    chunk = chunk * c_env
    sig = body + 0.55 * chunk
    sig = lowpass_fft(sig, 3000.0, order=4)   # warm, woody chunk
    env = adsr(n, a=0.003, d=0.08, s_level=0.0, r=0.05)
    out = sig[:env.size] * env[:sig.size]
    out = soft_clip(out * 1.05, 1.0)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.50 / peak)
    return out


# ---- ukechirp (chirp) ----
def voice_ukechirp(seed):
    """A bright high uke-flick — a grinning little porch accent. A quick
    two-note rising plink in the HIGH pentatonic: bright, friendly, playful.
    Additive sines + tiny octave sparkle, ~0.42s, near-dry. Seed picks the
    starting note and a small upward leap so each chirp grins differently."""
    rng = np.random.default_rng(int(seed) & 0xffffffff)
    HIGH = [69, 73, 76, 78, 81, 85]
    leaps = [2, 3, 4]
    start_i = int(rng.integers(0, 3))
    leap = leaps[int(rng.integers(0, len(leaps)))]
    end_i = min(start_i + leap, len(HIGH) - 1)
    f0 = freq(HIGH[start_i]); f1 = freq(HIGH[end_i])
    dur = 0.42; n = int(dur * SR); t = t_axis(dur)
    # quick rising plink: pitch lifts over first ~45%, then the string rings
    rise = np.clip(t / (dur * 0.45), 0.0, 1.0)
    rise = rise * rise * (3 - 2*rise)        # smoothstep
    f_t = f0 + (f1 - f0) * rise
    phase = 2*np.pi*np.cumsum(f_t)/SR
    sig = (
        np.sin(phase) * np.exp(-t*5.5) +              # bright plink
        0.22 * np.sin(2*phase) * np.exp(-t*8.0) +     # octave sparkle
        0.06 * np.sin(3*phase) * np.exp(-t*16.0)      # tiny chiff onset
    )
    sig = lowpass_fft(sig, 7500.0, order=3)
    env = adsr(n, a=0.006, d=0.30, s_level=0.0, r=0.12)
    out = sig[:env.size] * env[:sig.size]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out * (0.49 / peak)
    return out


PLAN = {
    "banjobass": {
        "kind": "midi",
        "midis": [33, 36, 40, 45, 49, 52],
        "pans": [0, 0, 0, 0, 0, 0],
        "target_peak": 0.6,
        "reverb": {"wet": 0.12, "decay": 1.4, "predelay_ms": 12, "brightness": 0.32}
    },
    "banjolead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [-0.2, 0.2, -0.1, 0.15, 0, -0.18, 0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.20, "decay": 1.6, "predelay_ms": 18, "brightness": 0.6}
    },
    "ukelead": {
        "kind": "midi",
        "midis": [57, 59, 61, 64, 66, 69, 71, 73, 76, 78, 81],
        "pans": [0.2, -0.2, 0.1, -0.15, 0, 0.18, -0.18],
        "target_peak": 0.8,
        "reverb": {"wet": 0.18, "decay": 1.5, "predelay_ms": 16, "brightness": 0.5}
    },
    "mutedstring": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69, 73, 76],
        "pans": [-0.12, 0.12, -0.06, 0.1, 0, -0.1, 0.08],
        "target_peak": 0.78,
        "reverb": {"wet": 0.16, "decay": 1.2, "predelay_ms": 12, "brightness": 0.4}
    },
    "banjoping": {
        "kind": "midi",
        "midis": [69, 73, 76, 78, 81, 85, 88],
        "pans": [-0.35, 0.3, -0.2, 0.35, -0.25, 0.2, 0],
        "target_peak": 0.8,
        "reverb": {"wet": 0.34, "decay": 3.0, "predelay_ms": 26, "brightness": 0.62}
    },
    "topflick": {
        "kind": "seed",
        "count": 6,
        "pans": [0.35, -0.3, 0.45, -0.4, 0.25, -0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.22, "decay": 1.8, "predelay_ms": 14, "brightness": 0.62}
    },
    "ukebloom": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [0, -0.15, 0.15],
        "target_peak": 0.8,
        "reverb": {"wet": 0.5, "decay": 5.0, "predelay_ms": 45, "brightness": 0.45}
    },
    "banjoroll": {
        "kind": "midi",
        "midis": [57, 61, 64, 66, 69],
        "pans": [-0.2, 0.2, -0.1, 0.15, 0],
        "target_peak": 0.78,
        "reverb": {"wet": 0.46, "decay": 4.4, "predelay_ms": 36, "brightness": 0.6}
    },
    "strumtap": {
        "kind": "seed",
        "count": 4,
        "pans": [-0.18, 0.18, -0.1, 0.14],
        "target_peak": 0.5,
        "reverb": {"wet": 0.05, "decay": 0.6, "predelay_ms": 8, "brightness": 0.35}
    },
    "ukechirp": {
        "kind": "seed",
        "count": 6,
        "pans": [0.3, -0.3, 0.4, -0.4, 0.2, -0.2],
        "target_peak": 0.78,
        "reverb": {"wet": 0.1, "decay": 1.4, "predelay_ms": 12, "brightness": 0.6}
    }
}


def _voice_reverb(name):
    rv = dict(PLAN[name]["reverb"])
    cfg = (_PRESET_CFG.get("voices", {}).get(name, {}) or {}).get("reverb")
    if isinstance(cfg, dict):
        rv.update(cfg)
    return rv


def _render(mono, rv, pan, target_peak, path):
    st = reverb_stereo(mono, wet=rv.get("wet", 0.0), decay_s=rv.get("decay", 2.0),
                       predelay_ms=rv.get("predelay_ms", 20),
                       brightness=rv.get("brightness", 0.45))
    if pan != 0.0:
        pan = float(np.clip(pan, -1.0, 1.0))
        lg = math.cos((pan + 1) * math.pi / 4); rg = math.sin((pan + 1) * math.pi / 4)
        st = st.copy(); st[:, 0] *= 2 * lg; st[:, 1] *= 2 * rg
    write_wav(path, st, target_peak=target_peak)


def render_voice(name):
    fn = globals()["voice_" + name]
    spec = PLAN[name]; rv = _voice_reverb(name); pans = spec["pans"]
    (OUT / name).mkdir(parents=True, exist_ok=True)
    if spec["kind"] == "midi":
        for i, m in enumerate(spec["midis"]):
            _render(fn(m), rv, pans[i % len(pans)], spec["target_peak"],
                    OUT / name / f"{i:02d}_m{m}.wav")
    else:  # seed
        for i in range(spec["count"]):
            _render(fn(1000 + i * 7), rv, pans[i % len(pans)], spec["target_peak"],
                    OUT / name / f"{i:02d}.wav")
    print("porchstrum:", name)


def gen_all():
    OUT.mkdir(exist_ok=True)
    for name in PLAN:
        render_voice(name)
    print("done.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        OUT.mkdir(exist_ok=True)
        for v in sys.argv[1:]:
            if v in PLAN: render_voice(v)
            else: print("unknown voice:", v)
    else:
        gen_all()
