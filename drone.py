#!/usr/bin/env python3
"""
Claudio Symphony — preset-aware drone player.

Reads the active preset; if preset.drone is null, exits cleanly (no drone).
Otherwise loops the preset's drone WAV via the detected audio backend
(audio.py) until idle-timeout.
Single-instance via PID file.
"""
import os, sys, time, signal, wave
from pathlib import Path

def _root_offset(cfg):
    """Global live transpose in semitones off A, clamped to a tritone — mirrors
    event.root_offset so the drone bed follows the same re-key as the voices."""
    try: n = int(round(float(cfg.get("root_offset", 0) or 0)))
    except (TypeError, ValueError): return 0
    return max(-6, min(6, n))

def _drone_semis(cfg):
    """Effective drone transpose: the live root_offset, plus — when the user
    opts in with config `drone_chords` — the current chord's root, so the bed
    walks the progression instead of holding the A pedal. Clamped to ±9 so a
    stacked shift never warps the bed beyond recognition."""
    off = _root_offset(cfg)
    if cfg.get("drone_chords"):
        try:
            progression = cfg.get("progression") or {}
            _, label = music.chord_step(progression)
            chord = music.CHORDS.get(label)
            if progression.get("enabled") and chord:
                off += ((int(chord[1]) - 9 + 6) % 12) - 6   # nearest move off A
        except Exception:
            pass
    return max(-9, min(9, off))

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audio  # noqa: E402  (cross-platform playback backend)
import config_store  # noqa: E402
import music  # noqa: E402
import paths  # noqa: E402
import preset_store  # noqa: E402
PRESETS = paths.BUILTIN_PRESETS_DIR
STATE = paths.STATE_DIR
LOGS = paths.LOG_DIR
CONFIG = paths.CONFIG_FILE
PID_FILE = STATE / "drone.pid"
ACTIVE_PRESET_FILE = STATE / "drone-preset.txt"
HEARTBEAT_FILE = STATE / "heartbeat"
LOG_FILE = LOGS / "drone.log"
STOP_SENTINEL = STATE / "drone.stop"   # cooperative stop (Windows has no SIGTERM handler)
STATE.mkdir(exist_ok=True); LOGS.mkdir(exist_ok=True)

IDLE_TIMEOUT_S = 10 * 60   # exit after 10 min of no events
LOOP_LEAD_S = 0.02         # spawn the next pass this far before the clip ends

def log(msg):
    try:
        with LOG_FILE.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass

def read_config():
    return config_store.load(CONFIG)

def active_preset_name():
    return config_store.active_preset(CONFIG)

def load_preset(name):
    return preset_store.load(name, None)

def existing_pid_alive():
    if not PID_FILE.exists(): return None
    try: pid = int(PID_FILE.read_text().strip())
    except Exception: return None
    return pid if audio.pid_alive(pid) else None

def write_pid():
    PID_FILE.write_text(str(os.getpid()))

