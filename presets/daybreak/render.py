#!/usr/bin/env python3
"""
daybreak — sample renderer (per-voice reverb read from preset.json).

A dawn-bright, minimal palette: a curious music-box, warm rosewood marimba,
sun catching on water (glass), soft warm blooms, and a low felt anchor.
A major pentatonic @ A=432, additive only, never dreary.

Per-voice REVERB lives in preset.json under voices.<name>.reverb
({wet,decay,predelay_ms,brightness}) and is baked here. Per-voice DELAY is a
live playback echo handled by event.py (no re-render needed).

Usage:
  python3 render.py            # render every voice
  python3 render.py <voice>    # render just one voice (fast fx tweaks)
"""
import sys, math
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from synth import (SR, freq, t_axis, adsr, lowpass_fft,
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

# ---- dewdrop ----
def voice_dewdrop(midi):
    """A of Clubs — the curious student. One pure music-box note with a tiny
    upward grace-lift at the attack (a quick rising 'oh?' over ~45 ms), then a
    clean glassy decay. Minimal: essentially a single sine + two soft additive
    partials with independent decays. Bright, never dreary."""
    f = freq(midi)
    dur = 3.2
    n = int(dur * SR); t = t_axis(dur)

    # tiny upward pitch grace: starts ~1.2 semitone low, glides up in ~45 ms.
    # curious little lift, then settles — the "perking up" gesture.
    glide = np.ones(n)
    g_n = int(0.045 * SR)
    bend = np.linspace(2**(-1.2/12.0), 1.0, g_n)   # from ~1.2 semitone below up to pitch
    glide[:g_n] = bend
    phase = 2*np.pi*f*np.cumsum(glide)/SR

    sig = (
        1.00 * np.sin(phase)      * np.exp(-t*1.4) +   # pure body
        0.28 * np.sin(2.0*phase)  * np.exp(-t*3.2) +   # soft octave
        0.10 * np.sin(3.01*phase) * np.exp(-t*6.0) +   # gentle glass
        0.05 * np.sin(4.5 *phase) * np.exp(-t*14.0)    # brief tinkle, gone fast
    )
    # soft music-box attack (no click), short bloom, clean tail to silence
    env = adsr(n, a=0.008, d=2.4, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size]
    # tame anything above ~5x just in case
    out = lowpass_fft(out, f*5.5, order=4)
    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / peak * 0.48
    return out


# ---- lullaby ----
def voice_lullaby(midi):
    """Music-box / harp grace-note bloom. Q of Clubs: nurturing mastery.
    A quick lower grace note (a pentatonic step below, within the
    A-pentatonic family) flicks UP into the warm main note, like a mother
    humming a phrase. Additive only: pure fundamental + a gently stretched
    octave + a soft inharmonic plate that decays fast for music-box sparkle,
    plus a faint 1.003 detune for warmth. Bright, never dreary."""
    f = freq(midi)
    dur = 4.0
    n = int(dur * SR)
    t = t_axis(dur)

    def note(fr, t_local):
        # additive plucked-mallet partial stack, each partial its own decay
        s = (
            1.00 * np.sin(2*np.pi*fr*t_local)            * np.exp(-t_local*1.1) +
            0.42 * np.sin(2*np.pi*fr*2.003*t_local)      * np.exp(-t_local*2.0) +
            0.16 * np.sin(2*np.pi*fr*3.01*t_local)       * np.exp(-t_local*4.5) +
            0.05 * np.sin(2*np.pi*fr*4.78*t_local)       * np.exp(-t_local*9.0) +
            0.18 * np.sin(2*np.pi*fr*1.003*t_local)      * np.exp(-t_local*1.4)
        )
        return s

    # grace note: a soft, brief lower neighbor a pentatonic step+ below,
    # ~70 ms before the main note. Keep it within the family (down ~3 semis).
    grace_midi = midi - 3 if (midi - 3) >= 45 else midi + 2
    fg = freq(grace_midi)
    g_delay = int(0.07 * SR)

    sig = np.zeros(n)
    # grace (quiet, quick)
    tg = t_axis(dur)
    grace = note(fg, tg) * np.exp(-tg*3.0)
    grace_env = adsr(n, a=0.006, d=0.25, s_level=0.0, r=0.2)
    grace = grace[:n] * grace_env * 0.30
    sig += grace

    # main note, delayed by the grace
    main = note(f, t)
    main_env = adsr(n, a=0.010, d=2.2, s_level=0.0, r=1.6)
    main = main[:n] * main_env
    shifted = np.zeros(n)
    if g_delay < n:
        seg = n - g_delay
        shifted[g_delay:] = main[:seg]
    sig += shifted

    # gentle overall lowpass for that felt/music-box warmth (no harsh top)
    sig = lowpass_fft(sig, 5200.0, order=3)

    peak = float(np.max(np.abs(sig)))
    if peak > 1e-9:
        sig = sig / peak * 0.50
    return sig


# ---- marimba ----
def voice_marimba(midi):
    """Warm rosewood marimba bar — 'The Teacher': a rounded wooden tone with a
    generous, tasteful harmonic body. Real marimba bars are tuned so the first
    overtone sits a TWELFTH (3x) and the next near 2 octaves+M3 (~6x), each with
    its own fast decay; a soft low mallet thump grounds the attack. Additive
    only — no FM. Upper partials decay fast so it never screeches; the body is
    the warm fundamental + low octave that rings a touch longer."""
    f = freq(midi); dur = 3.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*2.6) +   # fundamental — the warm body
        0.45 * np.sin(2*np.pi*f*0.5*t)    * np.exp(-t*2.0) +   # sub-octave — rosewood depth
        0.40 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*5.5) +   # tuned twelfth — marimba signature
        0.16 * np.sin(2*np.pi*f*6.05*t)   * np.exp(-t*8.0) +   # 2oct+M3 shimmer, decays fast
        0.06 * np.sin(2*np.pi*f*9.2*t)    * np.exp(-t*14.0)    # faint air, gone in a blink
    )
    # soft mallet thump: a quick low sine blip at attack, no click
    thump = 0.30 * np.sin(2*np.pi*(f*0.5)*t) * np.exp(-t*42.0)
    sig = sig + thump
    # gentle detune on the fundamental for a living, wooden beat
    sig += 0.12 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*2.6)
    sig = lowpass_fft(sig, 7000.0, order=3)   # round off any harsh edge
    env = adsr(n, a=0.006, d=2.4, s_level=0.0, r=0.6)
    out = sig[:env.size] * env[:sig.size] * 0.28
    return out


