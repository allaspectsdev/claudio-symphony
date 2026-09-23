#!/usr/bin/env python3
"""
Claudio Symphony — control CLI.

Ambient music that sonifies Claude Code hook events. Commands below tune what
you hear, where it plays, and how to capture and share it.

Quick on/off
  off                              Silence everything (hooks short-circuit, kills drone + afplay)
  on                               Restore enabled state (auto-restarts drone if preset has one)
  toggle                           Flip between on and off

Setup
  setup                            Verify dependencies, migrate data, and render all presets
  install                          Add claudio hooks to ~/.claude/settings.json
  uninstall                        Remove claudio hooks from ~/.claude/settings.json
  status                           Show install + drone + preset state, hooks, sessions, songs, quant
                                   (also what bare `claudio` runs; `claudio --help` prints this list)
  doctor [--fix]                   Preflight check (python/numpy/player/samples/hooks); --fix renders if needed
  migrate                          Copy legacy checkout data into platform user directories
  start                            Start the drone daemon for the active preset (no-op if no drone)
  stop                             Stop the drone process and kill afplay
  drone [on|off|status]            Drone bed — always follows the live root note (~½s retune)
  drone follow on|off              Drone also walks the chord progression's roots (off = A pedal)
  regen [preset]                   Re-render samples for a preset (active if unspecified)
  reset [--yes|-y]                 Full reset to shipped defaults; clears songs/quant/pins/rules/sessions

Presets
  preset list                      Available presets (* marks active)
  preset current                   Print the active preset name
  preset use <name>|default        Switch global default preset (live: stops old drone, starts new)
  preset reset [name]              Restore a preset.json from its preset.default.json
  preset validate [name|--all]     Validate preset schema and voice mappings
  preset diff [name]               Show changes from the preset's baseline
  preset history [name]            List automatic edit snapshots
  preset undo [name]               Restore the most recent edit snapshot
  preset export <name> <file>      Export portable, validated preset JSON
  preset import <file> [name]      Import preset JSON into user data
  preset reverb <0..2>             Set active preset reverb_scale multiplier and regenerate
  audition                         Hear every preset, optionally pick one (safe anytime)

Per-session routing
  sessions                         List active sessions from the last 4h (presets + cwd)
  session list                     Same as `sessions`
  session pin <id|idx> <preset>    Pin one session to a specific preset
  session unpin <id|idx>           Remove a session's preset pin
  session song <id|idx> <name|off> Pin a song to one session (overrides preset)
  session scale <id|idx> <name|off> Pin a scale to one session
  here <preset>                    Add a cwd rule for the current directory → preset

Directory rules (routing by cwd, optionally time/idle gated)
  rule list                        Show all cwd-pattern → preset rules (alias: rules)
  rule add <pattern> <preset>      Add or replace a rule (glob or path-prefix)
  rule add <pattern> <preset> --time HH:MM-HH:MM    Time-of-day rule (apply only in window)
  rule add <pattern> <preset> --idle-after <secs>   Idle-only rule (apply after N secs idle)
  rule rm <pattern>                Remove all rules matching pattern

Live tuning
  volume [0..1]                    Master gain (no value: print current)
  drone-volume [0..1]              Drone gain (apply requires drone restart; no value: print current)
  voice <name> gain <0..1>         Per-voice gain
  voice <name> mioi <seconds>      Per-voice minimum-interval rate-limit
  voice <name> reverb <wet> [decay] [bright]|off    Per-voice reverb (regenerates that voice)
  voice <name> delay <ms> [fb] [count]|off          Per-voice delay/echo (live, no regen)
  voice <name> fx                  Show this voice's reverb + delay (alias: show)
  voice <name> play                Preview one random sample from this voice
  test [voice]                     Walk all events of the active preset (or only those on voice)
  demo                             60-second showcase of the active preset with musical pacing

Event mapping
  map <event>[:<tool>] <voice|none> Map event[/tool] to a voice (none/-/null/silent = silent)
  mute <event>[:<tool>]            Set an event/tool mapping to silent
  unmute <event>[:<tool>] [voice]  Restore a mapping (event: first voice; event:tool: clears the override)
  event show                       Show current per-event effects (alias: list, ls)
  event delay <Event> <ms> [fb] [count]   Per-event delay/echo (40-2000ms, 0..0.85 fb, 0..8 count)
  event delay <Event> off          Remove an event's delay

Key, scales & chords
  scale list                       Available scales (* marks active)
  scale use <name>                 Set global scale override (or just `scale <name>`)
  scale off                        Clear global scale override (off/stop/disable/clear)
  scale show                       Print active override + session pins (show/current/status)
  root <note|±semis|off>           Live-transpose the key off A (e.g. `root C`, `root -2`, `root off`)
  chords [pop|list|off|A E F#m D]  Cycle the room through a chord progression (`chords every 8` sets pace)

MIDI songs (melody source for events)
  song list                        List imported songs (* = global default)
  song import <file.mid> [name]    Import a MIDI file (auto-detects lead channel)
  song import-dir <folder>         Import every *.mid in a folder
  song use <name>                  Set as global default (events cycle through notes)
  song off                         Clear global default → Markov picker (off/stop/disable)
  song current                     Show position + channel + preset/session pins (current/status/show)
  song reset [name]                Restart a song's pointer (default: global song)
  song channel <name> <lead|all|N> Pick which MIDI channel drives melody (lead = auto-detect)
  song info <name>                 Show channel summary + detected lead
  preset song <preset> <name|off>  Per-preset default song (overrides global)

Quantization
  quant on|off|toggle              Enable/disable master quantization
  quant status                     Show current quant state (status/show)
  tempo <bpm>                      Set master quantization tempo
  grid <subdivision>               Beats per cell (0.25=16th, 0.5=8th, 1=quarter, half=2.0)

Jukebox — perform a MIDI file through the active preset (easter egg)
  play list                        Songs you can perform (alias: jukebox)
  play <name> [--preset X] [--tempo 1.0] [--loop] [--map ch=Event,...]
                                   Perform a MIDI now; each channel → event type → its voice
  play stop                        Stop the current performance (stop/halt)
  play status                      Show JSON status of current playback

Session replay — re-run a captured session as music
  replay list                      Captured sessions with event counts + density (alias: session-replay)
  replay <id|latest> [--preset X] [--tempo 1] [--loop] [--render]
                                   Replay one session; --render captures it to WAV
  replay stop                      Stop the current replay (stop/halt)
  replay export <id|latest> [label] Export a session as a tiny shareable score.json

Record & share
  record [seconds] [--drone]       Record a clip of your session (default 30s, max 300s)
                                   --drone bakes in a faded drone bed (off by default)
  record stop                      Finish the current recording now and save (stop/end/finish)
  record status                    Show recording state + saved clips (status/show)
  record list                      List saved clips (.wav + .m4a) in the recordings folder (alias: rec)

Control surfaces
  web [--port N] [--no-open]       Open the browser control panel (default port 8788; alias: ui)
  tune                             Open the curses TUI for live parameter editing
  status-line                      Print one-line live state, for tmux/etc. (alias: statusline)

Support
  coffee                           Show on-chain tip addresses (alias: tip, donate)
"""
import os, sys, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import song as song_mod  # noqa: E402
import audio  # noqa: E402  (cross-platform playback + process helpers)
import midiplay as midiplay_mod  # noqa: E402
import timeline as timeline_mod  # noqa: E402
import stateio  # noqa: E402
import config_store  # noqa: E402
import music  # noqa: E402
import paths  # noqa: E402
import preset_schema  # noqa: E402
import preset_store  # noqa: E402

PRESETS = paths.BUILTIN_PRESETS_DIR
STATE = paths.STATE_DIR
LOGS = paths.LOG_DIR
SETTINGS = Path.home() / ".claude" / "settings.json"
BACKUPS = Path.home() / ".claude" / "backups"
CONFIG = paths.CONFIG_FILE
SESSIONS_FILE = paths.SESSIONS_FILE
RULES_FILE = paths.RULES_FILE
EVENT_PATH = str(HERE / "event.py")
DRONE_PATH = str(HERE / "drone.py")
TUNE_PATH = str(HERE / "tune.py")
PID_FILE = STATE / "drone.pid"

MARKER = "__claudio_symphony__"

HOOK_EVENTS = music.HOOK_EVENTS

# ---------- json helpers ----------

def load_json(p, default):
    return stateio.load_json(p, default)

def save_json(p, d):
    stateio.save_json(p, d)

DEFAULT_PRESET = config_store.DEFAULT_PRESET
DEFAULT_CONFIG = config_store.DEFAULT_CONFIG

def load_config(): return config_store.load(CONFIG)
def save_config(d): return config_store.save(d, CONFIG)
def active_preset_name(): return config_store.active_preset(CONFIG)
def list_preset_names():
    return preset_store.list_names()
def load_preset(name):
    return preset_store.load(name, None)
def save_preset(name, d): preset_store.save(name, d)

# ---------- settings.json hook install ----------

class SettingsError(Exception):
    """~/.claude/settings.json exists but can't be read as a JSON object."""


def _err(msg, rc=1):
    """Print an error to stderr and return an exit code for main()."""
    print(msg, file=sys.stderr)
    return rc


def load_settings():
    if not SETTINGS.exists(): return {}
    try:
        d = json.loads(SETTINGS.read_text())
    except json.JSONDecodeError as e:
        raise SettingsError(f"{SETTINGS} is not valid JSON "
                            f"(line {e.lineno}, column {e.colno}: {e.msg})")
    except (OSError, UnicodeDecodeError) as e:
        raise SettingsError(f"could not read {SETTINGS}: {e}")
    if not isinstance(d, dict) or not isinstance(d.get("hooks", {}), dict):
        raise SettingsError(f"{SETTINGS} is not a JSON object with a \"hooks\" object")
    return d

def _settings_error(e):
    print(f"claudio: {e}", file=sys.stderr)
    print(f"  Fix it by hand, or restore a copy from {BACKUPS}", file=sys.stderr)

def _load_settings_readonly():
    """For status/doctor: warn about a broken settings.json and carry on."""
    try:
        return load_settings(), None
    except SettingsError as e:
        _settings_error(e)
        return {}, e

def save_settings(d):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    if SETTINGS.exists():
        ts = time.strftime("%Y%m%d-%H%M%S")
        dest = BACKUPS / f"settings.json.claudio-{ts}"
        n = 1
        while dest.exists():  # several writes in one second must not clobber
            dest = BACKUPS / f"settings.json.claudio-{ts}-{n}"; n += 1
        dest.write_bytes(SETTINGS.read_bytes())
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(d, indent=2) + "\n")

def hook_block_for():
    return {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            # Exec form: paths are arguments, not shell input.  This is safe for
            # spaces and shell metacharacters and works with the active Python.
            "command": sys.executable,
            "args": [EVENT_PATH],
            "async": True,
            "timeout": 1,
            MARKER: True,
        }],
    }

def _is_ours(h):
    return isinstance(h, dict) and bool(h.get(MARKER))

