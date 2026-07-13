#!/usr/bin/env python3
"""
Claudio Symphony — local web UI server (pure stdlib, no deps).

A small threaded HTTP server that serves the browser control panel in web/ and
exposes a tiny JSON API over the SAME files the CLI + hooks use (config.json,
presets/<name>/preset.json, state/). So anything you change here is live, and
the live-activity view reads the very markers event.py touches when Claude works.

Run:  python3 webui.py [--port 8788] [--open]
  or: claudio web
"""
import os, sys, json, time, re, random, secrets, shutil, threading, urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audio  # noqa: E402  (cross-platform playback + process helpers)
import cache_manager  # noqa: E402
import config_store  # noqa: E402
import music  # noqa: E402
import paths  # noqa: E402
import preset_store  # noqa: E402
import stateio  # noqa: E402  (cross-process JSON transactions)
PRESETS = paths.BUILTIN_PRESETS_DIR
STATE = paths.STATE_DIR
CONFIG = paths.CONFIG_FILE
RULES_FILE = paths.RULES_FILE
SESSIONS_FILE = paths.SESSIONS_FILE
EVENT_PY = str(HERE / "event.py")
RECORD_PY = str(HERE / "record.py")
MIDIPLAY_PY = str(HERE / "midiplay.py")
RENDER_WORKER_PY = str(HERE / "render_worker.py")
REC_DIR = STATE / "recording"
REC_ACTIVE = REC_DIR / "active.json"
REC_EVENTS = REC_DIR / "events.jsonl"
OUT_DIR = paths.RECORDINGS_DIR
WEB = paths.WEB_DIR
SR_HINT = 44100
AUTH_COOKIE = "claudio_session"
AUTH_TOKEN = secrets.token_urlsafe(32)
MAX_JSON_BODY = 12 * 1024 * 1024      # enough for a ~9 MB MIDI upload, bounded against memory DoS
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "microphone=(self)",
}

try:
    import song as song_mod
except Exception:
    song_mod = None

try:
    import midiplay as midiplay_mod
except Exception:
    midiplay_mod = None

try:
    import timeline as timeline_mod
except Exception:
    timeline_mod = None

# A-rooted scales (mirrors event.py SCALES keys) — for the global/per-session override.
SCALE_NAMES = list(music.SCALES)

# Chord progressions (mirrors event.py CHORDS keys / PROGRESSIONS).
CHORD_NAMES = list(music.CHORDS)
PROGRESSION_PRESETS = music.PROGRESSIONS

# ---------- json + domain helpers (mirror cli.py, no import side effects) ----------

def load_json(p, default):
    return stateio.load_json(p, default)

def save_json(p, d):
    stateio.save_json(p, d)

def load_config(): return config_store.load(CONFIG)
def save_config(d): return config_store.save(d, CONFIG)
def update_config(mutator): return config_store.update(mutator, CONFIG)
def patch_config(values=None, remove=()):
    def mutate(cfg):
        cfg.update(values or {})
        for key in remove:
            cfg.pop(key, None)
    return update_config(mutate)
def active_preset_name(): return config_store.active_preset(CONFIG)

def list_preset_names():
    return preset_store.list_names()

def safe_child(root, relative):
    """Resolve ``relative`` below ``root`` or return None on traversal."""
    try:
        root = Path(root).resolve()
        candidate = (root / urllib.parse.unquote(str(relative))).resolve()
        candidate.relative_to(root)
        return candidate
    except (OSError, ValueError):
        return None

def preset_path(name, leaf="preset.json"):
    if leaf == "preset.json":
        return preset_store.preset_path(name)
    if leaf == "preset.default.json":
        return preset_store.default_path(name)
    if leaf == "render.py":
        return preset_store.render_path(name)
    directory = preset_store.source_dir(name)
    return safe_child(directory, leaf) if directory else None

def load_preset(name):
    return preset_store.load(name)

def save_preset(name, d):
    return preset_store.save(name, d)

def clamp(x, lo, hi): return max(lo, min(hi, x))

ALL_EVENTS = music.MAPPABLE_EVENTS

# ---------- audio (play on the host, like Claudio itself) ----------

def voice_dir(preset, voice):
    cfg = (load_preset(preset) or {}).get("voices", {}).get(voice, {})
    return preset_store.sample_asset(preset, cfg.get("dir", voice))

def voice_output_dir(preset, voice):
    cfg = (load_preset(preset) or {}).get("voices", {}).get(voice, {})
    base = preset_store.sample_output_dir(preset)
    return safe_child(base, cfg.get("dir", voice)) or (paths.SAMPLES_DIR / "__invalid__")

def samples_in(d):
    return sorted(p for p in d.iterdir() if p.suffix == ".wav") if d.exists() else []

def play_sample(path, gain):
    try:
        audio.play_simple(path, clamp(gain, 0, 1))
        return True
    except Exception:
        return False

def master_gain(preset_obj):
    cfg = load_config()
    m = cfg.get("master_gain")
    return float(m if m is not None else preset_obj.get("master_gain", 0.5))

def play_voice(preset, voice):
    p = load_preset(preset) or {}
    v = p.get("voices", {}).get(voice, {})
    smp = samples_in(voice_dir(preset, voice))
    if not smp: return False
    g = clamp(float(v.get("gain", 0.5)) * master_gain(p), 0, 1)
    return play_sample(random.choice(smp), g)

def regen_voice(preset, voice):
    render = preset_path(preset, "render.py")
    if render is None or not render.exists(): return False, "no render.py for this preset"
    def _run():
        try:
            audio.spawn_python(RENDER_WORKER_PY, [preset, voice], cwd=str(HERE))
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
    return True, "regenerating"

# ---------- state shaping ----------

def preset_card(name):
    p = load_preset(name) or {}
    return {
        "name": name,
        "description": p.get("description", ""),
        "voice_count": len(p.get("voices", {})),
        "scale_len": len(p.get("scale_pitches", []) or []),
        "has_drone": bool(p.get("drone")),
        "master_gain": p.get("master_gain", 0.5),
        "custom": bool(p.get("custom")),
    }

SESSION_TTL = 4 * 3600

def sessions_list():
    d = load_json(STATE / "sessions.json", {}).get("active", {}) or {}
    now = time.time()
    out = []
    for sid, rec in d.items():
        ls = float(rec.get("last_seen", 0) or 0)
        if now - ls > SESSION_TTL:
            continue
        cwd = rec.get("cwd", "") or ""
        base = cwd.rstrip("/").split("/")[-1] if cwd else ""
        out.append({
            "id": sid, "short": (sid[:6] if sid else "—"),
            "cwd": cwd, "base": base or (cwd or "—"),
            "preset": rec.get("preset_resolved"),
            "source": rec.get("preset_source", "?"),
            "pinned": rec.get("preset_pinned"),
            "scale": rec.get("scale_override"),
            "song": rec.get("song_pinned"),
            "age": round(now - ls, 1), "ended": bool(rec.get("ended")),
        })
    out.sort(key=lambda s: s["age"])
    return out

