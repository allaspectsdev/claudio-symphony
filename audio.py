#!/usr/bin/env python3
"""
Claudio Symphony — cross-platform audio backend.

The SINGLE place in the project that knows what OS it is on, which player to
spawn, how to detach a process so it outlives a 1-second hook, how to defer a
launch, and how to stop audio. Every other file imports from here and never
names `afplay` / `/bin/sh` / `pkill` / `start_new_session` / `/usr/bin/open` /
`/usr/bin/env` again.

Design goals, in priority order:
  1. ZERO regression on macOS. The afplay argv and the detached `sh -c
     "sleep N; exec ..."` delay trampoline are preserved byte-for-byte, so a
     mac user hears exactly what they heard before.
  2. The event hook stays instant. Claudio installs its hook with
     `"timeout": 1`, and the README promises hooks "never slow Claude down".
     So delayed/echoed plays are launched in DETACHED helper processes that
     outlive the hook (a `/bin/sh` sleep-trampoline on macOS+Linux, a detached
     Python sleep-trampoline on Windows) — never an in-process timer the hook
     would have to block on.
  3. Graceful degradation. Pick the most capable player present; fall back
     down a per-OS priority list; reproduce afplay's `-r` pitch shift via an
     offline numpy pre-render on players that can't resample; and when a
     capability is simply unavailable (e.g. no per-shot volume on `aplay`, no
     overlap on `winsound`), do the best possible thing and log it once.

Hard deps: stdlib only. numpy is imported LAZILY and only for the pitch-shift
pre-render fallback (it is already a project dependency). Players (afplay,
ffplay, mpv, sox, pw-play, paplay, aplay, PowerShell, winsound) are discovered
at runtime via shutil.which — this module never pip/winget-installs anything.

The chosen backend is detected once and cached. Override with CLAUDIO_PLAYER.
"""
import os
import sys
import math
import json
import time
import shlex
import shutil
import hashlib
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, List
import stateio

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
LOGS = HERE / "logs"
CACHE_DIR = STATE / "rate_cache"          # numpy pre-render cache (under gitignored state/)
PLAYERS_FILE = STATE / "players.json"     # persisted PIDs for cross-process stop_all
AUDIO_LOG = LOGS / "audio.log"
REC_ACTIVE = STATE / "recording" / "active.json"   # presence = a `claudio record` window is open
REC_EVENTS = STATE / "recording" / "events.jsonl"  # one line per captured sound (record.py mixes these)
try:
    STATE.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
except Exception:
    pass

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

if IS_WIN:
    try:
        import winsound  # stdlib, Windows only
    except Exception:
        winsound = None
else:
    winsound = None

# How long a persisted PID is considered "could still be playing" and thus a
# valid kill target. Sample plays are short; the drone refreshes its record
# every loop. Anything older is assumed dead — this bounds the (already small)
# risk of terminating an unrelated process that reused a recycled PID.
_STOP_FRESHNESS_S = 120.0


def _log(msg: str) -> None:
    try:
        with AUDIO_LOG.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


_LOG_ONCE: set = set()


def _log_once(key: str, msg: str) -> None:
    if key not in _LOG_ONCE:
        _LOG_ONCE.add(key)
        _log(msg)


# ----------------------------------------------------------------------------
# Backend descriptor
# ----------------------------------------------------------------------------
@dataclass
class Backend:
    name: str                       # afplay|ffplay|mpv|play|pw-play|paplay|
                                    #   aplay|mediaplayer|winsound|null
    kind: str                       # "argv" | "winsound" | "powershell" | "null"
    exe: Optional[str] = None       # resolved executable (argv / powershell)
    can_volume: bool = False        # supports per-shot linear gain
    can_pitch: bool = False         # supports afplay -r style resample natively
    can_overlap: bool = True        # multiple concurrent plays mix at the OS layer
    image_name: str = ""            # process image for image-name kill (no extension)
    build_argv: Optional[Callable] = field(default=None, repr=False)
    # build_argv(path:str, gain:float, rate:Optional[float]) -> List[str]


_BACKEND: Optional[Backend] = None


# ----------------------------------------------------------------------------
# WAV sample-rate read (asetrate is relative to the source rate; never hardcode)
# ----------------------------------------------------------------------------
_sr_cache: dict = {}