# ---- light_drop ----
def voice_light_drop(midi):
    """A single drop of light on water. One pure high sine, a faint
    stretched-octave glass partial that vanishes in the first instant,
    and a tiny downward pitch glint at the attack (the surface tension
    'plink'). Minimal — almost one sine. Bright, clean, never dreary."""
    f = freq(midi); dur = 2.2
    n = int(dur * SR); t = t_axis(dur)
    # tiny downward pitch glint over the first ~25 ms — the 'plink'
    glint = 1.0 + 0.018 * np.exp(-t * 60.0)
    phase = 2*np.pi*f * np.cumsum(glint) / SR
    sig = (
        np.sin(phase) +                                       # pure fundamental
        0.16 * np.sin(2.005*phase) * np.exp(-t * 18.0) +      # glass tinkle, gone fast
        0.05 * np.sin(3.01 *phase) * np.exp(-t * 34.0)        # top glint, vanishes
    )
    env = adsr(n, a=0.006, d=0.9, s_level=0.0, r=1.1)
    return sig[:env.size] * env[:sig.size] * 0.46


# ---- sunglint ----
def voice_sunglint(midi):
    """The Sun catching on water — a bright, full-bodied glass chime.

    Additive only. A confident fundamental with a stretched octave gives
    body (this is a PRESENT bell, not a thin tinkle), plus two short
    inharmonic glints up top that flash at the attack and decay fast so
    there's sparkle without any screech. A whisper of slow shimmer
    (1.002x beating) keeps the tail alive and jewel-like. Major-pentatonic
    safe — pure ratios, no dissonance possible."""
    f = freq(midi)
    dur = 3.2
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t)        * np.exp(-t*1.1) +    # body — full but quick
        0.55 * np.sin(2*np.pi*f*2.003*t)  * np.exp(-t*1.7) +    # stretched octave shine
        0.28 * np.sin(2*np.pi*f*3.01*t)   * np.exp(-t*3.2) +    # bright glint
        0.10 * np.sin(2*np.pi*f*4.52*t)   * np.exp(-t*7.0) +    # glass flash (fast)
        0.05 * np.sin(2*np.pi*f*6.0*t)    * np.exp(-t*12.0)     # top sparkle, gone in ~80ms
    )
    # slow beating shimmer keeps the tail glittering, not static
    sig += 0.16 * np.sin(2*np.pi*f*1.002*t) * np.exp(-t*1.3)
    env = adsr(n, a=0.012, d=2.6, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size] * 0.27
    return out