def rules_list():
    return (load_json(RULES_FILE, {"rules": []}) or {}).get("rules", []) or []

def music_state():
    cfg = load_config()
    q = cfg.get("quant") or {}
    songs, gsong = [], None
    if song_mod:
        try:
            songs = [s[0] if isinstance(s, (list, tuple)) else s for s in song_mod.list_songs()]
        except Exception:
            songs = []
        try: gsong = song_mod.global_song()
        except Exception: gsong = None
    off = root_offset_clamped(cfg.get("root_offset", 0))
    prog = cfg.get("progression") or {}
    return {
        "scales": SCALE_NAMES, "scale_global": cfg.get("scale_override"),
        "quant": {"enabled": bool(q.get("enabled")), "bpm": float(q.get("bpm", 120.0)), "grid": float(q.get("grid", 0.5))},
        "songs": songs, "song_global": gsong,
        "root_offset": off, "root_note": root_note_name(off),
        "chords": {"library": CHORD_NAMES, "presets": PROGRESSION_PRESETS,
                   "prog": {"enabled": bool(prog.get("enabled")), "preset": prog.get("preset"),
                            "steps": prog.get("steps") or [], "step_s": float(prog.get("step_s", 8) or 8)}},
    }

# Note names by pitch class; A (pc 9) is Claudio's rendered root (A=432).
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
def root_offset_clamped(v):
    try: n = int(round(float(v or 0)))
    except (TypeError, ValueError): return 0
    return max(-6, min(6, n))
def root_note_name(off):
    return _NOTE_NAMES[(9 + int(off)) % 12]

def fire_test(preset_hint=None):
    """Fire one of each event through event.py (uses the active routing)."""
    seq = [("SessionStart", {}), ("UserPromptSubmit", {}),
           ("PreToolUse", {"tool_name": "Read"}), ("PreToolUse", {"tool_name": "Edit"}),
           ("PostToolUse", {"tool_name": "Bash"}),
           ("PostToolUseFailure", {"tool_name": "Bash", "error": "test failure"}),
           ("SubagentStop", {}),
           ("Stop", {}), ("Notification", {}), ("SessionEnd", {})]
    def _run():
        for name, extra in seq:
            payload = {"hook_event_name": name, "session_id": "webtest", **extra}
            try:
                audio.spawn_python(EVENT_PY, stdin_bytes=json.dumps(payload).encode(),
                                   timeout=3)
            except Exception:
                pass
            time.sleep(1.4)
    threading.Thread(target=_run, daemon=True).start()

def drone_running():
    try:
        pid = int((STATE / "drone.pid").read_text().strip())
        return pid if audio.pid_alive(pid) else None
    except Exception:
        return None

def drone_state(cfg, active):
    p = load_preset(active) or {}
    return {
        "available": bool(p.get("drone")),
        "running": bool(drone_running()),
        "follow_chords": bool(cfg.get("drone_chords")),
        "gain": float(cfg.get("drone_gain", p.get("drone_gain", 0.45))),
    }

def full_state():
    cfg = load_config()
    active = cfg.get("preset", "meadow")
    return {
        "active": active,
        "muted": bool(cfg.get("muted")),
        "master_gain": master_gain(load_preset(active) or {}),
        "drone_gain": float(cfg.get("drone_gain", 0.0)),
        "drone": drone_state(cfg, active),
        "presets": [preset_card(n) for n in list_preset_names()],
        "sessions": sessions_list(),
        "rules": rules_list(),
        "music": music_state(),
    }

# ---------- custom preset builder ----------

# Voice config keys worth carrying when a voice is borrowed from another preset
# (everything but "dir", which we repoint at the copied sample folder).
_CARRY_VOICE_KEYS = ("gain", "mioi", "rate_jitter", "reverb", "delay",
                     "tonal_anchor_midi", "tonal_range")
_RESERVED_NAMES = {"_archive", "samples", "default"}

def build_palette():
    """Every voice from every preset, so the builder can offer any sound."""
    out = []
    for name in list_preset_names():
        p = load_preset(name) or {}
        vs = []
        for vn, vc in (p.get("voices", {}) or {}).items():
            n = len(samples_in(voice_dir(name, vn)))
            if n:
                vs.append({"voice": vn, "gain": vc.get("gain", 0.5), "samples": n})
        if vs:
            out.append({"preset": name, "description": p.get("description", ""), "voices": vs})
    return out

def _slug(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())[:28]

def create_custom_preset(spec):
    name = _slug(spec.get("name", ""))
    if len(name) < 2:
        return {"ok": False, "msg": "name must be at least 2 letters/digits"}
    if name in _RESERVED_NAMES or name in list_preset_names():
        return {"ok": False, "msg": f"'{name}' already exists — pick another name"}
    base = spec.get("base")
    picks = spec.get("voices") or []
    if base and base not in list_preset_names():
        base = None
    if not base and not picks:
        return {"ok": False, "msg": "pick at least one sound (or start from a preset)"}

    target = preset_store.user_dir(name)
    try:
        (target / "samples").mkdir(parents=True, exist_ok=False)
    except Exception:
        return {"ok": False, "msg": "could not create preset folder"}

    try:
        if base:
            preset = load_preset(base) or {}
            preset = json.loads(json.dumps(preset))         # deep copy
            # copy the base's sample folders
            for vn, vc in (preset.get("voices", {}) or {}).items():
                d = vc.get("dir", vn)
                src = preset_store.sample_asset(base, d)
                if src.exists():
                    shutil.copytree(src, target / "samples" / d, dirs_exist_ok=True)
            preset["description"] = spec.get("description") or f"custom · from {base}"
        else:
            preset = {"schema_version": 1, "name": name,
                      "description": spec.get("description") or "custom preset",
                      "master_gain": 0.5, "voices": {}, "events": {}}
        preset["name"] = name
        preset["custom"] = True                          # marks it user-built (deletable/renamable)
        # blank: no scale_pitches → the picker uses each voice's full sample set,
        # which is the safe choice for a mixed bag of borrowed sounds.

        voices = preset.setdefault("voices", {})
        added = []
        for pk in picks:
            sp, sv = pk.get("src_preset"), pk.get("src_voice")
            srcp = load_preset(sp) if sp else None
            if not srcp or sv not in (srcp.get("voices") or {}):
                continue
            svc = srcp["voices"][sv]
            srcdir = voice_dir(sp, sv)
            if not samples_in(srcdir):
                continue
            vn = _slug(pk.get("name") or sv) or sv
            base_vn = vn; i = 2
            while vn in voices:                              # de-dupe voice name
                vn = f"{base_vn}{i}"; i += 1
            shutil.copytree(srcdir, target / "samples" / vn, dirs_exist_ok=True)
            nvc = {k: svc[k] for k in _CARRY_VOICE_KEYS if k in svc}
            nvc["dir"] = vn
            voices[vn] = nvc
            added.append(vn)

        if not voices:
            shutil.rmtree(target, ignore_errors=True)
            return {"ok": False, "msg": "none of the chosen sounds had samples"}

        # event map: keep base's; for a blank preset, auto-spread voices across
        # the 9 events so it makes sound immediately (refine later in the Sounds tab).
        evmap = preset.setdefault("events", {})
        if not base:
            vlist = list(voices.keys())
            for i, ev in enumerate(ALL_EVENTS):
                evmap[ev] = {"default": vlist[i % len(vlist)]}

        preset_store.save(name, preset, save_default=True)   # custom reset baseline
        return {"ok": True, "name": name, "voices": list(voices.keys()), "added": added}
    except Exception as e:
        shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "msg": f"build failed: {e}"}

