#!/usr/bin/env python3
"""
Claudio Symphony — sample generator.

Implements the SONIC_FRAMEWORK voice palette as pre-rendered WAV files.
Pure numpy (no scipy). A=432 Hz, A Lydian, just-intoned drone bed,
equal-tempered upper voices, FFT-convolved synthetic-IR reverb tail.

Run once:  python3 synth.py
"""
import os, math, wave
from pathlib import Path
import numpy as np

SR = 44100
HERE = Path(__file__).resolve().parent
# CLAUDIO_SAMPLES_DIR lets `presets/cathedral/render.py` redirect output
# into its own samples/ folder. Falls back to the project-root samples/ dir.
SAMPLES = Path(os.environ["CLAUDIO_SAMPLES_DIR"]) if os.environ.get("CLAUDIO_SAMPLES_DIR") else (HERE / "samples")

# A = 432 Hz tuning. Equal-tempered upper voices off this root.
A4 = 432.0
def freq(midi):
    return A4 * (2 ** ((midi - 69) / 12.0))

# Just-intoned drone fundamentals (frame says strict 3:2 between root and 5th)
F_A1 = A4 / 8.0          # 54.0
F_A2 = A4 / 4.0          # 108.0
F_E3 = F_A2 * 1.5        # 162.0  (perfect fifth, just)

# ---------- helpers ----------

def t_axis(seconds):
    return np.arange(int(seconds * SR)) / SR

def adsr(n, a, d, s_level, r, hold=0.0):
    a_n = max(1, int(a * SR)); d_n = max(1, int(d * SR))
    h_n = max(0, int(hold * SR)); r_n = max(1, int(r * SR))
    env = np.zeros(n); i = 0
    seg = min(a_n, n - i); env[i:i+seg] = np.linspace(0, 1, seg, endpoint=False); i += seg
    if i >= n: return env
    seg = min(d_n, n - i); env[i:i+seg] = np.linspace(1, s_level, seg, endpoint=False); i += seg
    if i >= n: return env
    seg = min(h_n, n - i); env[i:i+seg] = s_level; i += seg
    if i >= n: return env
    seg = min(r_n, n - i); env[i:i+seg] = np.linspace(s_level, 0, seg, endpoint=True)
    return env

def soft_clip(x, drive=1.0):
    return np.tanh(x * drive)

def lowpass_fft(x, cutoff_hz, order=4):
    """FFT-based smooth lowpass — Butterworth-ish magnitude rolloff."""
    N = len(x)
    if N == 0: return x
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(N, d=1.0/SR)
    mask = 1.0 / (1.0 + (freqs / max(cutoff_hz, 1.0))**(2*order))
    return np.fft.irfft(X * mask, N)

# ---------- Synthetic-IR reverb (FFT convolution) ----------

_IR_CACHE = {}

def make_ir(decay_s=6.0, predelay_ms=40, brightness=0.4):
    """Synthetic stereo IR: noise * exponential decay, gentle low-pass."""
    key = (round(decay_s,2), predelay_ms, round(brightness,2))
    if key in _IR_CACHE:
        return _IR_CACHE[key]
    rng = np.random.default_rng(2026)
    pre = int(predelay_ms * SR / 1000)
    n = int(decay_s * SR) + pre
    t = np.arange(n) / SR
    decay_curve = np.exp(-(np.maximum(t - predelay_ms/1000, 0)) / (decay_s * 0.3))
    decay_curve[:pre] = 0.0
    L = rng.standard_normal(n) * decay_curve
    R = rng.standard_normal(n) * decay_curve
    # warmth
    cutoff = 800 + brightness * 5000
    L = lowpass_fft(L, cutoff, order=2)
    R = lowpass_fft(R, cutoff, order=2)
    # tame DC and ultra-low rumble
    L = L - lowpass_fft(L, 80, order=2)
    R = R - lowpass_fft(R, 80, order=2)
    # normalize energy
    s = max(np.max(np.abs(L)), np.max(np.abs(R)))
    if s > 0:
        L /= s; R /= s
    _IR_CACHE[key] = (L, R)
    return L, R

def fft_convolve(a, b):
    n = len(a) + len(b) - 1
    N = 1 << (n - 1).bit_length()
    A = np.fft.rfft(a, N)
    B = np.fft.rfft(b, N)
    return np.fft.irfft(A * B, N)[:n]

