#!/usr/bin/env python3
"""
Claudio Symphony — interactive tuner (curses TUI).

Four panes (TAB to cycle):
  Voices    — gain/mioi/reverb/delay per voice (g/t/v/e pick column, ←→ adjust);
              reverb is baked so it flags a regen (r); delay is a live echo.
              SPACE plays a sample from that voice.
  Events    — event → voice mapping (incl. by-tool overrides + on_failure).
              SPACE plays the mapped voice; m mutes/unmutes; d cycles delay.
  Settings  — master/drone gain, reverb scale (per-preset), scale override,
              quant on/bpm/grid, active song. ←/→ adjusts.
  Sessions  — active sessions (last 4h). ←/→ cycles a per-session preset pin.

Globals:
  p — cycle active preset
  s — save changes back to preset.json + config.json (stays open)
  ./, — master gain ±0.05
  q — quit (auto-saves any pending changes, like vim :wq)
  Q — quit WITHOUT saving (capital Q, discards edits)

In Voices pane, ←/→ adjusts the focused column. Use g (gain) or t (mioi/time)
to switch which column ←/→ tweaks. In Events pane, 'd' on a row cycles the
per-event delay/echo (off → subtle → medium → long → echo).
Reverb_scale changes require regen; the TUI flags it on save and you can run
`claudio regen <preset>` (or 'r' inside the TUI) to apply.
"""
import json, time, os, sys, math, random
from pathlib import Path
try:
    import curses
except ImportError:
    curses = None   # Windows: needs `pip install windows-curses` (see guard in main)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audio  # noqa: E402  (cross-platform playback + process helpers)
import config_store  # noqa: E402
import music  # noqa: E402
import paths  # noqa: E402
import preset_store  # noqa: E402
import stateio  # noqa: E402
PRESETS = paths.BUILTIN_PRESETS_DIR
STATE = paths.STATE_DIR
CONFIG = paths.CONFIG_FILE
SESSIONS_FILE = paths.SESSIONS_FILE
EVENT_PY = HERE / "event.py"

def load_json(p, default):
    return stateio.load_json(p, default)

def save_json(p, d):
    stateio.save_json(p, d)

def list_preset_names():
    return preset_store.list_names()

def list_samples(preset_name, voice_dir):
    d = preset_store.sample_asset(preset_name, voice_dir)
    if not d.exists(): return []
    return sorted(p for p in d.iterdir() if p.suffix == ".wav")

# ---------- TUI ----------