def cmd_install():
    try:
        s = load_settings()
    except SettingsError as e:
        _settings_error(e)
        return _err("install aborted — settings.json was not modified.")
    hooks = s.setdefault("hooks", {})
    want = hook_block_for()["hooks"][0]
    added, updated = [], []
    for ev in HOOK_EVENTS:
        existing = hooks.get(ev, [])
        if not isinstance(existing, list):
            _settings_error(SettingsError(f"{SETTINGS}: hooks.{ev} is not a list"))
            return _err("install aborted — settings.json was not modified.")
        found = False
        for b in existing:
            handlers = b.get("hooks", []) if isinstance(b, dict) else []
            for i, h in enumerate(handlers):
                if not _is_ours(h): continue
                found = True
                # Refresh stale handlers (old shell-string form, moved checkout,
                # different interpreter) so they point at this install.
                if h.get("command") != want["command"] or h.get("args") != want["args"]:
                    handlers[i] = dict(want)
                    if ev not in updated: updated.append(ev)
        if found: continue
        existing.append(hook_block_for())
        hooks[ev] = existing
        added.append(ev)
    if added or updated:
        save_settings(s)
    print(f"installed hooks for: {', '.join(added) if added else '(none — already present)'}")
    if updated:
        print(f"updated: {', '.join(updated)} (now → {want['command']} {EVENT_PATH})")
    print(f"settings {'written' if added or updated else 'unchanged'}: {SETTINGS}")
    print()
    print("Note: only NEW Claude Code sessions pick up hook changes (settings.json).")
    print("Preset/voice/mapping/session changes ARE live — no Claude restart needed.")

def cmd_uninstall():
    try:
        s = load_settings()
    except SettingsError as e:
        _settings_error(e)
        return _err("uninstall aborted — settings.json was not modified.")
    hooks = s.get("hooks", {})
    removed = []
    for ev in list(hooks.keys()):
        if not isinstance(hooks[ev], list): continue
        new_blocks = []
        for block in hooks[ev]:
            handlers = block.get("hooks", []) if isinstance(block, dict) else []
            new_handlers = [h for h in handlers if not _is_ours(h)]
            if new_handlers != handlers:
                if new_handlers:
                    block["hooks"] = new_handlers
                    new_blocks.append(block)
                removed.append(ev)
            else:
                new_blocks.append(block)
        if new_blocks:
            hooks[ev] = new_blocks
        else:
            del hooks[ev]
    if not removed:
        print("removed claudio hooks from: (none) — settings.json unchanged")
        return
    if not hooks:
        s.pop("hooks", None)
    save_settings(s)
    print(f"removed claudio hooks from: {', '.join(sorted(set(removed)))}")

# ---------- drone control ----------

def drone_pid():
    try:
        if not PID_FILE.exists(): return None
        pid = int(PID_FILE.read_text().strip())
        return pid if audio.pid_alive(pid) else None
    except Exception:
        return None

def cmd_start():
    pid = drone_pid()
    if pid: print(f"drone already running pid={pid}"); return
    name = active_preset_name()
    preset = load_preset(name)
    if preset is None:
        return _err(f"active preset '{name}' not found — try: claudio preset use {DEFAULT_PRESET}")
    if not preset.get("drone"):
        print(f"preset '{name}' has no continuous drone — nothing to start")
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / "drone.out"
    audio.spawn_python(DRONE_PATH, detached=True, log_file=str(out))
    time.sleep(0.4)
    pid = drone_pid()
    print(f"drone started pid={pid}" if pid else f"launch attempted; check {LOGS / 'drone.log'}")

def cmd_drone(args):
    """Drone bed control. The drone always follows the live root note (mic-jam
    included, retuning in ~½s); `follow on` makes it walk the chord progression
    roots too. Usage: claudio drone [on|off|status|follow on|off]."""
    sub = args[0] if args else "status"
    if sub in ("on", "start"):
        return cmd_start()
    if sub in ("off", "stop"):
        return cmd_stop()
    if sub == "follow":
        cfg = load_config()
        if len(args) > 1 and args[1] in ("on", "off"):
            cfg["drone_chords"] = args[1] == "on"; save_config(cfg)
        print(f"drone follows chords: {'on' if cfg.get('drone_chords') else 'off'}"
              f"  (always follows the root note)")
        return
    pid = drone_pid()
    cfg = load_config()
    name = active_preset_name()
    has = bool((load_preset(name) or {}).get("drone"))
    print(f"drone: {'running pid=' + str(pid) if pid else 'off'} · preset {name}"
          f"{'' if has else ' (no drone in this preset)'} · gain {cfg.get('drone_gain', 0.45)}"
          f" · follows chords: {'on' if cfg.get('drone_chords') else 'off'}")

def cmd_stop():
    pid = drone_pid()
    if not pid: print("drone not running"); return
    try:
        audio.terminate_pid(pid)
        if audio.IS_WIN:
            # Windows has no deliverable SIGTERM handler; ask the loop to stop.
            (audio.STATE / "drone.stop").write_text("1")
        time.sleep(0.3)
        audio.stop_drone()          # silence the in-flight drone player now
        print(f"drone stopped pid={pid}")
    except Exception as e:
        return _err(f"stop failed: {e}")

# ---------- on/off ----------

def cmd_off():
    cfg = load_config()
    if cfg.get("muted"):
        print("🔇 already off")
        return
    cfg["muted"] = True
    save_config(cfg)
    # stop drone if running
    if drone_pid():
        cmd_stop()
    # kill any in-flight players so existing tails go silent now, not at end
    audio.stop_all()
    print("🔇 OFF — run `claudio on` to restore")

def cmd_on():
    cfg = load_config()
    cfg.pop("muted", None)
    save_config(cfg)
    name = cfg.get("preset", "meadow")
    preset = load_preset(name)
    # auto-start drone if active preset has one
    if preset and preset.get("drone") and not drone_pid():
        cmd_start()
    print(f"🔊 ON — preset: {name}")

def cmd_toggle():
    if load_config().get("muted"):
        cmd_on()
    else:
        cmd_off()

# ---------- status ----------

def cmd_doctor(args):
    """Preflight: verify everything Claudio needs is in place and say exactly
    how to fix whatever isn't. `--fix` renders the active preset if its samples
    are missing. Safe to run anytime; the /claudio skill runs this on silence."""
    fix = "--fix" in args or "-f" in args
    ok = True
    def line(good, label, detail=""):
        nonlocal ok
        if not good: ok = False
        print(f"  {'✓' if good else '✗'} {label}{('  — ' + detail) if detail else ''}")

    print("Claudio doctor\n")
    print(f"  • claudio: {HERE / 'bin' / 'claudio'}")
    # 1. Python
    v = sys.version_info
    line(v >= (3, 9), f"Python {v.major}.{v.minor}", "" if v >= (3, 9) else "need 3.9+")
    # 2. numpy (only needed to render/record — not to play)
    try:
        import numpy as _np
        line(True, f"numpy {_np.__version__}")
        have_np = True
    except Exception:
        line(False, "numpy", "render needs it → python3 -m pip install numpy")
        have_np = False
    # 3. audio player
    try:
        be = audio.get_backend()
        line(be.kind != "null", f"audio player: {be.name}",
             "" if be.kind != "null" else "install ffmpeg (Linux/Win) — see README requirements")
    except Exception as e:
        line(False, "audio player", str(e))
    # 4. active preset exists, and its samples are rendered
    name = active_preset_name()
    wavs = []
    if load_preset(name) is None:
        line(False, f"active preset '{name}'", f"not found → claudio preset use {DEFAULT_PRESET}")
    else:
        sdir = preset_store.sample_read_dir(name)
        wavs = list(sdir.rglob("*.wav")) if sdir.exists() else []
        line(bool(wavs), f"sounds for '{name}'", "" if wavs else f"not rendered yet → claudio regen {name}")
    # 5. config writable
    try:
        cfg = load_config(); save_config(cfg); line(True, "config writable")
    except Exception as e:
        line(False, "config writable", str(e))
    # 6. hooks (manual install only — plugin hooks are managed by Claude Code)
    s, bad = _load_settings_readonly(); wired = _wired_events(s)
    if bad:
        line(False, "settings.json readable", f"{bad} — restore from {BACKUPS}")
    elif wired:
        line(True, "hooks wired (manual install)", f"{len(set(wired))} events")
    else:
        print(f"  • hooks: none in {SETTINGS} — that's expected if you")
        print("        installed the plugin (Claude Code manages those). Otherwise run")
        print(f"        {HERE / 'bin' / 'claudio'} install")

    if fix and not wavs and have_np and load_preset(name) is not None:
        render = preset_store.render_path(name)
        if render:
            print(f"\n→ rendering '{name}' …")
            r = subprocess_run_render(render, name)
            print("  done." if r else "  render failed — see output above.")

    print("\n" + ("✓ all set — start (or restart) a Claude Code session and listen."
                  if ok else "✗ fix the ✗ items above, then run `claudio doctor` again."))
    return 0 if ok else 1

def cmd_migrate(args):
    result = paths.migrate_legacy(include_large=True)
    print("Claudio user-data migration\n")
    for key, count in result.items():
        print(f"  {key:<18} {count} copied")
    print(f"\n  config      {paths.CONFIG_DIR}")
    print(f"  data        {paths.DATA_DIR}")
    print(f"  cache       {paths.CACHE_DIR}")
    print(f"  state       {paths.STATE_DIR}")
    print("\nLegacy files were preserved; Claudio now reads and writes the locations above.")

def cmd_setup(args):
    """Run the explicit, foreground setup flow; never installs dependencies."""
    import subprocess
    result = subprocess.run([sys.executable, str(HERE / "install.py")], cwd=str(HERE))
    if result.returncode:
        print("\nSetup did not change your Python environment.")
        print(f"Install dependencies explicitly with:\n  {sys.executable} -m pip install -r {HERE / 'requirements.txt'}")
    return result.returncode

