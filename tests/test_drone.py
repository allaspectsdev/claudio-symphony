#!/usr/bin/env python3
"""
drone.py loop/lifecycle tests + synth.write_wav edge fades. Players are stubbed
(no audio is ever played) and every state path lives in a temp dir.
"""
import os
import signal
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import audio  # noqa: E402
import drone  # noqa: E402

try:
    import numpy as np
    import synth
except Exception:  # pragma: no cover
    np = synth = None


def _silent_wav(path, seconds, sr=44100):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\0\0\0\0" * int(seconds * sr))


class FakePlayer:
    def __init__(self, gain, rate):
        self.gain, self.rate, self.t = gain, rate, time.monotonic()
        self.terminated = False

    def poll(self):
        return None            # never "finishes": the loop must not wait on poll()

    def terminate(self):
        self.terminated = True


class DroneTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(drone, "PID_FILE", self.d / "drone.pid"),
            mock.patch.object(drone, "ACTIVE_PRESET_FILE", self.d / "drone-preset.txt"),
            mock.patch.object(drone, "HEARTBEAT_FILE", self.d / "heartbeat"),
            mock.patch.object(drone, "STOP_SENTINEL", self.d / "drone.stop"),
            mock.patch.object(drone, "LOG_FILE", self.d / "drone.log"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()


class PidClaimTests(DroneTestBase):
    def test_claims_when_free(self):
        self.assertIsNone(drone.claim_pid())
        self.assertEqual(drone.PID_FILE.read_text(), str(os.getpid()))

    def test_refuses_when_owner_alive(self):
        drone.PID_FILE.write_text("424242")
        with mock.patch.object(drone.audio, "pid_alive", return_value=True):
            self.assertEqual(drone.claim_pid(), 424242)
        self.assertEqual(drone.PID_FILE.read_text(), "424242")

    def test_replaces_dead_owner(self):
        drone.PID_FILE.write_text("424242")
        with mock.patch.object(drone.audio, "pid_alive", return_value=False):
            self.assertIsNone(drone.claim_pid())
        self.assertEqual(drone.PID_FILE.read_text(), str(os.getpid()))

    def test_wav_seconds_from_header(self):
        p = self.d / "x.wav"
        _silent_wav(p, 0.5)
        self.assertAlmostEqual(drone.wav_seconds(p), 0.5, places=3)
        self.assertIsNone(drone.wav_seconds(self.d / "missing.wav"))


class DroneLoopTests(DroneTestBase):
    def _run_main(self, cfg_fn, clip_s=0.3):
        wav = self.d / "drone.wav"
        _silent_wav(wav, clip_s)
        players = []

        def start(path, gain, rate=None):
            p = FakePlayer(gain, rate)
            players.append(p)
            return p
        saved = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
        with mock.patch.object(drone, "active_preset_name", return_value="cathedral"), \
             mock.patch.object(drone, "load_preset", return_value={"drone": "drone.wav"}), \
             mock.patch.object(drone.preset_store, "sample_asset", return_value=wav), \
             mock.patch.object(drone.audio, "get_backend",
                               return_value=audio.Backend(name="ffplay", kind="argv")), \
             mock.patch.object(drone.audio, "drone_play_start", side_effect=start), \
             mock.patch.object(drone.audio, "drone_play_once", return_value=127), \
             mock.patch.object(drone, "read_config", side_effect=cfg_fn):
            try:
                drone.main()
            finally:
                signal.signal(signal.SIGINT, saved[0])
                signal.signal(signal.SIGTERM, saved[1])
        return players

    def test_gapless_handoff_and_mute_exit(self):
        t0 = time.monotonic()

        def cfg():
            return {"drone_gain": 0.4, "muted": time.monotonic() - t0 > 1.0}
        players = self._run_main(cfg, clip_s=0.3)
        # ~1s of 0.3s clips => ~4 passes, each spawned just before the last ends
        self.assertGreaterEqual(len(players), 3)
        gaps = [b.t - a.t for a, b in zip(players, players[1:])]
        for g in gaps:
            self.assertLess(g, 0.3 + 0.1)         # next pass never late
            self.assertGreater(g, 0.15)           # nor wildly early
        self.assertTrue(players[-1].terminated)   # finally: no orphan player
        self.assertFalse(drone.PID_FILE.exists())

    def test_gain_change_swaps_promptly(self):
        t0 = time.monotonic()

        def cfg():
            el = time.monotonic() - t0
            return {"drone_gain": 0.4 if el < 0.3 else 0.1, "muted": el > 1.2}
        players = self._run_main(cfg, clip_s=30.0)    # long clip: no natural loop
        self.assertEqual(len(players), 2)
        self.assertTrue(players[0].terminated)
        self.assertAlmostEqual(players[1].gain, 0.1)
        self.assertLess(players[1].t - t0, 1.0)


@unittest.skipIf(synth is None, "numpy not installed")
class WriteWavFadeTests(unittest.TestCase):
    def _read(self, path):
        with wave.open(str(path), "rb") as w:
            a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        return a.reshape(-1, 2)

    def test_one_shot_starts_and_ends_at_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "kick.wav"
            synth.write_wav(p, np.ones((4410, 2)) * 0.9)     # hard DC step both ends
            a = self._read(p)
        self.assertLessEqual(int(np.max(np.abs(a[0]))), 1)
        self.assertLessEqual(int(np.max(np.abs(a[-1]))), 1)
        self.assertGreater(int(np.max(np.abs(a[2205]))), 20000)   # body untouched

    def test_loop_is_not_faded(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "drone.wav"
            synth.write_wav(p, np.ones((4410, 2)) * 0.5, target_peak=0.5, loop=True)
            a = self._read(p)
        self.assertEqual(int(a[0, 0]), int(a[-1, 0]))
        self.assertGreater(int(a[0, 0]), 10000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
