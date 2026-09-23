#!/usr/bin/env python3
"""
Claudio Symphony — workflow recorder.

Claudio already knows every sound it plays: event.py funnels each afplay
through one spawn. So we don't capture system audio (which would need a virtual
audio device) — instead, while a recording window is open, event.py appends one
line per sound to state/recording/events.jsonl (wav, gain, pitch-rate, play
time). When the window closes we mix the *actual* sample WAVs back onto a
timeline here. Clean (only Claudio, no mic/room noise), deterministic, no deps
beyond numpy — and numpy lives ONLY here, never in the event hot-path.

Usage (also driven by cli.py and the web UI):
  python3 record.py run [seconds]   # foreground: record, then mix + save
  python3 record.py stop            # signal a running recorder to finish now
"""
import os, sys, json, time, wave, signal, subprocess
from pathlib import Path
import numpy as np
import audio
import paths
import preset_store

HERE = Path(__file__).resolve().parent
STATE = paths.STATE_DIR
REC_DIR = STATE / "recording"
ACTIVE = REC_DIR / "active.json"
EVENTS = REC_DIR / "events.jsonl"
# Cooperative stop (like drone.stop): the recorder polls for this file and
# finalizes itself. Hard-killing it (taskkill /F on Windows) skipped finalize()
# and leaked active.json, so the UI said "already recording" forever.
STOP_SENTINEL = REC_DIR / "stop"
STOP_WAIT_S = 3.0
OUT_DIR = paths.RECORDINGS_DIR

SR = 44100
DEFAULT_SECS = 30
MAX_SECS = 300          # 5 minutes
TAIL_S = 8.0            # let the last sounds ring out past the window

# Optional drone bed baked into a recording. The live/daily drone stays OFF;
# this is purely a "give the clip some body" option that fades in and out so
# the take feels like one cohesive piece. cathedral's A root-fifth drone is the
# bed (every preset is A-rooted at 432 Hz, so it sits under any of them).
DRONE_REC_GAIN = 0.32
DRONE_FADE_IN = 3.0
DRONE_FADE_OUT = 5.0
DRONE_SRC = preset_store.sample_asset("cathedral", "drone.wav")

# ---------- recording lifecycle (no numpy needed) ----------

def load_active():
    try:
        return json.loads(ACTIVE.read_text())
    except Exception:
        return None

def _clear_stop():
    try:
        STOP_SENTINEL.unlink()
    except Exception:
        pass

def _heal_stale(meta=None):
    """If active.json names a recorder process that is gone (crashed, killed,
    machine slept through it), salvage the take and clear the window. Returns
    the still-live meta, or None when nothing is (any longer) recording."""
    meta = meta if meta is not None else load_active()
    if not meta:
        return None
    pid = meta.get("pid")
    if pid and not audio.pid_alive(pid):
        try:
            finalize()                  # best effort: mix what was captured
        except Exception:
            pass
        try:
            ACTIVE.unlink()
        except Exception:
            pass
        _clear_stop()
        return None
    return meta

def is_active():
    return _heal_stale() is not None

def start(duration, src="cli", pid=None, drone=False, drone_gain=DRONE_REC_GAIN):
    duration = max(1, min(MAX_SECS, int(duration)))
    REC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    _heal_stale()                        # a dead recorder's leftovers never block us
    _clear_stop()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    meta = {"start": time.time(), "duration": duration,
            "out": f"claudio-{stamp}",
            "pid": int(pid if pid is not None else os.getpid()), "src": src,
            "drone": bool(drone), "drone_gain": float(drone_gain)}
    EVENTS.write_text("")            # truncate any previous capture
    ACTIVE.write_text(json.dumps(meta))
    return meta

def _wait_gone(pid, secs):
    """Poll until the recorder has claimed finalize (active.json removed)."""
    deadline = time.time() + secs
    while time.time() < deadline:
        if not ACTIVE.exists():
            return True
        if pid and not audio.pid_alive(pid):
            return not ACTIVE.exists()
        time.sleep(0.1)
    return not ACTIVE.exists()

