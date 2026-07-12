#!/usr/bin/env python3
"""
Claudio Symphony — installer.

Run from a fresh clone:

    python3 install.py

This will:
  1. Verify dependencies (Python 3, numpy, and an audio player for your OS).
  2. Render samples for every preset under presets/.
  3. Write a starter config.json (preset=meadow, master 0.55, drone 0.0)
     unless one already exists.
  4. Print the next steps (./bin/claudio install / start / tune).

Re-run any time to regenerate samples (existing samples are overwritten).
"""
import sys, subprocess, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paths
import preset_store
import config_store

PRESETS = paths.BUILTIN_PRESETS_DIR
CONFIG = paths.CONFIG_FILE

# Ships with these defaults. Mirrors the curator's working setup:
# meadow as the default preset, master 0.55, drone fully off, quant primed
# but disabled. Users can `claudio reset` to restore this exact state.
DEFAULT_CONFIG = config_store.DEFAULT_CONFIG

def step(msg):
    print(f"\n→ {msg}")

def fatal(msg):
    print(f"\n✗ {msg}", file=sys.stderr)
    sys.exit(1)

step("Checking Python version")
if sys.version_info < (3, 9):
    fatal(f"Python 3.9+ required (you have {sys.version.split()[0]})")
print(f"  Python {sys.version.split()[0]} ✓")

step("Checking numpy")
try:
    import numpy as np
    print(f"  numpy {np.__version__} ✓")
except ImportError:
    fatal("numpy not installed. Try: pip install numpy")

step("Checking audio backend")
import audio
ok, fatal_if_missing, msg = audio.install_check()
print("  " + msg)
if not ok:
    print("  ✗ No capable audio player found.")
    if audio.IS_LINUX:
        print("    Best:  sudo apt install ffmpeg     (Debian/Ubuntu)")
        print("           sudo dnf install ffmpeg     (Fedora; needs RPM Fusion)")
        print("           sudo pacman -S ffmpeg       (Arch)")
        print("    (pw-play / paplay are often already present and give volume;")
        print("     ffmpeg adds full pitch-shift quality via ffplay.)")
    elif audio.IS_WIN:
        print("    Best:  winget install -e --id Gyan.FFmpeg")
        print("    (Otherwise PowerShell MediaPlayer / winsound are used.)")
    elif audio.IS_MAC:
        print("    macOS ships afplay at /usr/bin/afplay — this should not happen.")
    if fatal_if_missing:
        sys.exit(1)
    print("    Samples will still render; audio plays once a backend is installed.")

step("Rendering presets")
paths.migrate_legacy(include_large=True)
preset_dirs = sorted(p for p in PRESETS.iterdir()
                     if (p / "render.py").exists())
if not preset_dirs:
    fatal(f"No presets found under {PRESETS}/")
for p in preset_dirs:
    print(f"  · {p.name} ...")
    env = os.environ.copy()
    env.update(preset_store.renderer_env(p.name))
    r = subprocess.run([sys.executable, str(p / "render.py")],
                       cwd=str(p), capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr, file=sys.stderr)
        fatal(f"render failed for preset '{p.name}'")
    n_wavs = sum(1 for _ in preset_store.sample_output_dir(p.name).rglob("*.wav"))
    print(f"    {n_wavs} samples")

step("Writing starter config (only if config.json doesn't exist)")
if CONFIG.exists():
    print(f"  config.json already present — leaving it alone")
else:
    config_store.save(DEFAULT_CONFIG, CONFIG)
    print(f"  wrote {CONFIG.name} with preset={DEFAULT_CONFIG['preset']}, "
          f"master_gain={DEFAULT_CONFIG['master_gain']}, "
          f"drone_gain={DEFAULT_CONFIG['drone_gain']}")

claudio = HERE / "bin" / ("claudio.cmd" if sys.platform.startswith("win") else "claudio")
print()
print("─" * 60)
print(" Done. Next steps:")
print("─" * 60)
print()
print(f"  Add hooks to ~/.claude/settings.json:")
print(f"    {claudio} install")
print()
print(f"  Start the drone (cathedral preset has a continuous bed):")
print(f"    {claudio} start")
print()
print(f"  Open the web console (tune everything, browse presets):")
print(f"    {claudio} web")
print()
print(f"  Or the terminal tuner:")
print(f"    {claudio} tune")
print()
print(f"  See all options:")
print(f"    {claudio}")
print()
