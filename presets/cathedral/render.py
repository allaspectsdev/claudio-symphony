#!/usr/bin/env python3
"""
Cathedral preset — sample renderer.

The cathedral voices and gen_all() live in the top-level synth.py (since
they were the original implementation). This thin wrapper sets the output
directory to this preset's samples/ folder and invokes the generator.
"""
import os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# Tell synth.py to write samples here, then import + run.
os.environ.setdefault("CLAUDIO_SAMPLES_DIR", str(HERE / "samples"))
sys.path.insert(0, str(ROOT))

import synth  # noqa: E402

# === reverb_scale monkeypatch ===
# Cathedral uses synth.gen_all() directly, so we mutate synth's namespace
# (rather than shadowing in render.py like the other presets) so that calls
# inside gen_all() see the patched reverb_stereo.
import json as _json
_PRESET_CFG = _json.loads(Path(__import__("os").environ.get("CLAUDIO_PRESET_CONFIG", str(HERE / "preset.json"))).read_text())
_REVERB_SCALE = float(_PRESET_CFG.get("reverb_scale", 1.0))
_orig_reverb_stereo = synth.reverb_stereo
def _patched_reverb_stereo(mono, **kwargs):
    if "wet" in kwargs:
        kwargs["wet"] = max(0.0, min(1.0, float(kwargs["wet"]) * _REVERB_SCALE))
    return _orig_reverb_stereo(mono, **kwargs)
synth.reverb_stereo = _patched_reverb_stereo

if __name__ == "__main__":
    synth.gen_all()
