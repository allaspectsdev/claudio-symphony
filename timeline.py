#!/usr/bin/env python3
"""
Claudio Symphony — session timeline / "mini-track" reader.

event.py quietly appends a compact symbolic line per hook event to
state/timeline/<session_id>.ndjson — the always-on session score. This module
reads those back into a replayable timeline, computes a heavy-traffic density
sparkline, and exports a tiny, shareable .score.json (a few KB instead of a
multi-MB WAV).

Pure stdlib. midiplay.py replays these; webui.py + cli.py surface them.
"""
import json, time
from pathlib import Path
import paths

HERE = Path(__file__).resolve().parent
STATE = paths.STATE_DIR
TIMELINE = STATE / "timeline"
OUT_DIR = paths.RECORDINGS_DIR


def safe_sid(s):
    return "".join(c for c in (s or "") if c.isalnum() or c in "-_")[:64]


def _path(session_id):
    return TIMELINE / f"{safe_sid(session_id)}.ndjson"


def has_timeline(session_id):
    p = _path(session_id)
    return bool(safe_sid(session_id)) and p.exists() and p.stat().st_size > 0


def read_session(session_id):
    """Return {session, start, duration, count, events:[{t,e,tool,f}, …]} with
    t relative to the first event, or None if there's no timeline."""
    p = _path(session_id)
    if not p.exists():
        return None
    raw = []
    try:
        for ln in p.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                raw.append(json.loads(ln))
            except Exception:
                pass
    except Exception:
        return None
    if not raw:
        return None
    raw.sort(key=lambda e: e.get("t", 0))
    t0 = raw[0].get("t", 0)
    events = [{"t": round(e.get("t", 0) - t0, 3), "e": e.get("e", "unknown"),
               "tool": e.get("tool", ""), "f": int(e.get("f", 0))} for e in raw]
    return {"session": session_id, "start": t0,
            "duration": round(raw[-1].get("t", 0) - t0, 3),
            "count": len(events), "events": events}


def density(score, buckets=40):
    """Bin event counts into `buckets` even time-slices — the heavy-traffic
    heatmap. Returns a list of ints (counts per slice)."""
    if not score or not score.get("events"):
        return [0] * buckets
    dur = score.get("duration") or 0
    b = [0] * buckets
    if dur <= 0:
        b[0] = score.get("count", 0)
        return b
    for e in score["events"]:
        i = min(buckets - 1, int(e["t"] / dur * buckets))
        b[i] += 1
    return b


def summary(session_id, buckets=40):
    """Lightweight rail payload: counts, duration, density, busiest slice."""
    s = read_session(session_id)
    if not s:
        return None
    d = density(s, buckets)
    return {"session": session_id, "count": s["count"], "duration": s["duration"],
            "density": d, "peak": max(d) if d else 0}


def replay_schedule(events, tempo=1.0, max_gap=2.5):
    """Map captured (relative) event times to replay times. Idle gaps are capped
    at `max_gap` so a session where you stepped away doesn't replay minutes of
    silence — the heavy stretches stay dense, the dead air shrinks. `tempo`
    scales the result (>1 faster). Returns [(t, e, tool, f), …]."""
    evs = sorted(events, key=lambda x: x.get("t", 0))
    out = []
    prev_raw = None
    cur = 0.0
    tempo = float(tempo or 1.0) or 1.0
    for e in evs:
        raw = e.get("t", 0)
        if prev_raw is not None:
            gap = raw - prev_raw
            if max_gap and gap > max_gap:
                gap = max_gap
            cur += gap / tempo
        out.append((round(cur, 4), e.get("e", "unknown"), e.get("tool", ""), int(e.get("f", 0))))
        prev_raw = raw
    return out


def replay_duration(events, tempo=1.0, max_gap=2.5):
    sched = replay_schedule(events, tempo, max_gap)
    return sched[-1][0] if sched else 0.0


def export_score(session_id, label=None, stamp=None):
    """Freeze a session into a shareable recordings/claudio-<stamp>.score.json.
    Returns the basename, or None."""
    s = read_session(session_id)
    if not s:
        return None
    OUT_DIR.mkdir(exist_ok=True)
    base = f"claudio-{stamp or time.strftime('%Y%m%d-%H%M%S')}"
    data = {"version": 1, "label": label or "", "kind": "session-score",
            "duration": s["duration"], "count": s["count"], "events": s["events"]}
    (OUT_DIR / f"{base}.score.json").write_text(json.dumps(data))
    return base


def load_score_file(path):
    """Load a saved .score.json (from a share) → {events, duration, …}."""
    try:
        d = json.loads(Path(path).read_text())
        if isinstance(d, dict) and isinstance(d.get("events"), list):
            return d
    except Exception:
        pass
    return None


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a:
        ids = sorted(p.stem for p in TIMELINE.glob("*.ndjson")) if TIMELINE.exists() else []
        for sid in ids:
            s = summary(sid)
            if s:
                print(f"{sid[:12]:<14} {s['count']:>5} events  {s['duration']:>6.1f}s  peak={s['peak']}")
        if not ids:
            print("(no session timelines captured yet)")
    elif a[0] == "show" and len(a) > 1:
        print(json.dumps(read_session(a[1]), indent=2))
    elif a[0] == "export" and len(a) > 1:
        print("exported:", export_score(a[1], a[2] if len(a) > 2 else None))
