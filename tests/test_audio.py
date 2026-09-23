#!/usr/bin/env python3
"""
Cross-platform unit tests for audio.py.

These run on ANY OS with zero audio hardware and no external players — the
whole point of routing playback through a single seam is that detection, argv
construction, scheduling, degradation, and stop logic become pure functions we
can exercise by monkeypatching `shutil.which` / `sys.platform`.

    python -m unittest tests.test_audio       (from the repo root)
"""
import os
import sys
import wave
import struct
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import audio  # noqa: E402


def _write_wav(path, sr=44100, nch=2, nframes=2000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(nframes):
            val = (i * 31 % 20000) - 10000
            for _ in range(nch):
                frames += struct.pack("<h", val)
        w.writeframes(bytes(frames))


class ArgvBuilderTests(unittest.TestCase):
    """Each backend builds the right command — incl. the macOS regression
    guard that afplay's argv is byte-identical to the original code."""

    def setUp(self):
        self.wav = HERE / "tests" / "_fixture_44100.wav"
        if not self.wav.exists():
            _write_wav(self.wav)
        audio._sr_cache.clear()

    def test_afplay_regression(self):
        build = audio._argv_afplay("/usr/bin/afplay")
        self.assertEqual(
            build("/x.wav", 0.42, 1.05946),
            ["/usr/bin/afplay", "-v", "0.420", "-r", "1.05946", "/x.wav"],
        )
        # No rate -> no -r flag (native pitch), exactly as before.
        self.assertEqual(build("/x.wav", 0.5, None),
                         ["/usr/bin/afplay", "-v", "0.500", "/x.wav"])

    def test_ffplay_asetrate_reads_wav_rate(self):
        build = audio._argv_ffplay("ffplay")
        argv = build(str(self.wav), 0.42, 1.05946)
        self.assertEqual(argv[0], "ffplay")
        self.assertIn("-nodisp", argv)
        self.assertIn("-autoexit", argv)
        af = argv[argv.index("-af") + 1]
        expected_rate = int(round(44100 * 1.05946))
        self.assertIn("volume=0.4200", af)
        self.assertIn(f"asetrate={expected_rate}", af)   # SR from header, not hardcoded
        self.assertIn("aresample=44100", af)

    def test_mpv(self):
        argv = audio._argv_mpv("mpv")(str(self.wav), 0.42, 1.05946)
        # mpv volume is cubic: 100 * 0.42 ** (1/3) ~= 74.9
        self.assertIn("--volume=74.9", argv)
        self.assertIn("--audio-pitch-correction=no", argv)
        self.assertIn("--speed=1.05946", argv)

    def test_sox_play_order(self):
        # gain (-v) before the file; speed effect after it.
        argv = audio._argv_sox_play("play")("/x.wav", 0.42, 1.05946)
        self.assertEqual(argv, ["play", "-q", "-v", "0.420", "/x.wav",
                                "speed", "1.05946"])

    def test_paplay_and_pwplay_volume_scale(self):
        # PulseAudio volume is cubic: pa = 65536 * linear ** (1/3)
        self.assertEqual(audio._argv_paplay("paplay")("/x.wav", 0.42, None),
                         ["paplay", f"--volume={int(round(65536 * 0.42 ** (1 / 3)))}", "/x.wav"])
        self.assertEqual(audio._argv_paplay("paplay")("/x.wav", 1.0, None),
                         ["paplay", "--volume=65536", "/x.wav"])
        self.assertIn("--volume=100.0", audio._argv_mpv("mpv")("/x.wav", 1.0, None))
        self.assertIn("--volume=0.0", audio._argv_mpv("mpv")("/x.wav", 0.0, None))
        self.assertEqual(audio._argv_pwplay("pw-play")("/x.wav", 0.42, None),
                         ["pw-play", "--volume=0.4200", "/x.wav"])


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self._saved = (audio.IS_MAC, audio.IS_LINUX, audio.IS_WIN,
                       audio.winsound, audio._BACKEND)
        audio._BACKEND = None
        os.environ.pop("CLAUDIO_PLAYER", None)

    def tearDown(self):
        (audio.IS_MAC, audio.IS_LINUX, audio.IS_WIN,
         audio.winsound, audio._BACKEND) = self._saved
        os.environ.pop("CLAUDIO_PLAYER", None)

    def _platform(self, mac=False, linux=False, win=False):
        audio.IS_MAC, audio.IS_LINUX, audio.IS_WIN = mac, linux, win

    def _which(self, present):
        present = set(present)
        return lambda name: (f"/usr/bin/{name}" if name in present else None)

    def test_mac_prefers_afplay(self):
        self._platform(mac=True)
        with mock.patch("audio.shutil.which", self._which({"afplay", "ffplay"})):
            b = audio._detect()
        self.assertEqual(b.name, "afplay")
        self.assertTrue(b.can_volume and b.can_pitch and b.can_overlap)

    def test_linux_prefers_ffplay_over_paplay(self):
        self._platform(linux=True)
        with mock.patch("audio.shutil.which", self._which({"ffplay", "paplay", "aplay"})):
            b = audio._detect()
        self.assertEqual(b.name, "ffplay")
        self.assertTrue(b.can_pitch)

    def test_linux_aplay_only_capabilities(self):
        self._platform(linux=True)
        with mock.patch("audio.shutil.which", self._which({"aplay"})):
            b = audio._detect()
        self.assertEqual(b.name, "aplay")
        self.assertFalse(b.can_volume)
        self.assertFalse(b.can_pitch)
        self.assertFalse(b.can_overlap)

    def test_windows_falls_back_to_winsound(self):
        self._platform(win=True)
        audio.winsound = object()   # pretend the stdlib module is present
        with mock.patch("audio.shutil.which", self._which(set())):
            b = audio._detect()
        self.assertEqual(b.name, "winsound")
        self.assertFalse(b.can_overlap)

    def test_windows_prefers_ffplay(self):
        self._platform(win=True)
        audio.winsound = object()
        with mock.patch("audio.shutil.which", self._which({"ffplay", "powershell"})):
            b = audio._detect()
        self.assertEqual(b.name, "ffplay")

    def test_env_override_wins(self):
        self._platform(mac=True)
        os.environ["CLAUDIO_PLAYER"] = "mpv"
        with mock.patch("audio.shutil.which", self._which({"afplay", "mpv"})):
            b = audio._detect()
        self.assertEqual(b.name, "mpv")

    def test_null_when_nothing_present(self):
        self._platform(linux=True)
        audio.winsound = None
        with mock.patch("audio.shutil.which", self._which(set())):
            b = audio._detect()
        self.assertEqual(b.name, "null")


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self._saved = audio._BACKEND

    def tearDown(self):
        audio._BACKEND = self._saved

    def _fake_backend(self, can_overlap=True):
        audio._BACKEND = audio.Backend(name="fake", kind="argv",
                                       can_volume=True, can_pitch=True,
                                       can_overlap=can_overlap)

    def test_echo_fanout_delays_and_gains(self):
        self._fake_backend(can_overlap=True)
        calls = []
        with mock.patch("audio._spawn_one",
                        side_effect=lambda p, g, r, d, t: calls.append((round(g, 6), round(d, 6)))):
            audio.play("/x.wav", 0.5, delay_s=0.0,
                       echo={"ms": 320, "feedback": 0.3, "count": 3})
        self.assertEqual([d for _, d in calls], [0.0, 0.32, 0.64, 0.96])
        self.assertEqual([g for g, _ in calls], [0.5, 0.15, 0.045, 0.0135])

    def test_echo_skipped_without_overlap(self):
        self._fake_backend(can_overlap=False)
        calls = []
        with mock.patch("audio._spawn_one",
                        side_effect=lambda *a: calls.append(a)):
            audio.play("/x.wav", 0.5, echo={"ms": 320, "feedback": 0.3, "count": 3})
        self.assertEqual(len(calls), 1)   # only the dry hit; taps dropped

    def test_pitch_math_matches_equal_temperament(self):
        self._fake_backend()
        captured = {}
        with mock.patch("audio._spawn_one",
                        side_effect=lambda p, g, r, d, t: captured.setdefault("rate", r)):
            audio.play("/x.wav", 0.5, shift_semitones=12)   # one octave
        self.assertAlmostEqual(captured["rate"], 2.0, places=6)


class DegradationTests(unittest.TestCase):
    def setUp(self):
        self._saved = audio._BACKEND

    def tearDown(self):
        audio._BACKEND = self._saved

    def test_pitch_routes_through_prerender_when_unsupported(self):
        # pw-play: volume yes, pitch no -> rate must be pre-rendered away.
        audio._BACKEND = audio.Backend(name="pw-play", kind="argv",
                                       can_volume=True, can_pitch=False)
        with mock.patch("audio._prerender", return_value="/tmp/shifted.wav") as pr:
            src, gain, rate = audio._resolve_src("/x.wav", 0.42, 1.05946)
        pr.assert_called_once()
        self.assertEqual(src, "/tmp/shifted.wav")
        self.assertIsNone(rate)            # native pitch on the rendered file
        self.assertEqual(gain, 0.42)       # volume still applied by the player

    def test_native_pitch_fallback_when_prerender_fails(self):
        audio._BACKEND = audio.Backend(name="pw-play", kind="argv",
                                       can_volume=True, can_pitch=False)
        with mock.patch("audio._prerender", return_value=None):
            src, gain, rate = audio._resolve_src("/x.wav", 0.42, 1.05946)
        self.assertEqual(src, "/x.wav")
        self.assertIsNone(rate)            # gave up on pitch, plays native

    def test_aplay_bakes_gain(self):
        audio._BACKEND = audio.Backend(name="aplay", kind="argv",
                                       can_volume=False, can_pitch=False)
        with mock.patch("audio._prerender", return_value="/tmp/quiet.wav") as pr:
            src, gain, rate = audio._resolve_src("/x.wav", 0.42, None)
        pr.assert_called_once()
        self.assertEqual(src, "/tmp/quiet.wav")
        self.assertEqual(gain, 1.0)        # gain baked into the WAV, not passed to player


class StopTests(unittest.TestCase):
    def setUp(self):
        self._saved = (audio._BACKEND, audio.IS_WIN)
        audio._LIVE.clear()

    def tearDown(self):
        audio._BACKEND, audio.IS_WIN = self._saved
        audio._LIVE.clear()

    def test_image_kill_only_for_dedicated_binaries(self):
        audio._BACKEND = audio.Backend(name="ffplay", kind="argv",
                                       image_name="ffplay")
        audio.IS_WIN = False
        with mock.patch("audio.PLAYERS_FILE") as pf, \
             mock.patch("audio.shutil.which", return_value="/usr/bin/pkill"), \
             mock.patch("audio.subprocess.run") as run:
            pf.exists.return_value = False
            audio.stop_all()
        # exact process-name match (-x), never a command-line substring (-f)
        run.assert_called_once_with(["pkill", "-x", "ffplay"], check=False)

    def test_no_image_kill_for_generic_player_name(self):
        # sox 'play' / powershell must NEVER be image-killed (would hit unrelated procs).
        audio._BACKEND = audio.Backend(name="play", kind="argv", image_name="play")
        audio.IS_WIN = False
        with mock.patch("audio.PLAYERS_FILE") as pf, \
             mock.patch("audio.subprocess.run") as run:
            pf.exists.return_value = False
            audio.stop_all()
        run.assert_not_called()

    def test_tagged_stop_only_terminates_matching_live_players(self):
        audio._BACKEND = audio.Backend(name="ffplay", kind="argv", image_name="ffplay")
        audio.IS_WIN = False
        drone_p, note_p = mock.Mock(), mock.Mock()
        drone_p.poll.return_value = None
        note_p.poll.return_value = None
        audio._LIVE[:] = [(drone_p, "drone"), (note_p, "note")]
        with mock.patch("audio.PLAYERS_FILE") as pf, \
             mock.patch("audio.subprocess.run") as run:
            pf.exists.return_value = False
            audio.stop_drone()
        drone_p.terminate.assert_called_once()
        note_p.terminate.assert_not_called()
        run.assert_not_called()                  # no image sweep on a tagged stop
        # stop_all (tag None) terminates everything
        with mock.patch("audio.PLAYERS_FILE") as pf, \
             mock.patch("audio.shutil.which", return_value=None):
            pf.exists.return_value = False
            audio.stop_all()
        note_p.terminate.assert_called_once()

    def test_stop_drone_purges_stale_other_tag_records(self):
        # H2 regression: stopping one tag must drop STALE other-tag records
        # (dead PIDs), keep only fresh ones, and never let the file grow forever.
        import json
        audio._BACKEND = audio.Backend(name="ffplay", kind="argv", image_name="ffplay")
        audio.IS_WIN = False
        saved = audio.PLAYERS_FILE.read_text() if audio.PLAYERS_FILE.exists() else None
        try:
            now = __import__("time").time()
            audio._write_players([
                {"pid": 11, "tag": "drone", "ts": now, "image": "ffplay"},   # killed
                {"pid": 22, "tag": "note", "ts": 0, "image": "ffplay"},       # stale -> dropped
                {"pid": 33, "tag": "note", "ts": now, "image": "ffplay"},     # fresh -> kept
            ])
            killed = []
            with mock.patch("audio.terminate_pid", side_effect=killed.append), \
                 mock.patch("audio.shutil.which", return_value=None), \
                 mock.patch("audio.subprocess.run"):
                audio.stop_drone()
            remaining = json.loads(audio.PLAYERS_FILE.read_text())
            self.assertEqual(killed, [11])                      # only the drone pid
            self.assertEqual([r["pid"] for r in remaining], [33])  # stale note purged
        finally:
            if saved is not None:
                audio.PLAYERS_FILE.write_text(saved)
            elif audio.PLAYERS_FILE.exists():
                audio.PLAYERS_FILE.unlink()


class PreRenderTests(unittest.TestCase):
    """Only runs where numpy is present (the project requires it anyway)."""

    def setUp(self):
        try:
            import numpy  # noqa: F401
        except Exception:
            self.skipTest("numpy not installed")
        self.wav = HERE / "tests" / "_fixture_pr.wav"
        _write_wav(self.wav, sr=44100, nch=1, nframes=4000)

    def test_octave_up_halves_frames(self):
        out = audio._prerender(self.wav, 2.0)   # +12 semitones
        self.assertIsNotNone(out)
        with wave.open(out, "rb") as w:
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(w.getframerate(), 44100)
            n_out = w.getnframes()
        # afplay-style varispeed: one octave up ~= half the samples.
        self.assertTrue(1900 <= n_out <= 2100, f"got {n_out} frames")

    def test_cache_hit_returns_same_path(self):
        a = audio._prerender(self.wav, 1.5)
        b = audio._prerender(self.wav, 1.5)
        self.assertEqual(a, b)

    def test_cache_invalidates_when_source_changes(self):
        a = audio._prerender(self.wav, 1.5)
        st = os.stat(self.wav)
        _write_wav(self.wav, sr=44100, nch=1, nframes=3000)       # "regenerated"
        os.utime(self.wav, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        b = audio._prerender(self.wav, 1.5)
        self.assertNotEqual(a, b)
        with wave.open(b, "rb") as w:
            self.assertTrue(1900 <= w.getnframes() <= 2100)        # 3000 / 1.5

    def test_baked_gain_quantized_to_half_db(self):
        a = audio._prerender(self.wav, 1.0, bake_gain=0.500)
        b = audio._prerender(self.wav, 1.0, bake_gain=0.501)       # < 0.02 dB apart
        c = audio._prerender(self.wav, 1.0, bake_gain=0.25)        # -6 dB
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        q = audio._quantize_gain(0.42)
        import math
        self.assertAlmostEqual(20 * math.log10(q) * 2, round(20 * math.log10(q) * 2), places=6)
        self.assertEqual(audio._quantize_gain(0.0), 0.0)

    def test_prune_keeps_newest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("audio.CACHE_DIR", Path(d)):
            for i in range(5):
                f = Path(d) / f"{i}.wav"
                f.write_bytes(b"x")
                os.utime(f, (1000 + i, 1000 + i))
            audio._prune_cache(max_files=2)
            self.assertEqual(sorted(p.name for p in Path(d).glob("*.wav")),
                             ["3.wav", "4.wav"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
