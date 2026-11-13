from __future__ import annotations

import unittest

from midivault.engine.smf_parser import MidiParseError, parse_smf
from tests.midi_builder import MidiTrack, build_smf, vlq


class ParserTests(unittest.TestCase):
    def test_format_1_tracks_tempo_time_and_key(self) -> None:
        conductor = MidiTrack().track_name("Conductor").tempo(0, 100).time_signature(0, 3, 4).key_signature(0, -2)
        conductor.end(4 * 3 * 480)
        bass = MidiTrack().track_name("Bass").program(0, 33)
        for bar in range(4):
            for step, pitch in enumerate([36, 36, 43, 41]):
                bass.note(bar * 3 * 480 + step * 360, pitch, 200, 90)
        bass.end(4 * 3 * 480)
        result = parse_smf(build_smf([conductor, bass], midi_format=1))
        self.assertEqual(result.format, 1)
        self.assertEqual(result.timing_type, "metrical")
        self.assertEqual(result.ticks_per_quarter, 480)
        self.assertEqual(len(result.sequences), 1)
        sequence = result.sequences[0]
        self.assertEqual(sequence.time_signatures[0].label, "3/4")
        self.assertEqual(sequence.key_signatures[0].label, "Bb major")
        self.assertAlmostEqual(sequence.tempos[0].bpm, 100.0)
        self.assertEqual(sequence.track_count, 1)
        self.assertEqual(sequence.tracks[0].name, "Bass")
        self.assertEqual(sequence.tracks[0].program, 33)
        self.assertAlmostEqual(sequence.duration_beats, 12.0, places=3)
        self.assertAlmostEqual(sequence.duration_seconds, 7.2, places=3)
        self.assertEqual(sequence.tracks[0].notes[0].pitch, 36)

    def test_format_2_sequences_are_independent(self) -> None:
        first = MidiTrack().track_name("Sequence A").tempo(0, 100).time_signature(0, 4, 4)
        first.note(0, 60, 480, 90)
        first.note(480, 64, 480, 90)
        first.end(960)
        second = MidiTrack().track_name("Sequence B").tempo(0, 120).time_signature(0, 4, 4)
        for i in range(8):
            second.note(i * 480, 48, 240, 100)
        second.end(8 * 480)
        result = parse_smf(build_smf([first, second], midi_format=2))
        self.assertEqual(result.format, 2)
        self.assertEqual(len(result.sequences), 2)
        self.assertEqual(result.sequences[0].note_count, 2)
        self.assertEqual(result.sequences[1].note_count, 8)
        self.assertAlmostEqual(result.sequences[0].duration_seconds, 1.2, places=3)
        self.assertAlmostEqual(result.sequences[1].duration_seconds, 4.0, places=3)
        self.assertEqual(result.duration_seconds, 4.0)
        self.assertEqual(result.sequences[0].tracks[0].name, "Sequence A")
        self.assertEqual(result.sequences[1].tracks[0].name, "Sequence B")
        self.assertTrue(any("independent" in warning for warning in result.warnings))

    def test_smpte_timing(self) -> None:
        track = MidiTrack().track_name("SMPTE").program(0, 73)
        track.note(0, 72, 500, 90)
        track.note(500, 74, 500, 90)
        track.end(2000)
        # 25fps * 40 ticks/frame = 1000 ticks per second.
        result = parse_smf(build_smf([track], midi_format=0, division=0xE728))
        self.assertEqual(result.timing_type, "smpte")
        self.assertAlmostEqual(result.smpte_fps or 0, 25.0)
        self.assertEqual(result.ticks_per_frame, 40)
        self.assertAlmostEqual(result.duration_seconds, 2.0, places=3)
        self.assertAlmostEqual(result.sequences[0].tracks[0].notes[1].start_seconds, 0.5, places=3)

    def test_tempo_map_changes_timing(self) -> None:
        track = MidiTrack().track_name("Tempo Map").tempo(0, 120).tempo(4 * 480, 60)
        track.note(0, 60, 480, 90)
        track.note(4 * 480, 62, 480, 90)
        track.note(6 * 480, 64, 480, 90)
        track.end(7 * 480)
        result = parse_smf(build_smf([track], midi_format=0))
        notes = result.sequences[0].tracks[0].notes
        self.assertAlmostEqual(notes[0].start_seconds, 0.0, places=3)
        self.assertAlmostEqual(notes[1].start_seconds, 2.0, places=3)
        self.assertAlmostEqual(notes[2].start_seconds, 4.0, places=3)
        self.assertEqual(result.sequences[0].tempos[1].bpm, 60.0)
        self.assertAlmostEqual(result.duration_seconds, 5.0, places=3)

    def test_sustain_extends_note_duration(self) -> None:
        track = MidiTrack().track_name("Piano").program(0, 0).tempo(0, 120)
        track.sustain(0, True)
        track.note_on(0, 60, 90)
        track.note_off(480, 60)
        track.note_off(1440, 64)
        track.note_on(960, 64, 80)
        track.sustain(4 * 480, False)
        track.end(4 * 480)
        result = parse_smf(build_smf([track], midi_format=0))
        notes = result.sequences[0].tracks[0].notes
        self.assertEqual(len(notes), 2)
        by_pitch = {note.pitch: note for note in notes}
        self.assertTrue(by_pitch[60].sustained)
        self.assertAlmostEqual(by_pitch[60].duration_seconds, 2.0, places=3)
        self.assertGreaterEqual(by_pitch[64].duration_seconds, 0.4)

    def test_overlapping_same_pitch_notes_use_fifo(self) -> None:
        track = MidiTrack().track_name("Overlap").program(0, 73).tempo(0, 120)
        track.note_on(0, 72, 84)
        track.note_on(240, 72, 96)
        track.note_off(960, 72)
        track.note_off(1440, 72)
        track.end(1440)
        result = parse_smf(build_smf([track], midi_format=0))
        notes = result.sequences[0].tracks[0].notes
        self.assertEqual(len(notes), 2)
        ordered = sorted(notes, key=lambda note: note.start_tick)
        self.assertEqual(ordered[0].end_tick, 960)
        self.assertEqual(ordered[1].end_tick, 1440)
        self.assertEqual(ordered[0].velocity, 84)
        self.assertEqual(ordered[1].velocity, 96)

    def test_missing_note_offs_are_assumed_and_reported(self) -> None:
        track = MidiTrack().track_name("No Offs").program(0, 0).tempo(0, 120)
        for index, pitch in enumerate([60, 62, 64, 65]):
            track.note_on(index * 120, pitch, 90)
        track.end(4 * 480)
        result = parse_smf(build_smf([track], midi_format=0))
        notes = result.sequences[0].tracks[0].notes
        self.assertEqual(len(notes), 4)
        self.assertTrue(all(note.assumed_duration for note in notes))
        self.assertEqual(result.sequences[0].tracks[0].assumed_durations, 4)
        self.assertTrue(any("assumed" in warning for warning in result.warnings))

    def test_velocity_zero_note_on_is_note_off(self) -> None:
        track = MidiTrack().track_name("Zero Velocity").tempo(0, 120)
        track.note_on(0, 60, 90)
        track.raw(480, bytes([0x90, 60, 0]))
        track.end(480)
        result = parse_smf(build_smf([track], midi_format=0))
        notes = result.sequences[0].tracks[0].notes
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].end_tick, 480)
        self.assertFalse(notes[0].assumed_duration)

    def test_running_status_and_unknown_chunk(self) -> None:
        track = MidiTrack().track_name("Running").tempo(0, 120)
        for i in range(6):
            track.note(i * 240, 60 + i, 200, 80)
        track.end(6 * 240)
        data = build_smf([track], midi_format=0, running_status=True)
        # Inject an unknown chunk before the track, with a small payload.
        header = data[:14]
        track_chunk = data[14:]
        unknown = b"Xtra" + (5).to_bytes(4, "big") + b"hello"
        result = parse_smf(header + unknown + track_chunk)
        self.assertEqual(result.note_count, 6)
        self.assertTrue(any("unknown chunk" in warning for warning in result.warnings))

    def test_seven_eight_bars(self) -> None:
        track = MidiTrack().track_name("7/8").tempo(0, 100).time_signature(0, 7, 8)
        for bar in range(8):
            for step in range(7):
                track.note(bar * 7 * 240 + step * 240, 36 + step, 200, 80)
        track.end(8 * 7 * 240)
        result = parse_smf(build_smf([track], midi_format=0))
        sequence = result.sequences[0]
        self.assertEqual(sequence.time_signatures[0].label, "7/8")
        self.assertAlmostEqual(sequence.bars or 0, 8.0, places=2)
        self.assertAlmostEqual(sequence.duration_beats, 28.0, places=2)

    def test_program_bank_and_controllers(self) -> None:
        track = MidiTrack().track_name("Controllers").tempo(0, 120)
        track.bank(0, 1, 2).program(0, 42).cc(120, 10, 64).cc(240, 64, 127).cc(480, 64, 0)
        track.note(0, 60, 480, 80)
        track.end(960)
        result = parse_smf(build_smf([track], midi_format=0))
        parsed = result.sequences[0].tracks[0]
        self.assertEqual(parsed.program, 42)
        self.assertEqual(parsed.bank_msb, 1)
        self.assertEqual(parsed.bank_lsb, 2)
        self.assertEqual(parsed.controller_counts[10], 1)
        self.assertEqual(parsed.sustain_events, 2)

    def test_unusual_metric_divisions(self) -> None:
        for division in (192, 384, 960):
            track = MidiTrack().track_name("Division").tempo(0, 100)
            track.note(0, 60, division, 80)
            track.end(division)
            result = parse_smf(build_smf([track], midi_format=0, division=division))
            self.assertEqual(result.ticks_per_quarter, division)
            self.assertAlmostEqual(result.sequences[0].duration_seconds, 0.6, places=3)

    def test_meta_only_file_has_no_tracks(self) -> None:
        track = MidiTrack().track_name("Metadata only").text(0, 0x01, "hello").tempo(0, 100)
        track.end(0)
        result = parse_smf(build_smf([track], midi_format=0))
        self.assertEqual(result.note_count, 0)
        self.assertEqual(result.sequences[0].track_count, 0)
        self.assertEqual(result.duration_seconds, 0.0)

    def test_malformed_header_rejected(self) -> None:
        for data in (b"", b"not a midi file", b"MThd" + (6).to_bytes(4, "big") + b"\x00\x00\x00\x01\x00\x00\x01\xe0"):
            with self.assertRaises(MidiParseError):
                parse_smf(data)

    def test_zero_time_division_rejected(self) -> None:
        track = MidiTrack().track_name("Zero Division").end(480)
        data = build_smf([track], midi_format=0, division=1)
        # Replace division with zero while keeping a structurally valid header.
        data = data[:12] + b"\x00\x00" + data[14:]
        with self.assertRaises(MidiParseError):
            parse_smf(data)

    def test_format_two_with_mismatched_declared_tracks(self) -> None:
        first = MidiTrack().track_name("A").tempo(0, 120).note(0, 60, 480, 80).end(480)
        second = MidiTrack().track_name("B").tempo(0, 90).note(0, 48, 480, 90).end(480)
        result = parse_smf(build_smf([first, second], midi_format=2, declared_tracks=1))
        self.assertEqual(len(result.sequences), 2)
        self.assertTrue(any("declares 1" in warning for warning in result.warnings))

    def test_truncated_track_chunk_is_handled(self) -> None:
        track = MidiTrack().track_name("Truncated").tempo(0, 120)
        for i in range(3):
            track.note(i * 480, 60 + i, 240, 80)
        track.end(3 * 480)
        data = bytearray(build_smf([track], midi_format=0))
        # Make declared MTrk length longer than available bytes.
        data[14 + 4:14 + 8] = (9999).to_bytes(4, "big")
        result = parse_smf(bytes(data))
        self.assertGreater(result.note_count, 0)
        self.assertTrue(any("shorter than declared" in warning for warning in result.warnings))

    def test_vlq_round_trip(self) -> None:
        for value in (0, 1, 127, 128, 255, 16383, 16384, 0x0FFFFFFF):
            encoded = vlq(value)
            self.assertLessEqual(len(encoded), 4)
        with self.assertRaises(ValueError):
            vlq(-1)


if __name__ == "__main__":
    unittest.main()
