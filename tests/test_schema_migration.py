"""Schema 1 → schema 2: the fingerprint generation, and a real migration path.

These tests rewind an index that a *released* build would have written — the
current layout minus ``files.fingerprint_version``, version stamps at 1 and
fingerprints with no generation key — then open it with this build. Nothing
here can pass on the code that shipped, because that code had no column, no
backup, no comparison and no refusal.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

os.environ["SKEER_SCAN_EXECUTOR"] = "threads"

from midivault import db as db_module
from midivault.db import Database, SchemaError
from midivault.engine.versions import (
    FINGERPRINT_VERSION,
    LEGACY_FINGERPRINT_VERSION,
    SCHEMA_VERSION,
)
from midivault.pipeline import parse_and_classify_file
from midivault.scanner import ScanManager
from tests.test_scanner_db import bass_midi, wait_scan


@contextmanager
def opened(path: Path):
    """A real read handle that is closed.

    ``with sqlite3.connect(...)`` only wraps a transaction — it never closes,
    and on Windows an open handle makes the temp directory undeletable.
    """
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _file_rows(db: Database) -> list[dict]:
    with db.connection() as con:
        return [dict(row) for row in con.execute(
            "SELECT id,filename,favorite,user_notes,role,role_source,instrument,"
            "fingerprint_json,fingerprint_version,cache_blob FROM files ORDER BY id"
        ).fetchall()]


class SchemaMigrationTests(unittest.TestCase):
    """A v1 index must survive, advance, and stay restorable."""

    def setUp(self) -> None:
        # Windows can hold a just-written WAL file one beat too long; that must not read as a test failure.
        self.temp = tempfile.TemporaryDirectory(prefix="midivault-migrate-", ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.db_path = self.data / "midivault.sqlite3"
        self.library = self.root / "music"
        self.library.mkdir()
        for name, shift in (("First Bass.mid", 0), ("Second Bass.mid", 2), ("Third Bass.mid", 1)):
            (self.library / name).write_bytes(bass_midi(shift=shift))
        self.db = Database(self.db_path)
        self.source = self.db.add_source(str(self.library), "Fixture", optional=True, enabled=True)
        self.scanner = ScanManager(self.db, self.data)
        self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco", workers=1)
        wait_scan(self.scanner)

    def tearDown(self) -> None:
        self.temp.cleanup()

    # --------------------------------------------------------------- fixtures
    def _add_user_data(self) -> int:
        """Everything a person may have typed, which no migration may lose."""
        file_id = int(self.db.query_library(page_size=1)["items"][0]["id"])
        self.db.set_favorite(file_id, True)
        self.db.set_user_notes(file_id, "keep me through the upgrade")
        self.db.set_file_label(file_id, "role", "Arpeggio")
        self.db.add_tag(file_id, "upgrade-check")
        collection = self.db.create_collection("Upgrade picks")
        self.db.add_to_collection(int(collection["id"]), [file_id])
        return file_id

    def _downgrade_to_v1(self) -> None:
        """Rewrite this index as schema 1, byte-for-byte in shape."""
        with self.db.connection(write=True) as con:
            con.execute("DROP INDEX IF EXISTS idx_files_fingerprint_version")
            columns = {row["name"] for row in con.execute("PRAGMA table_info(files)").fetchall()}
            if "fingerprint_version" in columns:
                con.execute("ALTER TABLE files DROP COLUMN fingerprint_version")
            for row in con.execute(
                "SELECT id, fingerprint_json FROM files WHERE fingerprint_json IS NOT NULL"
            ).fetchall():
                payload = json.loads(row["fingerprint_json"])
                payload.pop("fv", None)
                con.execute(
                    "UPDATE files SET fingerprint_json=? WHERE id=?",
                    (json.dumps(payload, separators=(",", ":")), row["id"]),
                )
            con.execute(
                "UPDATE meta SET value='1' WHERE key='schema_version'"
            )
            con.execute("DELETE FROM meta WHERE key='last_migration'")
            con.execute("PRAGMA user_version=1")
        self.db = None

    def _v1_snapshot(self) -> tuple[int, dict[str, str], set[str], list[dict]]:
        """The exact index state a released build left behind."""
        with opened(self.db_path) as con:
            version = int(con.execute("PRAGMA user_version").fetchone()[0])
            meta = {row["key"]: row["value"] for row in con.execute("SELECT key, value FROM meta")}
            columns = {row["name"] for row in con.execute("PRAGMA table_info(files)")}
            rows = [dict(row) for row in con.execute(
                "SELECT id,filename,favorite,user_notes,role,role_source,instrument,fingerprint_json "
                "FROM files ORDER BY id"
            ).fetchall()]
        return version, meta, columns, rows

    # ----------------------------------------------------------------- tests
    def test_v1_index_advances_and_keeps_every_user_edit(self) -> None:
        file_id = self._add_user_data()
        self._downgrade_to_v1()
        before_version, before_meta, before_columns, before_rows = self._v1_snapshot()
        self.assertEqual(before_version, 1)
        self.assertNotIn("fingerprint_version", before_columns)
        self.assertTrue(all("fv" not in json.loads(row["fingerprint_json"]) for row in before_rows))

        migrated = Database(self.db_path)

        # The version moved, in both places that claim to know it.
        with opened(self.db_path) as con:
            self.assertEqual(int(con.execute("PRAGMA user_version").fetchone()[0]), SCHEMA_VERSION)
            stored = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
            self.assertEqual(stored, str(SCHEMA_VERSION))
        self.assertEqual(migrated.schema_version, SCHEMA_VERSION)
        self.assertEqual(migrated.last_migration["from"], 1)
        self.assertEqual(migrated.last_migration["to"], SCHEMA_VERSION)

        # The column exists, and every pre-existing fingerprint is legacy.
        with opened(self.db_path) as con:
            after_columns = {row["name"] for row in con.execute("PRAGMA table_info(files)")}
        self.assertIn("fingerprint_version", after_columns)
        rows = _file_rows(migrated)
        self.assertEqual(len(rows), len(before_rows))
        self.assertTrue(
            all(row["fingerprint_version"] == LEGACY_FINGERPRINT_VERSION for row in rows)
        )

        # Nothing a person entered was replaced by the upgrade.
        kept = next(row for row in rows if row["id"] == file_id)
        self.assertEqual(int(kept["favorite"]), 1)
        self.assertEqual(kept["user_notes"], "keep me through the upgrade")
        self.assertEqual(kept["role"], "Arpeggio")
        self.assertEqual(kept["role_source"], "user")
        self.assertIsNotNone(kept["cache_blob"])
        details = migrated.get_file_details(file_id)
        self.assertTrue(any(tag["name"] == "upgrade-check" for tag in details["tags"]))
        self.assertTrue(any(
            item["name"] == "Upgrade picks" and item["count"] == 1
            for item in migrated.list_collections()
        ))
        self.assertEqual(migrated.db_health()["integrity"], "ok")

    def test_migration_writes_a_restorable_backup_of_the_old_index(self) -> None:
        self._add_user_data()
        self._downgrade_to_v1()
        expected_notes = "keep me through the upgrade"
        Database(self.db_path)

        backups = sorted((self.data).glob("midivault-index-v1-before-migration-*.sqlite3"))
        self.assertEqual(len(backups), 1, "expected exactly one pre-migration backup")
        with opened(backups[0]) as con:
            self.assertEqual(int(con.execute("PRAGMA user_version").fetchone()[0]), 1)
            columns = {row["name"] for row in con.execute("PRAGMA table_info(files)").fetchall()}
            self.assertNotIn("fingerprint_version", columns, "the backup must be the old shape")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM files").fetchone()[0], 3)
            row = con.execute(
                "SELECT user_notes, favorite FROM files WHERE user_notes<>''"
            ).fetchone()
            self.assertEqual(row[0], expected_notes)
            self.assertEqual(int(row[1]), 1)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_reopening_a_current_index_does_not_back_up_again(self) -> None:
        self._downgrade_to_v1()
        Database(self.db_path)
        Database(self.db_path)
        first = sorted(self.data.glob("midivault-index-v1-before-migration-*.sqlite3"))
        self.assertEqual(len(first), 1)
        reopened = Database(self.db_path)
        self.assertIsNone(reopened.last_migration)
        self.assertEqual(
            len(sorted(self.data.glob("midivault-index-v1-before-migration-*.sqlite3"))), 1,
            "an index already at the current schema must not be copied again",
        )

    def test_a_fresh_index_is_not_migrated_and_needs_no_backup(self) -> None:
        with self.db.connection() as con:
            self.assertEqual(int(con.execute("PRAGMA user_version").fetchone()[0]), SCHEMA_VERSION)
            stored = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
            self.assertEqual(stored, str(SCHEMA_VERSION))
        self.assertEqual(list(self.data.glob("*before-migration*")), [])
        self.assertIsNone(self.db.last_migration)

    def test_a_newer_index_is_refused_without_being_touched(self) -> None:
        self._downgrade_to_v1()
        with opened(self.db_path) as con:
            con.execute("PRAGMA user_version=99")
            con.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
            con.commit()
        before = self.db_path.read_bytes()

        with self.assertRaises(SchemaError) as caught:
            Database(self.db_path)
        self.assertIn("newer", str(caught.exception))

        self.assertEqual(self.db_path.read_bytes(), before, "refusal must not write")
        self.assertEqual(list(self.data.glob("*before-migration*")), [])
        with opened(self.db_path) as con:
            self.assertEqual(int(con.execute("PRAGMA user_version").fetchone()[0]), 99)
            columns = {row["name"] for row in con.execute("PRAGMA table_info(files)").fetchall()}
            self.assertNotIn("fingerprint_version", columns)

    def test_an_unmapped_version_jump_is_refused(self) -> None:
        # A gap in MIGRATIONS must stop the app, not silently skip work.
        with mock.patch.object(db_module, "MIGRATIONS", {}):
            self._downgrade_to_v1()
            with self.assertRaises(SchemaError) as caught:
                Database(self.db_path)
        self.assertIn("migration", str(caught.exception))
        with opened(self.db_path) as con:
            self.assertEqual(int(con.execute("PRAGMA user_version").fetchone()[0]), 1)

    def test_legacy_fingerprints_are_skipped_until_reindexed(self) -> None:
        """The point of the whole step: a mixed index under-reports, never lies."""
        self._downgrade_to_v1()
        migrated = Database(self.db_path)

        # Right after the upgrade the three similar bass lines are invisible,
        # because their vectors carry no generation and cannot be compared.
        counts = migrated.finalise_duplicate_groups()
        self.assertEqual(counts["similar_groups"], 0)
        self.assertEqual(counts["stale_fingerprints"], 3)

        # One incremental scan is enough: the legacy stamp forces re-indexing
        # even though size and mtime never changed.
        scanner = ScanManager(migrated, self.data)
        scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        status = wait_scan(scanner)
        self.assertGreaterEqual(status["indexed"], 3)
        self.assertEqual(status["skipped"], 0)

        rows = _file_rows(migrated)
        self.assertTrue(all(row["fingerprint_version"] == FINGERPRINT_VERSION for row in rows))
        self.assertTrue(all(json.loads(row["fingerprint_json"])["fv"] == FINGERPRINT_VERSION
                            for row in rows))
        counts = migrated.finalise_duplicate_groups()
        self.assertEqual(counts["similar_groups"], 1)
        self.assertEqual(counts["stale_fingerprints"], 0)

        # A second scan must be a no-op: this is one pass, not permanent churn.
        scanner.start(source_ids=[self.source["id"]], mode="incremental", intensity="eco", workers=1)
        again = wait_scan(scanner)
        self.assertEqual(again["indexed"], 0)
        self.assertGreaterEqual(again["skipped"], 3)

    def test_pipeline_stamps_the_generation_it_writes(self) -> None:
        path = self.library / "First Bass.mid"
        result = parse_and_classify_file({"path": str(path)})
        self.assertTrue(result["ok"])
        self.assertEqual(result["fingerprint_version"], FINGERPRINT_VERSION)
        self.assertEqual(json.loads(result["fingerprint_json"])["fv"], FINGERPRINT_VERSION)


class FingerprintVersionTests(unittest.TestCase):
    """Engine-level refusal, independent of any database."""

    def _file(self, file_id: int, *, fv: int | None) -> dict:
        payload = {
            "pc": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.7, 0.0],
            "on": [0.25, 0, 0, 0, 0.25, 0, 0, 0, 0.25, 0, 0, 0, 0.25, 0, 0, 0],
            "pitch_mean": 40,
            "density": 1.8,
        }
        if fv is not None:
            payload["fv"] = fv
        return {
            "id": file_id,
            "instrument": "Bass",
            "role": "Bassline",
            "tempo_bpm": 108.0,
            "duration_seconds": 18.0,
            "note_count": 32,
            "scan_state": "indexed",
            "content_hash": f"hash-{file_id}",
            "fingerprint_json": json.dumps(payload),
        }

    def test_only_the_current_generation_is_compared(self) -> None:
        from midivault.engine.duplicates import fingerprint_generation, similar_groups

        current = [self._file(1, fv=FINGERPRINT_VERSION), self._file(2, fv=FINGERPRINT_VERSION)]
        self.assertEqual(len(similar_groups(current)), 1)
        self.assertEqual(fingerprint_generation(current[0]), FINGERPRINT_VERSION)

        # An unversioned fingerprint is legacy, not "version 1 by implication".
        legacy = [self._file(1, fv=None), self._file(2, fv=FINGERPRINT_VERSION)]
        self.assertEqual(fingerprint_generation(legacy[0]), LEGACY_FINGERPRINT_VERSION)
        self.assertEqual(similar_groups(legacy), [])

        # Neither is a future generation silently trusted by an older build.
        future = [self._file(1, fv=FINGERPRINT_VERSION + 1), self._file(2, fv=FINGERPRINT_VERSION)]
        self.assertEqual(similar_groups(future), [])

        # Two files of the same *unknown-old* generation still say nothing.
        both_legacy = [self._file(1, fv=None), self._file(2, fv=None)]
        self.assertEqual(similar_groups(both_legacy), [])


if __name__ == "__main__":
    unittest.main()