# ---- heart_bloom ----
def voice_heart_bloom(midi):
    """A of Hearts — a single warm sustained bloom that swells like a held
    breath given freely. Almost one pure sine: fundamental + a soft octave
    companion an octave up (the 'giving more than asked') that fades sooner,
    plus a whisper-quiet fifth for warmth. A slow gentle vibrato that reads
    as tenderness, never wobble. Long swell-in attack, long release. Bright,
    major, simple. No inharmonic bell metal, no FM."""
    f = freq(midi)
    dur = 9.0
    n = int(dur * SR); t = t_axis(dur)

    # slow tender vibrato — a held breath, not a wobble
    vib = 1.0 + 0.0025 * np.sin(2*np.pi*4.7*t)
    phase = 2*np.pi*f * np.cumsum(vib) / SR

    # the pure core
    core = np.sin(phase)
    # octave companion — gives a little more, fades sooner (the seeker)
    octave = 0.32 * np.sin(2*phase) * np.exp(-t*0.5)
    # whisper fifth for warmth, very quiet, settles in
    fifth = 0.10 * np.sin(1.5*phase) * np.exp(-t*0.35)
    # faint 4th harmonic shimmer at the very top of the bloom, decays fast
    shimmer = 0.04 * np.sin(4*phase) * np.exp(-t*1.6)

    sig = core + octave + fifth + shimmer

    # gentle warmth — tame anything harsh up top
    sig = lowpass_fft(sig, 3200.0, order=3)

    # held-breath envelope: long swell-in, sustained bloom, long release
    env = adsr(n, a=1.6, d=1.2, s_level=0.78, hold=1.5, r=4.0)
    out = sig[:env.size] * env[:sig.size]

    # land softly around 0.45 peak
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out / peak * 0.46
    return out


# ---- aubade ----
def voice_aubade(arg):
    # 9 of Hearts — Universal Love. A warm bell-bloom that swells like a held
    # breath, blooms with soft additive partials, then lets go and fades all
    # the way to nothing. Bright A-pentatonic, never dreary.
    midi = int(arg)
    f = freq(midi)
    dur = 9.0
    n = int(dur * SR); t = t_axis(dur)

    # Additive partials with INDEPENDENT decay rates (no FM). Inharmonic stretch
    # gives a warm glassy bell-bloom; upper partials decay fast (no screech).
    sig = np.zeros(n)
    sig += 1.00 * np.sin(2*np.pi*f*t)             * np.exp(-t*0.45)   # fundamental, slow
    sig += 0.30 * np.sin(2*np.pi*f*2.005*t)       * np.exp(-t*0.75)   # stretched octave
    sig += 0.16 * np.sin(2*np.pi*f*3.01*t)        * np.exp(-t*1.30)   # warm twelfth-ish
    sig += 0.09 * np.sin(2*np.pi*f*4.502*t)       * np.exp(-t*2.40)   # glass shimmer, fast
    sig += 0.05 * np.sin(2*np.pi*f*5.43*t)        * np.exp(-t*3.80)   # faint air, fastest

    # Gentle pad-like sub bloom underneath for warmth (a soft detuned pair).
    bloom = (np.sin(2*np.pi*f*t) + np.sin(2*np.pi*f*1.003*t)) * 0.5
    bloom = lowpass_fft(bloom, 900.0, order=3)
    sig = sig + 0.35 * bloom

    # Soft breath of vibrato that deepens as it blooms then settles.
    vib = 1.0 + 0.0016 * np.sin(2*np.pi*4.7*t) * np.linspace(0.0, 1.0, n)
    sig = sig * vib

    # Tame any upper grit so it stays warm and round.
    sig = lowpass_fft(sig, 4200.0, order=3)

    # Held-breath envelope: slow swell-in, brief hold, very long release to nothing.
    env = adsr(n, a=0.9, d=1.6, s_level=0.7, r=5.6, hold=0.9)
    out = sig * env

    peak = float(np.max(np.abs(out)))
    if peak > 1e-9:
        out = out / peak * 0.48
    return out