def reverb_stereo(mono, wet=0.45, decay_s=6.0, predelay_ms=40, brightness=0.4):
    """mono in → stereo wet+dry mix. Output length = mono + IR - 1.
    For wet ≤ 0.02, skip the convolution entirely and return a dry stereo
    replicate — saves time and gives a truly clean dry signal for voices
    that should sound 'in the room' (wood taps, breath, bird chirps)."""
    if wet <= 0.02:
        return np.stack([mono, mono], axis=1)
    irL, irR = make_ir(decay_s, predelay_ms, brightness)
    wetL = fft_convolve(mono, irL)
    wetR = fft_convolve(mono, irR)
    n_out = len(wetL)
    dry = np.zeros(n_out)
    dry[:len(mono)] = mono
    L = dry * (1-wet) + wetL * wet * 0.7
    R = dry * (1-wet) + wetR * wet * 0.7
    return np.stack([L, R], axis=1)

# ---------- voices (return mono, then voice→stereo handles spatial) ----------

def voice_pluck(midi):
    f = freq(midi); dur = 4.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        1.00 * np.sin(2*np.pi*f*t) +
        0.30 * np.sin(2*np.pi*f*2*t) * np.exp(-t*4) +
        0.12 * np.sin(2*np.pi*f*3*t) * np.exp(-t*6) +
        0.08 * np.sin(2*np.pi*f*5*t) * np.exp(-t*9) +
        0.05 * np.sin(2*np.pi*f*1.005*t)
    )
    env = adsr(n, a=0.02, d=1.5, s_level=0.0, r=3.0)
    out = sig[:env.size] * env[:sig.size] * 0.55
    return out

def voice_bell(midi, dur=8.0, inharm=None):
    """Additive bell — replaces the previous FM bell which had a buzzy
    synth-bell character. Real bells get their color from inharmonic
    partials with independent decay rates, not from modulation.

    The `inharm` parameter is kept for backward compat but ignored — the
    inharmonicity is now implicit in the partial ratios (2.005, 2.76, 4.5)."""
    f = freq(midi)
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t)              * np.exp(-t*0.55) +   # fundamental — slow
        0.50 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*0.95) +   # stretched octave
        0.22 * np.sin(2*np.pi*f*2.76*t)  * np.exp(-t*2.2) +    # inharmonic bell color
        0.07 * np.sin(2*np.pi*f*4.50*t)  * np.exp(-t*4.0)      # high glass shimmer
    )
    sig += 0.18 * np.sin(2*np.pi*f*1.003*t) * np.exp(-t*0.75)
    env = adsr(n, a=0.018, d=6.0, s_level=0.0, r=0.5)
    out = sig[:env.size] * env[:sig.size] * 0.45
    return out

def voice_harmonic(midi):
    f = freq(midi); dur = 6.0
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t) +
        0.6 * np.sin(2*np.pi*f*2*t) +
        0.2 * np.sin(2*np.pi*f*3*t) +
        0.05 * np.sin(2*np.pi*f*4*t)
    )
    vib = 1 + 0.003 * np.sin(2*np.pi*5.5*t)
    sig = sig * vib
    env = adsr(n, a=0.2, d=2.0, s_level=0.3, r=4.0)
    out = sig[:env.size] * env[:sig.size] * 0.38
    return out

def voice_breath(seed):
    rng = np.random.default_rng(seed)
    dur = 2.5; n = int(dur * SR)
    noise = rng.standard_normal(n)
    lp1 = lowpass_fft(noise, 600.0, order=2)
    bp = noise - lp1
    bp = lowpass_fft(bp, 2400.0, order=2)
    env = adsr(n, a=0.15, d=0.6, s_level=0.4, r=1.5)
    return bp * env * 0.32

def voice_shimmer(midi):
    """Tiny high airy ping. Pure sine + a very brief glass partial — no
    FM (FM at high pitches is piercing). The partial decays in ~30 ms so
    you only hear it as the 'tinkle' at attack."""
    f = freq(midi); dur = 1.5
    n = int(dur * SR); t = t_axis(dur)
    sig = (
        np.sin(2*np.pi*f*t) +
        0.25 * np.sin(2*np.pi*f*2.005*t) * np.exp(-t*30)
    )
    env = adsr(n, a=0.005, d=0.4, s_level=0.0, r=0.6)
    return sig[:env.size] * env[:sig.size] * 0.20

def voice_sparkle(seed):
    rng = np.random.default_rng(seed)
    pitches = [81, 85, 88, 90, 93]
    chosen = rng.choice(pitches, size=4, replace=False)
    n = int(6.0 * SR)
    out = np.zeros(n + int(6*SR))
    for i, m in enumerate(chosen):
        offset = int((0.05 + i*0.18 + rng.uniform(0, 0.05)) * SR)
        bell = voice_bell(int(m), dur=4.0)
        end = offset + bell.size
        if end > out.size: bell = bell[:out.size - offset]; end = out.size
        out[offset:end] += bell * 0.55
    return out