def _wav_rate(path) -> int:
    p = str(path)
    if p not in _sr_cache:
        try:
            import wave
            with wave.open(p, "rb") as w:
                _sr_cache[p] = w.getframerate()
        except Exception:
            _sr_cache[p] = 44100
    return _sr_cache[p]


# ----------------------------------------------------------------------------
# Per-backend argv builders. `gain` is linear 0..1 (afplay -v semantics);
# `rate` is the playback multiplier (afplay -r), or None for native rate.
# ----------------------------------------------------------------------------
def _argv_afplay(exe):
    def build(path, gain, rate):
        cmd = [exe, "-v", f"{gain:.3f}"]
        if rate is not None:
            cmd += ["-r", f"{rate:.5f}"]
        cmd.append(path)
        return cmd
    return build


def _argv_ffplay(exe):
    def build(path, gain, rate):
        af = [f"volume={gain:.4f}"]
        if rate is not None:
            sr = _wav_rate(path)
            # asetrate reinterprets the samples at a new rate (tape-style
            # varispeed: pitch AND speed shift together, exactly like afplay
            # -r); aresample brings the stream back to the device rate without
            # undoing that.
            af.append(f"asetrate={int(round(sr * rate))}")
            af.append(f"aresample={sr}")
        return [exe, "-nodisp", "-autoexit", "-loglevel", "quiet",
                "-af", ",".join(af), path]
    return build


def _argv_mpv(exe):
    def build(path, gain, rate):
        cmd = [exe, "--no-video", "--really-quiet", f"--volume={gain * 100:.1f}"]
        if rate is not None:
            cmd += ["--audio-pitch-correction=no", f"--speed={rate:.5f}"]
        cmd.append(path)
        return cmd
    return build


def _argv_sox_play(exe):
    # sox `play`: global -v (gain) BEFORE the filename; `speed` effect AFTER.
    def build(path, gain, rate):
        cmd = [exe, "-q", "-v", f"{gain:.3f}", path]
        if rate is not None:
            cmd += ["speed", f"{rate:.5f}"]
        return cmd
    return build


def _argv_pwplay(exe):
    # pw-play (PipeWire): linear --volume 0..1; no pitch -> numpy pre-render.
    def build(path, gain, rate):
        return [exe, f"--volume={gain:.4f}", path]
    return build


def _argv_paplay(exe):
    # paplay (PulseAudio): --volume on a 0..65536 scale; no pitch -> pre-render.
    def build(path, gain, rate):
        return [exe, f"--volume={int(round(gain * 65536))}", path]
    return build


def _argv_aplay(exe):
    # aplay (ALSA): no volume, no pitch. Gain (and pitch) baked via numpy.
    def build(path, gain, rate):
        return [exe, "-q", path]
    return build


# ----------------------------------------------------------------------------
# Detection / priority
# ----------------------------------------------------------------------------
def _bundled_ffplay():
    """Allow a self-contained ffplay drop-in next to the package (bin/)."""
    cand = HERE / "bin" / ("ffplay.exe" if IS_WIN else "ffplay")
    return str(cand) if cand.exists() else None


def _mk(name, exe, can_volume, can_pitch, can_overlap, image_name, builder):
    return Backend(name=name, kind="argv", exe=exe, can_volume=can_volume,
                   can_pitch=can_pitch, can_overlap=can_overlap,
                   image_name=image_name, build_argv=builder)


def _try_name(name) -> Optional[Backend]:
    if name == "afplay":
        exe = shutil.which("afplay") or ("/usr/bin/afplay"
                                         if Path("/usr/bin/afplay").exists() else None)
        if exe:
            return _mk("afplay", exe, True, True, True, "afplay", _argv_afplay(exe))
    if name == "ffplay":
        exe = _bundled_ffplay() or shutil.which("ffplay")
        if exe:
            return _mk("ffplay", exe, True, True, True, "ffplay", _argv_ffplay(exe))
    if name == "mpv":
        exe = shutil.which("mpv")
        if exe:
            return _mk("mpv", exe, True, True, True, "mpv", _argv_mpv(exe))
    if name in ("play", "sox"):
        exe = shutil.which("play")
        if exe:
            return _mk("play", exe, True, True, True, "play", _argv_sox_play(exe))
    if name == "pw-play":
        exe = shutil.which("pw-play")
        if exe:
            return _mk("pw-play", exe, True, False, True, "pw-play", _argv_pwplay(exe))
    if name == "paplay":
        exe = shutil.which("paplay")
        if exe:
            return _mk("paplay", exe, True, False, True, "paplay", _argv_paplay(exe))
    if name == "aplay":
        exe = shutil.which("aplay")
        if exe:
            return _mk("aplay", exe, False, False, False, "aplay", _argv_aplay(exe))
    if name == "mediaplayer" and IS_WIN:
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if exe:
            return Backend(name="mediaplayer", kind="powershell", exe=exe,
                           can_volume=True, can_pitch=False, can_overlap=True,
                           image_name="")   # never image-kill the shell itself
    if name == "winsound" and winsound is not None:
        return Backend(name="winsound", kind="winsound",
                       can_volume=False, can_pitch=False, can_overlap=False,
                       image_name="")
    return None