def _is_custom(name):
    return bool((load_preset(name) or {}).get("custom"))

def delete_custom_preset(name):
    if name not in list_preset_names():
        return {"ok": False, "msg": "not found"}
    if not _is_custom(name):
        return {"ok": False, "msg": "only presets you built can be deleted"}
    # if it's the global default, fall back to meadow
    fallback = "meadow" if load_preset("meadow") else (list_preset_names() or ["meadow"])[0]
    def update_active(cfg):
        if cfg.get("preset") == name:
            cfg["preset"] = fallback
    update_config(update_active)
    # drop references in sessions pins + cwd rules
    try:
        def unpin(sj):
            for rec in (sj.get("active", {}) or {}).values():
                if rec.get("preset_pinned") == name: rec.pop("preset_pinned", None)
        stateio.update_json(SESSIONS_FILE, {"active": {}}, unpin)
    except Exception: pass
    try:
        stateio.update_json(RULES_FILE, {"rules": []},
                            lambda rj: rj.update(rules=[r for r in rj.get("rules", []) if r.get("preset") != name]))
    except Exception: pass
    preset_store.delete_custom(name)
    shutil.rmtree(STATE / name, ignore_errors=True)
    return {"ok": True, "name": name}

def rename_custom_preset(name, to):
    if name not in list_preset_names():
        return {"ok": False, "msg": "not found"}
    if not _is_custom(name):
        return {"ok": False, "msg": "only presets you built can be renamed"}
    to = _slug(to)
    if len(to) < 2:
        return {"ok": False, "msg": "new name must be at least 2 letters/digits"}
    if to == name:
        return {"ok": True, "name": to}
    if to in _RESERVED_NAMES or to in list_preset_names():
        return {"ok": False, "msg": f"'{to}' already exists"}
    try:
        if not preset_store.rename_custom(name, to):
            raise OSError("preset store rejected rename")
    except Exception as e:
        return {"ok": False, "msg": f"rename failed: {e}"}
    if (STATE / name).exists():
        try: (STATE / name).rename(STATE / to)
        except Exception: pass
    def update_active(cfg):
        if cfg.get("preset") == name: cfg["preset"] = to
    update_config(update_active)
    try:
        def repin(sj):
            for rec in (sj.get("active", {}) or {}).values():
                if rec.get("preset_pinned") == name: rec["preset_pinned"] = to
        stateio.update_json(SESSIONS_FILE, {"active": {}}, repin)
    except Exception: pass
    try:
        def reroute(rj):
            for r in rj.get("rules", []):
                if r.get("preset") == name: r["preset"] = to
        stateio.update_json(RULES_FILE, {"rules": []}, reroute)
    except Exception: pass
    return {"ok": True, "name": to}

def swap_voice_sound(preset, voice, src_preset, src_voice):
    """Replace one voice's underlying samples with another preset's voice — keeps
    the slot's name, level and event mappings, just changes how it sounds."""
    p = load_preset(preset)
    if not p or voice not in (p.get("voices") or {}):
        return {"ok": False, "msg": "voice not found"}
    sp = load_preset(src_preset)
    if not sp or src_voice not in (sp.get("voices") or {}):
        return {"ok": False, "msg": "source sound not found"}
    svc = sp["voices"][src_voice]
    srcdir = voice_dir(src_preset, src_voice)
    if not samples_in(srcdir):
        return {"ok": False, "msg": "source has no samples"}
    cfg = p["voices"][voice]
    vdir = voice_output_dir(preset, voice)
    try:
        vdir.mkdir(parents=True, exist_ok=True)
        for f in vdir.glob("*.wav"):            # clear old sound
            f.unlink()
        for f in samples_in(srcdir):            # copy new sound in (keeps NN_m{midi} pitch names)
            shutil.copy2(f, vdir / f.name)
    except Exception as e:
        return {"ok": False, "msg": f"swap failed: {e}"}
    # carry the sound-describing tonal fields; keep the slot's gain/mioi/reverb/delay
    for k in ("tonal_anchor_midi", "tonal_range"):
        if k in svc: cfg[k] = svc[k]
        else: cfg.pop(k, None)
    save_preset(preset, p)
    return {"ok": True, "preset": preset, "voice": voice, "from": f"{src_preset}/{src_voice}"}

def preset_detail(name):
    p = load_preset(name)
    if p is None: return None
    voices = []
    for vn, vc in (p.get("voices", {}) or {}).items():
        rv = vc.get("reverb") if isinstance(vc.get("reverb"), dict) else {}
        dl = vc.get("delay") if isinstance(vc.get("delay"), dict) else None
        voices.append({
            "name": vn, "gain": vc.get("gain", 0.5), "mioi": vc.get("mioi", 0.5),
            "rate_jitter": bool(vc.get("rate_jitter")),
            "reverb": {"wet": rv.get("wet", 0.0), "decay": rv.get("decay"),
                       "brightness": rv.get("brightness")},
            "delay": dl, "regenable": bool((preset_path(name, "render.py") or Path()).is_file()),
        })
    # events: always include all 9
    evmap = p.get("events", {}) or {}
    events = []
    for ev in ALL_EVENTS + [e for e in evmap if e not in ALL_EVENTS]:
        spec = evmap.get(ev) or {}
        events.append({
            "event": ev, "default": spec.get("default"),
            "by_tool": spec.get("by_tool") or {},
            "on_failure": spec.get("on_failure", "__none__") if "on_failure" in spec else None,
            "delay": (spec.get("effect") or {}).get("delay"),
        })
    return {
        "name": name, "description": p.get("description", ""),
        "master_gain": p.get("master_gain", 0.5),
        "reverb_scale": p.get("reverb_scale", 1.0),
        "scale_pitches": p.get("scale_pitches", []),
        "voice_names": list((p.get("voices", {}) or {}).keys()),
        "voices": voices, "events": events,
    }