def stop(wait=STOP_WAIT_S):
    """Ask a running recorder to finalize early. Cooperative first: write the
    stop sentinel and give the recorder a few seconds to mix + save itself.
    Only if it doesn't respond is it terminated, and we finalize on its
    behalf. Returns the recording's meta, or None when nothing was recording."""
    meta = load_active()
    if not meta:
        return None
    pid = meta.get("pid")
    if pid and pid != os.getpid() and audio.pid_alive(pid):
        try:
            REC_DIR.mkdir(parents=True, exist_ok=True)
            STOP_SENTINEL.write_text("1")
        except Exception:
            pass
        if _wait_gone(pid, wait):
            return meta                # the recorder is finalizing its own take
        audio.terminate_pid(pid)       # unresponsive: fall back to terminate
        _wait_gone(pid, 1.0)           # (POSIX SIGTERM still finalizes in-process)
    if ACTIVE.exists():
        finalize()                     # recorder gone — mix it ourselves
    _clear_stop()
    return meta

def request_stop(wait=STOP_WAIT_S):
    """Web/CLI entry point: stop the current recording gracefully.
    True if a recording was stopped (or is now finalizing), False if none."""
    return stop(wait=wait) is not None

def _event_count():
    try:
        with EVENTS.open() as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def list_recordings():
    if not OUT_DIR.exists():
        return []
    out = []
    for p in sorted(OUT_DIR.glob("*"), reverse=True):
        if p.suffix in (".wav", ".m4a"):
            out.append({"name": p.name, "size": p.stat().st_size})
    return out

def status():
    meta = _heal_stale()
    out = {"active": bool(meta), "recordings": list_recordings(),
           "max": MAX_SECS, "default": DEFAULT_SECS}
    if meta:
        elapsed = time.time() - meta["start"]
        out.update(remaining=max(0.0, round(meta["duration"] - elapsed, 1)),
                   duration=meta["duration"], events=_event_count(),
                   out=meta["out"])
    return out

# ---------- mixing (numpy) ----------

_wav_cache = {}

def _read_wav(path):
    """Load a sample as float32 stereo at SR. Cached. Resolves relative paths to HERE."""
    if path in _wav_cache:
        return _wav_cache[path]
    p = Path(path)
    if not p.is_absolute():
        p = HERE / p
    data = np.zeros((1, 2), dtype=np.float32)
    try:
        w = wave.open(str(p), "rb")
        n, ch, sw, fr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
        w.close()
        if sw == 2 and n > 0:
            a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            a = np.stack([a, a], axis=1) if ch == 1 else a.reshape(-1, ch)[:, :2]
            if fr != SR and a.shape[0] > 1:    # samples are 44.1k, but be safe
                idx = np.arange(0, a.shape[0], fr / SR)
                base = np.arange(a.shape[0])
                a = np.stack([np.interp(idx, base, a[:, c]) for c in range(2)], axis=1)
            data = a
    except Exception:
        pass
    _wav_cache[path] = data
    return data

def _rate_shift(a, r):
    """Emulate afplay -r: play the sample r× faster (pitch + speed scale by r)."""
    if abs(r - 1.0) < 1e-4 or a.shape[0] < 2:
        return a
    new_len = max(1, int(a.shape[0] / r))
    idx = np.arange(new_len) * r
    base = np.arange(a.shape[0])
    return np.stack([np.interp(idx, base, a[:, c]) for c in range(2)], axis=1)

def _drone_bed(n, gain):
    """Stereo drone bed of length n samples, faded in/out. None if unavailable."""
    if n <= 0:
        return None
    bed = None
    if DRONE_SRC.exists():
        a = _read_wav(str(DRONE_SRC))          # stereo float @ SR (seamless 60s loop)
        if a.shape[0] >= 2:
            reps = int(np.ceil(n / a.shape[0]))
            bed = np.tile(a, (reps, 1))[:n].astype(np.float32)
    if bed is None:                            # fallback: synthesize the A root-fifth drone
        try:
            import synth
            d = np.asarray(synth.voice_drone(max(1.0, n / SR)), dtype=np.float32)
            if d.shape[0] < n:
                d = np.pad(d, (0, n - d.shape[0]))
            bed = np.stack([d[:n], d[:n]], axis=1)
        except Exception:
            return None
    dur_s = n / SR
    fi = int(min(DRONE_FADE_IN, dur_s / 2) * SR)
    fo = int(min(DRONE_FADE_OUT, dur_s / 2) * SR)
    env = np.ones(n, dtype=np.float32)
    if fi > 1:
        env[:fi] = np.linspace(0.0, 1.0, fi, dtype=np.float32)
    if fo > 1:
        env[-fo:] = np.linspace(1.0, 0.0, fo, dtype=np.float32)
    return bed * env[:, None] * float(gain)