def _detect() -> Backend:
    forced = os.environ.get("CLAUDIO_PLAYER", "").strip().lower()
    if forced:
        b = _try_name(forced)
        if b:
            return b
        _log(f"CLAUDIO_PLAYER={forced!r} not available; auto-detecting")

    if IS_MAC:
        order = ["afplay", "ffplay", "mpv", "play"]
    elif IS_LINUX:
        order = ["ffplay", "mpv", "play", "pw-play", "paplay", "aplay"]
    elif IS_WIN:
        order = ["ffplay", "mpv", "mediaplayer", "winsound"]
    else:
        order = ["ffplay", "mpv", "play"]

    for name in order:
        b = _try_name(name)
        if b:
            return b
    return Backend(name="null", kind="null")


def get_backend() -> Backend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _detect()
        _log(f"backend={_BACKEND.name} volume={_BACKEND.can_volume} "
             f"pitch={_BACKEND.can_pitch} overlap={_BACKEND.can_overlap}")
    return _BACKEND


# ----------------------------------------------------------------------------
# numpy varispeed pre-render (pitch + optional gain bake) for players that
# can't resample. Reproduces afplay -r exactly: a naive linear-interpolated
# resample => pitch AND duration shift together. The cache key buckets the rate
# to 1 cent so per-note jitter doesn't explode the cache.
# ----------------------------------------------------------------------------
def _prerender(path, rate, bake_gain=None) -> Optional[str]:
    try:
        import numpy as np
    except Exception:
        _log_once("nonumpy", "numpy unavailable; cannot pre-render pitch shift")
        return None
    try:
        import wave
        cents = int(round(1200 * math.log2(rate))) if rate and rate > 0 else 0
        gtag = "" if bake_gain is None else f"{bake_gain:.3f}"
        key = hashlib.sha1(f"{path}:{cents}:{gtag}".encode()).hexdigest()[:16]
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out = CACHE_DIR / f"{key}.wav"
        if out.exists():
            return str(out)
        with wave.open(str(path), "rb") as w:
            nch, sw, sr, nframes = (w.getnchannels(), w.getsampwidth(),
                                    w.getframerate(), w.getnframes())
            raw = w.readframes(nframes)
        if sw != 2:                       # fallback only supports 16-bit PCM
            return None
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if nch > 1:
            data = data.reshape(-1, nch)
        ratio = 2 ** (cents / 1200.0)     # the bucketed rate actually rendered
        n_in = data.shape[0]
        if n_in < 2:
            return None
        idx = np.arange(0, n_in - 1, ratio, dtype=np.float64)
        lo = np.floor(idx).astype(np.int64)
        frac = (idx - lo).astype(np.float32)
        if nch > 1:
            frac = frac[:, None]
        buf = data[lo] * (1 - frac) + data[lo + 1] * frac
        if bake_gain is not None:
            buf = buf * float(bake_gain)
        buf = np.clip(buf, -32768, 32767).astype(np.int16)
        with wave.open(str(out), "wb") as wo:
            wo.setnchannels(nch)
            wo.setsampwidth(2)
            wo.setframerate(sr)
            wo.writeframes(buf.tobytes())
        return str(out)
    except Exception as e:
        _log_once("prerender_fail", f"pre-render failed: {e}")
        return None


# ----------------------------------------------------------------------------
# Detach + spawn + PID tracking
# ----------------------------------------------------------------------------
def _detach_kwargs():
    if IS_WIN:
        return {"creationflags": (subprocess.DETACHED_PROCESS
                                  | subprocess.CREATE_NEW_PROCESS_GROUP
                                  | subprocess.CREATE_NO_WINDOW)}
    return {"start_new_session": True}