def activity(name):
    if load_preset(name) is None:
        return None
    sd = safe_child(STATE, name) or (STATE / "__invalid__")
    now = time.time()
    def ts(path):
        try: return float(path.read_text().strip())
        except Exception: return 0.0
    def csize(path):
        try: return path.stat().st_size
        except Exception: return 0
    p = load_preset(name) or {}
    voices = {vn: ts(sd / f"last-{vn}.txt") for vn in (p.get("voices", {}) or {})}
    events = {ev: ts(sd / f"evt-{ev}.txt") for ev in ALL_EVENTS}
    counts = {ev: csize(sd / f"cnt-{ev}.bin") for ev in ALL_EVENTS}
    mp = midiplay_mod.status() if midiplay_mod else {"active": False}
    return {"now": now, "muted": bool(load_config().get("muted")),
            "active": active_preset_name(),
            "heartbeat": ts(STATE / "heartbeat"),
            "voices": voices, "events": events, "counts": counts,
            "sessions": sessions_list(), "midiplay": mp}

# ---------- HTTP ----------

CT = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
      ".js": "text/javascript; charset=utf-8", ".json": "application/json",
      ".wav": "audio/wav", ".m4a": "audio/mp4",
      ".svg": "image/svg+xml", ".woff2": "font/woff2"}

class HTTPInputError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message

def record_status():
    out = {"active": False, "recordings": [], "max": 300, "default": 30}
    if OUT_DIR.exists():
        for p in sorted(OUT_DIR.glob("*"), reverse=True):
            kind = "audio" if p.suffix in (".wav", ".m4a") else \
                   "score" if p.name.endswith(".score.json") else None
            if kind:
                out["recordings"].append({
                    "name": p.name, "size": p.stat().st_size, "kind": kind,
                    "url": "/recordings/" + urllib.parse.quote(p.name)})
    try:
        if REC_ACTIVE.exists():
            m = json.loads(REC_ACTIVE.read_text())
            elapsed = time.time() - m["start"]
            events = 0
            try: events = sum(1 for _ in REC_EVENTS.open())
            except Exception: pass
            out.update(active=True, duration=m["duration"], events=events,
                       remaining=max(0.0, round(m["duration"] - elapsed, 1)))
    except Exception:
        pass
    return out