def subprocess_run_render(render_path, preset_name=None):
    import subprocess
    try:
        env = os.environ.copy()
        env.update(preset_store.renderer_env(preset_name or Path(render_path).parent.name))
        r = subprocess.run([sys.executable, str(render_path)], cwd=str(HERE),
                           env=env, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(r.stdout[-500:]); print(r.stderr[-500:], file=sys.stderr)
        return r.returncode == 0
    except Exception as e:
        print(f"  {e}", file=sys.stderr); return False

def _wired_events(s):
    events = []
    for ev, blocks in s.get("hooks", {}).items():
        if not isinstance(blocks, list): continue
        for b in blocks:
            if isinstance(b, dict) and any(_is_ours(h) for h in b.get("hooks", [])):
                events.append(ev); break
    return events

def cmd_status():
    s, bad = _load_settings_readonly()
    events = _wired_events(s)
    cfg = load_config()
    name = cfg.get("preset", "meadow")
    preset = load_preset(name)
    pid = drone_pid()
    muted = cfg.get("muted", False)
    print(f"state:           {'🔇 OFF' if muted else '🔊 ON'}")
    print(f"active preset:   {name}{' (✓)' if preset else ' (NOT FOUND)'}")
    if preset:
        print(f"  description:   {preset.get('description','')}")
        print(f"  drone:         {preset.get('drone') or 'none'}")
        print(f"  voices:        {', '.join(preset.get('voices', {}).keys())}")
    print(f"available:       {', '.join(list_preset_names()) or '(none)'}")
    print(f"hooks installed: {'(settings.json unreadable — see above)' if bad else ', '.join(sorted(set(events))) if events else '(none)'}")
    print(f"drone:           {'running pid='+str(pid) if pid else 'stopped'}")
    print(f"master_gain:     {cfg.get('master_gain', preset.get('master_gain', 0.5) if preset else 0.5)}")
    print(f"drone_gain:      {cfg.get('drone_gain', preset.get('drone_gain', 0.45) if preset else 0.45)}")
    rules = load_json(RULES_FILE, {"rules": []}).get("rules", [])
    if rules:
        print("cwd rules:")
        for r in rules:
            print(f"  {r.get('pattern','?'):<60} → {r.get('preset','?')}")
    sessions = load_json(SESSIONS_FILE, {"active": {}}).get("active", {})
    fresh = {sid: s for sid, s in sessions.items() if s.get("last_seen", 0) > time.time() - 4*3600}
    print(f"active sessions: {len(fresh)} (last 4h)  (run `claudio sessions` for details)")
    g = song_mod.global_song()
    if g:
        n_total = len(song_mod.notes_for(g))
        s = song_mod.load_song(g) or {}
        print(f"song (global):   {g} ({song_mod.position(g)}/{n_total} notes, bpm={s.get('bpm')})")
    else:
        print(f"song (global):   (off — Markov picker)")
    if preset and preset.get("song"):
        print(f"  preset song:   {preset['song']} (overrides global for {name})")
    q = song_mod.quant_settings()
    print(f"quant:           {'ON' if q['enabled'] else 'off'}  tempo={q['bpm']} bpm  grid={q['grid']} beats")
    print(f"event log:       {LOGS / 'event.log'}")
    print()
    print("run `claudio --help` for all commands")

# ---------- presets ----------

def cmd_preset(args):
    if not args or args[0] in ("list", "ls"):
        names = list_preset_names()
        active = active_preset_name()
        for n in names:
            preset = load_preset(n)
            tag = " *" if n == active else "  "
            desc = preset.get("description", "") if preset else "(broken)"
            print(f"{tag} {n:<14} {desc}")
        return
    if args[0] in ("current", "show"):
        print(active_preset_name()); return
    if args[0] == "validate":
        targets = list_preset_names() if "--all" in args else [
            args[1] if len(args) > 1 else active_preset_name()
        ]
        failed = 0
        for name in targets:
            preset = load_preset(name)
            errors = ["preset document not found"] if preset is None else preset_schema.validate(preset)
            if preset is not None and preset.get("name") != name:
                errors.append(f"name: {preset.get('name')!r} does not match directory {name!r}")
            if errors:
                failed += 1
                print(f"✗ {name}")
                for error in errors:
                    print(f"    {error}")
            else:
                print(f"✓ {name} (schema v{preset_schema.CURRENT_VERSION})")
        print(f"\n{len(targets) - failed}/{len(targets)} presets valid")
        return failed
    if args[0] == "diff":
        name = args[1] if len(args) > 1 else active_preset_name()
        try:
            diff = preset_store.diff_from_default(name)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            return _err(f"could not diff preset: {error}")
        print(diff or f"preset '{name}' matches its baseline")
        return
    if args[0] == "history":
        name = args[1] if len(args) > 1 else active_preset_name()
        entries = preset_store.history(name)
        if not entries:
            print(f"(no edit history for '{name}')"); return
        for entry in entries:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["timestamp"]))
            print(f"  {entry['id']}  {stamp}  {entry['description']}")
        return
    if args[0] == "undo":
        name = args[1] if len(args) > 1 else active_preset_name()
        if preset_store.undo(name):
            print(f"preset '{name}' restored to its previous edit")
        else:
            return _err(f"no edit history for '{name}'")
        return
    if args[0] == "export":
        if len(args) < 3:
            return _err("usage: claudio preset export <name> <file>")
        try:
            destination = preset_store.export_to(args[1], args[2])
            print(f"exported '{args[1]}' → {destination}")
        except (ValueError, OSError) as error:
            return _err(f"export failed: {error}")
        return
    if args[0] == "import":
        if len(args) < 2:
            return _err("usage: claudio preset import <file> [name]")
        try:
            name = preset_store.import_from(args[1], args[2] if len(args) > 2 else None)
            print(f"imported preset '{name}'")
        except (ValueError, OSError, json.JSONDecodeError) as error:
            return _err(f"import failed: {error}")
        return
    if args[0] == "song":
        if len(args) < 3:
            return _err("usage: claudio preset song <preset> <song-name|off>")
        pname, song_name = args[1], args[2]
        preset = load_preset(pname)
        if preset is None:
            return _err(f"unknown preset '{pname}'")
        if song_name in ("off", "none", "-"):
            preset.pop("song", None)
            save_preset(pname, preset)
            print(f"preset '{pname}' song cleared")
            return
        if not song_mod.has_song(song_name):
            return _err(f"unknown song '{song_name}'. available: {', '.join(song_mod.list_songs()) or '(none)'}")
        preset["song"] = song_name
        save_preset(pname, preset)
        print(f"preset '{pname}' song → {song_name}")
        return
    if args[0] == "reset":
        target = args[1] if len(args) > 1 else active_preset_name()
        return cmd_preset_reset(target)
    if args[0] == "reverb":
        return cmd_preset_reverb(args[1:])
    if args[0] in ("use", "set", "switch"):
        if len(args) < 2: return _err("usage: claudio preset use <name>")
        name = args[1]
        if name == "default":
            name = DEFAULT_PRESET
        if load_preset(name) is None:
            return _err(f"unknown preset '{name}'. available: {', '.join(list_preset_names())}")
        cfg = load_config()
        cfg["preset"] = name
        # a new preset brings its own levels; only mention it if the user had tuned them
        reset = [k for k in ("master_gain", "drone_gain")
                 if cfg.pop(k, None) not in (None, DEFAULT_CONFIG.get(k))]
        save_config(cfg)
        print(f"active preset → {name}")
        if reset:
            print(f"(custom {' and '.join(reset)} reset to the preset's own level)")
        if drone_pid():
            print("(stopping drone — preset changed)"); cmd_stop()
        preset = load_preset(name)
        if preset and preset.get("drone"):
            print("(starting drone for new preset)"); cmd_start()
        return
    return _err(f"unknown preset subcommand: {args[0]}")

# ---------- reset ----------

def cmd_preset_reset(name):
    if not preset_store.reset(name):
        return _err(f"no shipped default for '{name}' (looking for preset.default.json)")
    print(f"preset '{name}' restored from preset.default.json")


def cmd_reset(args):
    """Full reset to shipped defaults — equivalent of a fresh install
    state. Asks for confirmation unless --yes is passed."""
    confirm = ("--yes" in args) or ("-y" in args)
    if not confirm:
        print("This will:")
        print(f"  · restore preset.json for ALL presets from preset.default.json")
        print(f"  · rewrite config.json to shipped defaults "
              f"(preset={DEFAULT_PRESET}, master_gain=0.55, drone_gain=0.0)")
        print(f"  · clear song positions, channel overrides, global song")
        print(f"  · clear session pins (sessions.json) and cwd rules (rules.json)")
        print(f"  · NOT touch installed hooks, samples, imported songs, or logs")
        print()
        print("Re-run with --yes to confirm: claudio reset --yes")
        return 1
    # restore presets
    for name in list_preset_names():
        cmd_preset_reset(name)
    # config
    save_config(dict(DEFAULT_CONFIG))
    print(f"config.json → shipped defaults")
    # song state
    song_state = paths.SONG_STATE_FILE
    if song_state.exists(): song_state.unlink()
    print(f"song state cleared")
    # session pins
    if SESSIONS_FILE.exists(): SESSIONS_FILE.unlink()
    if RULES_FILE.exists(): RULES_FILE.unlink()
    print(f"session pins + cwd rules cleared")
    # bounce drone
    if drone_pid():
        cmd_stop()
    preset = load_preset(DEFAULT_PRESET)
    if preset and preset.get("drone"):
        cmd_start()
    print()
    print(f"✓ reset complete — active preset: {DEFAULT_PRESET}")


# ---------- sessions / rules ----------

def _load_active_sessions():
    return load_json(SESSIONS_FILE, {"active": {}}).get("active", {})

def _resolve_session(target):
    """Resolve target (numeric index or id-prefix) to a session_id."""
    sessions = _load_active_sessions()
    rows = sorted(sessions.items(), key=lambda kv: -kv[1].get("last_seen", 0))
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(rows): return rows[idx][0]
        return None
    matches = [sid for sid, _ in rows if sid.startswith(target)]
    if len(matches) == 1: return matches[0]
    if len(matches) > 1:
        print(f"ambiguous prefix '{target}'; matches {len(matches)} sessions", file=sys.stderr)
    return None

def cmd_sessions():
    sessions = _load_active_sessions()
    cutoff = time.time() - 4 * 3600
    fresh = sorted(
        ((sid, s) for sid, s in sessions.items() if s.get("last_seen", 0) > cutoff),
        key=lambda kv: -kv[1].get("last_seen", 0),
    )
    if not fresh:
        print("no active sessions seen in last 4h")
        return
    print(f"{'#':>2}  {'sid':<10} {'pin':<3} {'preset':<12} {'ago':<6} {'src':<12} cwd")
    for i, (sid, s) in enumerate(fresh, 1):
        ago = max(0, int((time.time() - s.get("last_seen", 0)) / 60))
        pin = "📌" if s.get("preset_pinned") else " "
        preset = s.get("preset_resolved", "?")
        src = (s.get("preset_source", "") or "")[:11]
        cwd = s.get("cwd", "?")
        print(f"{i:>2}  {sid[:8]}    {pin}    {preset:<12} {ago:>3}m    {src:<12} {cwd}")