_LIVE: List[subprocess.Popen] = []          # same-process registry (precise)
_LIVE_LOCK = threading.Lock()


def _write_players(data) -> None:
    """Serialize and atomically replace the cross-process PID registry."""
    try:
        stateio.save_json(PLAYERS_FILE, data, indent=None, newline=False)
    except Exception:
        pass


def _persist_pid(pid: int, tag: str) -> None:
    """Record a spawned player's PID so a DIFFERENT process (e.g. `claudio
    off`) can stop it — event-hook players are separate processes from the CLI."""
    try:
        rec = {"pid": pid, "tag": tag, "ts": time.time(),
               "image": get_backend().image_name}
        def mutate(data):
            if not isinstance(data, list):
                data = []
            data.append(rec)
            return data[-256:]
        stateio.update_json(PLAYERS_FILE, [], mutate, indent=None, newline=False)
    except Exception:
        pass


def _track(p: subprocess.Popen, tag: str) -> None:
    with _LIVE_LOCK:
        _LIVE[:] = [q for q in _LIVE if q.poll() is None]
        _LIVE.append(p)
    if p and p.pid:
        _persist_pid(p.pid, tag)


def _env_posix_numeric():
    """ffmpeg/sox parse `asetrate=44100*..` with the locale decimal separator;
    pin LC_NUMERIC=C so comma-decimal locales don't mangle our floats."""
    if IS_WIN:
        return None
    env = os.environ.copy()
    env["LC_NUMERIC"] = "C"
    return env


def _popen(argv, *, tag="note") -> Optional[subprocess.Popen]:
    """Spawn a detached player and track it. Never blocks."""
    kw = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              stdin=subprocess.DEVNULL, close_fds=True)
    env = _env_posix_numeric()
    if env is not None:
        kw["env"] = env
    kw.update(_detach_kwargs())
    try:
        p = subprocess.Popen(argv, **kw)
    except Exception as e:
        _log_once(f"spawn_{get_backend().name}", f"launch failed: {e}")
        return None
    _track(p, tag)
    return p


def _delayed_argv(argv, delay_s):
    """Wrap a player argv so it launches `delay_s` later, in a detached helper
    that outlives this (≤1s) process — preserving the original macOS trampoline
    and giving Linux the identical mechanism (both have /bin/sh)."""
    if IS_WIN:
        # No /bin/sh on Windows: a tiny detached Python launcher sleeps, then
        # spawns the player and exits (the player keeps running on its own).
        # The inner spawn gets the SAME detach + redirect flags as _popen so
        # the player never inherits the (short-lived) hook's handles.
        return [sys.executable, "-c",
                "import time,subprocess,sys;time.sleep(float(sys.argv[1]));"
                "subprocess.Popen(sys.argv[2:],"
                "creationflags=subprocess.DETACHED_PROCESS"
                "|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW,"
                "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
                "stderr=subprocess.DEVNULL,close_fds=True)",
                f"{delay_s:.4f}", *argv]
    quoted = " ".join(shlex.quote(c) for c in argv)
    return ["/bin/sh", "-c", f"sleep {delay_s:.4f}; exec {quoted}"]


def _resolve_src(path, gain, rate):
    """Apply numpy pre-render where the backend can't do volume/pitch natively.
    Returns (src_path, effective_gain, effective_rate) for the argv builder."""
    be = get_backend()
    src, eff_rate = str(path), rate
    if rate is not None and not be.can_pitch:
        pr = _prerender(path, rate, bake_gain=None if be.can_volume else gain)
        if pr:
            src, eff_rate = pr, None
        else:
            _log_once(f"nopitch_{be.name}",
                      f"{be.name}: pitch shift unavailable; playing native pitch")
            eff_rate = None
    elif (not be.can_volume) and gain < 0.999:
        pr = _prerender(path, 1.0, bake_gain=gain)
        if pr:
            src = pr
    eff_gain = 1.0 if not be.can_volume else gain
    return src, eff_gain, eff_rate


