#!/usr/bin/env python3
"""
Claudio Symphony — preset-aware hook entry with per-session routing.

Reads JSON from stdin, resolves the preset to use for this event using
(in order):
  1. explicit pin on this session_id (state/sessions.json)
  2. first-matching cwd rule (state/rules.json)
  3. global default (config.json -> preset)

Then maps the event through the preset's mapping table, applies per-voice
MIOI rate-limiting + pressure accumulation, and launches the audio backend
(audio.py) detached — afplay on macOS, ffplay/etc. on Linux/Windows.

Always exits 0.
"""
import sys, os, json, time, fnmatch, random, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import song as song_mod  # noqa: E402  (sibling module, must come after sys.path)
    import audio  # noqa: E402  (cross-platform playback backend; same path insert)
    import timeline as timeline_mod  # noqa: E402  (owns the timeline dir + safe_sid; reader must match this writer)
    import stateio  # noqa: E402  (cross-process JSON transactions)
    import config_store  # noqa: E402
    import music  # noqa: E402
    import paths  # noqa: E402
    import preset_store  # noqa: E402
    PRESETS = paths.BUILTIN_PRESETS_DIR
    STATE = paths.STATE_DIR
    LOGS = paths.LOG_DIR
    CONFIG = paths.CONFIG_FILE
    SESSIONS_FILE = paths.SESSIONS_FILE
    RULES_FILE = paths.RULES_FILE
    LOG = LOGS / "event.log"
    TIMELINE = timeline_mod.TIMELINE                      # shared with timeline.py so writer/reader can't drift
    STATE.mkdir(parents=True, exist_ok=True); LOGS.mkdir(parents=True, exist_ok=True)
except Exception:
    # As a hook, a broken install/unwritable data dir must stay silent: any
    # traceback would surface in Claude's hook output. Importers still see it.
    if __name__ != "__main__":
        raise
    sys.exit(0)
TIMELINE_MAX_EVENTS = 20000                          # cap a marathon session's file growth
TIMELINE_KEEP_DAYS = 14                              # replayable history; pruned lazily
TIMELINE_KEEP_FILES = 200
LOG_MAX_BYTES = 1 << 20                              # rotate event.log -> event.log.1
# Hook budget is ~1s: wait briefly for hot-path locks, reclaim orphans fast.
LOCK_KW = {"timeout": stateio.HOT_TIMEOUT, "stale_after": stateio.HOT_STALE_AFTER}

DEFAULT_PRESET = "meadow"
SESSION_TTL_S = 4 * 3600   # prune sessions idle longer than this

def log(msg):
    try:
        try:
            if LOG.stat().st_size > LOG_MAX_BYTES:
                os.replace(str(LOG), str(LOG.with_name(LOG.name + ".1")))
        except OSError:
            pass
        with LOG.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

# ---------- session timeline capture (symbolic; audio capture lives in audio.py) ----------

def _timeline_log(session, event, tool, fail):
    """Always-on: append one compact line per handled event to this session's
    score. This is the cheap symbolic timeline (no audio) that powers replay,
    the heavy-traffic sparkline, and shareable .score.json exports. One atomic
    O_APPEND of a sub-PIPE_BUF line, so concurrent hook processes never clobber."""
    sid = timeline_mod.safe_sid(session)
    if not sid:
        return
    try:
        TIMELINE.mkdir(parents=True, exist_ok=True)
        f = TIMELINE / f"{sid}.ndjson"
        try:
            if f.exists() and f.stat().st_size > TIMELINE_MAX_EVENTS * 48:
                return            # marathon session — stop growing the file
        except Exception:
            pass
        rec = {"t": round(time.time(), 3), "e": event}
        if tool: rec["tool"] = tool
        if fail: rec["f"] = 1
        with f.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass

# ---------- atomic JSON helpers ----------

def _load(p, default):
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return default

def _save(p, d):
    stateio.save_json(p, d, indent=2, newline=False)

def read_config(): return config_store.load(CONFIG)

def root_offset(cfg=None):
    """Global live transpose in semitones off A (the rendered root), clamped to
    a tritone. Set by the web mic-jam mode / `claudio root`; 0 = shipped A=432."""
    if cfg is None: cfg = read_config()
    try: n = int(round(float(cfg.get("root_offset", 0) or 0)))
    except (TypeError, ValueError): return 0
    return max(-6, min(6, n))
def load_sessions(): return _load(SESSIONS_FILE, {"active": {}})
def save_sessions(d): _save(SESSIONS_FILE, d)
def load_rules(): return _load(RULES_FILE, {"rules": []})

def active_preset_name():
    return read_config().get("preset", DEFAULT_PRESET)