def claim_pid():
    """Atomically take the single-instance slot (O_CREAT|O_EXCL), replacing
    the pid file only when the pid it records is dead. Returns None on success,
    else the live owner's pid (or -1 when another drone is mid-claim)."""
    for _ in range(3):
        try:
            fd = os.open(str(PID_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                raw = PID_FILE.read_text().strip()
                age = time.time() - PID_FILE.stat().st_mtime
            except FileNotFoundError:
                continue                          # owner just left; retry
            except Exception:
                raw, age = "", 999.0
            try:
                pid = int(raw)
            except ValueError:
                if age < 2.0:
                    return -1                     # a peer created it, not yet written
                pid = None
            if pid and pid != os.getpid() and audio.pid_alive(pid):
                return pid
            try:
                PID_FILE.unlink()                 # stale: dead owner
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return None
    return -1

def wav_seconds(path):
    """Clip length from the WAV header (None if unreadable)."""
    try:
        with wave.open(str(path), "rb") as w:
            fr = w.getframerate()
            return (w.getnframes() / float(fr)) if fr else None
    except Exception:
        return None

def cleanup_pid():
    try:
        if PID_FILE.exists() and int(PID_FILE.read_text().strip()) == os.getpid():
            PID_FILE.unlink()
    except Exception:
        pass

def heartbeat_age():
    try:
        return time.time() - float(HEARTBEAT_FILE.read_text().strip())
    except Exception:
        return None

def main():
    name = active_preset_name()
    preset = load_preset(name)
    if preset is None:
        log(f"preset {name} missing; exiting")
        sys.exit(1)

    drone_file = preset.get("drone")
    if not drone_file:
        log(f"preset {name} has no drone; exiting cleanly")
        print(f"preset '{name}' has no continuous drone; nothing to play.", file=sys.stderr)
        sys.exit(0)

    drone_path = preset_store.sample_asset(name, drone_file)
    if not drone_path.exists():
        log(f"drone file missing: {drone_path}")
        sys.exit(1)

    existing = claim_pid()
    if existing is not None:
        log(f"already running pid={existing}, exiting")
        print(f"drone already running pid={existing}", file=sys.stderr)
        sys.exit(1)
    ACTIVE_PRESET_FILE.write_text(name)

    if not HEARTBEAT_FILE.exists():
        HEARTBEAT_FILE.write_text(str(time.time()))

    try:
        if STOP_SENTINEL.exists(): STOP_SENTINEL.unlink()
    except Exception:
        pass

    def shutdown(*_):
        log("shutdown signal")
        cleanup_pid()
        sys.exit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if audio.get_backend().name == "null":
        log("no audio backend available; exiting (not spinning)")
        cleanup_pid()
        sys.exit(1)

    cfg = read_config()
    drone_gain = float(cfg.get("drone_gain", preset.get("drone_gain", 0.45)))
    log(f"drone start preset={name} pid={os.getpid()} gain={drone_gain} "
        f"backend={audio.get_backend().name}")

    def should_exit(cfg=None):
        age = heartbeat_age()
        if age is not None and age > IDLE_TIMEOUT_S:
            log(f"idle {age:.0f}s, exiting"); return True
        if STOP_SENTINEL.exists():
            log("stop sentinel; exiting"); return True
        try:
            if (cfg if cfg is not None else read_config()).get("muted"):
                log("muted; exiting"); return True
        except Exception:
            pass
        # If user switched presets while drone running, exit so
        # `claudio start` can re-spawn for the new preset.
        try:
            if ACTIVE_PRESET_FILE.read_text().strip() != active_preset_name():
                log("preset changed; exiting"); return True
        except Exception:
            pass
        return False

    clip_s = wav_seconds(drone_path)
    cur, prev = None, None          # prev: the pass we just handed off from
    try:
        cur_off, cur_gain, cur_end = None, None, float("inf")
        while True:
            try:
                cfg = read_config()
            except Exception:
                cfg = {}
            if should_exit(cfg):
                break
            try:
                gain = float(cfg.get("drone_gain", preset.get("drone_gain", 0.45)))
                off = _drone_semis(cfg)
                rate = (2 ** (off / 12.0)) if off else None
                clip_len = (clip_s / (rate or 1.0)) if clip_s else None
                now = time.monotonic()
                if (cur is None or cur.poll() is not None
                        or now >= cur_end - LOOP_LEAD_S):
                    # clip (nearly) ended, or first pass: start the next pass a
                    # hair BEFORE the current one runs out, so there is no
                    # spawn-latency gap at the loop seam.
                    nxt = audio.drone_play_start(drone_path, gain, rate)
                    if nxt is None:
                        # winsound/null backend: no live retune possible —
                        # fall back to the original blocking loop-per-clip.
                        code = audio.drone_play_once(drone_path, gain, rate)
                        if code == 127:
                            log("backend unavailable; exiting"); break
                        continue
                    prev, cur = cur, nxt     # prev finishes its last ~20 ms
                    cur_off, cur_gain = off, gain
                    cur_end = time.monotonic() + clip_len if clip_len else float("inf")
                elif off != cur_off or abs(gain - cur_gain) > 1e-3:
                    # The root moved (mic-jam, `claudio root`, or a chord
                    # change with drone_chords on) or the drone-gain slider
                    # moved: apply it NOW, not at the next loop. Overlap the
                    # new player briefly so the swap reads as the bed bending,
                    # not cutting.
                    if off != cur_off:
                        log(f"retune {cur_off:+d} → {off:+d} semis")
                    nxt = audio.drone_play_start(drone_path, gain, rate)
                    if nxt is not None:
                        started = time.monotonic()
                        time.sleep(0.35)
                        try: cur.terminate()
                        except Exception: pass
                        cur, cur_off, cur_gain = nxt, off, gain
                        cur_end = started + clip_len if clip_len else float("inf")
                # watcher cadence: ~½s root response, but wake just in time
                # to hand off to the next pass
                remaining = cur_end - LOOP_LEAD_S - time.monotonic()
                time.sleep(max(0.005, min(0.5, remaining)))
            except Exception as e:
                log(f"player error: {e}")
                time.sleep(2)
    finally:
        # also reached via SIGTERM → sys.exit(): never leave a player behind
        for p in (cur, prev):
            if p is not None:
                try: p.terminate()
                except Exception: pass
        cleanup_pid()
        try:
            if STOP_SENTINEL.exists(): STOP_SENTINEL.unlink()
        except Exception:
            pass
        log("drone stop")

if __name__ == "__main__":
    main()