class TuneUI:
    PANE_VOICES, PANE_EVENTS, PANE_SETTINGS, PANE_SESSIONS = 0, 1, 2, 3
    N_PANES = 4

    # Scale names (mirror SCALES in event.py — read at runtime to avoid drift).
    @staticmethod
    def _scale_names():
        return list(music.SCALES)

    GRID_PRESETS = [(0.0625, "1/64"), (0.125, "1/32"), (0.25, "1/16"),
                    (0.5, "1/8"),     (1.0, "1/4"),    (2.0, "1/2"),
                    (4.0, "whole")]
    DELAY_PRESETS = [
        (None, "off"),
        ({"ms": 220, "feedback": 0.20, "count": 2}, "subtle"),
        ({"ms": 320, "feedback": 0.30, "count": 3}, "medium"),
        ({"ms": 500, "feedback": 0.40, "count": 4}, "long"),
        ({"ms": 700, "feedback": 0.50, "count": 5}, "echo!"),
    ]

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.config = config_store.load(CONFIG)
        names = list_preset_names()
        self.preset_name = self.config.get("preset", "cathedral")
        if self.preset_name not in names and names:
            self.preset_name = names[0]
        self.preset = self._load_preset(self.preset_name)
        # Track baseline reverb_scale so we know if a regen is needed on save.
        self._baseline_reverb_scale = float(self.preset.get("reverb_scale", 1.0))

        self.preset_dirty = False
        self.config_dirty = False
        self.regen_needed = False

        self.pane = self.PANE_VOICES
        self.row_v = 0
        self.col_v = 0  # 0=gain 1=mioi 2=reverb 3=delay
        self.row_e = 0
        self.row_g = 0   # settings row
        self.row_s = 0

        self.message = ""
        self.message_until = 0

    def _load_preset(self, name):
        return preset_store.load(name, {})

    def status(self, m, dur=2.5):
        self.message = m
        self.message_until = time.time() + dur

    # ---------- data accessors ----------

    def voices(self):
        return list(self.preset.get("voices", {}).items())

    def voice_names(self):
        return list(self.preset.get("voices", {}).keys())

    # Every Claude Code hook event Claudio can sonify — always shown so any
    # event can be mapped even if the preset doesn't define it yet.
    ALL_EVENTS = music.MAPPABLE_EVENTS

    def events_flat(self):
        rows = []
        evmap = self.preset.get("events", {})

        def _emit(ev, spec):
            spec = spec or {}
            rows.append((ev, "default", spec.get("default")))
            for t, v in (spec.get("by_tool") or {}).items():
                rows.append((ev, t, v))
            if "on_failure" in spec:
                rows.append((ev, "on_failure", spec.get("on_failure")))

        for ev in self.ALL_EVENTS:
            _emit(ev, evmap.get(ev))
        for ev, spec in evmap.items():          # any non-canonical extras
            if ev not in self.ALL_EVENTS:
                _emit(ev, spec)
        return rows

    def sessions(self):
        d = load_json(SESSIONS_FILE, {"active": {}}).get("active", {})
        cutoff = time.time() - 4 * 3600
        return sorted(
            ((sid, s) for sid, s in d.items() if s.get("last_seen", 0) > cutoff),
            key=lambda kv: -kv[1].get("last_seen", 0),
        )

    def master_gain(self):
        m = self.config.get("master_gain")
        if m is None:
            m = self.preset.get("master_gain", 0.5)
        return float(m)

    def settings_rows(self):
        """Live list of (label, kind, value_str, slider_or_marker).
        kind ∈ {"float01", "float_reverb", "scale", "songq", "songpick", "bool", "bpm", "grid"}.
        Used for both rendering and ←/→ dispatch.
        """
        cfg = self.config
        preset = self.preset
        rows = []

        master = self.master_gain()
        rows.append(("master gain", "master", master, self._slider(master) + f" {master:.2f}"))

        drone = float(cfg.get("drone_gain", preset.get("drone_gain", 0.0)))
        rows.append(("drone gain", "drone", drone, self._slider(drone) + f" {drone:.2f}"))

        rs = float(preset.get("reverb_scale", 1.0))
        rs_norm = rs / 2.0   # 0..2 scaled to 0..1 slider
        marker = self._slider(rs_norm) + f" {rs:.2f}"
        if abs(rs - self._baseline_reverb_scale) > 1e-3:
            marker += "  ● regen on save"
        rows.append(("reverb scale", "reverb", rs, marker))

        scale_now = cfg.get("scale_override")
        rows.append(("scale override", "scale", scale_now, scale_now or "(off — preset default)"))

        q = cfg.get("quant", {}) or {}
        en = bool(q.get("enabled", False))
        rows.append(("quant", "quant_en", en, "ON" if en else "off"))

        bpm = float(q.get("bpm", 120.0))
        rows.append(("quant bpm", "quant_bpm", bpm, f"{bpm:.1f}"))

        grid = float(q.get("grid", 0.5))
        # find label for this grid
        glabel = next((lbl for v, lbl in self.GRID_PRESETS if abs(v - grid) < 1e-3), f"{grid}")
        rows.append(("quant grid", "quant_grid", grid, glabel))

        # song state — read from state/song.json
        song_state = load_json(paths.SONG_STATE_FILE, {})
        active_song = song_state.get("global")
        rows.append(("active song", "song", active_song, active_song or "(off — Markov picker)"))

        return rows

    def _list_song_names(self):
        d = paths.SONGS_DIR
        if not d.exists(): return []
        return sorted(p.stem for p in d.iterdir() if p.suffix == ".json")

    def _event_delay(self, ev):
        spec = self.preset.get("events", {}).get(ev, {}) or {}
        if not isinstance(spec, dict): return None
        eff = spec.get("effect")
        if not isinstance(eff, dict): return None
        return eff.get("delay")

    # ---------- drawing ----------

    def _slider(self, v, n=10):
        v = max(0.0, min(1.0, v))
        filled = int(round(v * n))
        return "▰" * filled + "▱" * (n - filled)

    def _mioi_bar(self, s, n=8):
        # log scale 0.05..30 sec
        x = max(0.0, min(1.0, math.log10(max(s, 0.05) / 0.05) / math.log10(30 / 0.05)))
        filled = int(round(x * n))
        return "▰" * filled + "▱" * (n - filled)

    def _addstr(self, y, x, s, attr=0):
        """Safe addstr — clip to screen, swallow errors at corners."""
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h: return
        max_w = w - x - 1
        if max_w <= 0: return
        try:
            self.stdscr.addstr(y, x, s[:max_w], attr)
        except curses.error:
            pass

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        # Try to set up a red color pair for the dirty indicator
        try:
            curses.init_pair(1, curses.COLOR_RED, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            red = curses.color_pair(1) | curses.A_BOLD
            green = curses.color_pair(2) | curses.A_BOLD
        except Exception:
            red = curses.A_BOLD
            green = curses.A_BOLD

        # Header
        title = " claudio tune "
        self._addstr(0, 0, title.center(w, "─"), curses.A_BOLD)
        master = self.master_gain()
        is_dirty = self.preset_dirty or self.config_dirty
        sub = (f" preset: {self.preset_name}  "
               f"  master: {self._slider(master)} {master:.2f}")
        self._addstr(1, 1, sub)
        if is_dirty:
            tag = "● MODIFIED — press s to save, q to save+quit"
        else:
            saved_at = getattr(self, "_saved_at", 0)
            if time.time() - saved_at < 3:
                tag = f"✓ saved at {time.strftime('%H:%M:%S', time.localtime(saved_at))}"
            else:
                tag = "  (no changes)"
        # right-align the tag in the header
        x = max(1, w - len(tag) - 2)
        self._addstr(1, x, tag, red if is_dirty else green if "saved" in tag else curses.A_DIM)

        # Voices pane
        y = 3
        attr = curses.A_BOLD | (curses.A_REVERSE if self.pane == self.PANE_VOICES else 0)
        _cols = ["gain", "mioi", "reverb", "delay"]
        col_hint = "  ".join(f"[{c}]" if self.col_v == j else c for j, c in enumerate(_cols))
        header = f" Voices — {col_hint}  (g/t/v/e col · ←→ adjust · r regen) "
        self._addstr(y, 1, header.ljust(w - 2, "─"), attr); y += 1
        now = time.time()
        for i, (name, cfg) in enumerate(self.voices()):
            sel = (self.pane == self.PANE_VOICES and self.row_v == i)
            arrow = "▶" if sel else " "
            gain = cfg.get("gain", 0.5)
            mioi = cfg.get("mioi", 0.5)
            row_attr = curses.A_REVERSE if sel else 0
            # Last-fired indicator: ◉ < 0.5s, ● < 1.5s, ◎ < 3s, · older. Reads
            # the per-voice last-<voice>.txt the event hook touches on every fire.
            try:
                last_path = STATE / self.preset_name / f"last-{name}.txt"
                last_ts = float(last_path.read_text().strip()) if last_path.exists() else 0.0
            except Exception:
                last_ts = 0.0
            age = now - last_ts if last_ts else 1e9
            if   age < 0.5: dot = "◉"
            elif age < 1.5: dot = "●"
            elif age < 3.0: dot = "◎"
            else:           dot = "·"
            rv = cfg.get("reverb")
            wet = rv.get("wet") if isinstance(rv, dict) else None
            rev_str = f"{wet:.2f}" if isinstance(wet, (int, float)) else " · "
            dd = cfg.get("delay")
            dly_str = f"{int(dd['ms'])}ms" if isinstance(dd, dict) and dd.get("ms") else "off"
            def _br(j, txt):  # bracket the focused column

                return f"[{txt}]" if (sel and self.col_v == j) else f" {txt} "
            seg = (f"gain{_br(0, f'{gain:.2f}')} mioi{_br(1, f'{mioi:.2f}s')} "
                   f"rev{_br(2, rev_str)} dly{_br(3, dly_str)}")
            line = f" {arrow} {name:<11} {dot}  {seg}"
            self._addstr(y, 1, line.ljust(w-2), row_attr)
            y += 1
        y += 1

        # Events pane — shows a firing dot per event, the mapped voice, and delay.
        attr = curses.A_BOLD | (curses.A_REVERSE if self.pane == self.PANE_EVENTS else 0)
        self._addstr(y, 1, " Events  (◉ = just fired · d cycles delay) ".ljust(w - 2, "─"), attr); y += 1
        ev_rows = self.events_flat()
        # render with simple scroll if too many rows. The settings pane below
        # eats some space too; leave a budget per pane.
        n_settings = len(self.settings_rows())
        max_e_rows = max(4, h - y - 6 - n_settings - len(self.sessions()))
        start = max(0, self.row_e - max_e_rows + 2) if len(ev_rows) > max_e_rows else 0
        for i in range(start, min(start + max_e_rows, len(ev_rows))):
            ev, key, val = ev_rows[i]
            sel = (self.pane == self.PANE_EVENTS and self.row_e == i)
            arrow = "▶" if sel else " "
            v = "(silent)" if val is None else val
            delay_str = ""
            if key == "default":
                # Activity dot: read the per-event evt-<ev>.txt the hook touches
                # on every fire (mirrors the Voices pane's per-voice dot).
                try:
                    ep = STATE / self.preset_name / f"evt-{ev}.txt"
                    ets = float(ep.read_text().strip()) if ep.exists() else 0.0
                except Exception:
                    ets = 0.0
                eage = now - ets if ets else 1e9
                edot = "◉" if eage < 0.5 else "●" if eage < 1.5 else "◎" if eage < 3.0 else "·"
                indent = f"{edot} "
                label = ev
                d = self._event_delay(ev)
                if d:
                    delay_str = f"  · echo {d.get('ms','?')}ms ×{d.get('count','?')}"
            else:
                indent = "      · "
                label = key
            line = f" {arrow}{indent}{label:<22}→ {v}{delay_str}"
            row_attr = curses.A_REVERSE if sel else 0
            self._addstr(y, 1, line.ljust(w-2), row_attr)
            y += 1
        y += 1

        # Settings pane
        attr = curses.A_BOLD | (curses.A_REVERSE if self.pane == self.PANE_SETTINGS else 0)
        self._addstr(y, 1, " Settings ".ljust(w - 2, "─"), attr); y += 1
        for i, (label, kind, val, marker) in enumerate(self.settings_rows()):
            sel = (self.pane == self.PANE_SETTINGS and self.row_g == i)
            arrow = "▶" if sel else " "
            line = f" {arrow} {label:<16}  {marker}"
            row_attr = curses.A_REVERSE if sel else 0
            self._addstr(y, 1, line.ljust(w-2), row_attr)
            y += 1
        y += 1

        # Sessions pane
        attr = curses.A_BOLD | (curses.A_REVERSE if self.pane == self.PANE_SESSIONS else 0)
        self._addstr(y, 1, " Sessions (last 4h) ".ljust(w - 2, "─"), attr); y += 1
        sessions = self.sessions()
        if not sessions:
            self._addstr(y, 1, "   (no active sessions yet — fire any tool call from any Claude Code terminal)")
            y += 1
        for i, (sid, s) in enumerate(sessions):
            if y >= h - 2: break
            sel = (self.pane == self.PANE_SESSIONS and self.row_s == i)
            arrow = "▶" if sel else " "
            ago = max(0, int((time.time() - s.get("last_seen", 0)) / 60))
            cwd = s.get("cwd", "?")
            short = cwd if len(cwd) <= w - 50 else "…" + cwd[-(w-51):]
            pinned = s.get("preset_pinned")
            tag = "📌pin" if pinned else "    "
            preset = s.get("preset_resolved", "?")
            src = s.get("preset_source", "")
            line = f" {arrow} {sid[:8]} {tag}  {preset:<10}  {ago:>3}m  ({src})  {short}"
            row_attr = curses.A_REVERSE if sel else 0
            self._addstr(y, 1, line.ljust(w-2), row_attr)
            y += 1

        # Message
        if self.message and time.time() < self.message_until:
            self._addstr(h - 2, 1, self.message.ljust(w - 2), curses.A_DIM)

        # Footer — split across two lines so all keys fit at narrower widths
        keys = " TAB pane │ ↑↓ row │ ←→ value │ g/t/v/e col │ SPC play │ m mute │ p preset │ s save │ r regen │ q save+quit │ Q discard "
        self._addstr(h - 1, 0, keys.center(w, "─"), curses.A_BOLD)

        self.stdscr.refresh()

    # ---------- mutations ----------

    def adjust_master(self, delta):
        cur = self.master_gain()
        self.config["master_gain"] = round(max(0.0, min(1.0, cur + delta)), 3)
        self.config_dirty = True

    def adjust_voice(self, voice_idx, col, delta):
        names = self.voice_names()
        if not (0 <= voice_idx < len(names)): return
        v = self.preset["voices"][names[voice_idx]]
        if col == 0:
            v["gain"] = round(max(0.0, min(1.0, v.get("gain", 0.5) + delta * 0.05)), 3)
        elif col == 1:
            cur = v.get("mioi", 0.5)
            factor = 1.2 if delta > 0 else (1.0 / 1.2)
            v["mioi"] = round(max(0.01, min(120.0, cur * factor)), 3)
        elif col == 2:
            # reverb wet is baked at render → flag a regen (press r / save).
            rv = v.setdefault("reverb", {})
            rv["wet"] = round(max(0.0, min(1.0, float(rv.get("wet", 0.0)) + delta * 0.05)), 3)
            self.regen_needed = True
            self.status(f"{names[voice_idx]} reverb {rv['wet']:.2f} — press r to regen", dur=4.0)
        elif col == 3:
            # delay/echo is a live playback effect → no regen needed.
            self._cycle_voice_delay(names[voice_idx], delta)
        self.preset_dirty = True

    def _cycle_voice_delay(self, name, delta):
        """Cycle a voice's live delay/echo through DELAY_PRESETS (no regen)."""
        v = self.preset["voices"].get(name)
        if v is None: return
        cur = v.get("delay")
        idx = 0
        for i, (pv, _) in enumerate(self.DELAY_PRESETS):
            if pv is None and cur is None: idx = i; break
            if cur and isinstance(pv, dict) and cur.get("ms") == pv.get("ms") \
               and cur.get("count") == pv.get("count"): idx = i; break
        nv, label = self.DELAY_PRESETS[(idx + delta) % len(self.DELAY_PRESETS)]
        if nv is None:
            v.pop("delay", None)
        else:
            v["delay"] = dict(nv)
        self.status(f"{name} delay → {label}")

    def cycle_event_voice(self, row, delta):
        rows = self.events_flat()
        if not (0 <= row < len(rows)): return
        ev, key, val = rows[row]
        choices = [None] + self.voice_names()  # None == silent
        try: idx = choices.index(val)
        except ValueError: idx = 0
        new_val = choices[(idx + delta) % len(choices)]
        spec = self.preset["events"].setdefault(ev, {})
        if key == "default":
            spec["default"] = new_val
        elif key == "on_failure":
            spec["on_failure"] = new_val
        else:
            bt = spec.setdefault("by_tool", {})
            if new_val is None: bt.pop(key, None)
            else: bt[key] = new_val
        self.preset_dirty = True

    def mute_event(self, row):
        rows = self.events_flat()
        if not (0 <= row < len(rows)): return
        ev, key, val = rows[row]
        spec = self.preset["events"].setdefault(ev, {})
        if val is None:
            # restore default to first voice
            first = self.voice_names()[0] if self.voice_names() else None
            if first is None: return
            if key == "default":   spec["default"] = first
            elif key == "on_failure": spec["on_failure"] = first
            else: spec.setdefault("by_tool", {})[key] = first
            self.status(f"unmuted {ev}/{key} → {first}")
        else:
            if key == "default":   spec["default"] = None
            elif key == "on_failure": spec["on_failure"] = None
            else: spec.setdefault("by_tool", {}).pop(key, None)
            self.status(f"muted {ev}/{key}")
        self.preset_dirty = True

    def adjust_setting(self, row, delta):
        """Mutates self.config / self.preset for the focused settings row.
        delta is +1 or -1 from arrow keys."""
        rows = self.settings_rows()
        if not (0 <= row < len(rows)): return
        label, kind, val, _ = rows[row]
        if kind == "master":
            self.adjust_master(0.05 * delta)
        elif kind == "drone":
            cur = float(self.config.get("drone_gain", self.preset.get("drone_gain", 0.0)))
            self.config["drone_gain"] = round(max(0.0, min(1.0, cur + 0.05 * delta)), 3)
            self.config_dirty = True
        elif kind == "reverb":
            cur = float(self.preset.get("reverb_scale", 1.0))
            new = round(max(0.0, min(2.0, cur + 0.10 * delta)), 3)
            self.preset["reverb_scale"] = new
            self.preset_dirty = True
            if abs(new - self._baseline_reverb_scale) > 1e-3:
                self.regen_needed = True
            else:
                self.regen_needed = False
        elif kind == "scale":
            choices = [None] + self._scale_names()
            cur = self.config.get("scale_override")
            try: idx = choices.index(cur)
            except ValueError: idx = 0
            new = choices[(idx + delta) % len(choices)]
            if new is None:
                self.config.pop("scale_override", None)
            else:
                self.config["scale_override"] = new
            self.config_dirty = True
        elif kind == "quant_en":
            q = self.config.setdefault("quant", {})
            q["enabled"] = not bool(q.get("enabled", False))
            self.config_dirty = True
        elif kind == "quant_bpm":
            q = self.config.setdefault("quant", {})
            cur = float(q.get("bpm", 120.0))
            step = 5.0 if delta > 0 else -5.0
            q["bpm"] = round(max(30.0, min(300.0, cur + step)), 1)
            self.config_dirty = True
        elif kind == "quant_grid":
            q = self.config.setdefault("quant", {})
            cur = float(q.get("grid", 0.5))
            vals = [v for v, _ in self.GRID_PRESETS]
            try: idx = vals.index(cur)
            except ValueError: idx = vals.index(0.5)
            q["grid"] = vals[(idx + delta) % len(vals)]
            self.config_dirty = True
        elif kind == "song":
            choices = [None] + self._list_song_names()
            sf = paths.SONG_STATE_FILE
            song_state = load_json(sf, {})
            cur = song_state.get("global")
            try: idx = choices.index(cur)
            except ValueError: idx = 0
            new = choices[(idx + delta) % len(choices)]
            if new is None:
                song_state.pop("global", None)
            else:
                song_state["global"] = new
                song_state.setdefault("positions", {}).setdefault(new, 0)
            save_json(sf, song_state)
            self.status(f"song → {new or '(off)'}")

    def cycle_event_delay(self, row, delta=1):
        """'d' key cycles through DELAY_PRESETS for the selected event row.
        Delay is keyed on the event NAME (not by-tool / on_failure), so we
        ignore non-default rows by walking up to the parent event."""
        rows = self.events_flat()
        if not (0 <= row < len(rows)): return
        ev, key, val = rows[row]
        # Find or create the event spec
        spec = self.preset.setdefault("events", {}).setdefault(ev, {"default": None})
        if not isinstance(spec, dict):
            spec = {"default": spec}
            self.preset["events"][ev] = spec
        cur = self._event_delay(ev)
        # Find current index in DELAY_PRESETS
        cur_idx = 0
        for i, (preset_val, _) in enumerate(self.DELAY_PRESETS):
            if cur == preset_val:
                cur_idx = i; break
            if cur and isinstance(preset_val, dict) and \
               cur.get("ms") == preset_val.get("ms") and \
               cur.get("count") == preset_val.get("count"):
                cur_idx = i; break
        new_idx = (cur_idx + delta) % len(self.DELAY_PRESETS)
        new_val, new_label = self.DELAY_PRESETS[new_idx]
        if new_val is None:
            if "effect" in spec and "delay" in spec["effect"]:
                spec["effect"].pop("delay", None)
                if not spec["effect"]:
                    spec.pop("effect", None)
        else:
            spec.setdefault("effect", {})["delay"] = dict(new_val)
        self.preset_dirty = True
        self.status(f"{ev} delay → {new_label}")

    def trigger_regen(self):
        """Run `python3 presets/<preset>/render.py` in the background. Tells the
        user to wait. Used to apply reverb_scale changes after save."""
        rp = preset_store.render_path(self.preset_name)
        if rp is None or not rp.exists():
            self.status("no render.py for this preset"); return
        self.status(f"regenerating {self.preset_name} samples (background)...", dur=8.0)
        try:
            audio.spawn_python(rp, detached=True,
                               env=preset_store.renderer_env(self.preset_name))
        except Exception as e:
            self.status(f"regen failed: {e}")
            return
        self.regen_needed = False
        self._baseline_reverb_scale = float(self.preset.get("reverb_scale", 1.0))

    def cycle_session_pin(self, row, delta):
        sessions = self.sessions()
        if not (0 <= row < len(sessions)): return
        sid, s = sessions[row]
        choices = [None] + list_preset_names()
        cur = s.get("preset_pinned")
        try: idx = choices.index(cur)
        except ValueError: idx = 0
        new = choices[(idx + delta) % len(choices)]
        def mutate(d):
            if sid not in d.get("active", {}): return
            if new is None:
                d["active"][sid].pop("preset_pinned", None)
            else:
                d["active"][sid]["preset_pinned"] = new
        stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate)
        self.status(f"unpinned {sid[:8]}" if new is None else f"pinned {sid[:8]} → {new}")

    def cycle_preset(self):
        names = list_preset_names()
        if not names: return
        if self.preset_dirty:
            self.status("save (s) or discard your edits before switching presets")
            return
        try: idx = names.index(self.preset_name)
        except ValueError: idx = 0
        new = names[(idx + 1) % len(names)]
        self.preset_name = new
        self.preset = self._load_preset(new)
        self._baseline_reverb_scale = float(self.preset.get("reverb_scale", 1.0))
        self.regen_needed = False
        self.config["preset"] = new
        self.config.pop("master_gain", None)
        self.config_dirty = True
        self.row_v = self.row_e = self.row_g = self.row_s = 0
        self.status(f"preset → {new}")

    def play_voice(self, voice):
        v_cfg = self.preset.get("voices", {}).get(voice)
        if not v_cfg:
            self.status(f"no voice '{voice}'"); return
        samples = list_samples(self.preset_name, v_cfg.get("dir", voice))
        if not samples:
            self.status(f"no samples for {voice}"); return
        gain = v_cfg.get("gain", 0.5) * self.master_gain()
        gain = max(0.0, min(1.0, gain))
        sample = random.choice(samples)
        try:
            audio.play_simple(sample, gain)
            self.status(f"play {voice} ({sample.name})")
        except Exception as e:
            self.status(f"play failed: {e}")

    def fire_event_voice(self, row):
        rows = self.events_flat()
        if not (0 <= row < len(rows)): return
        ev, key, val = rows[row]
        if val is None:
            self.status(f"{ev}/{key} is silent"); return
        self.play_voice(val)

    def save(self):
        wrote = []
        if self.preset_dirty:
            preset_store.save(self.preset_name, self.preset)
            self.preset_dirty = False
            wrote.append(f"presets/{self.preset_name}/preset.json")
        if self.config_dirty:
            config_store.save(self.config, CONFIG)
            self.config_dirty = False
            wrote.append("config.json")
        self._saved_at = time.time()
        if wrote:
            msg = f"✓ saved {' + '.join(wrote)}"
            if self.regen_needed:
                msg += "  · reverb changed — press r to regen"
            self.status(msg, dur=4.0)
        else:
            self.status("nothing to save")

    # ---------- key dispatch ----------

    def handle(self, key):
        if key == -1:
            return True  # timeout/refresh
        # 'q' = save + quit (always exits)
        if key == ord('q'):
            if self.preset_dirty or self.config_dirty:
                self.save()
            return False
        # 'Q' = quit WITHOUT saving (capital)
        if key == ord('Q'):
            return False
        # ESC = save + quit (same as q)
        if key == 27:
            if self.preset_dirty or self.config_dirty:
                self.save()
            return False
        if key == ord('\t'):
            self.pane = (self.pane + 1) % self.N_PANES; return True
        if key in (curses.KEY_BTAB,):
            self.pane = (self.pane - 1) % self.N_PANES; return True
        if key == ord('s'): self.save(); return True
        if key == ord('r'): self.trigger_regen(); return True
        if key == ord('p'): self.cycle_preset(); return True
        if key == ord('m') and self.pane == self.PANE_EVENTS:
            self.mute_event(self.row_e); return True
        if key == ord('d') and self.pane == self.PANE_EVENTS:
            self.cycle_event_delay(self.row_e, +1); return True

        if key == curses.KEY_UP:
            if   self.pane == self.PANE_VOICES:   self.row_v = max(0, self.row_v - 1)
            elif self.pane == self.PANE_EVENTS:   self.row_e = max(0, self.row_e - 1)
            elif self.pane == self.PANE_SETTINGS: self.row_g = max(0, self.row_g - 1)
            elif self.pane == self.PANE_SESSIONS: self.row_s = max(0, self.row_s - 1)
            return True
        if key == curses.KEY_DOWN:
            if self.pane == self.PANE_VOICES:
                self.row_v = min(max(0, len(self.voices()) - 1), self.row_v + 1)
            elif self.pane == self.PANE_EVENTS:
                self.row_e = min(max(0, len(self.events_flat()) - 1), self.row_e + 1)
            elif self.pane == self.PANE_SETTINGS:
                self.row_g = min(max(0, len(self.settings_rows()) - 1), self.row_g + 1)
            elif self.pane == self.PANE_SESSIONS:
                self.row_s = min(max(0, len(self.sessions()) - 1), self.row_s + 1)
            return True
        if key == curses.KEY_LEFT:
            if   self.pane == self.PANE_VOICES:   self.adjust_voice(self.row_v, self.col_v, -1)
            elif self.pane == self.PANE_EVENTS:   self.cycle_event_voice(self.row_e, -1)
            elif self.pane == self.PANE_SETTINGS: self.adjust_setting(self.row_g, -1)
            elif self.pane == self.PANE_SESSIONS: self.cycle_session_pin(self.row_s, -1)
            return True
        if key == curses.KEY_RIGHT:
            if   self.pane == self.PANE_VOICES:   self.adjust_voice(self.row_v, self.col_v, +1)
            elif self.pane == self.PANE_EVENTS:   self.cycle_event_voice(self.row_e, +1)
            elif self.pane == self.PANE_SETTINGS: self.adjust_setting(self.row_g, +1)
            elif self.pane == self.PANE_SESSIONS: self.cycle_session_pin(self.row_s, +1)
            return True
        if key == ord('g') and self.pane == self.PANE_VOICES:
            self.col_v = 0; return True
        if key == ord('t') and self.pane == self.PANE_VOICES:
            self.col_v = 1; return True
        if key == ord('v') and self.pane == self.PANE_VOICES:
            self.col_v = 2; return True
        if key == ord('e') and self.pane == self.PANE_VOICES:
            self.col_v = 3; return True
        if key in (ord(','), ord('-'), ord('_')):
            self.adjust_master(-0.05); return True
        if key in (ord('.'), ord('+'), ord('=')):
            self.adjust_master(+0.05); return True
        if key == ord(' '):
            if self.pane == self.PANE_VOICES:
                names = self.voice_names()
                if 0 <= self.row_v < len(names):
                    self.play_voice(names[self.row_v])
            elif self.pane == self.PANE_EVENTS:
                self.fire_event_voice(self.row_e)
            return True
        return True

    def run(self):
        curses.curs_set(0)
        try:
            curses.start_color(); curses.use_default_colors()
        except Exception: pass
        # 500ms timeout so the UI auto-refreshes (sessions panel is live)
        self.stdscr.timeout(500)
        while True:
            self.draw()
            try: key = self.stdscr.getch()
            except KeyboardInterrupt: key = ord('q')
            if not self.handle(key):
                break

def main():
    if curses is None:
        print("`claudio tune` (curses TUI) needs the curses module.\n"
              "On Windows:  pip install windows-curses\n"
              "Or use the web console instead:  claudio web", file=sys.stderr)
        sys.exit(2)
    if not sys.stdout.isatty():
        print("claudio tune requires an interactive terminal", file=sys.stderr)
        sys.exit(2)
    curses.wrapper(lambda s: TuneUI(s).run())

if __name__ == "__main__":
    main()
