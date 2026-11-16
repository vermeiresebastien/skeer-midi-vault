from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ["SKEER_SCAN_EXECUTOR"] = "threads"

from midivault.db import Database
from midivault.engine.versions import PARSER_VERSION
from midivault.scanner import ScanError, ScanManager
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
        # Windows can hold a just-written WAL file one beat too long; that must not read as a test failure.
        self.temp = tempfile.TemporaryDirectory(prefix="midivault-test-", ignore_cleanup_errors=True)
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
        self.assertEqual(first["parser_version"], PARSER_VERSION)
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


    # ------------------------------------------------------ index correctness
    def _states(self) -> dict[str, dict]:
        with self.db.connection() as con:
            return {row["path"]: dict(row) for row in con.execute(
                "SELECT path,scan_state,is_missing,source_id,parser_version FROM files"
            ).fetchall()}

    def test_deleting_a_source_does_not_leave_rows_claiming_to_be_indexed(self) -> None:
        """A deleted source takes the only path to revalidating its rows with it.

        ``files.source_id`` is ON DELETE SET NULL and the missing-file sweep
        matches on source_id, so every row kept reporting "indexed" for a path no
        later scan would ever visit. They stayed in the library, the counts and
        search results whatever happened on disk. The rows and their user data
        are kept; only the state is corrected.
        """
        rows = self._states()
        owned = [path for path, row in rows.items() if row["scan_state"] == "indexed"]
        self.assertEqual(len(owned), 3)
        self.db.delete_source(self.source["id"])
        after = self._states()
        for path in owned:
            self.assertEqual(after[path]["scan_state"], "missing", path)
            self.assertEqual(after[path]["is_missing"], 1, path)
            self.assertIsNone(after[path]["source_id"], path)
        self.assertEqual(self.db.stats()["indexed"], 0)
        self.assertEqual(self.db.list_sources(with_counts=False), [])
        # The sweep cannot reach them any more either — nothing is left to claim.
        self.assertEqual(self.db.orphan_indexed_rows(), [])

    def test_a_scan_sweeps_rows_that_no_source_can_reach(self) -> None:
        """An index written before that fix can hold rows with no source at all."""
        ghost = self.library / "bass" / "First Bass.mid"
        keeper = self.library / "keys" / "Simple Piano.mid"
        with self.db.connection(write=True) as con:
            con.execute("UPDATE files SET source_id=NULL WHERE path IN (?,?)",
                        (str(ghost), str(keeper)))
        ghost.unlink()
        other = self.root / "other"
        other.mkdir()
        (other / "Solo Bass.mid").write_bytes(bass_midi(shift=4))
        source = self.db.add_source(str(other), "Other", optional=True, enabled=True)
        self.scanner.start(source_ids=[source["id"]], mode="incremental", intensity="eco", workers=1)
        wait_scan(self.scanner)
        states = self._states()
        self.assertEqual(states[str(ghost)]["scan_state"], "missing")
        self.assertEqual(states[str(ghost)]["is_missing"], 1)
        # A row whose file is still on disk is not a ghost: it stays usable,
        # because blanket-marking every unowned row would be its own bug.
        self.assertEqual(states[str(keeper)]["scan_state"], "indexed")
        self.assertEqual(states[str(other / "Solo Bass.mid")]["scan_state"], "indexed")

    def test_invalidating_one_source_leaves_another_ones_analysis_alone(self) -> None:
        """A rebuild re-analyses the sources it will actually walk, not all of them."""
        other = self.root / "keys-only"
        other.mkdir()
        (other / "Solo Piano.mid").write_bytes(simple_midi(67))
        second = self.db.add_source(str(other), "Keys only", optional=True, enabled=True)
        self.scanner.start(source_ids=[second["id"]], mode="incremental", intensity="eco", workers=1)
        wait_scan(self.scanner)

        first_id = self.db.query_library(q="First Bass")["items"][0]["id"]
        self.db.set_file_label(first_id, "instrument", "Synth")
        self.db.invalidate_sources([self.source["id"]])

        for path, row in self._states().items():
            if row["source_id"] == self.source["id"]:
                self.assertEqual(row["parser_version"], 0, path)
            else:
                self.assertEqual(row["parser_version"], PARSER_VERSION, path)
        with self.db.connection() as con:
            def unknown_tracks(source_id: int) -> int:
                return con.execute(
                    "SELECT COUNT(*) AS n FROM tracks WHERE auto_instrument='Unknown' "
                    "AND file_id IN (SELECT id FROM files WHERE source_id=?)",
                    (source_id,),
                ).fetchone()["n"]

            self.assertGreater(unknown_tracks(self.source["id"]), 0)
            self.assertEqual(unknown_tracks(second["id"]), 0,
                             "a file this run will not touch kept its stale reset")
            kept = con.execute("SELECT instrument, instrument_source FROM files WHERE id=?",
                               (first_id,)).fetchone()
        self.assertEqual(kept["instrument"], "Synth")
        self.assertEqual(kept["instrument_source"], "user")

    def test_a_refused_rebuild_does_not_empty_the_index(self) -> None:
        """The old route cleared the cache first and started the scan second.

        When the scan then refused — no source selected, one already running —
        the index was left zeroed and no later scan could repair it.
        """
        with self.assertRaises(ScanError):
            self.scanner.start(source_ids=[], mode="full", intensity="eco", invalidate=True)
        self.assertEqual(self.db.stats()["indexed"], 3)
        with self.db.connection() as con:
            zeroed = con.execute("SELECT COUNT(*) AS n FROM files WHERE parser_version=0").fetchone()["n"]
            unknown = con.execute(
                "SELECT COUNT(*) AS n FROM tracks WHERE auto_instrument='Unknown'"
            ).fetchone()["n"]
        self.assertEqual(zeroed, 0, "a refused run must not have invalidated anything")
        self.assertEqual(unknown, 0)

    def test_invalidate_on_start_clears_the_derived_cache_for_that_run(self) -> None:
        self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco",
                           workers=1, invalidate=True)
        status = wait_scan(self.scanner)
        self.assertEqual(status["indexed"], 3)
        self.assertEqual(self.db.stats()["indexed"], 3)
        self.assertEqual(
            [row for row in self._states().values()
             if row["scan_state"] == "indexed" and row["parser_version"] != PARSER_VERSION], []
        )

    # ------------------------------------------------------- unchanged checks
    def _make_same_size_edit(self) -> tuple[Path, str, str]:
        path = self.library / "bass" / "First Bass.mid"
        original = path.read_bytes()
        edited = bass_midi(shift=3)
        # The whole point of the fixture: same length, same mtime, different bytes.
        self.assertEqual(len(edited), len(original))
        self.assertNotEqual(edited, original)
        stamp = path.stat().st_mtime_ns
        before = self.db.query_library(q="First Bass")["items"][0]["content_hash"]
        path.write_bytes(edited)
        os.utime(path, ns=(stamp, stamp))
        stat = path.stat()
        self.assertEqual(stat.st_size, len(original))
        self.assertEqual(stat.st_mtime_ns, stamp)
        return path, before, edited

    def test_an_edit_that_keeps_size_and_mtime_is_still_reindexed(self) -> None:
        """Size plus mtime is not a content check.

        A copy restore, a sync client or a metadata-preserving editor can leave a
        changed file with the length and timestamp the index already recorded, and
        the incremental scan then skipped it forever: the library kept playing —
        and searching on — bytes that are no longer in the file.
        """
        _path, before, _edited = self._make_same_size_edit()
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental",
                           intensity="eco", workers=1)
        status = wait_scan(self.scanner)
        self.assertEqual(status["indexed"], 1)
        self.assertEqual(status["skipped"], 2)
        after = self.db.query_library(q="First Bass")["items"][0]
        self.assertNotEqual(after["content_hash"], before)

    def test_verification_can_be_turned_off_and_the_cheap_skip_returns(self) -> None:
        """The hash check is a cost the user may decline, and it is visible."""
        _path, before, _edited = self._make_same_size_edit()
        self.db.update_settings({"verify_unchanged": "0"})
        self.assertEqual(self.db.get_settings()["verify_unchanged"], "0")
        self.scanner.start(source_ids=[self.source["id"]], mode="incremental",
                           intensity="eco", workers=1)
        status = wait_scan(self.scanner)
        self.assertEqual(status["skipped"], 3)
        self.assertEqual(status["indexed"], 0)
        stored = self.db.query_library(q="First Bass")["items"][0]
        self.assertEqual(stored["content_hash"], before)

    # ------------------------------------------------------------ bulk writes
    def test_bulk_labels_use_one_transaction_and_record_the_correction(self) -> None:
        ids = [item["id"] for item in self.db.query_library(page_size=50)["items"]
               if item["scan_state"] == "indexed"]
        self.assertGreaterEqual(len(ids), 3)
        connections: list[int] = []
        original = Database._connect

        def counting(handler):
            connections.append(1)
            return original(handler)

        with mock.patch.object(Database, "_connect", counting):
            changed = self.db.bulk_file_labels(ids, "instrument", "Drums")
        self.assertEqual(changed, len(ids))
        self.assertEqual(len(connections), 1,
                         f"a bulk edit opened {len(connections)} connections for {len(ids)} files")
        for file_id in ids:
            details = self.db.get_file_details(file_id)
            self.assertEqual(details["file"]["instrument"], "Drums")
            self.assertEqual(details["file"]["instrument_source"], "user")
        with self.db.connection() as con:
            actions = con.execute(
                "SELECT action, COUNT(*) AS n FROM file_corrections WHERE dimension='instrument' "
                "GROUP BY action"
            ).fetchall()
        self.assertEqual({row["action"]: row["n"] for row in actions}, {"corrected": len(ids)})
        # The automatic prediction is untouched, so the label can still be reverted.
        reverted = self.db.set_file_label(ids[0], "instrument", "", clear=True)
        self.assertNotEqual(reverted["file"]["instrument"], "Drums")
        self.assertEqual(reverted["file"]["instrument_source"], "auto")

    def test_a_scan_reads_the_index_through_one_connection_per_run(self) -> None:
        """The skip check asks about every discovered file, and asks it through one handle.

        Opening a fresh handle per question was measurable: about 1.3 ms per file
        on the index alone, most of it SQLite open and WAL-header cost, on a scan
        whose whole purpose is to avoid work.

        The recording window is what had to be fixed here, not the fixture. `start()`
        returns as soon as the thread is running and the walk yields its first file
        right away, so a body that installed the spy after that call raced the run it
        was measuring: on 2 of 20 isolated runs of this exact fixture the scan finished
        before the patch landed and only 2 of the 4 lookups were recorded. A floor of 3
        was then met by a slow run's tail and missed by a fast run's head, which is a
        flake in the test body and says nothing about the scan.
        """
        seen: list[object] = []
        original = self.db.get_scan_file_record

        def spy(path, *, con=None):
            seen.append(con)
            return original(path, con=con)

        # The expectation is counted from the fixture, not from the run under test: setUp()
        # scanned this library once, so the index holds exactly one row per file the walk is
        # allowed to discover. Four of the six files on disk qualify -- First Bass.mid,
        # Second Bass.MIDI, Simple Piano.mid and corrupt.mid. library/excluded/Hidden.mid is
        # under the path add_exclude() was given and library/notes.txt is not a supported
        # extension (midivault/engine/versions.py:28), so neither is yielded and neither is
        # asked about. scanner.py:369-371 asks once per yielded file, so the gate is equality,
        # not a floor: fewer lookups means the window missed files, more means it asked twice.
        expected_lookups = self.db.stats()["files"]
        # The literal sits here so a fixture or rule change that emptied the index cannot turn
        # the equality above into a green comparison of len(seen) with zero.
        self.assertEqual(expected_lookups, 4, "the fixture no longer holds four discoverable files")

        # Before start(), so the window covers the whole run.
        self.db.get_scan_file_record = spy
        try:
            self.scanner.start(source_ids=[self.source["id"]], mode="incremental",
                               intensity="eco", workers=1)
            status = wait_scan(self.scanner)
        finally:
            self.db.get_scan_file_record = original

        self.assertEqual(len(seen), expected_lookups,
                         "the scan did not consult the index exactly once per discovered file")
        self.assertEqual(status["discovered"], expected_lookups,
                         "the run discovered a different number of files than the fixture holds")
        # Widening the window could have picked up a lookup made from the calling thread outside
        # a run, which would have no handle to reuse and would go red here. It stays green because
        # scanner.py:371 is the only caller in midivault/ and it always passes the handle opened at
        # scanner.py:339; a None now means the scan stopped reusing, which is what this test is for.
        self.assertNotIn(None, seen, "a lookup opened its own connection")
        self.assertTrue(all(handle is seen[0] for handle in seen),
                        "the run used more than one read handle")


if __name__ == "__main__":
    unittest.main()
