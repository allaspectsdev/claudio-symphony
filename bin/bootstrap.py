#!/usr/bin/env python3
"""
Claudio plugin bootstrap — runs once on SessionStart (alongside event.py) when
Claudio is installed as a Claude Code plugin.

Its ONE job is the numpy gap: a fresh plugin clone may not have numpy, which is
needed to synthesize sound samples. Hooks must never mutate the user's Python
environment or access the network, so this writes an actionable setup note and
returns immediately. Once numpy is present, the note is cleared and event.py
takes over rendering.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # plugin / repo root (bin/..)
sys.path.insert(0, str(ROOT))
import paths

STATE = paths.STATE_DIR
LOGS = paths.LOG_DIR
NOTE = LOGS / "SETUP_NEEDED.txt"


def have_numpy():
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if have_numpy():
        try: NOTE.unlink()                          # setup done; event.py renders on demand
        except Exception: pass
        return 0
    # numpy missing → guide only. Installation is always an explicit user action.
    NOTE.write_text(
        "Claudio needs numpy to synthesize its sounds.\n"
        "Claudio did not install anything automatically. Run these commands once:\n\n"
        "    python3 -m pip install numpy\n"
        f"    python3 \"{ROOT / 'install.py'}\"\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)                                  # bootstrap must never fail a session