# ---- deep_anchor ----
def voice_deep_anchor(midi):
    """The Magi's heartbeat — a single grounding low sub-pulse with a soft
    felt thump on top. Minimal: one warm sine fundamental + a gentle sub
    octave for body, plus a quiet woody knock that decays in ~120 ms so the
    note 'lands' softly. Bright-warm, never dreary: a touch of the 2nd and
    3rd partial keeps it from muddy, and everything above is rolled off."""
    f = freq(midi)
    dur = 4.5
    n = int(dur * SR); t = t_axis(dur)

    # Warm low body — fundamental + sub octave for weight, plus two quiet
    # harmonics with fast independent decay so it reads as warm, not dull.
    body = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.45 * np.sin(2*np.pi*f*0.5*t) +                          # sub octave (anchor weight)
        0.22 * np.sin(2*np.pi*f*2.0*t)   * np.exp(-t*2.5) +       # warmth, fades fast
        0.08 * np.sin(2*np.pi*f*3.01*t)  * np.exp(-t*5.0)         # gentle color, gone quickly
    )
    body_env = adsr(n, a=0.015, d=2.0, s_level=0.18, r=2.0)
    body = body * body_env

    # Soft felt knock — a short low woody tap layered at attack. Sine-y so it
    # never clicks; lowpassed and decays in ~120 ms.
    knock = np.sin(2*np.pi*f*1.5*t) * np.exp(-t*22.0)
    knock += 0.3 * np.sin(2*np.pi*f*0.75*t) * np.exp(-t*16.0)
    knock_env = adsr(n, a=0.006, d=0.12, s_level=0.0, r=0.05)
    knock = knock * knock_env * 0.30

    out = body + knock
    out = lowpass_fft(out, 900.0, order=3)   # keep it low & felt, no harsh top
    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / peak * 0.50
    return out


# ---- keystone ----
def voice_keystone(midi):
    """K of Spades — 'keystone': a grounding low woody anchor. A soft mallet
    knock on a warm low fundamental that settles into a brief, reassuring
    sub-bloom. Additive only. Authoritative, bright-warm, never dreary."""
    f = freq(midi)
    dur = 4.0
    n = int(dur * SR); t = t_axis(dur)

    # Warm low body: fundamental + just-tuned octave + gentle fifth shimmer.
    # Each partial decays on its own rate; nothing above ~4x and it dies fast.
    body = (
        1.00 * np.sin(2*np.pi*f*t)            * np.exp(-t*0.9) +   # fundamental, the anchor
        0.45 * np.sin(2*np.pi*f*2.0*t)        * np.exp(-t*1.6) +   # warm octave
        0.16 * np.sin(2*np.pi*f*3.0*t)        * np.exp(-t*3.0) +   # soft fifth-above color
        0.06 * np.sin(2*np.pi*f*4.02*t)       * np.exp(-t*6.0)     # faint wood ring, quick
    )
    # Tiny detune partial for a breathing warmth (no beating harshness).
    body += 0.10 * np.sin(2*np.pi*f*1.004*t) * np.exp(-t*1.1)

    # Soft woody knock: a short noise burst shaped low — the 'definitive tap'
    # of a wooden mallet meeting the anchor. Soft, no click.
    rng = np.random.default_rng(int(midi) * 7 + 11)
    knock = rng.standard_normal(n)
    knock = lowpass_fft(knock, 900.0, order=3)
    knock_env = np.exp(-t * 55.0)            # ~18 ms thud
    knock = knock * knock_env * 0.18

    sig = body + knock

    # Soft attack (no click), long settling release — the final word fading.
    env = adsr(n, a=0.008, d=2.6, s_level=0.0, r=1.2)
    out = sig[:env.size] * env[:sig.size]

    # Gentle warmth roll-off so nothing pokes, then land peak ~0.5.
    out = lowpass_fft(out, 2600.0, order=2)
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out * (0.50 / peak)
    return out