def cmd_session(args):
    if not args:
        cmd_sessions(); return
    sub = args[0]; rest = args[1:]
    if sub in ("list", "ls"):
        cmd_sessions(); return
    if sub == "pin":
        if len(rest) < 2: return _err("usage: claudio session pin <id|index> <preset>")
        sid = _resolve_session(rest[0])
        if not sid: return _err(f"no session matches '{rest[0]}'")
        preset = rest[1]
        if load_preset(preset) is None:
            return _err(f"unknown preset '{preset}'")
        def mutate(d): d.setdefault("active", {}).setdefault(sid, {})["preset_pinned"] = preset
        stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
        print(f"pinned {sid[:8]} → {preset}")
        return
    if sub == "scale":
        if len(rest) < 2:
            return _err("usage: claudio session scale <id|index> <scale|off>")
        sid = _resolve_session(rest[0])
        if not sid: return _err(f"no session matches '{rest[0]}'")
        target = rest[1]
        if target in ("off", "none", "-"):
            def mutate(d): d.setdefault("active", {}).setdefault(sid, {}).pop("scale_override", None)
            stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
            print(f"session {sid[:8]} scale cleared")
            return
        if target not in _scale_names():
            return _err(f"unknown scale '{target}'. available: {', '.join(_scale_names())}")
        def mutate(d): d.setdefault("active", {}).setdefault(sid, {})["scale_override"] = target
        stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
        print(f"session {sid[:8]} scale → {target}")
        return
    if sub == "song":
        if len(rest) < 2:
            return _err("usage: claudio session song <id|index> <song-name|off>")
        sid = _resolve_session(rest[0])
        if not sid: return _err(f"no session matches '{rest[0]}'")
        target = rest[1]
        if target in ("off", "none", "-"):
            def mutate(d): d.setdefault("active", {}).setdefault(sid, {}).pop("song_pinned", None)
            stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
            print(f"session {sid[:8]} song cleared")
            return
        if not song_mod.has_song(target):
            return _err(f"unknown song '{target}'")
        def mutate(d): d.setdefault("active", {}).setdefault(sid, {})["song_pinned"] = target
        stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
        print(f"session {sid[:8]} song → {target}")
        return
    if sub == "unpin":
        if not rest: return _err("usage: claudio session unpin <id|index>")
        sid = _resolve_session(rest[0])
        if not sid: return _err(f"no session matches '{rest[0]}'")
        def mutate(d):
            if sid in d.get("active", {}): d["active"][sid].pop("preset_pinned", None)
        stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
        print(f"unpinned {sid[:8]}")
        return
    return _err(f"unknown session subcommand: {sub}")

def cmd_here(args):
    if not args: return _err("usage: claudio here <preset>")
    preset = args[0]
    if load_preset(preset) is None:
        return _err(f"unknown preset '{preset}'")
    cwd = os.environ.get("CLAUDIO_CWD") or os.getcwd()
    return cmd_rule(["add", cwd, preset])

def _format_rule(r):
    parts = [f"  {r.get('pattern','?'):<48} → {r.get('preset','?'):<10}"]
    extras = []
    if "time" in r:           extras.append(f"time={r['time']}")
    if "idle_after_s" in r:   extras.append(f"idle≥{r['idle_after_s']}s")
    if extras:                parts.append("  " + "  ".join(extras))
    return "".join(parts)


def cmd_rule(args):
    if not args or args[0] in ("list", "ls"):
        rules = load_json(RULES_FILE, {"rules": []}).get("rules", [])
        if not rules: print("(no rules)"); return
        print("rules are evaluated top-to-bottom; first match wins")
        for r in rules:
            print(_format_rule(r))
        return
    sub = args[0]
    rest = list(args[1:])
    if sub == "add":
        # parse positional + flag args.
        # syntax: claudio rule add <pattern> <preset> [--time HH:MM-HH:MM] [--idle-after N]
        time_val = None
        idle_val = None
        positional = []
        i = 0
        while i < len(rest):
            a = rest[i]
            if a == "--time" and i + 1 < len(rest):
                time_val = rest[i + 1]; i += 2; continue
            if a in ("--idle-after", "--idle") and i + 1 < len(rest):
                try: idle_val = int(rest[i + 1])
                except ValueError: return _err(f"--idle-after needs whole seconds (got '{rest[i + 1]}')", 2)
                i += 2; continue
            positional.append(a); i += 1
        if len(positional) < 2:
            return _err("usage: claudio rule add <pattern> <preset> [--time HH:MM-HH:MM] [--idle-after N]")
        pattern, preset = positional[0], positional[1]
        if load_preset(preset) is None:
            return _err(f"unknown preset '{preset}'")
        new_rule = {"pattern": pattern, "preset": preset}
        if time_val:
            try:
                start_s, end_s = time_val.split("-")
                for s in (start_s, end_s):
                    h, m = s.split(":")
                    int(h); int(m)
            except Exception:
                return _err(f"--time must be HH:MM-HH:MM (got '{time_val}')")
            new_rule["time"] = time_val
        if idle_val is not None:
            if idle_val < 30:
                return _err(f"--idle-after below 30s is too jumpy; pick a higher value")
            new_rule["idle_after_s"] = idle_val
        # de-dup by pattern + time + idle (allow multiple rules for same pattern with different conditions)
        key = (new_rule["pattern"], new_rule.get("time"), new_rule.get("idle_after_s"))
        def mutate(d):
            rules = [r for r in d.get("rules", [])
                     if (r.get("pattern"), r.get("time"), r.get("idle_after_s")) != key]
            rules.append(new_rule)
            d["rules"] = rules
        stateio.update_json(RULES_FILE, {"rules": []}, mutate)
        print(f"rule added:")
        print(_format_rule(new_rule))
        return
    if sub in ("rm", "remove"):
        if not rest: return _err("usage: claudio rule rm <pattern>")
        pattern = rest[0]
        removed = {"count": 0}
        def mutate(d):
            before = len(d.get("rules", []))
            d["rules"] = [r for r in d.get("rules", []) if r.get("pattern") != pattern]
            removed["count"] = before - len(d["rules"])
        stateio.update_json(RULES_FILE, {"rules": []}, mutate)
        print(f"removed {removed['count']} rule(s) matching '{pattern}'")
        return
    return _err(f"unknown rule subcommand: {sub}")

# ---------- voice / mapping subcommands ----------

def _float_arg(value, usage):
    """Parse a numeric CLI argument, or print usage and exit 2."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        f = float("nan")
    if f != f or f in (float("inf"), float("-inf")):
        print(f"claudio: expected a number, got '{value}'", file=sys.stderr)
        print(usage, file=sys.stderr)
        sys.exit(2)
    return f

def _require_voice(preset, name):
    voices = preset.get("voices", {})
    if name not in voices:
        print(f"unknown voice '{name}'. available: {', '.join(voices)}", file=sys.stderr)
        return None
    return voices[name]

def _regen_voice(pname, vname):
    """Re-render a single voice's samples (used after a reverb change)."""
    render = preset_store.render_path(pname)
    if render is None or not render.exists():
        print(f"  (preset '{pname}' has no render.py; reverb change saved but "
              f"samples not regenerated)"); return
    audio.spawn_python(render, [vname], env=preset_store.renderer_env(pname))


def cmd_voice(args):
    if len(args) < 2:
        return _err("usage: claudio voice <name> <gain|mioi|reverb|delay|fx|play> [value]")
    name = args[0]; sub = args[1]; rest = args[2:]
    pname = active_preset_name()
    preset = load_preset(pname)
    if preset is None: return _err(f"preset {pname} not found")
    v = _require_voice(preset, name)
    if v is None: return 1
    if sub == "reverb":
        # claudio voice <name> reverb <wet> [decay] [brightness] | off
        # baked at render → regenerates just this voice's samples.
        rv = v.setdefault("reverb", {})
        if rest and rest[0] in ("off", "dry", "none", "0"):
            rv["wet"] = 0.0
        elif not rest:
            return _err("usage: claudio voice <name> reverb <wet 0..1> [decay s] [brightness 0..1] | off")
        else:
            u = "usage: claudio voice <name> reverb <wet 0..1> [decay s] [brightness 0..1] | off"
            rv["wet"] = round(max(0.0, min(1.0, _float_arg(rest[0], u))), 3)
            if len(rest) > 1: rv["decay"] = round(max(0.1, min(8.0, _float_arg(rest[1], u))), 2)
            if len(rest) > 2: rv["brightness"] = round(max(0.0, min(1.0, _float_arg(rest[2], u))), 2)
        save_preset(pname, preset)
        print(f"{name}.reverb = {rv}  (regenerating…)")
        _regen_voice(pname, name)
        return
    if sub == "delay":
        # claudio voice <name> delay <ms> [feedback] [count] | off
        # live playback echo — no re-render needed.
        if rest and rest[0] in ("off", "none", "0"):
            v.pop("delay", None)
            save_preset(pname, preset)
            print(f"{name}.delay = off"); return
        u = "usage: claudio voice <name> delay <ms> [feedback 0..0.85] [count 1..8] | off"
        if not rest:
            return _err(u)
        d = v.setdefault("delay", {})
        d["ms"] = int(max(40, min(2000, _float_arg(rest[0], u))))
        if len(rest) > 1: d["feedback"] = round(max(0.0, min(0.85, _float_arg(rest[1], u))), 2)
        if len(rest) > 2: d["count"] = int(max(1, min(8, _float_arg(rest[2], u))))
        d.setdefault("feedback", 0.30); d.setdefault("count", 3)
        save_preset(pname, preset)
        print(f"{name}.delay = {d}  (live — no regen)")
        return
    if sub in ("fx", "show"):
        rv = v.get("reverb"); d = v.get("delay")
        rtxt = (f"wet={rv.get('wet')} decay={rv.get('decay','?')}s "
                f"bright={rv.get('brightness','?')}" if isinstance(rv, dict) else "(default)")
        dtxt = (f"{d.get('ms')}ms fb={d.get('feedback')} x{d.get('count')}"
                if isinstance(d, dict) else "off")
        print(f"{name}: reverb {rtxt}  |  delay {dtxt}")
        return
    if sub == "gain":
        if not rest: return _err("usage: claudio voice <name> gain <0..1>")
        v["gain"] = round(max(0.0, min(1.0, _float_arg(rest[0], "usage: claudio voice <name> gain <0..1>"))), 3)
        save_preset(pname, preset)
        print(f"{name}.gain = {v['gain']}")
        return
    if sub == "mioi":
        if not rest: return _err("usage: claudio voice <name> mioi <seconds>")
        v["mioi"] = round(max(0.01, min(120.0, _float_arg(rest[0], "usage: claudio voice <name> mioi <seconds>"))), 3)
        save_preset(pname, preset)
        print(f"{name}.mioi = {v['mioi']}s")
        return
    if sub == "play":
        # fire one trigger via event.py with a fake event that maps to this voice
        # easier: play a random sample directly via the audio backend
        import random
        d = preset_store.sample_asset(pname, v.get("dir", name))
        samples = sorted(p for p in d.iterdir() if p.suffix == ".wav") if d.exists() else []
        if not samples: return _err(f"no samples in {d} — try: claudio regen {pname}")
        cfg = load_config()
        master = float(cfg.get("master_gain", preset.get("master_gain", 0.5)))
        gain = max(0.0, min(1.0, v.get("gain", 0.5) * master))
        sample = random.choice(samples)
        audio.play_simple(sample, gain)
        print(f"playing {name} → {sample.name} @ v={gain:.2f}")
        return
    return _err(f"unknown voice subcommand: {sub}")

def _parse_event_key(token):
    """ 'PostToolUse' → ('PostToolUse', 'default')
        'PostToolUse:Edit' → ('PostToolUse', 'Edit')
        'PostToolUse:on_failure' → ('PostToolUse', 'on_failure') """
    if ":" in token:
        ev, key = token.split(":", 1)
    else:
        ev, key = token, "default"
    if ev == "PostToolUseFailure" and key == "default":
        # failures are mapped via PostToolUse's on_failure slot (see event.py)
        ev, key = "PostToolUse", "on_failure"
    return ev, key

_CLEAR = object()   # _set_mapping sentinel: drop a by_tool override entirely

