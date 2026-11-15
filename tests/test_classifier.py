from __future__ import annotations

import tracemalloc
import unittest

from midivault.engine.analytics import analyze
from midivault.engine.classifier import classify
from midivault.engine.smf_parser import parse_smf
from tests.midi_builder import MidiTrack, build_smf


def classify_bytes(data: bytes, filename: str, folder: str = "") -> tuple:
    parse_result = parse_smf(data)
    analysis = analyze(parse_result, filename, folder)
    classification = classify(parse_result, analysis, filename, folder)
    return parse_result, analysis, classification


class ClassifierTests(unittest.TestCase):
    def test_program_and_track_name_produce_evidence(self) -> None:
        track = MidiTrack().track_name("Funk Bass").program(0, 33).tempo(0, 108)
        track.time_signature(0, 4, 4)
        for bar in range(4):
            for step, degree in enumerate([0, 0, 3, 5, 7, 5, 3, 0]):
                track.note(bar * 4 * 480 + step * 240, 36 + degree, 180, 90)
        track.end(4 * 4 * 480)
        _parse, _analysis, classification = classify_bytes(
            build_smf([track], midi_format=0), "Funk Bassline.mid", "Bass"
        )
        file_class = classification["file"]
        self.assertEqual(file_class["instrument"], "Bass")
        self.assertEqual(file_class["role"], "Bassline")
        self.assertGreater(file_class["instrument_confidence"], 0.6)
        evidence_labels = [item["label"] for item in file_class["instrument_evidence"]]
        self.assertTrue(any("Program" in label for label in evidence_labels))
        self.assertTrue(any("Track" in label or "track" in label for label in evidence_labels))

    def test_missing_program_unknown_preference(self) -> None:
        track = MidiTrack().track_name("Untitled Sketch").tempo(0, 100)
        track.time_signature(0, 4, 4)
        for step, pitch in enumerate([64, 67, 71, 74, 72, 69, 65, 62]):
            track.note(step * 240, pitch, 180, 80)
        track.end(8 * 240)
        _parse, _analysis, classification = classify_bytes(
            build_smf([track], midi_format=0), "unknown.mid", ""
        )
        # No program, no descriptive text and no definitive register evidence.
        self.assertEqual(classification["file"]["instrument"], "Unknown")
        self.assertEqual(classification["file"]["role"], "Lead/melody")
        self.assertTrue(classification["file"]["uncertain"])

    def test_misleading_name_is_conflict_not_proof(self) -> None:
        track = MidiTrack().track_name("Bass Groove").program(0, 4).tempo(0, 120)
        track.time_signature(0, 4, 4)
        for bar in range(4):
            base = bar * 4 * 480
            for pitch in (55, 59, 62, 67):
                track.note(base, pitch, 1600, 75)
        track.end(4 * 4 * 480)
        _parse, _analysis, classification = classify_bytes(
            build_smf([track], midi_format=0), "Misleading Bass Name.mid", "Misc"
        )
        file_class = classification["file"]
        self.assertEqual(file_class["instrument"], "Piano/keys")
        self.assertTrue(file_class["uncertain"])
        self.assertTrue(file_class["conflicts"])
        joined = " ".join(item["label"] for item in file_class["conflicts"]).lower()
        self.assertIn("filename", joined)

    def test_mixed_arrangement_track_level_roles(self) -> None:
        conductor = MidiTrack().track_name("Conductor").tempo(0, 118).time_signature(0, 4, 4)
        conductor.end(4 * 4 * 480)
        drums = MidiTrack().track_name("Drum Kit")
        bass = MidiTrack().track_name("Bass").program(0, 34)
        keys = MidiTrack().track_name("Rhodes Chords").program(0, 4)
        lead = MidiTrack().track_name("Lead Line").program(0, 81)
        for bar in range(4):
            base = bar * 4 * 480
            for beat in range(4):
                drums.note(base + beat * 480, 36, 20, 110)
            for beat in (1, 3):
                drums.note(base + beat * 480, 38, 20, 100)
            for step, degree in enumerate([0, 0, 3, 5, 7, 5, 3, 0]):
                bass.note(base + step * 240, 36 + degree, 160, 90)
            for pitch in (60, 64, 67, 71):
                keys.note(base, pitch, 1600, 70)
            for step, pitch in enumerate([72, 74, 76, 79, 76, 74]):
                lead.note(base + step * 240, pitch, 180, 85)
        for track in (drums, bass, keys, lead):
            track.end(4 * 4 * 480)
        _parse, analysis, classification = classify_bytes(
            build_smf([conductor, drums, bass, keys, lead], midi_format=1),
            "Midnight Drive.mid", "Full Arrangements",
        )
        file_class = classification["file"]
        self.assertEqual(file_class["instrument"], "Mixed arrangement")
        self.assertEqual(file_class["role"], "Complete song or multi-part arrangement")
        tracks = {track["name"]: track for track in classification["tracks"]}
        self.assertEqual(tracks["Drum Kit"]["instrument"], "Drums/percussion")
        self.assertEqual(tracks["Drum Kit"]["role"], "Drum groove")
        self.assertEqual(tracks["Bass"]["instrument"], "Bass")
        self.assertEqual(tracks["Bass"]["role"], "Bassline")
        self.assertEqual(tracks["Rhodes Chords"]["role"], "Chord progression")
        self.assertEqual(tracks["Lead Line"]["role"], "Lead/melody")
        self.assertEqual(analysis["file"]["key"]["source"], "estimated")

    def test_embedded_and_estimated_key_are_distinguished(self) -> None:
        embedded = MidiTrack().track_name("Key Sig").program(0, 0).tempo(0, 120).key_signature(0, -1)
        embedded.time_signature(0, 4, 4)
        for index, pitch in enumerate([65, 69, 72, 77, 72, 69, 65, 67, 69, 72, 74, 77]):
            embedded.note(index * 240, pitch, 200, 80)
        embedded.end(12 * 240)
        _p, analysis, classification = classify_bytes(build_smf([embedded], midi_format=0), "embedded.mid")
        self.assertEqual(analysis["file"]["key"]["source"], "embedded")
        self.assertEqual(analysis["file"]["key"]["embedded"], "F major")
        self.assertFalse(analysis["file"]["key"]["uncertain"])

        no_key = MidiTrack().track_name("No Key").program(0, 0).tempo(0, 120).time_signature(0, 4, 4)
        for index, pitch in enumerate([60, 64, 67, 72, 67, 64, 60, 62, 64, 67, 69, 72, 67, 64, 60, 55] * 2):
            no_key.note(index * 120, pitch, 100, 80)
        no_key.end(32 * 120)
        _p, analysis, classification = classify_bytes(build_smf([no_key], midi_format=0), "no-key.mid")
        key = analysis["file"]["key"]
        self.assertEqual(key["source"], "estimated")
        self.assertEqual(key["embedded"], None)
        self.assertIsNotNone(key["estimated"])
        self.assertIsNotNone(key["confidence"])

    def test_assumed_tempo_and_meter_are_reported(self) -> None:
        track = MidiTrack().track_name("Piano").program(0, 0)
        for index in range(8):
            track.note(index * 240, 60 + index, 200, 80)
        track.end(8 * 240)
        _parse, analysis, _classification = classify_bytes(build_smf([track], midi_format=0), "defaults.mid")
        self.assertEqual(analysis["file"]["tempo"]["source"], "assumed")
        self.assertTrue(analysis["file"]["tempo"]["assumed"])
        self.assertEqual(analysis["file"]["time_signature"]["initial"], "4/4")
        self.assertTrue(analysis["file"]["time_signature"]["assumed"])

    def test_format_two_sequences_keep_separate_track_labels(self) -> None:
        piano = MidiTrack().track_name("Sequence A").program(0, 0).tempo(0, 100)
        piano.time_signature(0, 4, 4)
        for step, pitch in enumerate([60, 64, 67, 72]):
            piano.note(step * 240, pitch, 200, 80)
        piano.end(960)
        drums = MidiTrack().track_name("Sequence B · Drums").tempo(0, 100)
        drums.time_signature(0, 4, 4)
        for beat in range(4):
            drums.note(beat * 480, 36, 20, 110, channel=9)
        drums.end(1920)
        parse_result, analysis, classification = classify_bytes(
            build_smf([piano, drums], midi_format=2), "two-sequences.mid"
        )
        self.assertEqual(parse_result.format, 2)
        self.assertEqual(len(parse_result.sequences), 2)
        self.assertTrue(classification["file"]["format_2_multi_sequence"])
        track_labels = {(track["sequence_index"], track["track_index"]): track for track in classification["tracks"]}
        self.assertEqual(track_labels[(0, 0)]["instrument"], "Piano/keys")
        self.assertEqual(track_labels[(1, 0)]["instrument"], "Drums/percussion")
        self.assertNotEqual(track_labels[(0, 0)]["instrument"], track_labels[(1, 0)]["instrument"])

    def test_genre_never_claims_high_confidence(self) -> None:
        track = MidiTrack().track_name("Chords").program(0, 4).tempo(0, 90).time_signature(0, 4, 4)
        for bar in range(4):
            for pitch in (60, 64, 67):
                track.note(bar * 4 * 480, pitch, 1500, 70)
        track.end(4 * 4 * 480)
        _p, _a, classification = classify_bytes(build_smf([track], midi_format=0), "chords.mid")
        self.assertLessEqual(classification["file"]["genre_confidence"], 0.45)

    def test_unnamed_track_falls_back_to_channel_label(self) -> None:
        # Regression: the unnamed-track fallback read `track.channel` from a
        # dict, raising AttributeError on every EZDrummer-style clip. The
        # label must come from the "channel" key instead.
        track = MidiTrack().tempo(0, 120).time_signature(0, 4, 4)
        for bar in range(2):
            for step, pitch in enumerate((36, 38, 42, 38, 36, 38, 42, 38)):
                track.note((bar * 8 + step) * 240, pitch, 120, 100, channel=9)
        track.end(2 * 8 * 240)
        _p, _a, classification = classify_bytes(
            build_smf([track], midi_format=0), "unnamed groove.mid", ""
        )
        self.assertEqual(classification["file"]["instrument"], "Drums/percussion")
        labels = [item["label"] for item in classification["file"]["instrument_evidence"]]
        self.assertTrue(any("ch 10" in label for label in labels), labels)

    def test_silent_bar_does_not_break_rhythm_analysis(self) -> None:
        # Regression: a clip that rests for a whole bar made the per-bar list
        # jump past its end, raising IndexError inside _grid_rhythm. Bar 1
        # here is deliberately empty between bars 0 and 2.
        track = MidiTrack().track_name("Sparse").tempo(0, 120).time_signature(0, 4, 4)
        for step in range(3):
            track.note(step * 480, 36 + step, 200, 90)
            track.note((2 * 4 + step) * 480, 48 + step, 200, 90)
        track.end(3 * 4 * 480)
        _p, analysis, _c = classify_bytes(
            build_smf([track], midi_format=0), "sparse.mid", ""
        )
        self.assertEqual(len(analysis["tracks"]), 1)
        self.assertIsInstance(analysis["tracks"][0]["pattern_repeat"], float)

    def test_a_stranded_note_cannot_stretch_the_rhythm_grid(self) -> None:
        """The bar grid follows the notes, not the address space between them.

        An SMF delta addresses ~268M ticks, so a broken export can put one note
        a million bars after the loop. ``_grid_rhythm`` grew its per-bar list to
        reach it: measured at 1.1M empty sets (about 230MB) for a ten-note file,
        and the empty bars then dominated ``pattern_repeat``, reporting a tight
        loop as almost non-repeating.
        """
        def loop(*, stranded: bool) -> dict:
            track = MidiTrack().track_name("Loop").tempo(0, 120).time_signature(0, 4, 4)
            for bar in range(8):
                for step in range(4):
                    track.note(bar * 4 * 480 + step * 240, 36 + step, 180, 90)
            if stranded:
                track.note(0x0FFFFF00, 60, 240, 90)
                track.end(0x0FFFFF00 + 480)
            else:
                track.end(8 * 4 * 480)
            _p, analysis, _c = classify_bytes(
                build_smf([track], midi_format=0), "loop.mid", ""
            )
            return analysis["tracks"][0]

        tight = loop(stranded=False)
        self.assertAlmostEqual(tight["pattern_repeat"], 1.0, places=3)

        tracemalloc.start()
        try:
            padded = loop(stranded=True)
            peak_bytes = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

        # The far note must not dilute the measure of the eight bars it is not in.
        self.assertAlmostEqual(padded["pattern_repeat"], 1.0, places=3)
        self.assertEqual(padded["grid_occupancy"], tight["grid_occupancy"])
        # Measured bound on the allocation, not a timing: this is the cost the
        # unbounded grid put on the worker for a file of ten notes.
        self.assertLess(peak_bytes, 24 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