def load_preset(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
        log(f"invalid preset name: {name!r}")
        return None
    p = preset_store.preset_path(name)
    if p is None:
        log(f"preset.json missing for {name}")
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        log(f"preset {name} parse error: {e}")
        return None

def ensure_rendered(name):
    """True if `name`'s samples exist (ready to play). Samples are generated,
    not shipped, so the first time a preset is needed without them we kick ONE
    detached render (via audio, which uses the running interpreter) and return
    False so this event stays silent — later events play once it lands. Fast
    path scans for a WAV before treating the preset as ready; the marker remains
    diagnostic state rather than a potentially stale source of truth."""
    sd = preset_store.sample_read_dir(name)
    sdir = preset_state_dir(name)
    if sd.is_dir() and next(sd.rglob("*.wav"), None) is not None:
        marker = sdir / ".rendered"
        if not marker.exists():
            try: marker.write_text("1")
            except Exception: pass
        return True
    # no samples — start one render, guarded so we don't respawn every event.
    # The guard is time-based: if a prior render didn't produce samples within
    # ~90s (it crashed, e.g. numpy wasn't installed yet), we retry — so once
    # numpy lands the bed renders without needing a fresh session.
    spawn_mark = sdir / ".rendering"
    try:
        with stateio.file_lock(spawn_mark, **LOCK_KW):
            try:
                fresh = spawn_mark.exists() and (time.time() - float(spawn_mark.read_text() or 0) < 90)
            except Exception:
                fresh = spawn_mark.exists()
            if not fresh:
                render = preset_store.render_path(name)
                if render is None:
                    return False
                spawn_mark.write_text(str(time.time()))
                audio.spawn_python(str(render), cwd=str(HERE), detached=True,
                                   env=preset_store.renderer_env(name))
    except Exception as e:
        log(f"render spawn failed for {name}: {e}")
    return False

def preset_state_dir(name):
    d = STATE / name
    d.mkdir(parents=True, exist_ok=True)
    return d

# ---------- preset resolution ----------

def _norm_path(p):
    """Compare paths the same way on every OS: Windows case-folding and
    backslashes (C:\\Users\\Me) become forward slashes on both sides."""
    return os.path.normcase(str(p)).replace("\\", "/")

def cwd_rule_match(cwd, pattern):
    """Glob if pattern has wildcards; otherwise prefix match on path components.
    Empty/missing pattern matches any cwd (for time-only or idle-only rules)."""
    if not pattern or pattern == "*":
        return True
    cwd, pattern = _norm_path(cwd or ""), _norm_path(pattern)
    if any(c in pattern for c in "*?["):
        return fnmatch.fnmatchcase(cwd, pattern)
    pat = pattern.rstrip("/")
    return cwd == pat or cwd.startswith(pat + "/")

def _parse_hhmm(s):
    """Parse 'HH:MM' → minutes since midnight; None on bad input."""
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None

def _in_time_window(now, window):
    """`window` is 'HH:MM-HH:MM'. End-before-start means overnight (e.g.,
    21:00-09:00 spans midnight). Match precision is the minute, not the second
    — avoids second-boundary flapping when bursts straddle the rule edge."""
    try:
        start_s, end_s = window.split("-")
    except ValueError:
        return False
    start = _parse_hhmm(start_s.strip())
    end = _parse_hhmm(end_s.strip())
    if start is None or end is None:
        return False
    cur = now.hour * 60 + now.minute
    if start == end:
        return False
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end

def _idle_match(idle_after_s):
    """Return True if last hook event was longer than `idle_after_s` ago,
    using the heartbeat file already written on every event."""
    try:
        hb = (STATE / "heartbeat").read_text().strip()
        return (time.time() - float(hb)) >= float(idle_after_s)
    except Exception:
        # No heartbeat file yet — consider the system idle (covers fresh installs).
        return True

def _rule_match(rule, cwd, now_dt):
    """All conditions on a rule are AND-combined. Empty rule → always matches."""
    pat = rule.get("pattern", "")
    if pat and not cwd_rule_match(cwd, pat):
        return False
    if "time" in rule and not _in_time_window(now_dt, rule["time"]):
        return False
    if "idle_after_s" in rule and not _idle_match(rule["idle_after_s"]):
        return False
    return True

def resolve_preset(session_id, cwd):
    sessions = load_sessions().get("active", {})
    sess = sessions.get(session_id, {})
    if sess.get("preset_pinned"):
        return sess["preset_pinned"], "pin"
    import datetime
    now_dt = datetime.datetime.now()
    for r in load_rules().get("rules", []):
        if _rule_match(r, cwd or "", now_dt):
            tag = r.get("pattern") or "*"
            extras = []
            if "time" in r: extras.append(f"time={r['time']}")
            if "idle_after_s" in r: extras.append(f"idle={r['idle_after_s']}s")
            label = ",".join([tag] + extras) if extras else tag
            return r.get("preset"), f"rule:{label}"
    return active_preset_name(), "default"

def update_session_record(session_id, cwd, event_name, resolved_preset, source):
    if not session_id:
        return
    pruned = []
    def mutate(sessions):
        active = sessions.setdefault("active", {})
        cutoff = time.time() - SESSION_TTL_S
        pruned.clear()
        for sid in list(active.keys()):
            if active[sid].get("last_seen", 0) < cutoff and sid != session_id:
                # Timelines outlive the session record (replay history); they
                # are aged out separately by prune_timelines().
                del active[sid]
                pruned.append(sid)
        rec = active.setdefault(session_id, {})
        now = time.time()
        rec.setdefault("first_seen", now)
        rec["last_seen"] = now
        if cwd: rec["cwd"] = cwd
        rec["preset_resolved"] = resolved_preset
        rec["preset_source"] = source
        if event_name == "SessionEnd":
            rec["ended"] = True
    try: committed = stateio.update_json(SESSIONS_FILE, {"active": {}}, mutate, **LOCK_KW)
    except Exception as e:
        log(f"sessions write: {e}")
        return
    if pruned:   # rare (once per expired session) — a cheap moment to age timelines
        prune_timelines(keep=committed.get("active", {}).keys())

def prune_timelines(keep=(), now=None):
    """Drop session scores older than TIMELINE_KEEP_DAYS and cap the directory
    at the newest TIMELINE_KEEP_FILES. Sessions still in sessions.json (live or
    pinned) are never pruned."""
    now = time.time() if now is None else now
    keep = {timeline_mod.safe_sid(s) for s in keep}
    try:
        files = []
        for f in TIMELINE.glob("*.ndjson"):
            if f.stem in keep:
                continue
            try: files.append((f.stat().st_mtime, f))
            except OSError: pass
    except OSError:
        return
    files.sort(key=lambda mf: mf[0], reverse=True)
    cutoff = now - TIMELINE_KEEP_DAYS * 86400
    for i, (mtime, f) in enumerate(files):
        if mtime < cutoff or i >= TIMELINE_KEEP_FILES:
            try: f.unlink()
            except OSError: pass

# ---------- sample selection + playback ----------

_SAMPLES_CACHE = {}   # (preset, voice_dir) -> (dir_mtime, [paths])

def list_samples(preset_name, voice_dir):
    """Sorted .wav paths for a voice, memoized by the sample dir's mtime. The
    per-hook process calls this once (negligible), but the jukebox/replay loops
    call it per note — caching avoids re-scanning the directory every note.
    Keyed on dir mtime so adding/removing samples invalidates; a regen that
    rewrites same-named WAVs keeps paths valid (audio reads content at play time)."""
    d = preset_store.sample_asset(preset_name, str(voice_dir))
    try:
        mtime = d.stat().st_mtime
    except OSError:
        return []
    key = (preset_name, voice_dir)
    hit = _SAMPLES_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    samples = sorted(p for p in d.iterdir() if p.suffix == ".wav")
    _SAMPLES_CACHE[key] = (mtime, samples)
    return samples

# ---------- melodic picker ----------
#
# Replaces simple round-robin with a Markov-weighted shuffled bag that
# parses midi from filenames "NN_m{midi}.wav". Successive picks favor
# stepwise motion (2nds, 3rds), occasional skips (5ths, 6ths), and every
# ~7 notes drift toward A or E to land a phrase. Result: the sequence
# sounds like an actual melody wandering through the scale, never repeats
# the same pitch back-to-back, and never produces the literal ascending
# scale that pure round-robin gives.

_MIDI_PATTERN = re.compile(r'_m(\d+)\.wav$')

# Weight by interval (semitones) from previous pitch. Tuned for both the
# pentatonic and Lydian voices in the shipped presets — prefers stepwise,
# allows musical leaps, never repeats, never tritones (which won't occur
# in our scales anyway but defensive).
# Pitch-class scales for per-session overrides. Each entry is (pcs, roots).
# pcs = which pitch classes (mod 12) belong to this scale.
# roots = preferred phrase landings (typically tonic + dominant).
# All A-rooted so switching mid-session stays continuous with the shipping presets.
SCALES = music.SCALES
CHORDS = music.CHORDS
PROGRESSIONS = music.PROGRESSIONS
chord_step = music.chord_step

def resolve_chord():
    """Returns (pcs, roots, label) for the chord that's live right now, or
    (None, None, None) when no progression is enabled. Roots = chord root +
    fifth so phrase landings stay chordal but not monotonous."""
    prog = read_config().get("progression") or {}
    if not prog.get("enabled"): return None, None, None
    _, label = chord_step(prog)
    if not label: return None, None, None
    c = CHORDS.get(label)
    if not c: return None, None, None
    pcs, root = c
    return list(pcs), [root, (root + 7) % 12], label


def resolve_scale(session_id):
    """Returns (pcs, roots) or (None, None). Resolution: session pin > config > none.
    Preset's scale_pitches/phrase_roots are used as default — we only return non-None
    when an explicit override is set."""
    if session_id:
        sess = load_sessions().get("active", {}).get(session_id, {})
        name = sess.get("scale_override")
        if name and name in SCALES:
            return SCALES[name] + (name,)
    name = read_config().get("scale_override")
    if name and name in SCALES:
        return SCALES[name] + (name,)
    return None, None, None


expand_pcs_to_midis = music.expand_pcs_to_midis

_INTERVAL_WEIGHTS = {
    0: 0.00,   # exact repeat — never
    1: 0.20,   # minor 2nd — awkward in major-family scales
    2: 1.50,   # major 2nd — favored (scale step)
    3: 1.40,   # minor 3rd — favored
    4: 1.20,   # major 3rd
    5: 1.00,   # perfect 4th
    6: 0.00,   # tritone — never
    7: 1.00,   # perfect 5th — meaningful leap, not default step (was 1.40, lowered after review)
    8: 0.40,   # minor 6th — uncommon in pentatonic
    9: 1.10,   # major 6th
    10: 0.30,  # minor 7th
    11: 0.20,  # major 7th
    12: 0.80,  # octave — fine
}

def _normalize_weights(raw):
    """JSON dict has str keys; convert to int-keyed for interval lookup."""
    if not raw: return None
    try:
        return {int(k): float(v) for k, v in raw.items()}
    except (ValueError, TypeError):
        return None

def _interval_weight(prev_midi, next_midi, table=None):
    table = table or _INTERVAL_WEIGHTS
    interval = abs(next_midi - prev_midi)
    if interval == 0:
        return 0.0
    if interval > 12:
        base = table.get(interval % 12, 0.5)
        oct_jumps = interval // 12
        return base * (0.7 ** (oct_jumps - 1))   # bigger leap, smaller weight
    return table.get(interval, 0.5)

def _parse_midi(filename):
    m = _MIDI_PATTERN.search(filename)
    return int(m.group(1)) if m else None

def _melody_state_file(preset_name, voice):
    return preset_state_dir(preset_name) / f"melody-{voice}.json"

def _load_state(p):
    return stateio.load_json(p, {})

def _save_state(p, d):
    stateio.save_json(p, d, indent=None, newline=False)

def _nearest_pitched(pitched, target_midi):
    """pitched = [(midi, path), ...]; return (path, semitone_shift) for the
    sample whose midi is closest to target. Shift is target-sample so playback
    rate = 2**(shift/12) lands the chosen sample on the requested pitch."""
    best = min(pitched, key=lambda mp: abs(mp[0] - target_midi))
    return best[1], target_midi - best[0]


def _markov_pitch(candidates, state, weight_table, roots):
    """Pick a target MIDI from `candidates` using the same Markov weighting
    + phrase-landing logic as the main picker. Returns (chosen_midi, updated_state).
    Used by the pitched mode AND by the tonal-overlay mode for unpitched voices
    (wood/bird/mokugyo) that get rate-shifted onto scale pitches."""
    last = state.get("last_pitches", [])
    phrase = state.get("phrase_count", 0)
    weights = []
    for midi in candidates:
        w = 1.0
        for i, recent in enumerate(reversed(last[-3:])):
            if midi == recent:
                w *= (0.05, 0.30, 0.55)[min(i, 2)]
        if last:
            w *= _interval_weight(last[-1], midi, weight_table)
        if phrase >= 6:
            pc = midi % 12
            if len(roots) > 0 and pc == roots[0]: w *= 2.5
            elif len(roots) > 1 and pc == roots[1]: w *= 2.0
            elif len(roots) > 2 and pc == roots[2]: w *= 1.6
        weights.append(w)
    total = sum(weights)
    if total <= 0:
        idx = random.randrange(len(candidates))
    else:
        r = random.random() * total
        acc = 0.0
        idx = len(candidates) - 1
        for i, w in enumerate(weights):
            acc += w
            if acc >= r:
                idx = i; break
    chosen = int(candidates[idx])
    new_last = (last + [chosen])[-4:]
    landed = (phrase >= 6) and (chosen % 12 in roots)
    new_phrase = 0 if landed else phrase + 1
    return chosen, {"last_pitches": new_last, "phrase_count": new_phrase}


def melodic_pick(preset_name, voice, voice_dir, song_name=None,
                  interval_weights=None, phrase_roots=None,
                  scale_pitches=None, tonal_anchor=None, tonal_range=12,
                  scale_override_pcs=None, scale_override_roots=None):
    """Pick the next sample for this voice. Returns (sample_path, shift_semitones).
    shift_semitones is non-zero only in song mode for chromatic transposition.

    Three modes:
      - **song mode** (`song_name` is set): pulls the next note from that
        song's pointer; nearest sample is chosen and the residual is corrected
        via afplay -r so playback lands on the requested pitch.
      - **Markov mode** (default): stepwise motion, occasional leaps, phrase
        landings, no immediate repeats.
      - **bag mode**: voices whose samples don't carry midi in filenames just
        get a shuffled bag (cluster, sparkle, bloom, swell, breath, wood, etc.).

    `interval_weights`: optional per-preset semitone→weight dict (already
        normalized to int keys). Falls back to the global `_INTERVAL_WEIGHTS`.
    `phrase_roots`: optional list of pitch classes that the picker pulls
        toward when a phrase has run ~7 notes. Defaults to [9, 4] (A, E).
    """
    weight_table = interval_weights or _INTERVAL_WEIGHTS
    # Phrase roots: scale override wins over preset default.
    roots = scale_override_roots or phrase_roots or [9, 4]
    # Scale-pitches for tonal-overlay voices: scale override expands to a midi
    # list within the preset's existing scale range; otherwise use preset's
    # scale_pitches as-is.
    if scale_override_pcs is not None:
        if scale_pitches:
            low, high = min(scale_pitches), max(scale_pitches)
        else:
            low, high = 57, 88
        scale_pitches = expand_pcs_to_midis(scale_override_pcs, low, high)
    samples = list_samples(preset_name, voice_dir)
    if not samples: return None, 0

    pitched = []
    for s in samples:
        m = _parse_midi(s.name)
        if m is not None: pitched.append((m, s))

    # Scale override: filter pitched bag to only midis whose pitch class is in
    # the override scale. Falls through to unfiltered if no in-scale samples
    # exist (rather than going silent).
    if pitched and scale_override_pcs is not None:
        in_scale = [(m, p) for m, p in pitched if m % 12 in scale_override_pcs]
        if in_scale:
            pitched = in_scale

    # Song-mode override: a MIDI file is driving the melody. Each voice trigger
    # advances that song's pointer by one note. Voices share the song.
    if pitched and song_name and song_mod.has_song(song_name):
        target = song_mod.next_note(song_name)
        if target is not None:
            return _nearest_pitched(pitched, int(target))

    state_file = _melody_state_file(preset_name, voice)
    # The selection and state advance are one transaction.  Without holding
    # the lock across both, simultaneous hooks can choose the same bag entry
    # and overwrite each other's phrase history even with atomic file writes.
    with stateio.edit_json(state_file, {}, indent=None, newline=False, **LOCK_KW) as state:
        # Tonal-overlay mode for unpitched voices: a noise-burst voice (wood,
        # bird, mokugyo) opts in by setting `tonal_anchor_midi` in preset.json.
        if not pitched and tonal_anchor is not None and scale_pitches:
            anchor = int(tonal_anchor)
            rng = int(tonal_range) if tonal_range else 12
            candidates = [p for p in scale_pitches if abs(int(p) - anchor) <= rng]
            if not candidates:
                candidates = list(scale_pitches)
            bag = state.get("bag", [])
            if not bag or any(b >= len(samples) for b in bag):
                bag = list(range(len(samples)))
                random.shuffle(bag)
            sample_idx = bag[0]
            target, mstate = _markov_pitch(candidates, state, weight_table, roots)
            state.clear()
            state.update({"bag": bag[1:], **mstate})
            return samples[sample_idx], target - anchor

        # Unpitched voice without tonal-overlay (cluster, sparkle, bloom, etc.).
        if not pitched:
            bag = state.get("bag", [])
            if not bag or any(b >= len(samples) for b in bag):
                bag = list(range(len(samples)))
                random.shuffle(bag)
            chosen = bag[0]
            state.clear()
            state["bag"] = bag[1:]
            return samples[chosen], 0

        # Pitched voice — Markov-weighted pick from the shuffled bag.
        last = state.get("last_pitches", [])
        bag = state.get("bag", [])
        phrase = state.get("phrase_count", 0)
        if not bag or any(b >= len(pitched) for b in bag):
            bag = list(range(len(pitched)))
            random.shuffle(bag)

        weights = []
        for idx in bag:
            midi, _ = pitched[idx]
            w = 1.0
            for i, recent in enumerate(reversed(last[-3:])):
                if midi == recent:
                    w *= (0.05, 0.30, 0.55)[min(i, 2)]
            if last:
                w *= _interval_weight(last[-1], midi, weight_table)
            if phrase >= 6:
                pc = midi % 12
                if len(roots) > 0 and pc == roots[0]: w *= 2.5
                elif len(roots) > 1 and pc == roots[1]: w *= 2.0
                elif len(roots) > 2 and pc == roots[2]: w *= 1.6
            weights.append(w)

        total = sum(weights)
        if total <= 0:
            chosen_bag_idx = random.randrange(len(bag))
        else:
            r = random.random() * total
            acc = 0.0
            chosen_bag_idx = len(bag) - 1
            for i, w in enumerate(weights):
                acc += w
                if acc >= r:
                    chosen_bag_idx = i
                    break

        sample_idx = bag[chosen_bag_idx]
        midi, sample = pitched[sample_idx]
        new_bag = bag[:chosen_bag_idx] + bag[chosen_bag_idx+1:]
        new_last = (last + [midi])[-4:]
        landed = (phrase >= 6) and (midi % 12 in roots)
        state.clear()
        state.update({
            "last_pitches": new_last,
            "bag": new_bag,
            "phrase_count": 0 if landed else phrase + 1,
        })
        return sample, 0

# Backward-compat alias — older code paths may still reference round_robin_pick
def round_robin_pick(preset_name, voice, voice_dir):
    return melodic_pick(preset_name, voice, voice_dir)

def check_mioi(preset_name, voice, mioi_s):
    sd = preset_state_dir(preset_name)
    last_file = sd / f"last-{voice}.txt"
    pressure_file = sd / f"pressure-{voice}.txt"
    # Serialize the timestamp + pressure pair: these are one logical state
    # transition and hooks for the same voice routinely overlap.
    with stateio.file_lock(last_file, **LOCK_KW):
        now = time.time()
        try: last = float(last_file.read_text().strip())
        except Exception: last = 0.0
        if now - last < mioi_s:
            try: p = int(pressure_file.read_text().strip())
            except Exception: p = 0
            pressure_file.write_text(str(p + 1))
            return False, 0.0
        try: p = int(pressure_file.read_text().strip())
        except Exception: p = 0
        pressure_file.write_text("0")
        last_file.write_text(str(now))
        pressure_db = min(3.0, 0.5 * p)
        return True, pressure_db

def play(sample_path, gain_linear, shift_semitones=0, delay_s=0.0,
          rate_jitter=False, echo=None):
    """Launch a detached play via the cross-platform backend (audio.play).
    `shift_semitones` triggers a playback-rate shift (afplay's -r on macOS,
    the equivalent on other players) so song-mode notes land on the requested
    pitch even when the nearest sampled pitch is off. `delay_s` (used by
    quantization) defers playback via a detached sleep-trampoline so the hook
    returns immediately and the play lands on the next grid boundary.
    `rate_jitter` adds ±0.4% (≈±7 cents) of pitch wobble — below conscious
    pitch perception, but the ear reads it as 'this is alive' rather than
    'mechanical recall'. Opt-in per voice via preset.json `rate_jitter: true`.
    NEVER enable on bell/bowl/pad/bloom/sparkle/drone — sustained voices accumulate
    audible drift, and chord-based voices beat against each other.

    `echo` is an optional dict {ms, feedback, count} that spawns N additional
    afplay copies at decreasing gain spaced by `ms` — gives a feedback-delay
    feel at trigger time WITHOUT re-rendering. Per-event-mapping, so different
    alert types (Stop, SubagentStop, Notification) can have different echoes."""
    # All afplay/-r/-v/sh-trampoline/echo mechanics now live in audio.py so
    # the same call works on macOS, Linux, and Windows. The musical math
    # (rate from semitones, jitter, gain clamp, echo decay) is unchanged —
    # audio.play() reproduces it exactly, and on macOS emits the identical
    # afplay argv this function used to build. Recording capture (when a
    # `claudio record` window is open) lives in audio._spawn_one, so every
    # tag="note" play — hook events, jukebox, and session replay — is mixed
    # into the clip, just as it was when this function did the spawning.
    audio.play(sample_path, gain_linear, shift_semitones=shift_semitones,
               delay_s=delay_s, rate_jitter=rate_jitter, echo=echo)

def trigger(preset_name, preset, voice, song_name=None, quant_override=None,
             scale_override_pcs=None, scale_override_roots=None,
             event_effect=None):
    if voice is None: return
    voices = preset.get("voices", {})
    cfg = voices.get(voice)
    if cfg is None:
        log(f"unknown voice '{voice}' in preset {preset_name}")
        return
    ok, pressure_db = check_mioi(preset_name, voice, cfg.get("mioi", 0.5))
    if not ok: return
    iw = _normalize_weights(preset.get("interval_weights"))
    pr = preset.get("phrase_roots")
    # Tonal-overlay opt-in: voice has tonal_anchor_midi and preset has scale_pitches.
    # Lets noise-burst voices (wood/bird/mokugyo) land on key.
    scale = preset.get("scale_pitches") if cfg.get("tonal_anchor_midi") is not None else None
    anchor = cfg.get("tonal_anchor_midi")
    trange = cfg.get("tonal_range", 12)
    sample, shift = melodic_pick(
        preset_name, voice, cfg.get("dir", voice),
        song_name=song_name,
        interval_weights=iw,
        phrase_roots=pr,
        scale_pitches=scale,
        tonal_anchor=anchor,
        tonal_range=trange,
        scale_override_pcs=scale_override_pcs,
        scale_override_roots=scale_override_roots,
    )
    if sample is None: return
    cfg = read_config()
    cfg_master = cfg.get("master_gain")
    master = float(cfg_master if cfg_master is not None
                   else preset.get("master_gain", 0.5))
    # Live root transpose: the web mic-jam mode (or `claudio root`) writes a
    # global semitone offset off A. We fold it into every note's shift so the
    # whole room re-keys instantly with no re-render. Clamped to a tritone so a
    # detected root never warps a sample by more than ±6 semitones.
    shift += root_offset(cfg)
    base_lin = float(cfg.get("gain", 0.5)) * master
    pressure_lin = 10 ** (pressure_db / 20.0)
    delay = song_mod.quant_delay_for(quant_override) if quant_override is not None else song_mod.quant_delay()
    rate_jitter = bool(cfg.get("rate_jitter", False))
    # Per-event-mapping echo (delay): events block in preset.json may carry
    # an `effect.delay` dict like {ms: 320, feedback: 0.30, count: 3}.
    # Applied at trigger time so the same voice can have different feels for
    # different alerts (e.g. Stop with long echo, PreToolUse with none).
    echo = None
    if event_effect and isinstance(event_effect, dict):
        d = event_effect.get("delay")
        if isinstance(d, dict):
            echo = d
    # Per-VOICE delay fallback: a voice may carry its own `delay` dict
    # ({ms, feedback, count}) in preset.json, applied live at playback (no
    # re-render). An event-mapping echo, if present, takes precedence so a
    # voice can still feel different per alert.
    if echo is None:
        vd = cfg.get("delay")
        if isinstance(vd, dict):
            echo = vd
    play(sample, base_lin * pressure_lin, shift_semitones=shift, delay_s=delay,
         rate_jitter=rate_jitter, echo=echo)

# ---------- event mapping ----------

def is_failure(payload):
    if payload.get("hook_event_name") == "PostToolUseFailure" or payload.get("error"):
        return True
    resp = payload.get("tool_response")
    if isinstance(resp, dict):
        if resp.get("is_error") or resp.get("error"):
            return True
    if payload.get("tool_error"):
        return True
    return False

def mapping_event_name(event_name):
    """Reuse the existing PostToolUse mapping for Claude's failure event.

    Current Claude Code emits PostToolUse only after success and emits
    PostToolUseFailure separately.  Presets predate that split and already
    carry an ``on_failure`` override under PostToolUse, so preserve the preset
    format while accepting the current hook surface.
    """
    return music.mapping_event_name(event_name)

def resolve_voice(preset, event_name, payload):
    events = preset.get("events", {})
    spec = events.get(mapping_event_name(event_name))
    if not spec:
        return None
    if event_name == "PostToolUseFailure" or (event_name == "PostToolUse" and is_failure(payload)):
        # An explicit null on_failure means "silence failures" (claudio map
        # PostToolUse:on_failure -); only a missing key falls back to default.
        return spec["on_failure"] if "on_failure" in spec else spec.get("default")
    tool = payload.get("tool_name", "")
    by_tool = spec.get("by_tool") or {}
    if tool and tool in by_tool:
        return by_tool[tool]
    return spec.get("default")

# ---------- main handler ----------

def handle(payload):
    event = payload.get("hook_event_name") or payload.get("event") or "unknown"
    tool = payload.get("tool_name", "")
    session = payload.get("session_id", "")
    cwd = payload.get("cwd", "")

    # Global mute — short-circuit before any work. Toggled via `claudio off/on`.
    if read_config().get("muted"):
        return

    preset_name, source = resolve_preset(session, cwd)
    preset = load_preset(preset_name)
    update_session_record(session, cwd, event, preset_name, source)

    if preset is None:
        log(f"no preset loaded ({preset_name}); silent")
        return

    # Render-on-demand: a preset's samples are generated, not shipped (esp. when
    # Claudio is installed as a plugin). The first time we'd play a preset that
    # has none, kick a one-time detached render and stay silent this round — the
    # next events play once it lands. Covers every path (preset switch, pin,
    # rule, default), not just the active preset at SessionStart.
    if not ensure_rendered(preset_name):
        log(f"[{preset_name}] no samples yet — started a background render; silent this round")
        return

    # Resolve song: session pin > preset's "song" > global.
    sess_rec = load_sessions().get("active", {}).get(session, {})
    song_name = (sess_rec.get("song_pinned")
                 or preset.get("song")
                 or song_mod.global_song())
    if song_name and not song_mod.has_song(song_name):
        song_name = None

    log(f"[{preset_name}/{source}] event={event} tool={tool} session={session[:8]} song={song_name or '-'}")
    try:
        (STATE / "heartbeat").write_text(str(time.time()))
    except Exception:
        pass
    # Per-event activity marker — lets the TUI show a growing dot when each
    # event TYPE fires (mirrors the per-voice last-<voice>.txt). Written on
    # every handled event, even if it maps to silence, so unmapped events
    # still light up and can be mapped.
    activity_event = mapping_event_name(event)
    try:
        _ed = STATE / preset_name
        _ed.mkdir(parents=True, exist_ok=True)
        (_ed / f"evt-{activity_event}.txt").write_text(str(time.time()))
        # Frequency counter: append one byte so the file SIZE == fire count.
        # O_APPEND of a single byte is atomic, so concurrent hook processes
        # never clobber each other (a read-modify-write counts.json would).
        with (_ed / f"cnt-{activity_event}.bin").open("ab") as _cf:
            _cf.write(b"\x01")
    except Exception:
        pass

    # Always-on session score: a compact symbolic timeline of this session, so
    # you can replay your whole workflow through any preset, spot the heavy
    # traffic, and share a few-KB file instead of a WAV. (Audio capture for the
    # WAV path stays separate, in play() → events.jsonl.)
    _timeline_log(session, event, tool, is_failure(payload))

    # Per-preset quant override: preset.json may carry a "quant" block that
    # overrides the global config.json quant settings on a per-preset basis,
    # so e.g. rainfall can be slowly-quantized while meadow runs ungated.
    preset_quant = preset.get("quant")

    # Per-session scale override: lets the user pin a different scale (e.g.
    # A_lydian when the active preset is meadow) for one session without
    # forking the whole preset. Filters pitched bag, overrides phrase_roots
    # and scale_pitches. Resolution: session pin > config-wide > none.
    override_pcs, override_roots, override_name = resolve_scale(session)

    # Chord progression: when enabled, the live chord's tones supersede the
    # scale override — same machinery (pitch-class filter + phrase roots), the
    # pool just moves with the wall-clock chord cycle. The drone keeps its A
    # pedal underneath, which is exactly the ambient move.
    ch_pcs, ch_roots, _ch = resolve_chord()
    if ch_pcs:
        override_pcs, override_roots = ch_pcs, ch_roots

    # Per-event effect block: preset.json events.<name> may carry an
    # `effect: {delay: {ms, feedback, count}}` block, applied at trigger time.
    spec = preset.get("events", {}).get(mapping_event_name(event), {}) if isinstance(preset.get("events"), dict) else {}
    event_effect = spec.get("effect") if isinstance(spec, dict) else None

    voice = resolve_voice(preset, event, payload)
    trigger(preset_name, preset, voice, song_name=song_name,
            quant_override=preset_quant,
            scale_override_pcs=override_pcs,
            scale_override_roots=override_roots,
            event_effect=event_effect)

def main():
    raw = ""
    try:
        # Bytes + explicit UTF-8: the locale codec (cp1252 on Windows) can't
        # decode Claude's payloads and would raise before we could stay silent.
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
    except Exception as e:
        log(f"json parse error: {e}; raw={raw[:200]!r}")
        return 0
    try: handle(payload)
    except Exception as e: log(f"handle error: {e}")
    return 0

if __name__ == "__main__":
    try: main()
    except Exception: pass      # a hook must never print a traceback
    sys.exit(0)