def _set_mapping(ev, key, voice_or_none):
    """voice_or_none: a voice name, None (explicitly silent — stored as null so
    a by_tool entry keeps overriding the event default), or _CLEAR (remove the
    by_tool override so the tool falls back to the event default)."""
    if ev not in HOOK_EVENTS:
        print(f"unknown event '{ev}'. events: {', '.join(HOOK_EVENTS)}", file=sys.stderr)
        return False
    pname = active_preset_name()
    preset = load_preset(pname)
    if preset is None:
        print(f"preset {pname} not found", file=sys.stderr); return False
    if voice_or_none not in (None, _CLEAR) and voice_or_none not in preset.get("voices", {}):
        print(f"unknown voice '{voice_or_none}'. available: {', '.join(preset.get('voices', {}))}",
              file=sys.stderr)
        return False
    spec = preset.setdefault("events", {}).setdefault(ev, {})
    if key in ("default", "on_failure"):
        spec[key] = None if voice_or_none is _CLEAR else voice_or_none
    else:
        bt = spec.setdefault("by_tool", {})
        if voice_or_none is _CLEAR:
            bt.pop(key, None)
        else:
            bt[key] = voice_or_none
    save_preset(pname, preset)
    return True

def cmd_map(args):
    if len(args) < 2: return _err("usage: claudio map <event>[:<tool>] <voice|none>")
    ev, key = _parse_event_key(args[0])
    voice = args[1]
    if voice in ("-", "none", "null", "silent"): voice = None
    if not _set_mapping(ev, key, voice): return 1
    print(f"map {ev}/{key} → {voice if voice is not None else '(silent)'}")

def cmd_mute(args):
    if not args: return _err("usage: claudio mute <event>[:<tool>]")
    ev, key = _parse_event_key(args[0])
    if not _set_mapping(ev, key, None): return 1
    print(f"muted {ev}/{key}")

def cmd_unmute(args):
    if not args: return _err("usage: claudio unmute <event>[:<tool>] [voice]")
    ev, key = _parse_event_key(args[0])
    if len(args) < 2 and key not in ("default", "on_failure"):
        # event:tool with no voice → drop the override; the tool follows the event default
        if not _set_mapping(ev, key, _CLEAR): return 1
        print(f"unmuted {ev}/{key} → (event default)")
        return
    pname = active_preset_name()
    preset = load_preset(pname)
    if preset is None: return _err(f"preset {pname} not found")
    voices = list(preset.get("voices", {}).keys())
    if not voices: return _err("preset has no voices")
    voice = args[1] if len(args) > 1 else voices[0]
    if not _set_mapping(ev, key, voice): return 1
    print(f"unmuted {ev}/{key} → {voice}")

# ---------- gain ----------

def _current_gain(key, fallback):
    cfg = load_config()
    if key in cfg: return cfg[key]
    return (load_preset(active_preset_name()) or {}).get(key, fallback)

def cmd_volume(v=None):
    if v is None:
        print(f"master_gain = {_current_gain('master_gain', 0.5)}"); return
    g = _float_arg(v, "usage: claudio volume <0..1>")
    cfg = load_config()
    cfg["master_gain"] = max(0.0, min(1.0, g))
    save_config(cfg)
    print(f"master_gain = {cfg['master_gain']}")

def cmd_drone_volume(v=None):
    if v is None:
        print(f"drone_gain = {_current_gain('drone_gain', 0.45)}"); return
    g = _float_arg(v, "usage: claudio drone-volume <0..1>")
    cfg = load_config()
    cfg["drone_gain"] = max(0.0, min(1.0, g))
    save_config(cfg)
    print(f"drone_gain = {cfg['drone_gain']} (restart drone to apply)")

# ---------- regen ----------

def cmd_regen(args):
    name = args[0] if args else active_preset_name()
    render = preset_store.render_path(name)
    legacy = HERE / "synth.py"
    if render is not None and render.exists():
        audio.spawn_python(render, env=preset_store.renderer_env(name))
    elif name == "cathedral" and legacy.exists():
        # legacy synth writes into samples/ at top level; need to redirect
        # to presets/cathedral/samples — but this is rarely needed since
        # cathedral was bootstrapped already. Tell the user to use rainfall path.
        print(f"cathedral has no render.py; samples already rendered at "
              f"{preset_store.sample_read_dir('cathedral')}")
    else:
        return _err(f"no renderer for preset '{name}'. available: {', '.join(list_preset_names())}")

# ---------- test demo ----------

def fire_event(payload):
    audio.spawn_python(EVENT_PATH, stdin_bytes=json.dumps(payload).encode())

def clear_mioi(preset_name):
    sd = STATE / preset_name
    if sd.exists():
        for p in sd.glob("last-*.txt"):
            try: p.unlink()
            except FileNotFoundError: pass