def _rec_capture(path, gain, rate, delay_s, tag):
    """If a `claudio record` window is open, append this play to the recording
    timeline (record.py mixes the actual sample WAVs back onto a timeline — no
    system-audio capture needed). Only musical `tag="note"` plays are captured
    (hook events, jukebox, session replay) — previews/drone are excluded, exactly
    as when event.play() owned the spawn. One cheap stat in the common case."""
    if tag != "note":
        return
    try:
        if not REC_ACTIVE.exists():
            return
        m = json.loads(REC_ACTIVE.read_text())
        start, duration = float(m["start"]), float(m["duration"])
    except Exception:
        return
    t_play = (time.time() - start) + delay_s
    if not (0.0 <= t_play <= duration):
        return
    try:
        line = json.dumps({"t": round(t_play, 4), "wav": str(path),
                           "v": round(float(gain), 4), "r": round(float(rate or 1.0), 5)})
        with REC_EVENTS.open("a") as f:        # O_APPEND of a sub-PIPE_BUF line is atomic
            f.write(line + "\n")
    except Exception:
        pass


def _spawn_one(path, gain, rate, delay_s, tag, block=False):
    """Launch ONE play (dry hit or a single echo tap). Returns the player's
    Popen for the subprocess-based backends (or None for null/winsound/launch
    failure). `block=True` is used ONLY by the drone loop: it makes winsound
    play synchronously (SND_SYNC) so the loop doesn't re-fire over itself. The
    note/echo/preview paths always pass block=False to stay instant."""
    _rec_capture(path, gain, rate, delay_s, tag)   # mix into an open recording, if any
    be = get_backend()
    if be.kind == "null":
        _log_once("null", "no audio backend found; playback is silent")
        return None

    if be.kind == "winsound":
        src = str(path)
        if (gain < 0.999) or (rate is not None):
            pr = _prerender(path, rate or 1.0,
                            bake_gain=gain if gain < 0.999 else None)
            if pr:
                src = pr
        if delay_s > 0.005:
            _log_once("winsound_delay",
                      "winsound: deferred/quantized timing is approximate")
        try:
            sync = winsound.SND_SYNC if block else winsound.SND_ASYNC
            winsound.PlaySound(src, winsound.SND_FILENAME | sync)
        except Exception as e:
            _log_once("winsound_fail", f"winsound failed: {e}")
        return None   # winsound has no child process to track/wait on

    if be.kind == "powershell":
        src = str(path)
        if rate is not None:
            pr = _prerender(path, rate)
            if pr:
                src = pr
            else:
                _log_once("ps_pitch", "MediaPlayer: pitch unavailable; native pitch")
        g = max(0.0, min(1.0, gain))
        sleep_ms = int(round(delay_s * 1000)) if delay_s > 0.005 else 0
        psrc = src.replace("'", "''")       # PowerShell single-quote escaping
        ps = (
            (f"Start-Sleep -Milliseconds {sleep_ms};" if sleep_ms else "") +
            "Add-Type -AssemblyName presentationCore;"
            "$p=New-Object System.Windows.Media.MediaPlayer;"
            f"try{{$p.Open([uri]'{psrc}')}}catch{{exit 1}};$p.Volume={g};$p.Play();"
            # Bounded poll for duration metadata (~5s cap) so a bad file can
            # never leave a PowerShell process spinning forever.
            "$i=0;while(-not $p.NaturalDuration.HasTimeSpan -and $i -lt 250)"
            "{Start-Sleep -Milliseconds 20;$i++};"
            "if($p.NaturalDuration.HasTimeSpan)"
            "{Start-Sleep -Seconds ([double]$p.NaturalDuration.TimeSpan.TotalSeconds)};"
            "$p.Stop();$p.Close()"
        )
        argv = [be.exe, "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps]
        return _popen(argv, tag=tag)   # the PS process blocks for the clip itself

    # ---- argv backends (afplay/ffplay/mpv/sox/pw-play/paplay/aplay) ----
    src, eff_gain, eff_rate = _resolve_src(path, gain, rate)
    argv = be.build_argv(src, eff_gain, eff_rate)
    if delay_s > 0.005:
        argv = _delayed_argv(argv, delay_s)
    return _popen(argv, tag=tag)


# ----------------------------------------------------------------------------
# PUBLIC API
# ----------------------------------------------------------------------------
def play(sample_path, gain_linear, shift_semitones=0, delay_s=0.0,
         rate_jitter=False, echo=None, tag="note"):
    """Drop-in replacement for the old event.play(): identical signature and
    musical semantics. Computes the playback rate from semitones/jitter (the
    exact math from the original), then fires a dry hit plus a geometric echo
    fan-out — each as its own DETACHED play, deferred via a sleep-trampoline so
    this process can return immediately (honoring the 1s hook timeout)."""
    if sample_path is None:
        return
    import random
    v = max(0.0, min(1.0, gain_linear))
    base_rate = 2 ** (shift_semitones / 12.0) if shift_semitones else 1.0
    if rate_jitter:
        base_rate *= 1.0 + random.uniform(-0.004, 0.004)
    rate = max(0.25, min(4.0, base_rate)) if (shift_semitones or rate_jitter) else None

    _spawn_one(sample_path, v, rate, delay_s, tag)

    if echo and isinstance(echo, dict):
        if not get_backend().can_overlap:
            _log_once("noecho", f"{get_backend().name}: no overlap; echo taps skipped")
            return
        ms = max(40, min(2000, int(echo.get("ms", 320))))
        fb = max(0.0, min(0.85, float(echo.get("feedback", 0.30))))
        count = max(0, min(8, int(echo.get("count", 3))))
        for i in range(1, count + 1):
            eg = v * (fb ** i)
            if eg < 0.005:
                break
            _spawn_one(sample_path, eg, rate, delay_s + (ms / 1000.0) * i, tag)


def play_simple(sample_path, gain_linear, tag="preview"):
    """Plain immediate one-shot preview (CLI / web / TUI voice auditions)."""
    if sample_path is None:
        return
    _spawn_one(sample_path, max(0.0, min(1.0, gain_linear)), None, 0.0, tag)


def drone_play_start(sample_path, gain_linear, rate=None):
    """Non-blocking drone spawn: start one tagged drone player and return its
    Popen (None on winsound/null backends — callers fall back to the blocking
    drone_play_once there). Lets drone.py watch for live root/chord changes
    mid-clip and retune by overlapping a new player and retiring this one."""
    be = get_backend()
    if be.kind in ("null", "winsound"):
        return None
    return _spawn_one(sample_path, max(0.0, min(1.0, gain_linear)), rate, 0.0,
                      "drone", block=True)


def drone_play_once(sample_path, gain_linear, rate=None) -> int:
    """Blocking single play for drone.py's loop. Spawns the player tracked
    (tag='drone') so stop_drone() can target exactly this player across
    processes, then waits for it. `rate` (playback multiplier) lets the drone
    follow a live root transpose so it stays consonant with the re-keyed
    voices. Returns 0 normally, 127 if no backend."""
    be = get_backend()
    if be.kind == "null":
        return 127
    # block=True: winsound plays synchronously; the others return a Popen we
    # wait on. Either way the call blocks for the clip's duration, so the
    # drone loop spaces its iterations correctly on every OS.
    p = _spawn_one(sample_path, max(0.0, min(1.0, gain_linear)), rate, 0.0,
                   "drone", block=True)
    if p is not None:
        try:
            p.wait()
        except Exception:
            pass
    elif be.kind != "winsound":
        return 127   # argv/powershell launch failed (winsound returns None ok)
    return 0


def _fresh(rec) -> bool:
    try:
        return (time.time() - float(rec.get("ts", 0))) <= _STOP_FRESHNESS_S
    except Exception:
        return False


def _stop(tag: Optional[str]) -> None:
    be = get_backend()
    # 1) same-process registry (precise)
    with _LIVE_LOCK:
        for p in list(_LIVE):
            try:
                p.terminate()
            except Exception:
                pass
        _LIVE[:] = [q for q in _LIVE if q.poll() is None]
    # 2) persisted PIDs (cross-process: `claudio off` vs hook-spawned players)
    try:
        if PLAYERS_FILE.exists():
            def mutate(data):
                keep = []
                for rec in data if isinstance(data, list) else []:
                    if (tag is None or rec.get("tag") == tag) and _fresh(rec):
                        terminate_pid(rec.get("pid"))
                    elif tag is not None and rec.get("tag") != tag and _fresh(rec):
                        keep.append(rec)
                return keep
            stateio.update_json(PLAYERS_FILE, [], mutate, indent=None, newline=False)
    except Exception:
        pass
    # 3) image-name sweep for OUR dedicated player binary (belt & suspenders).
    #    ONLY on stop_all (tag is None). A tagged stop (e.g. stop_drone) already
    #    killed its tracked PIDs in step 2; a broad image/winsound sweep here would
    #    also cut unrelated in-flight plays (notes still ringing) — the old
    #    `pkill -f 'afplay .*drone.wav'` was drone-specific, so this preserves that.
    #    Never image-kill shared/generic names (sox `play`, `powershell`).
    if tag is not None:
        return
    if be.kind == "winsound":
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        return
    if be.image_name in ("ffplay", "afplay", "mpv", "pw-play", "paplay", "aplay"):
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/IM", be.image_name + ".exe"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        elif shutil.which("pkill"):
            subprocess.run(["pkill", "-f", be.image_name], check=False)


def stop_all() -> None:
    """Replaces `pkill -f afplay`: stop every player this family spawned."""
    _stop(tag=None)


def stop_drone() -> None:
    """Replaces `pkill -f 'afplay .*drone.wav'`: stop only drone players."""
    _stop(tag="drone")


# ----------------------------------------------------------------------------
# Process-control + interpreter + browser helpers (the non-audio POSIX-isms)
# ----------------------------------------------------------------------------
def pid_alive(pid) -> bool:
    """Portable replacement for os.kill(pid, 0)."""
    if pid is None:
        return False
    if IS_WIN:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                                 capture_output=True, text=True)
            return str(int(pid)) in out.stdout
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False


