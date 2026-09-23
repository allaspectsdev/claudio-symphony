import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import midiplay
import song
import timeline


# ---------- tiny SMF builders ----------

def varlen(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def chunk(tag, body):
    return tag + struct.pack(">I", len(body)) + body


def header(fmt=1, ntracks=1, ppq=480):
    return chunk(b"MThd", struct.pack(">HHH", fmt, ntracks, ppq))


def tempo_ev(delta, bpm):
    us = int(round(60_000_000 / bpm))
    return varlen(delta) + b"\xff\x51\x03" + us.to_bytes(3, "big")


EOT = b"\x00\xff\x2f\x00"


def smf(*tracks, fmt=1, ppq=480, extra_chunks=()):
    body = b"".join(chunk(b"MTrk", t) for t in tracks)
    return header(fmt, len(tracks), ppq) + b"".join(extra_chunks) + body


def parse_bytes(data):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.mid"
        p.write_bytes(data)
        return song.parse_midi(p)


class ParseMidiTests(unittest.TestCase):
    def test_running_status(self):
        # note-on C4, then E4 and G4 via running status (no status byte)
        trk = (b"\x00\x90\x3c\x40"
               + b"\x83\x60\x40\x40"      # delta 480, running status 0x90
               + b"\x83\x60\x43\x40"
               + EOT)
        s = parse_bytes(smf(trk))
        self.assertEqual([n["midi"] for n in s["notes"]], [60, 64, 67])
        self.assertEqual([n["beat"] for n in s["notes"]], [0.0, 1.0, 2.0])
        self.assertEqual([n["sec"] for n in s["notes"]], [0.0, 0.5, 1.0])  # default 120

    def test_tempo_map_on_conductor_track(self):
        ppq = 480
        conductor = tempo_ev(0, 120) + tempo_ev(4 * ppq, 60) + EOT
        notes = (b"\x00\x90\x3c\x40"
                 + varlen(8 * ppq) + b"\x90\x3e\x40"
                 + EOT)
        s = parse_bytes(smf(conductor, notes, ppq=ppq))
        self.assertEqual(s["bpm"], 120.0)
        by_beat = {n["beat"]: n["sec"] for n in s["notes"]}
        self.assertAlmostEqual(by_beat[0.0], 0.0)
        self.assertAlmostEqual(by_beat[8.0], 6.0)   # 4 beats @120 + 4 beats @60
        # the jukebox schedule follows the tempo map (and tempo scales it)
        sched = midiplay._build_schedule(s, {0: "PostToolUse"})
        self.assertAlmostEqual(sched[-1][0], 6.0)
        sched = midiplay._build_schedule(s, {0: "PostToolUse"}, tempo=2.0)
        self.assertAlmostEqual(sched[-1][0], 3.0)
        self.assertAlmostEqual(midiplay._song_duration(s), 6.0)
        # explicit bpm override plays the beats on a flat grid
        sched = midiplay._build_schedule(s, {0: "PostToolUse"}, bpm=60)
        self.assertAlmostEqual(sched[-1][0], 8.0)

    def test_legacy_song_json_without_sec_uses_beats(self):
        s = {"bpm": 120.0, "notes": [{"midi": 60, "beat": 4.0, "velocity": 90, "channel": 0}]}
        sched = midiplay._build_schedule(s, {0: "Stop"})
        self.assertAlmostEqual(sched[0][0], 2.0)

    def test_alien_chunk_skipped(self):
        trk = b"\x00\x90\x3c\x40" + EOT
        data = smf(trk, extra_chunks=[chunk(b"XFIH", b"\x01\x02\x03\x04\x05")])
        s = parse_bytes(data)
        self.assertEqual([n["midi"] for n in s["notes"]], [60])

    def test_truncated_file_raises_value_error(self):
        trk = b"\x00\x90\x3c\x40" + b"\x83"          # delta varlen cut mid-quantity
        with self.assertRaisesRegex(ValueError, "truncated"):
            parse_bytes(smf(trk))

    def test_import_empty_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.mid"
            p.write_bytes(smf(EOT))
            with mock.patch.object(song, "SONGS", Path(td) / "songs"):
                with self.assertRaisesRegex(ValueError, "no playable notes"):
                    song.import_midi_file(p)
                self.assertFalse((Path(td) / "songs" / "empty.json").exists())


class NextNoteTests(unittest.TestCase):
    def test_lock_timeout_degrades_to_none(self):
        song_data = {"bpm": 120.0, "notes": [{"midi": 72, "beat": 0.0, "channel": 0}]}
        with mock.patch.object(song, "load_song", return_value=song_data), \
                mock.patch.object(song.stateio, "update_json",
                                  side_effect=song.stateio.LockTimeout("busy")) as uj:
            self.assertIsNone(song.next_note("tune"))
        kw = uj.call_args.kwargs
        self.assertEqual(kw["timeout"], song.stateio.HOT_TIMEOUT)
        self.assertEqual(kw["stale_after"], song.stateio.HOT_STALE_AFTER)


class RunLoopTests(unittest.TestCase):
    def test_zero_length_loop_is_paced(self):
        fired = []
        stop = {"stop": False}

        def fire(item):
            fired.append(time.time())
            if len(fired) >= 3:
                stop["stop"] = True

        with mock.patch.object(midiplay, "_MIN_PASS_S", 0.1):
            t0 = time.time()
            midiplay._run_loop([(0.0, "x")], fire, _stop=stop, loop=True, pass_len=0.0)
        # three passes of a 0-length schedule take at least 2 * min pass length
        self.assertGreaterEqual(fired[-1] - t0, 0.19)
        self.assertLess(time.time() - t0, 1.5)

    def test_pass_length_lets_last_note_ring(self):
        fired = []
        stop = {"stop": False}

        def fire(item):
            fired.append((item, time.time()))
            if len(fired) >= 3:
                stop["stop"] = True

        sched = [(0.0, "a"), (0.05, "b")]
        with mock.patch.object(midiplay, "_MIN_PASS_S", 0.05):
            midiplay._run_loop(sched, fire, _stop=stop, loop=True, pass_len=0.3)
        (_, ta), (_, tb), (item, ta2) = fired
        self.assertEqual(item, "a")
        self.assertGreaterEqual(ta2 - ta, 0.29)        # next pass waits for pass_len
        self.assertGreaterEqual(ta2 - tb, 0.2)         # last note not clobbered

    def test_pass_len_helper(self):
        self.assertEqual(midiplay._pass_len([], 0.0), midiplay._MIN_PASS_S)
        self.assertAlmostEqual(midiplay._pass_len([(0.0, 1), (3.0, 2)], 0.5), 3.5)


class TempoClampTests(unittest.TestCase):
    def test_clamp_tempo(self):
        self.assertEqual(midiplay.clamp_tempo(-2), 0.25)
        self.assertEqual(midiplay.clamp_tempo(100), 4.0)
        self.assertEqual(midiplay.clamp_tempo(0), 1.0)
        self.assertEqual(midiplay.clamp_tempo(float("nan")), 1.0)
        self.assertEqual(midiplay.clamp_tempo("junk"), 1.0)

    def test_negative_tempo_clamped_in_schedules(self):
        s = {"bpm": 120.0, "notes": [{"midi": 60, "beat": 1.0, "sec": 0.5,
                                       "velocity": 90, "channel": 0}]}
        sched = midiplay._build_schedule(s, {0: "Stop"}, tempo=-1)
        self.assertAlmostEqual(sched[0][0], 2.0)   # 0.5s / 0.25
        evs = [{"t": 0, "e": "Stop"}, {"t": 1, "e": "Stop"}]
        out = timeline.replay_schedule(evs, tempo=-5, max_gap=10)
        self.assertAlmostEqual(out[-1][0], 4.0)     # 1s / 0.25

    def test_replay_schedule_ignores_non_dict_events(self):
        out = timeline.replay_schedule([{"t": 0, "e": "Stop"}, "junk", 3, None])
        self.assertEqual(len(out), 1)

    def test_cli_bad_numbers_exit_2(self):
        with mock.patch.object(midiplay, "run") as run, \
                mock.patch("sys.stderr"):
            self.assertEqual(midiplay.main(["song", "--tempo", "fast"]), 2)
            self.assertEqual(midiplay.main(["song", "--bpm", "-3"]), 2)
            self.assertEqual(midiplay.main(["song", "--preset"]), 2)
            self.assertEqual(midiplay.main(["plan", "song", "--preset"]), 2)
            self.assertEqual(midiplay.main(["replay", "sid", "--max-gap", "x"]), 2)
            run.assert_not_called()
            self.assertEqual(midiplay.main(["song", "--tempo", "9"]), 0)
            self.assertEqual(run.call_args.kwargs["tempo"], 4.0)


if __name__ == "__main__":
    unittest.main()