def cmd_test(voice=None):
    name = active_preset_name()
    preset = load_preset(name)
    if preset is None: return _err(f"preset '{name}' not found")
    clear_mioi(name)
    events = preset.get("events", {})
    sequence = []
    if "SessionStart" in events:     sequence.append({"hook_event_name": "SessionStart", "session_id": "test"})
    if "UserPromptSubmit" in events: sequence.append({"hook_event_name": "UserPromptSubmit", "session_id": "test"})
    if "PreToolUse" in events:
        sequence.append({"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "test"})
        for t in (events["PreToolUse"].get("by_tool") or {}):
            sequence.append({"hook_event_name": "PreToolUse", "tool_name": t, "session_id": "test"})
    if "PostToolUse" in events:
        sequence.append({"hook_event_name": "PostToolUse", "tool_name": "Read", "session_id": "test"})
        for t in (events["PostToolUse"].get("by_tool") or {}):
            sequence.append({"hook_event_name": "PostToolUse", "tool_name": t, "session_id": "test"})
    if "SubagentStop" in events:     sequence.append({"hook_event_name": "SubagentStop", "session_id": "test"})
    if "Stop" in events:             sequence.append({"hook_event_name": "Stop", "session_id": "test"})
    if "SessionEnd" in events:       sequence.append({"hook_event_name": "SessionEnd", "session_id": "test"})

    if voice:
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("event_mod", str(HERE / "event.py"))
        mod = module_from_spec(spec); spec.loader.exec_module(mod)
        sequence = [p for p in sequence
                    if mod.resolve_voice(preset, p["hook_event_name"], p) == voice]
        if not sequence:
            return _err(f"no events in preset '{name}' map to voice '{voice}'")

    for p in sequence:
        ev = p["hook_event_name"]; tool = p.get("tool_name", "")
        print(f"  {ev}{('('+tool+')') if tool else ''}")
        clear_mioi(name)
        fire_event(p)
        time.sleep(2.5)
    print("done.")

# ---------- song / quant ----------

def _channel_label(song, name):
    ch = song_mod.get_channel(name)
    if ch is None:
        lead = song_mod.lead_channel(song)
        return f"lead (auto={lead})"
    if ch == "all":
        return "all"
    return f"ch{ch}"


def _timeline_ids():
    d = timeline_mod.TIMELINE
    if not d.exists():
        return []
    # snapshot (stem, mtime) defensively — event.py prunes idle-session files on
    # every hook, so a file can vanish between glob and stat.
    pairs = []
    for p in d.glob("*.ndjson"):
        try:
            pairs.append((p.stem, p.stat().st_mtime))
        except OSError:
            pass
    pairs.sort(key=lambda t: t[1], reverse=True)
    return [s for s, _ in pairs]


def cmd_replay(args):
    """Replay a captured session ('mini-track') through a preset — re-runs your
    actual workflow as music. Always-on capture means any recent session works."""
    if args and args[0] in ("stop", "halt"):
        midiplay_mod.stop_running(); print("replay stopped"); return
    if args and args[0] == "export":
        if len(args) < 2:
            return _err("usage: claudio replay export <session_id|latest> [label]")
        sid = _timeline_ids()[0] if args[1] == "latest" and _timeline_ids() else args[1]
        base = timeline_mod.export_score(sid, args[2] if len(args) > 2 else None)
        if not base: return _err("no timeline for that session")
        print(f"exported {paths.RECORDINGS_DIR / (base + '.score.json')} (tiny + shareable)")
        return
    if not args or args[0] in ("list", "ls"):
        ids = _timeline_ids()
        if not ids:
            print("(no sessions captured yet — they record automatically as you work)")
            return
        print(f"{'session':<14} {'events':>7}  {'length':>7}  busiest")
        for sid in ids:
            s = timeline_mod.summary(sid)
            if not s: continue
            bars = "".join("▁▂▃▄▅▆▇█"[min(7, int(v / (s['peak'] or 1) * 7))] for v in s["density"][::max(1, len(s["density"]) // 24)])
            print(f"{sid[:13]:<14} {s['count']:>7}  {s['duration']:>6.0f}s  {bars}")
        print("\nreplay one:  claudio replay <session_id|latest> [--preset X] [--tempo 1] [--loop] [--render]")
        return

    sid = args[0]
    rest = args[1:]
    if sid == "latest":
        ids = _timeline_ids()
        if not ids: return _err("(no sessions captured yet)")
        sid = ids[0]
    preset = None; tempo = 1.0; loop = False; render = False; max_gap = 2.5
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--preset" and i + 1 < len(rest): preset = rest[i + 1]; i += 2
        elif a == "--tempo" and i + 1 < len(rest):
            tempo = max(0.25, min(4.0, _float_arg(rest[i + 1], "usage: claudio replay <id> --tempo <0.25..4>"))); i += 2
        elif a == "--max-gap" and i + 1 < len(rest):
            max_gap = max(0.0, _float_arg(rest[i + 1], "usage: claudio replay <id> --max-gap <seconds>")); i += 2
        elif a == "--loop": loop = True; i += 1
        elif a in ("--render", "--wav"): render = True; i += 1
        else: i += 1
    s = timeline_mod.read_session(sid)
    if not s or not s.get("events"):
        return _err(f"no timeline for session '{sid}'. try: claudio replay list")
    preset = preset or active_preset_name()
    dur = timeline_mod.replay_duration(s["events"], tempo, max_gap)
    print(f"▶ replaying session {sid[:12]} through '{preset}'  "
          f"({s['count']} events · ~{dur:.0f}s{' · LOOP' if loop else ''})")
    if render:
        secs = max(1, min(300, int(dur) + 2))
        (STATE / "recording").mkdir(parents=True, exist_ok=True)
        audio.spawn_python(str(HERE / "record.py"), ["run", str(secs)], detached=True)  # absolute: claudio runs from any cwd
        print(f"  ● rendering to a WAV in {paths.RECORDINGS_DIR} ({secs}s)")
        time.sleep(0.3)
    print("  (Ctrl-C to stop)\n")
    midiplay_mod.run_score(sid, preset, tempo=tempo, loop=loop, max_gap=max_gap)
    print("done.")


def cmd_play(args):
    """Jukebox: perform a whole MIDI file through the active preset, mapping
    each MIDI channel to an event type → its voice. The easter egg."""
    if args and args[0] in ("stop", "halt"):
        midiplay_mod.stop_running()
        print("jukebox stopped")
        return
    if args and args[0] in ("status",):
        print(json.dumps(midiplay_mod.status(), indent=2))
        return
    if not args or args[0] in ("list", "ls"):
        names = song_mod.list_songs()
        if not names:
            print("(no songs imported — `claudio song import <file.mid>`)")
        else:
            print("songs you can perform:")
            for n in names:
                s = song_mod.load_song(n) or {}
                print(f"  {n:<24} {len(s.get('notes') or []):>5} notes  bpm={s.get('bpm')}")
            print("\nplay one:  claudio play <name> [--preset X] [--tempo 1.0] [--loop]")
        return

    song_name = args[0]
    rest = args[1:]
    preset = bpm = mapping = None
    tempo = 1.0
    loop = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--preset" and i + 1 < len(rest): preset = rest[i + 1]; i += 2
        elif a == "--tempo" and i + 1 < len(rest):
            tempo = max(0.25, min(4.0, _float_arg(rest[i + 1], "usage: claudio play <name> --tempo <0.25..4>"))); i += 2
        elif a == "--bpm" and i + 1 < len(rest):
            bpm = max(1.0, _float_arg(rest[i + 1], "usage: claudio play <name> --bpm <bpm>")); i += 2
        elif a == "--map" and i + 1 < len(rest): mapping = midiplay_mod._parse_map_arg(rest[i + 1]); i += 2
        elif a == "--loop": loop = True; i += 1
        else: i += 1

    if not song_mod.has_song(song_name):
        return _err(f"unknown song '{song_name}'. available: {', '.join(song_mod.list_songs()) or '(none)'}")
    preset = preset or active_preset_name()
    p = midiplay_mod.plan(song_name, preset, mapping)
    if not p or not p.get("channels"):
        return _err("nothing to play (no mappable channels / voices in this preset)")
    print(f"♪ performing '{song_name}' through '{preset}'  "
          f"({p['total_notes']} notes · {p['duration']:.0f}s · bpm {p['bpm']*tempo:.0f})")
    print("  track → event → voice:")
    for r in p["channels"]:
        lead = " ◆lead" if r["is_lead"] else ""
        print(f"    ch{r['channel']:<2} {r['register']:>4} {r['notes']:>4}n{lead:<6}"
              f"  →  {r['event'] or '—':<16} → {r['voice'] or '(silent)'}")
    print("  ▶ playing… (Ctrl-C to stop)\n")
    midiplay_mod.run(song_name, preset, bpm=bpm, tempo=tempo, loop=loop, mapping=mapping)
    print("done.")


def cmd_song(args):
    if not args or args[0] in ("list", "ls"):
        names = song_mod.list_songs()
        global_name = song_mod.global_song()
        if not names:
            print("(no songs imported — `claudio song import <file.mid>`)")
            return
        print(f"{'':2} {'name':<24} {'notes':>6}  {'bpm':>6}  channel")
        for n in names:
            tag = " *" if n == global_name else "  "
            s = song_mod.load_song(n) or {}
            print(f"{tag} {n:<24} {len(s.get('notes') or []):>6}  {s.get('bpm', 0):>6}  {_channel_label(s, n)}")
        return
    sub = args[0]; rest = args[1:]
    if sub == "import":
        if not rest:
            return _err("usage: claudio song import <file.mid> [name]")
        try:
            name, parsed = song_mod.import_midi_file(rest[0], rest[1] if len(rest) > 1 else None)
        except Exception as e:
            return _err(f"import failed: {e}")
        lead = song_mod.lead_channel(parsed)
        print(f"imported '{name}': {len(parsed['notes'])} notes  bpm={parsed['bpm']}  lead=ch{lead}")
        return
    if sub in ("import-dir", "importdir"):
        if not rest:
            return _err("usage: claudio song import-dir <folder>")
        folder = Path(rest[0]).expanduser()
        if not folder.is_dir():
            return _err(f"not a folder: {folder}")
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".mid")
        if not files:
            return _err(f"no .mid files in {folder}")
        for f in files:
            try:
                name, parsed = song_mod.import_midi_file(f)
                lead = song_mod.lead_channel(parsed)
                print(f"  ✓ {name:<24} {len(parsed['notes'])} notes  bpm={parsed['bpm']}  lead=ch{lead}")
            except Exception as e:
                print(f"  ✗ {f.name}: {e}")
        return
    if sub == "use":
        if not rest:
            return _err("usage: claudio song use <name>")
        if not song_mod.set_global(rest[0]):
            return _err(f"unknown song '{rest[0]}'. available: {', '.join(song_mod.list_songs()) or '(none)'}")
        print(f"global song → {rest[0]} (events cycle through its notes)")
        return
    if sub in ("off", "stop", "disable"):
        song_mod.disable_global()
        print("global song off — back to Markov picker (preset/session pins still apply)")
        return
    if sub in ("current", "status", "show"):
        g = song_mod.global_song()
        print(f"global default: {g or '(none)'}")
        if g:
            s = song_mod.load_song(g) or {}
            n = len(song_mod.notes_for(g))
            print(f"  position:     {song_mod.position(g)} / {n}")
            print(f"  channel:      {_channel_label(s, g)}")
            print(f"  bpm (file):   {s.get('bpm')}")
        # preset overrides
        for name in list_preset_names():
            preset = load_preset(name)
            ps = (preset or {}).get("song")
            if ps:
                print(f"  preset {name}: {ps}")
        # session pins
        sessions = load_json(SESSIONS_FILE, {"active": {}}).get("active", {})
        for sid, rec in sessions.items():
            sp = rec.get("song_pinned")
            if sp:
                print(f"  session {sid[:8]}: {sp}")
        return
    if sub == "reset":
        target = rest[0] if rest else song_mod.global_song()
        if not target:
            return _err("usage: claudio song reset <name> (no global song set)")
        song_mod.reset_position(target)
        print(f"song '{target}' position → 0")
        return
    if sub == "channel":
        if len(rest) < 2:
            return _err("usage: claudio song channel <name> <lead|all|N>")
        name, ch_str = rest[0], rest[1]
        if not song_mod.has_song(name):
            return _err(f"unknown song '{name}'")
        if ch_str in ("lead", "auto"):
            song_mod.set_channel(name, "lead")
        elif ch_str == "all":
            song_mod.set_channel(name, "all")
        else:
            try:
                song_mod.set_channel(name, int(ch_str))
            except ValueError:
                return _err("channel must be 'lead', 'all', or an integer 0-15")
        s = song_mod.load_song(name)
        print(f"{name}.channel = {_channel_label(s, name)}  ({len(song_mod.notes_for(name))} notes after filter)")
        return
    if sub == "info":
        if not rest:
            return _err("usage: claudio song info <name>")
        name = rest[0]
        s = song_mod.load_song(name)
        if not s:
            return _err(f"unknown song '{name}'")
        lead = song_mod.lead_channel(s)
        print(f"{name}: {len(s.get('notes') or [])} notes  bpm={s.get('bpm')}  ppq={s.get('ppq')}")
        print(f"  selected channel: {_channel_label(s, name)}")
        print(f"  detected lead:    ch{lead}")
        print(f"  channel breakdown:")
        for ch, ct, med in song_mod.channel_summary(s):
            marker = " ← lead" if ch == lead else ""
            print(f"    ch{ch:>2}  {ct:>5} notes  median midi={med}{marker}")
        return
    return _err(f"unknown song subcommand: {sub}")


def _print_quant():
    q = song_mod.quant_settings()
    state = "ON" if q["enabled"] else "off"
    print(f"quant: {state}  tempo={q['bpm']} bpm  grid={q['grid']} beats")


def cmd_quant(args):
    if not args or args[0] in ("status", "show"):
        _print_quant(); return
    sub = args[0]
    if sub == "on":
        song_mod.set_quant(enabled=True);  _print_quant(); return
    if sub == "off":
        song_mod.set_quant(enabled=False); _print_quant(); return
    if sub == "toggle":
        cur = song_mod.quant_settings()["enabled"]
        song_mod.set_quant(enabled=not cur); _print_quant(); return
    return _err(f"unknown quant subcommand: {sub}")


def cmd_tempo(args):
    if not args:
        _print_quant(); return
    try:
        bpm = float(args[0])
    except ValueError:
        return _err("usage: claudio tempo <bpm>", 2)
    song_mod.set_quant(bpm=bpm)
    _print_quant()


def cmd_grid(args):
    if not args:
        _print_quant(); return
    aliases = {
        "quarter": 1.0, "q": 1.0, "1/4": 1.0,
        "8th": 0.5, "eighth": 0.5, "1/8": 0.5,
        "16th": 0.25, "sixteenth": 0.25, "1/16": 0.25,
        "32nd": 0.125, "1/32": 0.125,
        "half": 2.0, "1/2": 2.0,
    }
    raw = args[0]
    if raw in aliases:
        grid = aliases[raw]
    else:
        try: grid = float(raw)
        except ValueError:
            return _err("usage: claudio grid <0.25|0.5|1.0|16th|8th|quarter|...>", 2)
    song_mod.set_quant(grid=grid)
    _print_quant()


# ---------- scale override ----------

def _scale_names():
    return list(music.SCALES)


def cmd_scale(args):
    """Apply a per-config (current shell) scale override. Affects all sessions
    that don't have their own pin. Resolution: session pin > config > preset default."""
    if not args or args[0] in ("list", "ls"):
        names = _scale_names()
        cur = load_config().get("scale_override")
        for n in names:
            tag = " *" if n == cur else "  "
            print(f"{tag} {n}")
        return
    sub = args[0]
    if sub in ("off", "stop", "disable", "clear"):
        cfg = load_config(); cfg.pop("scale_override", None); save_config(cfg)
        print("scale override cleared")
        return
    if sub in ("show", "current", "status"):
        cur = load_config().get("scale_override")
        print(f"global scale: {cur or '(off — preset default)'}")
        sessions = load_json(SESSIONS_FILE, {"active": {}}).get("active", {})
        for sid, rec in sessions.items():
            if rec.get("scale_override"):
                print(f"  session {sid[:8]}: {rec['scale_override']}")
        return
    if sub == "use" or sub in _scale_names():
        # `claudio scale use <name>` or shorthand `claudio scale <name>`
        name = args[1] if sub == "use" and len(args) > 1 else sub
        if name not in _scale_names():
            return _err(f"unknown scale '{name}'. available: {', '.join(_scale_names())}")
        cfg = load_config(); cfg["scale_override"] = name; save_config(cfg)
        print(f"global scale → {name}")
        return
    return _err(f"unknown scale '{sub}'. available: {', '.join(_scale_names())}")


# ---------- root note (live transpose off A) ----------

_PCS = {"C":0,"C#":1,"DB":1,"D":2,"D#":3,"EB":3,"E":4,"F":5,"F#":6,"GB":6,
        "G":7,"G#":8,"AB":8,"A":9,"A#":10,"BB":10,"B":11}
_NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

def _clamp_root(v):
    try: n = int(round(float(v)))
    except (TypeError, ValueError): return 0
    return max(-6, min(6, n))

def cmd_root(args):
    """Set the global live transpose off A (the rendered A=432 root). Re-keys
    every voice (and the drone) instantly, no re-render. The web 🎤 Listen mode
    drives this from your mic. Usage: claudio root <note|±semitones|off|show>."""
    if not args or args[0] in ("show", "status", "current"):
        off = _clamp_root(load_config().get("root_offset", 0))
        print(f"root: {_NOTES[(9 + off) % 12]}  ({'+' if off >= 0 else ''}{off} from A)")
        return
    sub = args[0]
    if sub in ("off", "clear", "reset", "a", "A"):
        cfg = load_config(); cfg.pop("root_offset", None); save_config(cfg)
        print("root → A (shipped key)")
        return
    key = sub.upper()
    if key in _PCS:                       # note name → nearest signed offset off A
        off = _clamp_root(((_PCS[key] - 9 + 6) % 12) - 6)
    else:
        try: off = _clamp_root(int(sub))  # raw semitone offset
        except ValueError:
            return _err(f"unknown root '{sub}'. give a note (C, F#, Bb), a ±semitone offset, or 'off'.")
    cfg = load_config(); cfg["root_offset"] = off; save_config(cfg)
    print(f"root → {_NOTES[(9 + off) % 12]}  ({'+' if off >= 0 else ''}{off} from A)")


# ---------- chord progressions ----------

def cmd_chords(args):
    """Cycle the room through a chord progression (wall-clock, no daemon).
    Usage: claudio chords [show|list|off|use <preset>|every <sec>|<chords…>]"""
    def _show():
        prog = load_config().get("progression") or {}
        if not prog.get("enabled") or not prog.get("steps"):
            print("chords: off"); return
        i, label = music.chord_step(prog)
        steps = prog["steps"]
        line = "  ".join(f"[{s}]" if j == i else f" {s} " for j, s in enumerate(steps))
        print(f"chords: {line}   (every {prog.get('step_s', 8):g}s, now: {label})")
    if not args or args[0] in ("show", "status", "current"):
        _show(); return
    sub = args[0]
    if sub in ("list", "ls"):
        for name, steps in music.PROGRESSIONS.items():
            print(f"  {name:<12} {' – '.join(steps)}")
        print(f"  chords available for custom: {', '.join(sorted(music.CHORDS))}")
        return
    cfg = load_config(); prog = cfg.get("progression") or {}
    if sub in ("off", "stop", "disable"):
        prog["enabled"] = False
        cfg["progression"] = prog; save_config(cfg); print("chords off"); return
    if sub == "every" and len(args) > 1:
        try: prog["step_s"] = max(2.0, min(60.0, float(args[1])))
        except ValueError: return _err("usage: claudio chords every <seconds>", 2)
        cfg["progression"] = prog; save_config(cfg)
        print(f"chord length → {prog['step_s']:g}s"); _show(); return
    if sub == "use" and len(args) > 1: sub, args = args[1], args[1:]
    if sub in music.PROGRESSIONS:
        prog.update(preset=sub, steps=list(music.PROGRESSIONS[sub]), enabled=True)
        cfg["progression"] = prog; save_config(cfg); _show(); return
    # custom: a list of chord names, e.g. `claudio chords A E F#m D`
    steps = [a for a in args if a in music.CHORDS]
    if len(steps) >= 2:
        prog.update(preset="custom", steps=steps, enabled=True)
        cfg["progression"] = prog; save_config(cfg); _show(); return
    return _err(f"unknown progression '{sub}'. presets: {', '.join(music.PROGRESSIONS)}; "
                f"or give 2+ chords from: {', '.join(sorted(music.CHORDS))}")


# ---------- preset reverb scale ----------

def cmd_preset_reverb(args):
    """Set or read the active preset's reverb_scale multiplier. Auto-regens.
    1.0 = unchanged from rendered defaults; 0.5 = half wet; 1.5 = 50% wetter."""
    pname = active_preset_name()
    preset = load_preset(pname)
    if preset is None:
        return _err(f"active preset '{pname}' not found")
    if not args:
        print(f"{pname}.reverb_scale = {preset.get('reverb_scale', 1.0)}")
        return
    try:
        scale = max(0.0, min(2.0, float(args[0])))
    except ValueError:
        return _err("usage: claudio preset reverb <0..2>", 2)
    preset["reverb_scale"] = round(scale, 3)
    save_preset(pname, preset)
    print(f"{pname}.reverb_scale = {scale}  (regenerating samples...)")
    return cmd_regen([pname])


# ---------- per-event delay ----------

def cmd_event(args):
    """Set per-event-mapping effects (currently only delay/echo).
    Examples:
      claudio event delay Stop 320 0.30 3      # ms / feedback / count
      claudio event delay PostToolUse off      # remove the echo
      claudio event show                       # show current event effects
    """
    if not args or args[0] in ("show", "list", "ls"):
        pname = active_preset_name()
        preset = load_preset(pname)
        if preset is None: return
        events = preset.get("events", {})
        any_effects = False
        for ev, spec in events.items():
            if not isinstance(spec, dict): continue
            eff = spec.get("effect")
            if eff:
                any_effects = True
                d = eff.get("delay")
                if d:
                    print(f"  {ev}: delay {d.get('ms','?')}ms  fb={d.get('feedback','?')}  count={d.get('count','?')}")
        if not any_effects:
            print(f"(no event effects on '{pname}')")
        return
    sub = args[0]
    rest = args[1:]
    if sub == "delay":
        if len(rest) < 2:
            return _err("usage: claudio event delay <Event> <ms|off> [feedback] [count]")
        ev = rest[0]
        pname = active_preset_name()
        preset = load_preset(pname)
        if preset is None: return
        events = preset.setdefault("events", {})
        spec = events.setdefault(ev, {"default": None})
        if not isinstance(spec, dict):
            spec = {"default": spec}
            events[ev] = spec
        if rest[1] in ("off", "none", "-", "0"):
            if "effect" in spec and "delay" in spec["effect"]:
                spec["effect"].pop("delay", None)
                if not spec["effect"]:
                    spec.pop("effect", None)
            save_preset(pname, preset)
            print(f"{ev}: delay cleared")
            return
        try:
            ms = max(40, min(2000, int(rest[1])))
            fb = float(rest[2]) if len(rest) > 2 else 0.30
            count = int(rest[3]) if len(rest) > 3 else 3
        except ValueError:
            return _err("usage: claudio event delay <Event> <ms> [feedback 0..0.85] [count 0..8]", 2)
        fb = max(0.0, min(0.85, fb))
        count = max(0, min(8, count))
        spec.setdefault("effect", {})["delay"] = {"ms": ms, "feedback": round(fb, 3), "count": count}
        save_preset(pname, preset)
        print(f"{ev}: delay {ms}ms  fb={fb}  count={count}")
        return
    return _err(f"unknown event subcommand: {sub}")


# ---------- demo / audition / status-line ----------

# Demo script: ~60 s of varied events with musical pacing. Designed to
# trigger every voice family in any preset and feel like a real session,
# not a checklist. Tools chosen so by_tool overrides actually fire.
_DEMO_SCRIPT = [
    ("SessionStart",     None,           1.6, "session begins"),
    ("UserPromptSubmit", None,           1.1, "you ask a question"),
    ("PreToolUse",       "Read",         0.3, "claude opens a file"),
    ("PostToolUse",      "Read",         1.6, "  …reads it"),
    ("PreToolUse",       "Bash",         0.3, "shell command"),
    ("PostToolUse",      "Bash",         1.4, "  …completes"),
    ("PreToolUse",       "Edit",         0.4, "file edit incoming"),
    ("PostToolUse",      "Edit",         2.4, "  …saved"),
    ("PreToolUse",       "Write",        0.4, "writing a new file"),
    ("PostToolUse",      "Write",        2.0, "  …written"),
    ("PreToolUse",       "Read",         0.3, "another read"),
    ("PostToolUse",      "Read",         3.0, "  …done"),
    ("SubagentStop",     None,           4.0, "subagent finishes"),
    ("PreToolUse",       "MultiEdit",    0.4, "batch edit"),
    ("PostToolUse",      "MultiEdit",    2.5, "  …complete"),
    ("PreToolUse",       "Bash",         0.3, "test command"),
    ("PostToolUse",      "Bash",         3.5, "  …passes"),
    ("Stop",             None,           5.0, "claude finishes"),
    ("SessionEnd",       None,           0.0, "session over"),
]


def cmd_demo(args):
    """60-second showcase. Fires events with musical gaps; selectively clears
    MIOI before bloom/cluster events so they actually sound."""
    pname = active_preset_name()
    preset = load_preset(pname)
    if preset is None:
        return _err(f"preset '{pname}' not found")
    voices_with_long_mioi = {n for n, v in preset.get("voices", {}).items()
                              if v.get("mioi", 0.5) >= 4.0}
    print(f"demo: {pname} ({preset.get('description','')[:60]})")
    print("─" * 70)
    clear_mioi(pname)
    started = time.time()
    for ev, tool, gap, label in _DEMO_SCRIPT:
        # Resolve the voice this event will pick — used for the timeline label
        # AND for pre-clearing MIOI on long-cooldown voices so they actually fire.
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("event_mod", str(HERE / "event.py"))
        mod = module_from_spec(spec); spec.loader.exec_module(mod)
        payload = {"hook_event_name": ev, "session_id": "demo"}
        if tool: payload["tool_name"] = tool
        voice = mod.resolve_voice(preset, ev, payload)
        if voice in voices_with_long_mioi:
            # let the slow voice fire even mid-demo
            (STATE / pname / f"last-{voice}.txt").unlink(missing_ok=True)
        elapsed = time.time() - started
        ev_label = f"{ev}{f'({tool})' if tool else ''}"
        print(f"  {int(elapsed):>2}s  {ev_label:<28} → {voice or '-':<10}  {label}")
        fire_event(payload)
        time.sleep(gap)
    print("─" * 70)
    print(f"demo complete ({int(time.time() - started)}s).")


def _audition_blurbs():
    return {
        "meadow":    "bright, happy, felt-mallets in a sunlit room",
        "cathedral": "modal drone bed; airy plucks; the lush one",
        "rainfall":  "sparse drops, near-silence — silence as canvas",
        "koto":      "plucked silk strings + temple bowl, japanese",
    }


def cmd_audition(args):
    """Play a 12-second slice of every preset in turn so you can pick one.
    Doesn't change config.json unless --pick is passed and the user chooses.
    Safe to run any time."""
    blurbs = _audition_blurbs()
    order = ["meadow", "cathedral", "rainfall", "koto"]
    available = [n for n in order if n in list_preset_names()]
    if not available:
        return _err("no presets installed")
    cur = active_preset_name()
    print("audition — listen to each preset, then pick one")
    print("─" * 70)
    cfg_save = load_config()
    try:
        for n in available:
            cfg = load_config(); cfg["preset"] = n
            cfg["muted"] = False
            save_config(cfg)
            print(f"  ▶ {n:<10}  {blurbs.get(n, '')}")
            clear_mioi(n)
            for ev in ("SessionStart", "UserPromptSubmit",
                       "PreToolUse", "PostToolUse",
                       "PreToolUse", "PostToolUse", "Stop"):
                payload = {"hook_event_name": ev, "session_id": "audition"}
                if ev in ("PreToolUse", "PostToolUse"):
                    payload["tool_name"] = "Read"
                fire_event(payload)
                time.sleep(1.4)
            time.sleep(1.0)
        print("─" * 70)
        try:
            choice = input(f"pick one [1-{len(available)}, Enter=keep '{cur}']: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        if choice.isdigit():
            i = int(choice) - 1
            if 0 <= i < len(available):
                target = available[i]
                cfg = load_config(); cfg["preset"] = target
                save_config(cfg)
                print(f"active preset → {target}")
                return
        # restore previous
        save_config(cfg_save)
        print(f"kept '{cur}'")
    except Exception:
        save_config(cfg_save)
        raise


def cmd_status_line(args):
    """Print ONE line summarizing live state. Suitable for tmux:
    `set -g status-right \"#(claudio status-line)\"`
    Reads existing state files; no per-event file write."""
    cfg = load_config()
    name = cfg.get("preset", DEFAULT_PRESET)
    muted = cfg.get("muted", False)
    # last fired voice across all voices for this preset
    sd = STATE / name
    last_voice, last_ts = None, 0.0
    if sd.exists():
        for f in sd.glob("last-*.txt"):
            try:
                ts = float(f.read_text().strip())
                if ts > last_ts:
                    last_ts = ts
                    last_voice = f.stem.replace("last-", "")
            except Exception:
                pass
    age = int(time.time() - last_ts) if last_ts else None
    voice_field = f"{last_voice}{f' {age}s' if age is not None else ''}" if last_voice else "—"
    state = "🔇" if muted else "🔊"
    sym = song_mod.global_song()
    pieces = [f"{state} {name}", f"voice:{voice_field}"]
    if sym:
        pieces.append(f"♪{sym}")
    q = song_mod.quant_settings()
    if q.get("enabled"):
        pieces.append(f"⏱ {int(q.get('bpm', 120))}bpm")
    print(" │ ".join(pieces))


# ---------- tune (TUI) ----------

def cmd_tune():
    # exec so curses gets a clean tty handoff (spawn-and-exit on Windows)
    audio.exec_python(TUNE_PATH)

# ---------- web UI ----------

def cmd_web(args):
    """Launch the browser control panel (pure-stdlib local server)."""
    import socket
    web = str(HERE / "webui.py")
    port = 8788; do_open = True
    usage = "usage: claudio web [--port N] [--no-open]"
    for i, a in enumerate(args):
        if a == "--port":
            if i + 1 >= len(args): return _err(usage, 2)
            try: port = int(args[i + 1])
            except ValueError: return _err(f"claudio: --port expects a number, got '{args[i + 1]}'\n{usage}", 2)
            if not 1 <= port <= 65535: return _err(f"claudio: --port must be 1-65535\n{usage}", 2)
        elif a == "--no-open": do_open = False
    # webui.py binds after exec (we can't catch its OSError), so probe first.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if not audio.IS_WIN:  # match http.server's allow_reuse_address (TIME_WAIT is fine)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as e:
        return _err(f"claudio: can't listen on 127.0.0.1:{port} ({e.strerror or e}).\n"
                    f"  Is the console already open? Try http://127.0.0.1:{port}/ "
                    f"or pick another port: claudio web --port {port + 1}")
    finally:
        probe.close()
    args = ["--port", str(port)]
    if do_open: args.append("--open")
    audio.exec_python(web, args)

# ---------- support ----------

def cmd_coffee(args):
    d = load_json(HERE / "donate.json", None)
    if not d or not d.get("methods"):
        print("No donate.json found.")
        return
    print()
    print(f"  ☕  {d.get('title', 'Buy me a coffee')}")
    if d.get("blurb"):
        print(f"      {d['blurb']}")
    print()
    for m in d["methods"]:
        accepts = m.get("accepts", [])
        extra = f"   ({', '.join(accepts[1:])})" if len(accepts) > 1 else ""
        print(f"  {m['label']:<10} {m['symbol']:<5} {m['address']}{extra}")
    print()
    print("  Native coin first; the listed tokens ride the same address (same chain only).")
    print("  QR codes + one-tap copy live in the web panel:  claudio web  →  ☕ Tip")
    print()

# ---------- record ----------

def cmd_record(args):
    import record as rec
    args = list(args)
    drone = False
    for f in ("--drone", "-d", "drone"):
        if f in args:
            drone = True
            args = [a for a in args if a != f]
    sub = args[0] if args else None
    if sub in ("stop", "end", "finish"):
        m = rec.stop()
        print("⏹  Stopping & saving the current recording…" if m else "Nothing is recording.")
        return
    if sub in ("status", "show"):
        s = rec.status()
        if s["active"]:
            print(f"🔴 recording — {s['remaining']}s left, {s['events']} sound(s) captured")
        else:
            print("Not recording.")
        recs = s.get("recordings", [])
        if recs:
            print(f"{paths.RECORDINGS_DIR} ({len(recs)}):")
            for r in recs[:10]:
                print(f"  {r['name']}  ({r['size'] // 1024} KB)")
        return
    if sub in ("list", "ls"):
        recs = rec.list_recordings()
        if not recs:
            print("No recordings yet — try:  claudio record")
            return
        print(f"{paths.RECORDINGS_DIR}:")
        for r in recs:
            print(f"  {r['name']}  ({r['size'] // 1024} KB)")
        return
    if rec.is_active():
        return _err("A recording is already running. `claudio record stop` to finish it.")
    secs = rec.DEFAULT_SECS
    if sub is not None:
        try:
            secs = int(sub)
        except ValueError:
            return _err(f"usage: claudio record [seconds|stop|status|list]  "
                        f"(default {rec.DEFAULT_SECS}s, max {rec.MAX_SECS}s)", 2)
    secs = max(1, min(rec.MAX_SECS, secs))
    drone_note = "  🌫️ drone bed: on (fades in/out)" if drone else ""
    print(f"🔴 Recording up to {secs}s of Claudio — go drive your Claude sessions. "
          f"Ctrl-C to stop early.{drone_note}\n")
    def prog(rem, n):
        sys.stdout.write(f"\r   ⏺  {rem:5.1f}s left  ·  {n} sound{'s' if n != 1 else ''} captured    ")
        sys.stdout.flush()
    res = rec.run(secs, src="cli", on_progress=prog, drone=drone)
    sys.stdout.write("\r" + " " * 64 + "\r")
    if not res or (res.get("events", 0) == 0 and not res.get("drone")):
        print("…no sounds were captured. Make sure claudio is ON and a session was active.")
        return
    extra = " + drone" if res.get("drone") else ""
    print(f"✅ Saved a {res['seconds']}s clip · {res['events']} sounds{extra}")
    print(f"   🎧  {res['wav']}")
    if res.get("m4a"):
        print(f"   📦  {res['m4a']}   ← small file, easy to share")
    print()
    print("   🎙️  Love how your sessions sound? Share the clip (post it with the preset")
    print("       name) so others can hear it — the more sounds people share, the better.")

# ---------- main ----------

# Alias → the name its entry uses in the help text above.
_HELP_NAMES = {"check": "doctor", "rules": "rule", "ui": "web", "key": "root",
               "progression": "chords", "prog": "chords", "songs": "song",
               "jukebox": "play", "session-replay": "replay", "tip": "coffee",
               "donate": "coffee", "rec": "record", "statusline": "status-line"}

def _print_help(cmd=None):
    """Print the __doc__ lines for one command (plus their continuation lines);
    fall back to the full help when the command has no entry."""
    name = _HELP_NAMES.get(cmd, cmd)
    lines = (__doc__ or "").splitlines()
    out, keep = [], False
    for ln in lines:
        if ln.startswith("  ") and not ln.startswith("   "):
            keep = ln.split()[0] == name
        elif not ln.startswith("   "):
            keep = False
        if keep: out.append(ln)
    print("\n".join(out) if out else __doc__)
    return 0

def main(argv):
    if not argv: argv = ["status"]
    cmd = argv[0]; args = argv[1:]
    if cmd in ("-h", "--help", "help"):
        return _print_help(args[0]) if args else (print(__doc__) or 0)
    if "-h" in args or "--help" in args:
        return _print_help(cmd)
    if   cmd == "install":              return cmd_install()
    elif cmd == "setup":                return cmd_setup(args)
    elif cmd == "uninstall":            return cmd_uninstall()
    elif cmd == "start":                return cmd_start()
    elif cmd == "stop":                 return cmd_stop()
    elif cmd == "drone":                return cmd_drone(args)
    elif cmd in ("doctor", "check"):    return cmd_doctor(args)
    elif cmd == "migrate":              return cmd_migrate(args)
    elif cmd == "status":               return cmd_status()
    elif cmd == "test":                 return cmd_test(args[0] if args else None)
    elif cmd == "volume":               return cmd_volume(args[0] if args else None)
    elif cmd == "drone-volume":         return cmd_drone_volume(args[0] if args else None)
    elif cmd == "preset":               return cmd_preset(args)
    elif cmd == "regen":                return cmd_regen(args)
    elif cmd == "sessions":             return cmd_sessions()
    elif cmd == "session":              return cmd_session(args)
    elif cmd == "here":                 return cmd_here(args)
    elif cmd in ("rule", "rules"):      return cmd_rule(args)
    elif cmd == "voice":                return cmd_voice(args)
    elif cmd == "map":                  return cmd_map(args)
    elif cmd == "mute":                 return cmd_mute(args)
    elif cmd == "unmute":               return cmd_unmute(args)
    elif cmd == "tune":                 return cmd_tune()
    elif cmd in ("web", "ui"):          return cmd_web(args)
    elif cmd == "off":                  return cmd_off()
    elif cmd == "on":                   return cmd_on()
    elif cmd == "toggle":               return cmd_toggle()
    elif cmd == "reset":                return cmd_reset(args)
    elif cmd == "demo":                 return cmd_demo(args)
    elif cmd == "audition":             return cmd_audition(args)
    elif cmd in ("status-line", "statusline"): return cmd_status_line(args)
    elif cmd == "scale":                return cmd_scale(args)
    elif cmd in ("root", "key"):        return cmd_root(args)
    elif cmd in ("chords", "progression", "prog"): return cmd_chords(args)
    elif cmd == "event":                return cmd_event(args)
    elif cmd in ("song", "songs"):      return cmd_song(args)
    elif cmd in ("play", "jukebox"):    return cmd_play(args)
    elif cmd in ("replay", "session-replay"): return cmd_replay(args)
    elif cmd == "quant":                return cmd_quant(args)
    elif cmd == "tempo":                return cmd_tempo(args)
    elif cmd == "grid":                 return cmd_grid(args)
    elif cmd in ("coffee", "tip", "donate"): return cmd_coffee(args)
    elif cmd in ("record", "rec"):      return cmd_record(args)
    return _err(f"claudio: unknown command '{cmd}' (see claudio --help)", 2)

if __name__ == "__main__":
    # Windows pipes/redirects default to a legacy code page that can't encode
    # the ✓/🔊 glyphs in our output; degrade them instead of crashing.
    for _stream in (sys.stdout, sys.stderr):
        try: _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError): pass
    sys.exit(main(sys.argv[1:]) or 0)