def terminate_pid(pid) -> None:
    """Portable replacement for os.kill(pid, SIGTERM)."""
    if pid is None:
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
        return
    import signal as _sig
    try:
        os.kill(int(pid), _sig.SIGTERM)
    except (OSError, ValueError):
        pass


def spawn_python(script, args=(), *, detached=False, stdin_bytes=None,
                 capture=False, cwd=None, log_file=None, timeout=None):
    """Replaces every ['/usr/bin/env','python3', ...] spawn: uses the running
    interpreter (sys.executable) and platform-correct detaching."""
    argv = [sys.executable, str(script), *map(str, args)]
    if detached:
        kw = dict(stdin=subprocess.DEVNULL, close_fds=True)
        fh = None
        if log_file is not None:
            # Accept a path (we own its lifecycle) or an already-open handle.
            fh = open(log_file, "a") if isinstance(log_file, (str, Path)) else log_file
            kw["stdout"] = fh
            kw["stderr"] = subprocess.STDOUT
        else:
            kw["stdout"] = subprocess.DEVNULL
            kw["stderr"] = subprocess.DEVNULL
        kw.update(_detach_kwargs())
        p = subprocess.Popen(argv, **kw)
        if fh is not None and isinstance(log_file, (str, Path)):
            fh.close()   # the child inherited the fd; the parent doesn't need it
        return p
    if stdin_bytes is not None:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             cwd=cwd)
        try:
            p.communicate(stdin_bytes, timeout=timeout)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        return p
    return subprocess.run(argv, cwd=cwd, check=False,
                          stdout=(None if capture else subprocess.DEVNULL),
                          stderr=(None if capture else subprocess.DEVNULL))


