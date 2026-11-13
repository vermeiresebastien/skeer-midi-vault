from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["SKEER_SCAN_EXECUTOR"] = "threads"

from midivault.db import Database
from midivault.scanner import ScanManager
from tests.midi_builder import MidiTrack, build_smf


def simple_midi(pitch: int = 60, tempo: float = 120.0) -> bytes:
    track = MidiTrack().track_name("Test Piano").program(0, 0).tempo(0, tempo).time_signature(0, 4, 4)
    for index in range(8):
        track.note(index * 240, pitch + (index % 4) * 2, 200, 80 + index)
    track.end(8 * 240)
    return build_smf([track], midi_format=0)


def bass_midi(shift: int = 0) -> bytes:
    track = MidiTrack().track_name("Bass").program(0, 33).tempo(0, 108).time_signature(0, 4, 4)
    for bar in range(2):
        for step, degree in enumerate([0, 0, 3, 5, 7, 5, 3, 0]):
            track.note(bar * 4 * 480 + step * 240, 36 + degree + (shift if step == 5 else 0), 190, 90)
    track.end(8 * 480)
    return build_smf([track], midi_format=0)


def wait_scan(scanner: ScanManager, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = scanner.get_status()
        if not status["active"]:
            return status
        time.sleep(0.05)
    raise AssertionError(f"scan did not finish: {scanner.get_status()}")


class ScannerDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="midivault-test-")
        self.root = Path(self.temp.name)
        self.library = self.root / "music"
        self.library.mkdir()
        (self.library / "bass").mkdir()
        (self.library / "keys").mkdir()
        (self.library / "excluded").mkdir()
        (self.library / "bass" / "First Bass.mid").write_bytes(bass_midi())
        (self.library / "bass" / "Second Bass.MIDI").write_bytes(bass_midi(shift=2))
        (self.library / "keys" / "Simple Piano.mid").write_bytes(simple_midi())
        (self.library / "excluded" / "Hidden.mid").write_bytes(simple_midi(72))
        (self.library / "corrupt.mid").write_bytes(b"this is not midi")
        (self.library / "notes.txt").write_text("not midi", encoding="utf-8")
        self.db = Database(self.root / "data.sqlite3")
        self.source = self.db.add_source(str(self.library), "Test Library", optional=True, enabled=True)
        self.db.add_exclude(str(self.library / "excluded"))
        self.scanner = ScanManager(self.db, self.root)
        self.scanned = self.scanner.start(
            source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1,
        )
        wait_scan(self.scanner)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_scan_discovers_indexes_and_reports_failures(self) -> None:
        stats = self.db.stats()
        self.assertEqual(stats["indexed"], 3)
        self.assertEqual(stats["failed"], 1)
        library = self.db.query_library(page_size=50)
        names = {item["filename"] for item in library["items"]}
        self.assertIn("First Bass.mid", names)
        self.assertIn("Second Bass.MIDI", names)
        self.assertIn("Simple Piano.mid", names)
        self.assertNotIn("Hidden.mid", names)
        self.assertNotIn("notes.txt", names)
        self.assertEqual(len(self.db.list_scan_issues()), 1)
        first = next(item for item in library["items"] if item["filename"] == "First Bass.mid")
        self.assertTrue(first["content_hash"])
        self.assertEqual(first["parser_version"], 1)
        self.assertEqual(first["instrument"], "Bass")
        self.assertEqual(first["role"], "Bassline")
        self.assertTrue(first["key_name"])

    def test_full_text_search_and_filters(self) -> None:
        result = self.db.query_library(q="bass", page_size=10)
        self.assertEqual(result["total"], 2)
        result = self.db.query_library(instrument="Piano/keys", page_size=10)
        self.assertEqual(result["total"], 1)
        result = self.db.query_library(tempo_min="100", tempo_max="130", page_size=10)
        self.assertEqual(result["total"], 3)
        result = self.db.query_library(folder=str(self.library / "bass"), page_size=10)
        self.assertEqual(result["total"], 2)
        result = self.db.query_library(q="piano", page_size=10)
        self.assertEqual(result["total"], 1)
        # Searching an embedded track name is required.
        result = self.db.query_library(q="Test Piano", page_size=10)
        self.assertEqual(result["total"], 1)

    def test_source_file_is_not_modified(self) -> None:
        path = self.library / "keys" / "Simple Piano.mid"
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco", workers=1)
        wait_scan(self.scanner)
        after = (path.read_bytes(), path.stat().st_mtime_ns)
        self.assertEqual(before, after)

    def test_incremental_rescan_skips_unchanged_files(self) -> None:
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        status = wait_scan(self.scanner)
        self.assertEqual(status["indexed"], 0)
        self.assertEqual(status["skipped"], 3)
        # DB entries and user data survive.
        self.assertEqual(self.db.stats()["indexed"], 3)

    def test_changed_file_is_reparsed(self) -> None:
        path = self.library / "keys" / "Simple Piano.mid"
        old = self.db.query_library(q="Simple Piano")["items"][0]
        old_hash = old["content_hash"]
        path.write_bytes(simple_midi(pitch=64))
        new_time = time.time_ns() + 2_000_000
        os.utime(path, ns=(new_time, new_time))
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        status = wait_scan(self.scanner)
        self.assertEqual(status["indexed"], 1)
        changed = self.db.query_library(q="Simple Piano")["items"][0]
        self.assertNotEqual(changed["content_hash"], old_hash)
        self.assertEqual(changed["pitch_min"], 64)

    def test_user_data_survives_full_rescan(self) -> None:
        target = self.db.query_library(q="First Bass")["items"][0]
        file_id = target["id"]
        self.db.set_favorite(file_id, True)
        self.db.set_user_notes(file_id, "A private note")
        self.db.add_tag(file_id, "keeper")
        collection = self.db.create_collection("Test collection")
        self.db.add_to_collection(collection["id"], [file_id])
        details = self.db.get_file_details(file_id)
        track = details["tracks"][0]
        self.db.set_file_label(file_id, "instrument", "Synth")
        self.db.set_track_label(
            file_id, track["sequence_index"], track["track_index"], "role", "Arpeggio",
        )
        auto_instrument = details["file"]["auto_instrument"]
        self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco", workers=1)
        wait_scan(self.scanner)
        details = self.db.get_file_details(file_id)
        self.assertTrue(details["file"]["favorite"])
        self.assertEqual(details["file"]["user_notes"], "A private note")
        self.assertEqual(details["file"]["instrument"], "Synth")
        self.assertEqual(details["file"]["instrument_source"], "user")
        self.assertEqual(details["file"]["auto_instrument"], auto_instrument)
        self.assertTrue(any(tag["name"] == "keeper" for tag in details["tags"]))
        self.assertTrue(any(item["name"] == "Test collection" for item in details["collections"]))
        self.assertEqual(details["tracks"][0]["role"], "Arpeggio")
        self.assertEqual(details["tracks"][0]["role_source"], "user")
        # The automatic prediction is preserved separately from the user label.
        predictions = [p for p in details["predictions"] if p["dimension"] == "instrument" and p["sequence_index"] == -1]
        self.assertTrue(predictions)
        self.assertIsNotNone(predictions[0]["predicted"])
        # Reverting restores the untouched automatic label.
        reverted = self.db.set_file_label(file_id, "instrument", "", clear=True)
        self.assertEqual(reverted["file"]["instrument"], auto_instrument)
        self.assertEqual(reverted["file"]["instrument_source"], "auto")

    def test_exact_duplicates_are_grouped_but_not_similar(self) -> None:
        duplicate = self.library / "keys" / "Simple Piano Copy.mid"
        duplicate.write_bytes(simple_midi())
        self.db.add_exclude("/nonexistent/exclude")
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        wait_scan(self.scanner)
        groups = self.db.duplicate_groups("exact")
        self.assertGreaterEqual(groups["group_count"], 1)
        all_members = [member for group in groups["groups"] for member in group["members"]]
        names = {member["filename"] for member in all_members}
        self.assertIn("Simple Piano.mid", names)
        self.assertIn("Simple Piano Copy.mid", names)
        # Exact copies must not be re-labelled as merely similar.
        for member in all_members:
            if member["filename"] == "Simple Piano.mid":
                similar_ids = {item["id"] for group in self.db.duplicate_groups("similar")["groups"] for item in group["members"]}
                self.assertNotIn(member["id"], similar_ids)

    def test_deleted_file_is_marked_missing_but_retained(self) -> None:
        path = self.library / "keys" / "Simple Piano.mid"
        path.unlink()
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        wait_scan(self.scanner)
        rows = self.db.query_library(q="Simple Piano", scan_state="missing", page_size=10)
        self.assertEqual(rows["total"], 1)
        self.assertEqual(rows["items"][0]["scan_state"], "missing")
        self.assertEqual(rows["items"][0]["is_missing"], 1)

    def test_unavailable_source_keeps_entries(self) -> None:
        before = self.db.stats()["indexed"]
        self.db.set_user_notes(self.db.query_library(q="Bass")["items"][0]["id"], "keep me")
        self.library.rename(self.root / "music-away")
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        wait_scan(self.scanner)
        sources = self.db.list_sources()
        current = next(item for item in sources if item["id"] == self.source["id"])
        self.assertFalse(current["available"])
        self.assertEqual(self.db.stats()["indexed"], before)
        self.assertEqual(self.db.stats()["missing"], 0)

    def test_pause_resume_and_cancel(self) -> None:
        # Slow the worker slightly so the pause/cancel checkpoints are observable
        # without making the test depend on machine speed.
        from unittest.mock import patch
        import midivault.scanner as scanner_module

        for index in range(25):
            (self.library / "bulk").mkdir(exist_ok=True)
            (self.library / "bulk" / f"bulk-{index}.mid").write_bytes(simple_midi(48 + index))
        original = scanner_module.parse_and_classify_file

        def slow_worker(job: dict) -> dict:
            time.sleep(0.06)
            return original(job)

        with patch.object(scanner_module, "parse_and_classify_file", side_effect=slow_worker):
            self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco", workers=1)
            time.sleep(0.18)
            paused_status = self.scanner.pause()
            self.assertEqual(paused_status["state"], "paused")
            # An in-flight parse may still commit once; after it settles the
            # paused scan must not start or process any new work.
            time.sleep(0.25)
            first_count = self.scanner.get_status()["indexed"]
            time.sleep(0.3)
            second_count = self.scanner.get_status()["indexed"]
            self.assertEqual(first_count, second_count)
            self.scanner.resume()
            status = wait_scan(self.scanner)
            self.assertEqual(status["state"], "completed")
            self.assertGreater(self.db.stats()["indexed"], 3)

            # Cancelling a fresh scan leaves committed index entries intact.
            self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco", workers=1)
            time.sleep(0.12)
            cancel_status = self.scanner.cancel()
            self.assertIn(cancel_status["state"], ("cancelling", "cancelled", "completed"))
            cancelled = wait_scan(self.scanner)
            self.assertEqual(cancelled["state"], "cancelled")
            self.assertGreater(self.db.stats()["indexed"], 0)


if __name__ == "__main__":
    unittest.main()
