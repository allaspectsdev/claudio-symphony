#!/usr/bin/env python3
"""Render one preset, then enforce the configured generated-audio cache cap."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cache_manager  # noqa: E402
import paths  # noqa: E402
import preset_store  # noqa: E402
import stateio  # noqa: E402


def render(name, renderer_args=()):
    renderer = preset_store.render_path(name)
    if renderer is None:
        return 2
    env = os.environ.copy()
    env.update(preset_store.renderer_env(name))
    marker = paths.STATE_DIR / name / ".rendering"
    try:
        with stateio.file_lock(marker, timeout=2.0, stale_after=900):
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(time.time()))
            result = subprocess.run(
                [sys.executable, str(renderer), *map(str, renderer_args)],
                cwd=str(HERE), env=env, check=False,
            )
            if result.returncode == 0:
                try:
                    marker.unlink()
                except OSError:
                    pass
                cache_manager.trim(preserve=(name,))
            return result.returncode
    except stateio.LockTimeout:
        return 0  # another worker is already rendering this preset


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: render_worker.py <preset> [renderer-args...]", file=sys.stderr)
        return 2
    return render(argv[0], argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