def exec_python(script, args=()):
    """Replaces os.execvp('/usr/bin/env', ...). On POSIX, truly exec for a clean
    tty handoff (curses); on Windows, spawn-wait-exit (no real exec)."""
    argv = [sys.executable, str(script), *map(str, args)]
    if IS_WIN:
        r = subprocess.run(argv)
        sys.exit(r.returncode)
    os.execv(sys.executable, argv)


def open_url(url) -> None:
    """Replaces ['/usr/bin/open', url] — webbrowser picks the right opener
    (open / xdg-open / start) per OS."""
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass


def install_check():
    """For install.py. Returns (ok: bool, fatal_if_missing: bool, message)."""
    be = get_backend()
    if be.name == "null":
        return (False, IS_MAC, "no audio player found")
    caps = (f"volume={'Y' if be.can_volume else 'n'} "
            f"pitch={'Y' if be.can_pitch else 'n'} "
            f"overlap={'Y' if be.can_overlap else 'n'}")
    note = ""
    if be.kind == "winsound":
        note = " (no volume/pitch/overlap — basic blips; install ffmpeg for full quality)"
    elif not be.can_pitch:
        note = " (pitch via numpy pre-render; song-mode micro-tuning works)"
    return (True, False, f"{be.name} ✓ [{caps}]{note}")
