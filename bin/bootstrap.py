#!/usr/bin/env python3
"""
Claudio plugin bootstrap — runs once on SessionStart (alongside event.py) when
Claudio is installed as a Claude Code plugin.

Its ONE job is the numpy gap: a fresh plugin clone may not have numpy, which is
needed to synthesize the sound samples. event.py renders presets on demand (so
samples themselves are handled there, for every preset, not just the active
one) — but that render needs numpy. So if numpy is missing, this kicks ONE
fully-detached best-effort `pip install` and leaves a clear note; it NEVER
blocks the session (returns in a few ms) and never loops.

If numpy can't be installed, logs/SETUP_NEEDED.txt tells the user the one
command to run. Once numpy is present, the note is cleared and event.py takes
over rendering.
"""
import sys, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # plugin / repo root (bin/..)
STATE = ROOT / "state"
LOGS = ROOT / "logs"
PIP_MARK = STATE / ".pip-attempted"
NOTE = LOGS / "SETUP_NEEDED.txt"


def have_numpy():
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def spawn_detached(argv):
    """Fire-and-forget: launch argv fully detached so it outlives the hook
    timeout and never blocks the caller. Best-effort; failures are swallowed."""
    try:
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if hasattr(os, "setsid"):
            kw["start_new_session"] = True
        subprocess.Popen(argv, cwd=str(ROOT), **kw)
    except Exception:
        pass


def main():
    STATE.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    if have_numpy():
        try: NOTE.unlink()                          # setup done; event.py renders on demand
        except Exception: pass
        return 0
    # numpy missing → guide + one detached best-effort install (never blocks)
    NOTE.write_text(
        "Claudio needs numpy to synthesize its sounds.\n"
        "Trying to install it in the background now — start a new session in a minute.\n"
        "If sound still doesn't come, run this once:\n\n"
        f"    python3 -m pip install numpy && python3 \"{ROOT / 'install.py'}\"\n")
    if not PIP_MARK.exists():
        PIP_MARK.write_text("1")
        spawn_detached([sys.executable, "-m", "pip", "install", "--user", "--quiet", "numpy"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)                                  # bootstrap must never fail a session