def _read_events():
    events = []
    if EVENTS.exists():
        for ln in EVENTS.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                events.append(json.loads(ln))
            except Exception:
                pass
    return events

def mix(duration, out_basename, drone=False, drone_gain=DRONE_REC_GAIN):
    events = _read_events()
    total_n = int((duration + TAIL_S) * SR)
    buf = np.zeros((total_n, 2), dtype=np.float32)
    used = 0
    for e in events:
        t = float(e.get("t", 0.0))
        if t < 0 or t > duration:
            continue
        a = _read_wav(e.get("wav", ""))
        if a.shape[0] < 2:
            continue
        a = _rate_shift(a, float(e.get("r", 1.0))) * float(e.get("v", 0.0))
        s = int(t * SR)
        end = min(total_n, s + a.shape[0])
        if end <= s:
            continue
        buf[s:end] += a[:end - s]
        used += 1
    # final length: cover the window, plus any captured-sound tail ringing past it
    nz = np.where(np.max(np.abs(buf), axis=1) > 1e-4)[0]
    end_n = int(duration * SR)
    if len(nz):
        end_n = max(end_n, min(total_n, int(nz[-1]) + SR))
    buf = buf[:end_n]
    # optional drone bed under the whole clip, faded in/out for a cohesive feel
    droned = False
    if drone:
        bed = _drone_bed(end_n, drone_gain)
        if bed is not None:
            buf += bed
            droned = True
    # gentle peak guard (afplay sums at the system mixer and can clip; we don't)
    peak = float(np.max(np.abs(buf))) if buf.size else 0.0
    if peak > 0.99:
        buf *= (0.985 / peak)

    OUT_DIR.mkdir(exist_ok=True)
    wav_path = OUT_DIR / f"{out_basename}.wav"
    pcm = (np.clip(buf, -1.0, 1.0) * 32767.0).astype("<i2")
    w = wave.open(str(wav_path), "wb")
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes()); w.close()

    m4a_path = _to_m4a(wav_path)
    return {"wav": str(wav_path),
            "m4a": (str(m4a_path) if m4a_path else None),
            "events": used, "seconds": round(end_n / SR, 1), "drone": droned}

def _to_m4a(wav_path):
    afconvert = "/usr/bin/afconvert"
    if not os.path.exists(afconvert):
        return None
    m4a = Path(wav_path).with_suffix(".m4a")
    try:
        subprocess.run([afconvert, "-f", "m4af", "-d", "aac", "-b", "128000",
                        str(wav_path), str(m4a)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return m4a if m4a.exists() else None
    except Exception:
        return None

def finalize():
    meta = load_active()
    if not meta:
        return None
    try:
        ACTIVE.unlink()                # claim: only one finalizer mixes a take
    except FileNotFoundError:
        return None
    except Exception:
        pass
    _clear_stop()
    # An early stop yields only what was actually recorded, not the full
    # requested window (mix still adds the captured sounds' ring-out tail).
    try:
        dur = min(float(meta["duration"]),
                  max(1.0, time.time() - float(meta["start"])))
    except Exception:
        dur = float(meta.get("duration", DEFAULT_SECS))
    return mix(dur, meta["out"],
               drone=bool(meta.get("drone")),
               drone_gain=float(meta.get("drone_gain", DRONE_REC_GAIN)))

def run(duration, src="cli", on_progress=None, drone=False, drone_gain=DRONE_REC_GAIN):
    """Foreground: open the window, count down, then mix + save.
    Finalizes on the timer, on SIGINT (Ctrl-C), on the stop sentinel
    (`record stop` / the web UI), or on SIGTERM."""
    meta = start(duration, src=src, pid=os.getpid(), drone=drone, drone_gain=drone_gain)
    flag = {"stop": False}
    def _sig(_signum, _frame):
        flag["stop"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    dur, t0 = meta["duration"], meta["start"]
    while not flag["stop"]:
        elapsed = time.time() - t0
        if elapsed >= dur or STOP_SENTINEL.exists():
            break
        if on_progress:
            on_progress(max(0.0, dur - elapsed), _event_count())
        time.sleep(0.2)
    return finalize()

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "run"
    if arg == "stop":
        stop()
    else:
        drone = "--drone" in sys.argv
        secs = DEFAULT_SECS
        for a in sys.argv[2:]:
            if a.lstrip("-").isdigit():
                secs = int(a)
                break
        run(secs, src="web", drone=drone)