# Per-voice render plan. reverb defaults here are the as-designed values; the
# live value is read from preset.json voices.<name>.reverb so `claudio voice
# reverb <name> <wet>` can retune a single voice and regen just that voice.
PLAN = {
    "dewdrop": {
        "midis": [
            57,
            59,
            61,
            64,
            66,
            69,
            71,
            73,
            76,
            78,
            81
        ],
        "pans": [
            -0.3,
            0.25,
            -0.15,
            0.35,
            0
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.18,
            "decay": 2.2,
            "predelay_ms": 24,
            "brightness": 0.55
        }
    },
    "lullaby": {
        "midis": [
            57,
            59,
            61,
            64,
            66,
            69,
            71,
            73,
            76,
            78,
            81
        ],
        "pans": [
            -0.22,
            0.18,
            -0.12,
            0.26
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.18,
            "decay": 2.2,
            "predelay_ms": 24,
            "brightness": 0.5
        }
    },
    "marimba": {
        "midis": [
            57,
            59,
            61,
            64,
            66,
            69,
            71,
            73,
            76,
            78,
            81
        ],
        "pans": [
            -0.3,
            0.3,
            -0.15,
            0.15,
            0
        ],
        "target_peak": 0.82,
        "reverb": {
            "wet": 0.18,
            "decay": 2,
            "predelay_ms": 22,
            "brightness": 0.5
        }
    },
    "light_drop": {
        "midis": [
            69,
            73,
            76,
            78,
            81,
            85,
            88
        ],
        "pans": [
            -0.5,
            0.5,
            -0.25,
            0.25,
            0,
            -0.6
        ],
        "target_peak": 0.55,
        "reverb": {
            "wet": 0.4,
            "decay": 2.4,
            "predelay_ms": 20,
            "brightness": 0.7
        }
    },
    "sunglint": {
        "midis": [
            69,
            73,
            76,
            78,
            81,
            85,
            88
        ],
        "pans": [
            -0.5,
            0.3,
            -0.25,
            0.55,
            -0.4,
            0.45
        ],
        "target_peak": 0.62,
        "reverb": {
            "wet": 0.4,
            "decay": 2.4,
            "predelay_ms": 60,
            "brightness": 0.7
        }
    },
    "heart_bloom": {
        "midis": [
            57,
            61,
            64,
            69,
            73,
            76
        ],
        "pans": [
            -0.18,
            0.18,
            0
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.5,
            "decay": 4.5,
            "predelay_ms": 45,
            "brightness": 0.45
        }
    },
    "aubade": {
        "midis": [
            57,
            61,
            64,
            69,
            73,
            76
        ],
        "pans": [
            -0.35,
            0.3,
            -0.15,
            0.4,
            0
        ],
        "target_peak": 0.82,
        "reverb": {
            "wet": 0.5,
            "decay": 5,
            "predelay_ms": 45,
            "brightness": 0.42
        }
    },
    "deep_anchor": {
        "midis": [
            33,
            36,
            40,
            45,
            49,
            52
        ],
        "pans": [
            0,
            -0.12,
            0.12
        ],
        "target_peak": 0.78,
        "reverb": {
            "wet": 0.12,
            "decay": 2.2,
            "predelay_ms": 25,
            "brightness": 0.3
        }
    },
    "keystone": {
        "midis": [
            33,
            36,
            40,
            45,
            49,
            52
        ],
        "pans": [
            -0.15,
            0.15,
            0
        ],
        "target_peak": 0.8,
        "reverb": {
            "wet": 0.16,
            "decay": 2.2,
            "predelay_ms": 25,
            "brightness": 0.42
        }
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
        lg = math.cos((pan + 1) * math.pi / 4)
        rg = math.sin((pan + 1) * math.pi / 4)
        st = st.copy(); st[:, 0] *= 2 * lg; st[:, 1] *= 2 * rg
    write_wav(path, st, target_peak=target_peak)


def render_voice(name):
    fn = globals()["voice_" + name]
    spec = PLAN[name]
    rv = _voice_reverb(name)
    (OUT / name).mkdir(parents=True, exist_ok=True)
    pans = spec["pans"]
    for i, m in enumerate(spec["midis"]):
        _render(fn(m), rv, pans[i % len(pans)], spec["target_peak"],
                OUT / name / f"{i:02d}_m{m}.wav")
    print("daybreak:", name)


def gen_all():
    OUT.mkdir(exist_ok=True)
    for name in PLAN:
        render_voice(name)
    print("done.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        OUT.mkdir(exist_ok=True)
        for v in sys.argv[1:]:
            if v in PLAN:
                render_voice(v)
            else:
                print("unknown voice:", v)
    else:
        gen_all()