def voice_pad(chord_midis):
    dur = 14.0; n = int(dur * SR); t = t_axis(dur)
    sig = np.zeros(n)
    for m in chord_midis:
        f = freq(m)
        partials = np.zeros(n)
        for h in range(1, 7):
            partials += (1.0/h) * np.sin(2*np.pi*f*h*t)
        partials *= 0.4
        sine = np.sin(2*np.pi*f*t)
        det = np.sin(2*np.pi*f*1.004*t)
        sig += 0.7*sine + 0.5*det + 0.4*partials
    sig /= max(1, len(chord_midis))
    sig = lowpass_fft(sig, 1200.0, order=3)
    env = adsr(n, a=4.0, d=0.5, s_level=0.85, hold=2.0, r=8.0)
    return sig[:env.size] * env[:sig.size] * 0.45

def voice_drone(loop_seconds=60.0):
    t = t_axis(loop_seconds)
    sig = (
        0.7 * np.sin(2*np.pi*F_A1*t) +
        0.55 * np.sin(2*np.pi*F_A2*t) +
        0.4 * np.sin(2*np.pi*F_E3*t) +
        0.10 * np.sin(2*np.pi*F_A2*2*t) +
        0.06 * np.sin(2*np.pi*F_E3*2*t) +
        0.04 * np.sin(2*np.pi*F_A2*3*t)
    )
    # Slow filter LFO: split spectrum, modulate the bright band amplitude.
    lfo = 0.5 + 0.5 * np.sin(2*np.pi*(1.0/90.0)*t)
    low_band = lowpass_fft(sig, 400.0, order=3)
    bright_band = sig - low_band
    out = low_band + bright_band * (0.3 + 0.7 * lfo)

    # seamless loop via half-overlap crossfade between head and tail
    fade_n = int(2.5 * SR)
    seam = (out[:fade_n] + out[-fade_n:]) * 0.5
    out[:fade_n] = seam
    out[-fade_n:] = seam
    out = soft_clip(out * 0.8, 1.0) * 0.55
    return out

# ---------- writers ----------

def to_stereo(mono, pan=0.0):
    pan = float(np.clip(pan, -1.0, 1.0))
    left_g = math.cos((pan + 1) * math.pi / 4)
    right_g = math.sin((pan + 1) * math.pi / 4)
    return np.stack([mono * left_g, mono * right_g], axis=1)

FADE_IN_S = 0.0004    # ~18 samples: kills the DC-step click on hard attacks
FADE_OUT_S = 0.005    # 5 ms: no click when a tail is truncated mid-wave