class Handler(BaseHTTPRequestHandler):
    server_version = "ClaudioWeb/1.0"
    def log_message(self, *a): pass  # quiet

    def _common_headers(self):
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def _send(self, code, body, ctype="application/json", set_cookie=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._common_headers()
        if set_cookie:
            self.send_header("Set-Cookie", f"{AUTH_COOKIE}={AUTH_TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        ctype = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise HTTPInputError(415, "Content-Type must be application/json")
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            raise HTTPInputError(400, "invalid Content-Length")
        if n < 0 or n > MAX_JSON_BODY:
            raise HTTPInputError(413, "request body too large")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except (UnicodeDecodeError, ValueError):
            raise HTTPInputError(400, "invalid JSON")
        if not isinstance(body, dict):
            raise HTTPInputError(400, "JSON body must be an object")
        return body

    def _valid_host(self):
        raw = self.headers.get("Host", "")
        try:
            parsed = urllib.parse.urlsplit("//" + raw)
            port = parsed.port or 80
            return parsed.hostname in LOOPBACK_HOSTS and port == self.server.server_port
        except ValueError:
            return False

    def _authorized(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            value = cookie.get(AUTH_COOKIE)
            return value is not None and secrets.compare_digest(value.value, AUTH_TOKEN)
        except Exception:
            return False

    def _origin_allowed(self):
        raw = self.headers.get("Origin")
        if not raw:
            return True     # non-browser clients still need the unguessable cookie
        try:
            origin = urllib.parse.urlsplit(raw)
            return (origin.scheme == "http" and origin.hostname in LOOPBACK_HOSTS
                    and (origin.port or 80) == self.server.server_port)
        except ValueError:
            return False

    def _protected(self, path):
        return path.startswith("/api/") or path.startswith("/recordings/") or path == "/sample"

    def do_OPTIONS(self):
        return self._send(403, {"error": "cross-origin requests are not allowed"})

    # ---- GET ----
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path
        if not self._valid_host():
            return self._send(421, {"error": "invalid Host header"})
        if self._protected(path) and not self._authorized():
            return self._send(403, {"error": "authorization required"})
        if path == "/" or path == "/index.html":
            return self._file(WEB / "index.html", set_cookie=True)
        if path.startswith("/static/"):
            rel = urllib.parse.unquote(path[len("/static/"):])
            f = safe_child(WEB, rel)
            return self._file(f) if f else self._send(404, {"error": "not found"})
        if path == "/api/state":
            return self._send(200, full_state())
        if path == "/api/preset":
            name = (q.get("name") or [active_preset_name()])[0]
            d = preset_detail(name)
            return self._send(200, d) if d else self._send(404, {"error": "not found"})
        if path == "/api/preset/history":
            name = (q.get("name") or [active_preset_name()])[0]
            if load_preset(name) is None:
                return self._send(404, {"error": "not found"})
            entries = [{k: v for k, v in entry.items() if k != "path"}
                       for entry in preset_store.history(name)]
            return self._send(200, {"name": name, "history": entries})
        if path == "/api/preset/export":
            name = (q.get("name") or [active_preset_name()])[0]
            preset = load_preset(name)
            if preset is None:
                return self._send(404, {"error": "not found"})
            return self._send(200, {
                "name": name, "filename": f"{name}.claudio-preset.json", "preset": preset
            })
        if path == "/api/cache":
            return self._send(200, cache_manager.status(CONFIG))
        if path == "/api/activity":
            name = (q.get("name") or [active_preset_name()])[0]
            data = activity(name)
            return self._send(200, data) if data is not None else self._send(404, {"error": "not found"})
        if path == "/api/donate":
            return self._send(200, load_json(HERE / "donate.json", {"methods": []}))
        if path == "/api/palette":
            return self._send(200, {"palette": build_palette()})
        if path == "/api/record/status":
            return self._send(200, record_status())
        if path == "/api/midiplay/status":
            if not midiplay_mod:
                return self._send(200, {"active": False})
            return self._send(200, midiplay_mod.status())
        if path == "/api/midiplay/plan":
            if not midiplay_mod:
                return self._send(200, {"error": "no midiplay module"})
            song = (q.get("song") or [""])[0]
            preset = (q.get("preset") or [active_preset_name()])[0]
            p = midiplay_mod.plan(song, preset)
            return self._send(200, p) if p else self._send(404, {"error": "no plan"})
        if path == "/api/timelines":
            # heavy-traffic sparkline + counts for each active session (rail)
            if not timeline_mod:
                return self._send(200, {})
            out = {}
            for s in sessions_list():
                summ = timeline_mod.summary(s["id"])
                if summ:
                    out[s["id"]] = summ
            return self._send(200, out)
        if path.startswith("/recordings/"):
            fn = urllib.parse.unquote(path[len("/recordings/"):])
            f = safe_child(OUT_DIR, fn)
            if f is None or not f.exists():
                return self._send(404, {"error": "not found"})
            return self._file(f)
        if path == "/sample":
            preset = (q.get("preset") or [active_preset_name()])[0]
            voice = (q.get("voice") or [""])[0]
            smp = samples_in(voice_dir(preset, voice))
            if not smp: return self._send(404, {"error": "no samples"})
            return self._file(random.choice(smp))
        return self._send(404, {"error": "not found"})

    def _file(self, p, set_cookie=False):
        if p is None:
            return self._send(404, {"error": "not found"})
        p = Path(p)
        if not p.exists() or not p.is_file():
            return self._send(404, {"error": "not found"})
        ctype = CT.get(p.suffix, "application/octet-stream")
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._common_headers()
        if set_cookie:
            self.send_header("Set-Cookie", f"{AUTH_COOKIE}={AUTH_TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(data)

    # ---- POST ----
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        if not self._valid_host():
            return self._send(421, {"error": "invalid Host header"})
        if not self._authorized():
            return self._send(403, {"error": "authorization required"})
        if not self._origin_allowed():
            return self._send(403, {"error": "cross-origin request rejected"})
        try:
            b = self._json_body()
        except HTTPInputError as e:
            return self._send(e.status, {"error": e.message})
        try:
            if path == "/api/preset/use":
                name = str(b["name"])
                if load_preset(name) is None:
                    return self._send(400, {"error": "unknown preset"})
                cfg = patch_config({"preset": name})
                return self._send(200, {"ok": True, "active": cfg["preset"]})
            if path == "/api/mute":
                cfg = patch_config({"muted": bool(b.get("muted"))})
                return self._send(200, {"ok": True, "muted": cfg["muted"]})
            if path == "/api/master":
                cfg = patch_config({"master_gain": round(clamp(float(b["gain"]), 0, 1), 3)})
                return self._send(200, {"ok": True, "master_gain": cfg["master_gain"]})
            if path == "/api/drone":
                cfg = patch_config({"drone_gain": round(clamp(float(b["gain"]), 0, 1), 3)})
                return self._send(200, {"ok": True, "drone_gain": cfg["drone_gain"]})
            if path == "/api/drone/start":
                cfg = load_config(); active = cfg.get("preset", "meadow")
                p = load_preset(active) or {}
                if not p.get("drone"):
                    return self._send(200, {"ok": False, "msg": f"'{active}' has no drone"})
                if not drone_running():
                    try: (STATE / "drone.stop").unlink()
                    except Exception: pass
                    audio.spawn_python(str(HERE / "drone.py"), detached=True)
                    time.sleep(0.4)
                return self._send(200, {"ok": True, "drone": drone_state(load_config(), active)})
            if path == "/api/drone/stop":
                pid = drone_running()
                if pid:
                    try:
                        audio.terminate_pid(pid)
                        (STATE / "drone.stop").write_text("1")
                    except Exception: pass
                    time.sleep(0.3)
                audio.stop_drone()        # silence the in-flight player now
                cfg = load_config()
                return self._send(200, {"ok": True, "drone": drone_state(cfg, cfg.get("preset", "meadow"))})
            if path == "/api/drone/follow":
                # drone walks the chord progression's roots instead of holding A
                cfg = patch_config({"drone_chords": bool(b.get("on"))})
                return self._send(200, {"ok": True, "follow_chords": cfg["drone_chords"]})
            if path == "/api/voice":
                return self._voice(b)
            if path == "/api/voice/reverb":
                return self._voice_reverb(b)
            if path == "/api/voice/delay":
                return self._voice_delay(b)
            if path == "/api/voice/play":
                preset = b.get("preset", active_preset_name())
                ok = play_voice(preset, b["voice"])
                return self._send(200, {"ok": ok})
            if path == "/api/map":
                return self._map(b)
            if path == "/api/reverb_scale":
                return self._reverb_scale(b)
            if path == "/api/audition":
                return self._audition(b)
            if path == "/api/session/pin":
                return self._session_set(b, "preset_pinned", b.get("preset"))
            if path == "/api/session/scale":
                return self._session_set(b, "scale_override", b.get("scale"))
            if path == "/api/session/song":
                return self._session_set(b, "song_pinned", b.get("song"))
            if path == "/api/rule/add":
                return self._rule_add(b)
            if path == "/api/rule/rm":
                return self._rule_rm(b)
            if path == "/api/root":
                # Live re-key: set the global transpose off A. Accepts a raw
                # semitone offset, or a pitch class 0..11 (the browser mic-jam
                # mode sends the detected pitch class and we wrap to ±6 so the
                # move is always the nearest enharmonic). null/clear → back to A.
                clear = b.get("clear") or (b.get("offset") is None and b.get("pc") is None)
                if clear:
                    cfg = patch_config(remove=("root_offset",))
                else:
                    if b.get("pc") is not None:
                        # nearest signed distance from A (pc 9), wrapped to [-6,6]
                        off = ((int(b["pc"]) - 9 + 6) % 12) - 6
                    else:
                        off = root_offset_clamped(b.get("offset"))
                    cfg = patch_config({"root_offset": root_offset_clamped(off)})
                o = root_offset_clamped(cfg.get("root_offset", 0))
                return self._send(200, {"ok": True, "root_offset": o, "root_note": root_note_name(o)})
            if path == "/api/chords":
                # Chord progression: a wall-clock cycle of chords that re-pools
                # every voice to the live chord's tones. Body: {preset} to load
                # a shipped progression, {steps:[labels]} for custom, {step_s},
                # {enabled}, or {off:true}.
                def mutate_chords(cfg):
                    prog = cfg.get("progression") or {}
                    if b.get("off"):
                        prog["enabled"] = False
                    else:
                        if b.get("preset") in PROGRESSION_PRESETS:
                            prog["preset"] = b["preset"]
                            prog["steps"] = list(PROGRESSION_PRESETS[b["preset"]])
                            prog["enabled"] = True
                        if isinstance(b.get("steps"), list):
                            steps = [s for s in b["steps"] if s in CHORD_NAMES][:12]
                            if len(steps) >= 2:
                                prog["steps"] = steps; prog["preset"] = "custom"; prog["enabled"] = True
                        if b.get("step_s") is not None:
                            prog["step_s"] = round(clamp(float(b["step_s"]), 2, 60), 1)
                        if "enabled" in b:
                            prog["enabled"] = bool(b["enabled"]) and bool(prog.get("steps"))
                    cfg["progression"] = prog
                cfg = update_config(mutate_chords); prog = cfg.get("progression") or {}
                return self._send(200, {"ok": True, "progression": prog})
            if path == "/api/scale":
                name = b.get("name")
                cfg = patch_config({"scale_override": name}) if name in SCALE_NAMES else patch_config(remove=("scale_override",))
                return self._send(200, {"ok": True, "scale_global": cfg.get("scale_override")})
            if path == "/api/quant":
                def mutate_quant(cfg):
                    q = cfg.setdefault("quant", {})
                    if "enabled" in b: q["enabled"] = bool(b["enabled"])
                    if b.get("bpm") is not None: q["bpm"] = round(clamp(float(b["bpm"]), 30, 300), 1)
                    if b.get("grid") is not None: q["grid"] = clamp(float(b["grid"]), 0.0625, 4.0)
                cfg = update_config(mutate_quant); q = cfg.get("quant", {})
                return self._send(200, {"ok": True, "quant": q})
            if path == "/api/song":
                if not song_mod: return self._send(200, {"ok": False, "msg": "no song module"})
                name = b.get("name")
                if name: song_mod.set_global(name)
                else: song_mod.disable_global()
                return self._send(200, {"ok": True, "song_global": song_mod.global_song()})
            if path == "/api/regen":
                name = b.get("name", active_preset_name())
                render = preset_path(name, "render.py")
                if render and render.exists():
                    threading.Thread(target=lambda: audio.spawn_python(
                        RENDER_WORKER_PY, [name], cwd=str(HERE)),
                                     daemon=True).start()
                return self._send(200, {"ok": bool(render and render.exists())})
            if path == "/api/preset/reset":
                return self._preset_reset(b)
            if path == "/api/preset/undo":
                name = b.get("name", active_preset_name())
                return self._send(200, {"ok": preset_store.undo(name), "name": name})
            if path == "/api/preset/restore":
                name = b.get("name", active_preset_name())
                return self._send(200, {
                    "ok": preset_store.restore(name, str(b.get("id", ""))), "name": name
                })
            if path == "/api/preset/import":
                try:
                    name = preset_store.import_data(b.get("preset"), b.get("name"))
                except (TypeError, ValueError) as error:
                    return self._send(400, {"ok": False, "error": str(error)})
                return self._send(200, {"ok": True, "name": name})
            if path == "/api/cache/limit":
                try:
                    result = cache_manager.set_limit(
                        b.get("mb"), CONFIG, preserve=(active_preset_name(),)
                    )
                except ValueError as error:
                    return self._send(400, {"ok": False, "error": str(error)})
                return self._send(200, {"ok": True, **result})
            if path == "/api/cache/trim":
                return self._send(200, {
                    "ok": True,
                    **cache_manager.trim(config_path=CONFIG, preserve=(active_preset_name(),)),
                })
            if path == "/api/cache/clear":
                try:
                    result = cache_manager.clear(
                        str(b.get("scope", "")), preset=b.get("preset"), config_path=CONFIG
                    )
                except ValueError as error:
                    return self._send(400, {"ok": False, "error": str(error)})
                return self._send(200, {"ok": True, **result})
            if path == "/api/test":
                fire_test(b.get("name"))
                return self._send(200, {"ok": True})
            if path == "/api/preset/create":
                res = create_custom_preset(b)
                if res.get("ok") and b.get("set_active"):
                    patch_config({"preset": res["name"]})
                return self._send(200, res)
            if path == "/api/preset/delete":
                return self._send(200, delete_custom_preset(str(b.get("name", ""))))
            if path == "/api/preset/rename":
                return self._send(200, rename_custom_preset(str(b.get("name", "")), str(b.get("to", ""))))
            if path == "/api/voice/swap":
                return self._send(200, swap_voice_sound(
                    b.get("preset", active_preset_name()), b.get("voice"),
                    b.get("src_preset"), b.get("src_voice")))
            if path == "/api/counts/reset":
                name = b.get("name", active_preset_name())
                if load_preset(name) is None:
                    return self._send(400, {"error": "unknown preset"})
                sd = safe_child(STATE, name)
                removed = 0
                if sd.exists():
                    for f in sd.glob("cnt-*.bin"):
                        try: f.unlink(); removed += 1
                        except Exception: pass
                return self._send(200, {"ok": True, "removed": removed})
            if path == "/api/record/start":
                if REC_ACTIVE.exists():
                    return self._send(200, {"ok": False, "msg": "already recording"})
                try: secs = int(b.get("seconds", 30))
                except Exception: secs = 30
                secs = max(1, min(300, secs))
                REC_DIR.mkdir(parents=True, exist_ok=True)
                rargs = ["run", str(secs)] + (["--drone"] if b.get("drone") else [])
                audio.spawn_python(RECORD_PY, rargs, detached=True)
                return self._send(200, {"ok": True, "seconds": secs, "drone": bool(b.get("drone"))})
            if path == "/api/record/stop":
                try:
                    m = json.loads(REC_ACTIVE.read_text())
                    audio.terminate_pid(int(m["pid"]))   # portable; keeps POSIX-isms in audio.py
                except Exception:
                    pass
                return self._send(200, {"ok": True})
            if path == "/api/midiplay/start":
                return self._midiplay_start(b)
            if path == "/api/midiplay/stop":
                if midiplay_mod:
                    midiplay_mod.stop_running()
                return self._send(200, {"ok": True})
            if path == "/api/song/import":
                return self._song_import(b)
            if path == "/api/score/replay":
                return self._score_replay(b)
            if path == "/api/score/stop":
                if midiplay_mod:
                    midiplay_mod.stop_running()
                return self._send(200, {"ok": True})
            if path == "/api/score/export":
                if not timeline_mod:
                    return self._send(200, {"ok": False, "msg": "no timeline module"})
                base = timeline_mod.export_score(str(b.get("id", "")), b.get("label"))
                return self._send(200, {"ok": bool(base), "name": base} if base
                                  else {"ok": False, "msg": "no timeline for that session"})
        except KeyError as e:
            return self._send(400, {"error": f"missing {e}"})
        except Exception as e:
            return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def _voice(self, b):
        preset = b.get("preset", active_preset_name())
        path = preset_store.preset_path(preset)
        if path is None or load_preset(preset) is None:
            return self._send(400, {"error": "unknown preset"})
        field = b["field"]
        if field not in ("gain", "mioi", "rate_jitter"):
            return self._send(400, {"error": "bad field"})
        def mutate(p):
            v = p["voices"][b["voice"]]
            if field == "gain":
                v["gain"] = round(clamp(float(b["value"]), 0, 1), 3)
            elif field == "mioi":
                v["mioi"] = round(clamp(float(b["value"]), 0.01, 120), 3)
            elif bool(b["value"]):
                v["rate_jitter"] = True
            else:
                v.pop("rate_jitter", None)
        preset_store.update(preset, mutate)
        return self._send(200, {"ok": True})

    def _voice_reverb(self, b):
        preset = b.get("preset", active_preset_name())
        path = preset_store.preset_path(preset)
        if path is None or load_preset(preset) is None:
            return self._send(400, {"error": "unknown preset"})
        def mutate(p):
            rv = p["voices"][b["voice"]].setdefault("reverb", {})
            rv["wet"] = round(clamp(float(b["wet"]), 0, 1), 3)
            if b.get("decay") is not None: rv["decay"] = round(clamp(float(b["decay"]), 0.1, 8), 2)
            if b.get("brightness") is not None: rv["brightness"] = round(clamp(float(b["brightness"]), 0, 1), 2)
        preset_store.update(preset, mutate)
        ok, msg = regen_voice(preset, b["voice"])
        return self._send(200, {"ok": True, "regen": ok, "msg": msg})

    def _voice_delay(self, b):
        preset = b.get("preset", active_preset_name())
        path = preset_store.preset_path(preset)
        if path is None or load_preset(preset) is None:
            return self._send(400, {"error": "unknown preset"})
        def mutate(p):
            v = p["voices"][b["voice"]]
            if b.get("off"):
                v.pop("delay", None)
            else:
                d = v.setdefault("delay", {})
                d["ms"] = int(clamp(float(b["ms"]), 40, 2000))
                d["feedback"] = round(clamp(float(b.get("feedback", d.get("feedback", 0.30))), 0, 0.85), 2)
                d["count"] = int(clamp(float(b.get("count", d.get("count", 3))), 1, 8))
        preset_store.update(preset, mutate)
        return self._send(200, {"ok": True})  # live, no regen

    def _map(self, b):
        preset = b.get("preset", active_preset_name())
        path = preset_store.preset_path(preset); ev = b["event"]; key = b.get("key", "default")
        current = load_preset(preset)
        if path is None or current is None:
            return self._send(400, {"error": "unknown preset"})
        if not isinstance(ev, str) or len(ev) > 80 or any(ord(c) < 32 for c in ev):
            return self._send(400, {"error": "invalid event"})
        if not isinstance(key, str) or len(key) > 120 or any(ord(c) < 32 for c in key):
            return self._send(400, {"error": "invalid mapping key"})
        voice = b.get("voice")
        if voice in ("", "__none__", None) and b.get("voice", "__keep__") != "__keep__":
            voice = None
        if voice is not None and voice not in (current.get("voices") or {}):
            return self._send(400, {"error": "unknown voice"})
        def mutate(p):
            spec = p.setdefault("events", {}).setdefault(ev, {})
            if key == "default":
                spec["default"] = voice
            elif key == "on_failure":
                if voice is None: spec.pop("on_failure", None)
                else: spec["on_failure"] = voice
            else:
                bt = spec.setdefault("by_tool", {})
                if voice is None: bt.pop(key, None)
                else: bt[key] = voice
        preset_store.update(preset, mutate)
        return self._send(200, {"ok": True})

    def _reverb_scale(self, b):
        preset = b.get("preset", active_preset_name())
        path = preset_store.preset_path(preset)
        if path is None or load_preset(preset) is None:
            return self._send(400, {"error": "unknown preset"})
        preset_store.update(preset,
                            lambda p: p.update(reverb_scale=round(clamp(float(b["value"]), 0, 2), 3)))
        # full regen in background
        render = preset_path(preset, "render.py")
        if render and render.exists():
            threading.Thread(target=lambda: audio.spawn_python(
                RENDER_WORKER_PY, [preset], cwd=str(HERE)),
                             daemon=True).start()
        return self._send(200, {"ok": True, "regen": bool(render and render.exists())})

    def _session_set(self, b, key, value):
        sid = str(b["id"])
        if not sid or len(sid) > 256:
            return self._send(400, {"error": "invalid session id"})
        if key == "preset_pinned" and value not in (None, "", "__none__") and load_preset(value) is None:
            return self._send(400, {"error": "unknown preset"})
        if key == "scale_override" and value not in (None, "", "__none__") and value not in SCALE_NAMES:
            return self._send(400, {"error": "unknown scale"})
        if key == "song_pinned" and value not in (None, "", "__none__") and (not song_mod or not song_mod.has_song(value)):
            return self._send(400, {"error": "unknown song"})
        found = {"value": False}
        def mutate(d):
            active = d.setdefault("active", {})
            if sid not in active:
                return
            found["value"] = True
            rec = active[sid]
            if value in (None, "", "__none__"): rec.pop(key, None)
            else: rec[key] = value
        stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
        if not found["value"]:
            return self._send(404, {"error": "session not found"})
        return self._send(200, {"ok": True})

    def _rule_add(self, b):
        pattern = (b.get("pattern") or "").strip()
        preset = b.get("preset")
        if (not pattern or len(pattern) > 1024 or any(ord(c) < 32 for c in pattern)
                or not preset or load_preset(preset) is None):
            return self._send(400, {"error": "need valid pattern + preset"})
        rule = {"pattern": pattern, "preset": preset}
        if b.get("time"):
            window = str(b["time"])
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d", window):
                return self._send(400, {"error": "time must be HH:MM-HH:MM"})
            rule["time"] = window
        if b.get("idle_after_s"):
            rule["idle_after_s"] = int(clamp(int(b["idle_after_s"]), 30, 86400))
        key = (rule["pattern"], rule.get("time"), rule.get("idle_after_s"))
        def mutate(d):
            rules = [r for r in d.get("rules", []) if (r.get("pattern"), r.get("time"), r.get("idle_after_s")) != key]
            rules.append(rule); d["rules"] = rules
        d = stateio.update_json(RULES_FILE, {"rules": []}, mutate)
        rules = d["rules"]
        return self._send(200, {"ok": True, "rules": rules})

    def _rule_rm(self, b):
        pat = b.get("pattern")
        d = stateio.update_json(RULES_FILE, {"rules": []},
                                lambda d: d.update(rules=[r for r in d.get("rules", []) if r.get("pattern") != pat]))
        return self._send(200, {"ok": True, "rules": d["rules"]})

    def _preset_reset(self, b):
        name = b["name"]
        if preset_store.reset(name):
            return self._send(200, {"ok": True, "msg": "restored from default"})
        return self._send(200, {"ok": False, "msg": "no preset.default.json for this preset"})

    def _audition(self, b):
        preset = b["name"]
        p = load_preset(preset) or {}
        # prefer the Stop voice, else a melodic-ish default, else first voice
        ev = p.get("events", {})
        pick = (ev.get("Stop", {}) or {}).get("default") \
            or (ev.get("PostToolUse", {}) or {}).get("default") \
            or next(iter(p.get("voices", {})), None)
        ok = play_voice(preset, pick) if pick else False
        return self._send(200, {"ok": ok, "voice": pick})

    # ---- jukebox: perform a MIDI file through the active preset ----

    def _midiplay_start(self, b):
        if not midiplay_mod:
            return self._send(200, {"ok": False, "msg": "no midiplay module"})
        song = str(b.get("song", "")).strip()
        if not song or not song_mod or not song_mod.has_song(song):
            return self._send(200, {"ok": False, "msg": "unknown song"})
        midiplay_mod.stop_running()                       # only one at a time
        preset = b.get("preset") or active_preset_name()
        pargs = [song, "--preset", str(preset)]
        if b.get("tempo") is not None:
            pargs += ["--tempo", f"{clamp(float(b['tempo']), 0.25, 4.0):.3f}"]
        if b.get("bpm") is not None:
            pargs += ["--bpm", f"{clamp(float(b['bpm']), 20, 400):.2f}"]
        if b.get("loop"):
            pargs += ["--loop"]
        # mapping: {channel: event} → "ch=Event,ch=Event"
        mapping = b.get("mapping") or {}
        if isinstance(mapping, dict) and mapping:
            pairs = ",".join(f"{k}={v}" for k, v in mapping.items() if v)
            if pairs:
                pargs += ["--map", pairs]
        audio.spawn_python(MIDIPLAY_PY, pargs, detached=True)
        return self._send(200, {"ok": True, "song": song, "preset": preset})

    def _score_replay(self, b):
        """Replay a captured session through a preset. With render=true, opens an
        audio recording window first so the replay bounces to a shareable WAV."""
        if not midiplay_mod or not timeline_mod:
            return self._send(200, {"ok": False, "msg": "replay unavailable"})
        sid = str(b.get("id", "")).strip()
        score = timeline_mod.read_session(sid)
        if not score or not score.get("events"):
            return self._send(200, {"ok": False, "msg": "no timeline for that session"})
        midiplay_mod.stop_running()                       # one performance at a time
        preset = b.get("preset") or active_preset_name()
        tempo = clamp(float(b.get("tempo", 1.0)), 0.25, 4.0)
        max_gap = clamp(float(b.get("max_gap", 2.5)), 0.2, 30.0)
        loop = bool(b.get("loop"))
        # render-to-WAV: arm a recording window sized to the replay before playing
        rendered = False
        if b.get("render") and not loop:
            dur = timeline_mod.replay_duration(score["events"], tempo, max_gap)
            if not REC_ACTIVE.exists() and dur > 0:
                secs = max(1, min(300, int(dur) + 2))
                REC_DIR.mkdir(parents=True, exist_ok=True)
                rargs = ["run", str(secs)] + (["--drone"] if b.get("drone") else [])
                audio.spawn_python(RECORD_PY, rargs, detached=True)
                rendered = True
                # wait until the recorder has actually opened its window (active.json)
                # before starting the replay, so the opening notes aren't dropped.
                # Bounded (~2s) so a failed recorder can't hang the request.
                for _ in range(40):
                    if REC_ACTIVE.exists():
                        break
                    time.sleep(0.05)
        rargs = ["replay", sid, "--preset", str(preset),
                 "--tempo", f"{tempo:.3f}", "--max-gap", f"{max_gap:.2f}"]
        if loop:
            rargs.append("--loop")
        audio.spawn_python(MIDIPLAY_PY, rargs, detached=True)
        return self._send(200, {"ok": True, "session": sid, "preset": preset, "rendering": rendered})

    def _song_import(self, b):
        """Accept a base64-encoded .mid upload and add it to the song library —
        so you can drop a MIDI straight into the jukebox from the browser."""
        if not song_mod:
            return self._send(200, {"ok": False, "msg": "no song module"})
        import base64, tempfile
        data_b64 = b.get("b64") or ""
        if "," in data_b64 and data_b64[:5] == "data:":   # strip data: URL prefix
            data_b64 = data_b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(data_b64)
        except Exception:
            return self._send(200, {"ok": False, "msg": "bad upload data"})
        if not raw or raw[:4] != b"MThd":
            return self._send(200, {"ok": False, "msg": "not a Standard MIDI File"})
        name = b.get("name") or "song"
        fd, tmpname = tempfile.mkstemp(suffix=".mid")    # unique per request — no concurrent clobber
        os.close(fd)
        tmp = Path(tmpname)
        try:
            tmp.write_bytes(raw)
            sname, parsed = song_mod.import_midi_file(tmp, name)
        except Exception as e:
            return self._send(200, {"ok": False, "msg": f"import failed: {e}"})
        finally:
            try: tmp.unlink()
            except Exception: pass
        return self._send(200, {"ok": True, "name": sname,
                                "notes": len(parsed.get("notes") or []),
                                "bpm": parsed.get("bpm")})


def main():
    port = 8788
    do_open = False
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args): port = int(args[i + 1])
        if a == "--open": do_open = True
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Claudio web UI → {url}  (Ctrl-C to stop)")
    if do_open:
        audio.open_url(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