def edge_fades(s, fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S):
    """Short linear fade-in/out so a one-shot starts and ends at zero."""
    n = s.shape[0]
    fi = min(n // 2, int(fade_in_s * SR))
    fo = min(n // 2, int(fade_out_s * SR))
    if fi <= 0 and fo <= 0:
        return s
    s = np.array(s, dtype=np.float64, copy=True)
    shape = (-1,) + (1,) * (s.ndim - 1)
    if fi > 0:
        s[:fi] *= np.linspace(0.0, 1.0, fi, endpoint=False).reshape(shape)
    if fo > 0:
        s[-fo:] *= np.linspace(1.0, 0.0, fo).reshape(shape)
    return s

def write_wav(path, stereo, target_peak=0.85, loop=False):
    """Normalize + write 16-bit stereo. One-shots get edge fades (no clicks on
    drum hits / truncated tails); `loop=True` (drone beds) skips them so the
    clip still wraps seamlessly."""
    s = stereo
    peak = float(np.max(np.abs(s)))
    if peak > 1e-6:
        s = s * min(1.0, target_peak / peak)
    if not loop:
        s = edge_fades(s)
    s_int = (s * 32767.0).astype(np.int16)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(s_int.tobytes())

# ---------- generation plan ----------

def render_with_reverb(mono, wet, decay, predelay_ms, brightness, pan=0.0):
    st = reverb_stereo(mono, wet=wet, decay_s=decay,
                       predelay_ms=predelay_ms, brightness=brightness)
    if pan != 0.0:
        # constant-power re-pan of stereo: scale L/R independently
        pan = float(np.clip(pan, -1.0, 1.0))
        lg = math.cos((pan + 1) * math.pi / 4)
        rg = math.sin((pan + 1) * math.pi / 4)
        # blend toward chosen side
        st = st.copy()
        st[:,0] *= 2*lg
        st[:,1] *= 2*rg
    return st

def gen_all():
    SAMPLES.mkdir(exist_ok=True)
    for sub in ("pluck","bell","harmonic","breath","shimmer","sparkle","pad"):
        (SAMPLES / sub).mkdir(exist_ok=True)

    print("[drone] generating 60s loop...")
    drone = voice_drone(60.0)
    haas = int(0.012 * SR)
    L = drone
    # circular Haas delay: the R channel's head is the loop's own tail, so the
    # clip wraps with no silent gap / step on the right side
    R = np.roll(drone, haas) * 0.95
    write_wav(SAMPLES / "drone.wav", np.stack([L, R], axis=1), target_peak=0.7,
              loop=True)

    # Reverb taste: plucked melodic voices get LIGHT reverb so they feel
    # present rather than washy. Sustained voices (pad, sparkle) keep more
    # tail. Atmospheric voices (breath, shimmer) get less than before.
    pluck_midis = [57, 59, 61, 63, 64, 66, 68, 69]   # A3..A4
    for i, m in enumerate(pluck_midis):
        print(f"[pluck] m{m}...")
        pan = 0.25 if i % 2 == 0 else -0.25
        st = render_with_reverb(voice_pluck(m), wet=0.20, decay=3.0,
                                predelay_ms=30, brightness=0.45, pan=pan)
        write_wav(SAMPLES / "pluck" / f"{i:02d}_m{m}.wav", st, target_peak=0.85)

    bell_midis = [69, 73, 76, 78, 81]
    for i, m in enumerate(bell_midis):
        print(f"[bell] m{m}...")
        st = render_with_reverb(voice_bell(m), wet=0.42, decay=5.0,
                                predelay_ms=70, brightness=0.5, pan=-0.2)
        write_wav(SAMPLES / "bell" / f"{i:02d}_m{m}.wav", st, target_peak=0.78)

    harm_midis = [69, 71, 73, 76, 78]
    for i, m in enumerate(harm_midis):
        print(f"[harmonic] m{m}...")
        st = render_with_reverb(voice_harmonic(m), wet=0.28, decay=3.5,
                                predelay_ms=40, brightness=0.4, pan=+0.2)
        write_wav(SAMPLES / "harmonic" / f"{i:02d}_m{m}.wav", st, target_peak=0.80)

    # breath should sound LIKE breath, not like breath in a cave: near-dry.
    for i in range(4):
        print(f"[breath] {i}...")
        L = voice_breath(seed=i)
        R = voice_breath(seed=i + 100)
        m = min(L.size, R.size)
        sr = reverb_stereo(L[:m], wet=0.10, decay_s=2.0,
                           predelay_ms=15, brightness=0.3)
        write_wav(SAMPLES / "breath" / f"{i:02d}.wav", sr, target_peak=0.60)

    shim_midis = [81, 85, 88, 90]
    for i, m in enumerate(shim_midis):
        print(f"[shimmer] m{m}...")
        pan = (-0.6, -0.3, 0.3, 0.6)[i]
        st = render_with_reverb(voice_shimmer(m), wet=0.40, decay=3.0,
                                predelay_ms=20, brightness=0.7, pan=pan)
        write_wav(SAMPLES / "shimmer" / f"{i:02d}_m{m}.wav", st, target_peak=0.55)

    for i in range(3):
        print(f"[sparkle] {i}...")
        st = render_with_reverb(voice_sparkle(seed=42+i), wet=0.50, decay=5.0,
                                predelay_ms=50, brightness=0.6, pan=0.0)
        write_wav(SAMPLES / "sparkle" / f"{i:02d}.wav", st, target_peak=0.72)

    # Pad voicings — Stop/SessionEnd/PreCompact rotate through these.
    # First three are A-rooted variants (root, sus2-flavored, A maj triad with
    # added 6 and 9). Fourth is a first-inversion arrangement so closing pads
    # occasionally land on a less-final voicing — feels like the work isn't
    # over so much as resting.
    chords = [
        [69, 76, 71],         # A4 E5 B4 — open, two stacked fifths
        [69, 73, 76],         # A4 C#5 E5 — root-position triad, the home
        [69, 75, 78, 81],     # A4 D#5 F#5 A5 — Lydian color (raised 4)
        [73, 76, 81, 83],     # C#5 E5 A5 B5 — first inversion + 9 (floating)
    ]
    for i, c in enumerate(chords):
        print(f"[pad] {i} {c}...")
        st = render_with_reverb(voice_pad(c), wet=0.5, decay=6.0,
                                predelay_ms=40, brightness=0.4, pan=0.0)
        write_wav(SAMPLES / "pad" / f"{i:02d}.wav", st, target_peak=0.78)

    print("done.")

if __name__ == "__main__":
    gen_all()
