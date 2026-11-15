"""SQLite persistence for SKEER MIDI VAULT.

The engine writes only JSON-friendly payloads here. User data (favorites,
collections, tags, notes, manual labels) lives in separate tables and is never
replaced by a parser/classifier cache update.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .engine.duplicates import exact_groups, similar_groups
from .engine.versions import (
    CLASSIFIER_METHOD,
    FINGERPRINT_VERSION,
    LEGACY_FINGERPRINT_VERSION,
    SCHEMA_VERSION,
)

JSON_FIELDS = {
    "style_tags", "embedded_text_json", "conflicts_json", "uncertainty_json",
    "warnings_json", "controller_json", "programs_json",
    "auto_instrument_evidence_json", "auto_instrument_alternatives_json",
    "auto_role_evidence_json", "auto_role_alternatives_json",
    "fingerprint_json", "evidence_json", "alternatives_json", "issues_json",
    "sources_json", "options_json",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class SchemaError(RuntimeError):
    """The index on disk cannot be opened by this build without risking data."""


class Database:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(self.path)
        self.fts_enabled = False
        self.schema_version = SCHEMA_VERSION
        self.last_migration: dict[str, Any] | None = None
        self._prepare_schema()
        self._initialise()

    # ------------------------------------------------------------------ core
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def connection(self, write: bool = False):
        connection = self._connect()
        try:
            yield connection
            if write:
                connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def reader(self):
        """One long-lived read handle for a per-item query loop.

        ``connection()`` opens and closes a handle on every call, which cost a
        scan about 1.3 ms for each file it had merely discovered.
        """
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _stored_schema_version(self) -> int | None:
        """Schema version stamped on an existing index, or None when empty.

        Read-only on purpose: it runs before anything is written, so an index
        this build does not understand is refused without being touched.
        ``meta.schema_version`` wins over ``PRAGMA user_version``; an index from
        before either was maintained is schema 1, the only layout that existed.
        """
        if not self.path.exists():
            return None
        connection = self._connect()
        try:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                row["name"]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "files" not in tables:
                return None
            stored = 0
            if "meta" in tables:
                row = connection.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()
                if row is not None:
                    try:
                        stored = int(str(row["value"]).strip())
                    except (TypeError, ValueError):
                        stored = 0
            pragma = connection.execute("PRAGMA user_version").fetchone()[0]
            try:
                pragma = int(pragma or 0)
            except (TypeError, ValueError):
                pragma = 0
            return stored or pragma or 1
        finally:
            connection.close()

    def _prepare_schema(self) -> None:
        """Compare the index against this build, back up, then allow migration.

        Newer-than-this is fatal and fail-closed: silently downgrading an index
        loses columns, and a half-read index is worse than a refused start.
        """
        stored = self._stored_schema_version()
        if stored is None or stored == SCHEMA_VERSION:
            return
        if stored > SCHEMA_VERSION:
            raise SchemaError(
                f"This index was written by a newer version of MIDI Vault (schema {stored}). "
                f"This build understands schema {SCHEMA_VERSION} and will not open it, because "
                "opening a newer index can drop data on the way out. Update MIDI Vault — "
                "nothing in the index has been changed."
            )
        missing = [version for version in range(stored, SCHEMA_VERSION) if version not in MIGRATIONS]
        if missing:
            raise SchemaError(
                f"There is no tested migration from schema {stored} to "
                f"{SCHEMA_VERSION} (missing {', '.join(str(v) for v in missing)}). "
                "The index has been left untouched."
            )
        self.last_migration = {
            "from": stored,
            "to": SCHEMA_VERSION,
            "backup": self._backup_before_migration(stored),
            "at": utcnow(),
        }

    def _backup_before_migration(self, stored: int) -> str:
        """Keep a restorable copy of the index exactly as it was found."""
        base = f"midivault-index-v{stored}-before-migration"
        destination = self.path.parent / f"{base}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.sqlite3"
        suffix = 1
        while destination.exists():
            destination = destination.with_name(f"{destination.stem}-{suffix}.sqlite3")
            suffix += 1
        return self.backup_to(destination)

    def _initialise(self) -> None:
        with self.connection(write=True) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA temp_store=MEMORY")
            con.executescript(SCHEMA_SQL)
            try:
                con.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5("
                    "filename, path, track_names, tags, notes, embedded_text, auto_labels, "
                    "tokenize='unicode61 remove_diacritics 2')"
                )
                self.fts_enabled = True
            except sqlite3.OperationalError:
                self.fts_enabled = False
            if self.last_migration:
                for version in range(self.last_migration["from"], self.last_migration["to"]):
                    MIGRATIONS[version](con)
                con.execute(
                    "INSERT INTO meta(key, value) VALUES('last_migration', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (_json(self.last_migration),),
                )
            # Runs after the migrations: an index on a column a migration adds
            # cannot be created before the migration has added it.
            con.executescript(POST_SCHEMA_SQL)
            # Both stamps always follow the code, never only a fresh database:
            # an index that was written back as-is still records that it has
            # been checked by this build.
            con.execute(f"PRAGMA user_version={int(SCHEMA_VERSION)}")
            con.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            defaults = {
                "scan_intensity": "balanced",
                "scan_mode": "incremental",
                "include_optional_sources": "0",
                "parse_workers": "2",
                "theme": "clean",
                "preview_autoplay": "0",
                # An incremental scan that only trusts size + mtime will keep a
                # stale analysis after an in-place edit that preserved both.
                # Re-hashing the skipped files is the default; the toggle exists
                # for crates too large to re-read on every pass.
                "verify_unchanged": "1",
            }
            for key, value in defaults.items():
                con.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO NOTHING",
                    (key, value),
                )
            con.execute(
                "UPDATE scan_runs SET state='interrupted', ended_at=COALESCE(ended_at, ?), "
                "message=COALESCE(message, 'Application closed during scan') "
                "WHERE state IN ('running','paused')",
                (utcnow(),),
            )

    def metadata(self) -> dict[str, Any]:
        with self.connection() as con:
            rows = con.execute("SELECT key, value FROM meta").fetchall()
            settings = con.execute("SELECT key, value FROM settings").fetchall()
        return {
            "meta": {row["key"]: row["value"] for row in rows},
            "settings": {row["key"]: row["value"] for row in settings},
            "fts_enabled": self.fts_enabled,
            "db_path": self.db_path,
            "db_size_bytes": self.path.stat().st_size if self.path.exists() else 0,
        }

    # --------------------------------------------------------------- settings
    def get_settings(self) -> dict[str, str]:
        with self.connection() as con:
            rows = con.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def update_settings(self, values: dict[str, Any]) -> dict[str, str]:
        allowed = {
            "scan_intensity", "scan_mode", "include_optional_sources",
            "parse_workers", "theme", "preview_autoplay", "verify_unchanged",
        }
        with self.connection(write=True) as con:
            for key, value in values.items():
                if key not in allowed:
                    continue
                con.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)),
                )
        return self.get_settings()

    # ---------------------------------------------------------------- sources
    def sync_drives(self, drives: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = utcnow()
        seen_paths = {drive["path"] for drive in drives}
        with self.connection(write=True) as con:
            existing = {
                row["path"]: row for row in con.execute("SELECT * FROM sources").fetchall()
            }
            for drive in drives:
                path = drive["path"]
                row = existing.get(path)
                if row:
                    became_optional = bool(drive.get("optional")) and not bool(row["optional"])
                    con.execute(
                        "UPDATE sources SET label=?, kind=?, optional=?, available=?, "
                        "enabled=CASE WHEN ? THEN 0 ELSE enabled END, last_seen_at=? WHERE id=?",
                        (drive.get("label") or path, drive.get("kind", "unknown"),
                         1 if drive.get("optional") else 0,
                         1 if drive.get("available", True) else 0,
                         1 if became_optional else 0,
                         now, row["id"]),
                    )
                else:
                    con.execute(
                        "INSERT INTO sources(path, label, kind, optional, enabled, available, "
                        "last_seen_at, created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (path, drive.get("label") or path, drive.get("kind", "unknown"),
                         1 if drive.get("optional") else 0,
                         0 if drive.get("optional") else 1,
                         1 if drive.get("available", True) else 0,
                         now, now),
                    )
            # Remember unavailable drive sources rather than deleting them.
            for path, row in existing.items():
                if row["kind"] in ("fixed", "removable", "network", "optical", "unknown") \
                        and re.match(r"^[A-Za-z]:\\?$", path) and path not in seen_paths:
                    con.execute(
                        "UPDATE sources SET available=0 WHERE id=?", (row["id"],)
                    )
        return self.list_sources()

    def list_sources(self, with_counts: bool = True) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute("SELECT * FROM sources ORDER BY path COLLATE NOCASE").fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["enabled"] = bool(row["enabled"])
                item["optional"] = bool(row["optional"])
                item["available"] = bool(row["available"])
                if with_counts:
                    counts = con.execute(
                        "SELECT COUNT(*) AS total, "
                        "SUM(CASE WHEN scan_state='indexed' THEN 1 ELSE 0 END) AS indexed, "
                        "SUM(CASE WHEN scan_state='failed' THEN 1 ELSE 0 END) AS failed "
                        "FROM files WHERE source_id=?", (row["id"],)
                    ).fetchone()
                    item["counts"] = {
                        "files": counts["total"] or 0,
                        "indexed": counts["indexed"] or 0,
                        "failed": counts["failed"] or 0,
                    }
                result.append(item)
        return result

    def get_source(self, source_id: int) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def add_source(self, path: str, label: str | None = None, optional: bool = True,
                   enabled: bool = True) -> dict[str, Any]:
        normalised = os.path.abspath(os.path.expanduser(path))
        now = utcnow()
        with self.connection(write=True) as con:
            con.execute(
                "INSERT INTO sources(path,label,kind,optional,enabled,available,last_seen_at,created_at) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET label=excluded.label, enabled=excluded.enabled",
                (normalised, label or Path(normalised).name or normalised, "folder",
                 1 if optional else 0, 1 if enabled else 0,
                 1 if os.path.isdir(normalised) else 0, now, now),
            )
            row = con.execute("SELECT * FROM sources WHERE path=?", (normalised,)).fetchone()
        return dict(row) if row else {}

    def update_source(self, source_id: int, **fields: Any) -> dict[str, Any] | None:
        allowed = {"enabled", "optional", "label"}
        with self.connection(write=True) as con:
            for key, value in fields.items():
                if key not in allowed:
                    continue
                con.execute(f"UPDATE sources SET {key}=? WHERE id=?", (value, source_id))
        return self.get_source(source_id)

    def delete_source(self, source_id: int) -> None:
        with self.connection(write=True) as con:
            # ``files.source_id`` is ON DELETE SET NULL, and mark_missing_not_seen
            # matches on source_id, so without this the rows would stay 'indexed'
            # against paths no future scan can reach. The rows and their user
            # data are kept; only the index state is corrected.
            con.execute(
                "UPDATE files SET scan_state='missing', is_missing=1, updated_at=? "
                "WHERE source_id=? AND scan_state='indexed'",
                (utcnow(), source_id),
            )
            con.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def orphan_indexed_rows(self) -> list[tuple[int, str]]:
        """Rows still called indexed whose source row is gone.

        Only reachable in an index written before ``delete_source`` started
        marking its files, which is why the scan has to check the paths itself.
        """
        with self.connection() as con:
            return [(row["id"], row["path"]) for row in con.execute(
                "SELECT id,path FROM files WHERE source_id IS NULL AND scan_state='indexed'"
            ).fetchall()]

    def mark_rows_missing(self, file_ids: Iterable[int]) -> int:
        ids = [int(file_id) for file_id in file_ids]
        if not ids:
            return 0
        now = utcnow()
        with self.connection(write=True) as con:
            con.executemany(
                "UPDATE files SET scan_state='missing', is_missing=1, updated_at=? WHERE id=?",
                [(now, file_id) for file_id in ids],
            )
        return len(ids)

    def set_source_available(self, source_id: int, available: bool) -> None:
        with self.connection(write=True) as con:
            con.execute("UPDATE sources SET available=? WHERE id=?", (1 if available else 0, source_id))

    def enabled_sources(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute("SELECT * FROM sources WHERE enabled=1 ORDER BY path").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["optional"] = bool(row["optional"])
            item["available"] = bool(row["available"])
            item["enabled"] = bool(row["enabled"])
            result.append(item)
        return result

    # --------------------------------------------------------------- excludes
    def list_excludes(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute("SELECT * FROM excludes ORDER BY path").fetchall()
        return [dict(row) for row in rows]

    def add_exclude(self, path: str, note: str | None = None) -> dict[str, Any]:
        normalised = os.path.abspath(os.path.expanduser(path))
        now = utcnow()
        with self.connection(write=True) as con:
            con.execute(
                "INSERT INTO excludes(path,note,created_at) VALUES(?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET note=COALESCE(excluded.note, excludes.note)",
                (normalised, note, now),
            )
            row = con.execute("SELECT * FROM excludes WHERE path=?", (normalised,)).fetchone()
        return dict(row) if row else {}

    def delete_exclude(self, exclude_id: int) -> None:
        with self.connection(write=True) as con:
            con.execute("DELETE FROM excludes WHERE id=?", (exclude_id,))

    def excluded_paths(self) -> list[str]:
        return [item["path"] for item in self.list_excludes()]

    # -------------------------------------------------------------- scan runs
    def create_scan_run(self, mode: str, source_ids: Sequence[int],
                        options: dict[str, Any] | None = None) -> int:
        with self.connection(write=True) as con:
            cursor = con.execute(
                "INSERT INTO scan_runs(started_at,state,mode,sources_json,total_sources,"
                "discovered,indexed,skipped,failed,completion,current_path,message,options_json) "
                "VALUES(?,?,?,?,?,0,0,0,0,0,'','',?)",
                (utcnow(), "running", mode, _json(list(source_ids)), len(source_ids),
                 _json(options or {})),
            )
            return int(cursor.lastrowid)

    def update_scan_run(self, scan_id: int, **fields: Any) -> None:
        allowed = {
            "state", "completion", "current_path", "message", "discovered",
            "indexed", "skipped", "failed", "total_sources", "ended_at",
            "sources_json", "options_json",
        }
        values = []
        clauses = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            clauses.append(f"{key}=?")
            values.append(_json(value) if key in ("sources_json", "options_json") else value)
        if not clauses:
            return
        values.append(scan_id)
        with self.connection(write=True) as con:
            con.execute(f"UPDATE scan_runs SET {', '.join(clauses)} WHERE id=?", values)

    def get_scan_run(self, scan_id: int) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM scan_runs WHERE id=?", (scan_id,)).fetchone()
        return self._scan_row(row) if row else None

    def latest_scan_run(self) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
        return self._scan_row(row) if row else None

    def _scan_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["sources_json"] = _decode_json(item.get("sources_json"), [])
        item["options_json"] = _decode_json(item.get("options_json"), {})
        return item

    def add_scan_issue(self, scan_id: int | None, kind: str, path: str,
                       message: str) -> None:
        with self.connection(write=True) as con:
            con.execute(
                "INSERT INTO scan_issues(scan_run_id,kind,path,message,created_at) "
                "VALUES(?,?,?,?,?)",
                (scan_id, kind, path, message[:1000], utcnow()),
            )

    def list_scan_issues(self, scan_id: int | None = None,
                         limit: int = 200) -> list[dict[str, Any]]:
        with self.connection() as con:
            if scan_id is None:
                rows = con.execute(
                    "SELECT * FROM scan_issues ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM scan_issues WHERE scan_run_id=? ORDER BY id DESC LIMIT ?",
                    (scan_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------- scan files
    def get_scan_file_record(self, path: str, *, con: sqlite3.Connection | None = None) -> dict[str, Any] | None:
        """The fields an incremental scan needs to decide whether to skip a file.

        Pass ``con`` to reuse a read handle; the scan asks for every discovered
        file and opening one per call was measurable cost.
        """
        query = (
            "SELECT id,size,mtime_ns,parser_version,classifier_version,"
            "fingerprint_version,scan_state,"
            "content_hash,is_missing FROM files WHERE path=?"
        )
        if con is not None:
            row = con.execute(query, (path,)).fetchone()
            return dict(row) if row else None
        with self.connection() as local:
            row = local.execute(query, (path,)).fetchone()
        return dict(row) if row else None

    def touch_last_seen(self, paths: Iterable[str], scan_id: int) -> None:
        with self.connection(write=True) as con:
            self._touch_last_seen_conn(con, paths, scan_id)

    @staticmethod
    def _touch_last_seen_conn(con: sqlite3.Connection, paths: Iterable[str],
                              scan_id: int) -> int:
        now = utcnow()
        count = 0
        for path in paths:
            cursor = con.execute(
                "UPDATE files SET last_seen_at=?, last_seen_scan_id=?, is_missing=0, "
                "scan_state=CASE WHEN scan_state='missing' THEN 'indexed' ELSE scan_state END "
                "WHERE path=?",
                (now, scan_id, path),
            )
            count += cursor.rowcount
        return count

    def apply_index_result(self, payload: dict[str, Any], source_id: int | None,
                           scan_id: int | None = None) -> int:
        with self.connection(write=True) as con:
            return self._apply_index_result_conn(
                con, payload, source_id, scan_id, utcnow()
            )

    def _apply_index_result_conn(self, con: sqlite3.Connection, payload: dict[str, Any],
                                 source_id: int | None, scan_id: int | None,
                                 now: str) -> int:
        path = payload["path"]
        dirname = os.path.dirname(path)
        filename = payload.get("filename") or os.path.basename(path)
        extension = os.path.splitext(filename)[1].lower()
        file_columns = {
            "path": path,
            "source_id": source_id,
            "dirname": dirname,
            "filename": filename,
            "extension": extension,
            "size": payload.get("size"),
            "mtime_ns": payload.get("mtime_ns"),
            "content_hash": payload.get("content_hash"),
            "parser_version": payload.get("parser_version"),
            "classifier_version": payload.get("classifier_version"),
            "scan_state": "indexed",
            "error": None,
            "is_missing": 0,
            "format": payload.get("format"),
            "declared_tracks": payload.get("declared_tracks"),
            "actual_tracks": payload.get("actual_tracks"),
            "sequence_count": payload.get("sequence_count"),
            "division": payload.get("division"),
            "timing_type": payload.get("timing_type"),
            "duration_seconds": payload.get("duration_seconds"),
            "duration_beats": payload.get("duration_beats"),
            "bars": payload.get("bars"),
            "ticks_per_quarter": payload.get("ticks_per_quarter"),
            "tempo_bpm": payload.get("tempo_bpm"),
            "tempo_source": payload.get("tempo_source"),
            "tempo_min_bpm": payload.get("tempo_min_bpm"),
            "tempo_max_bpm": payload.get("tempo_max_bpm"),
            "tempo_change_count": payload.get("tempo_change_count"),
            "time_sig": payload.get("time_sig"),
            "time_sig_source": payload.get("time_sig_source"),
            "time_sig_change_count": payload.get("time_sig_change_count"),
            "key_name": payload.get("key_name"),
            "key_source": payload.get("key_source"),
            "key_confidence": payload.get("key_confidence"),
            "key_embedded": payload.get("key_embedded"),
            "key_mode": payload.get("key_mode"),
            "note_count": payload.get("note_count"),
            "track_count": payload.get("track_count"),
            "channel_count": payload.get("channel_count"),
            "program_count": payload.get("program_count"),
            "pitch_min": payload.get("pitch_min"),
            "pitch_max": payload.get("pitch_max"),
            "velocity_min": payload.get("velocity_min"),
            "velocity_max": payload.get("velocity_max"),
            "velocity_mean": payload.get("velocity_mean"),
            "note_density": payload.get("note_density"),
            "polyphony_max": payload.get("polyphony_max"),
            "polyphony_mean": payload.get("polyphony_mean"),
            "auto_instrument": payload.get("auto_instrument"),
            "auto_instrument_confidence": payload.get("auto_instrument_confidence"),
            "auto_role": payload.get("auto_role"),
            "auto_role_confidence": payload.get("auto_role_confidence"),
            "style_tags": _json(payload.get("style_tags") or []),
            "genre_hint": payload.get("genre_hint"),
            "genre_confidence": payload.get("genre_confidence"),
            "classifier_method": payload.get("classifier_method") or CLASSIFIER_METHOD,
            "uncertain": 1 if payload.get("uncertain") else 0,
            "confidence": payload.get("confidence"),
            "conflicts_json": _json(payload.get("conflicts") or []),
            "uncertainty_json": _json(payload.get("uncertainty_notes") or []),
            "warnings_json": _json(payload.get("warnings") or []),
            "embedded_text_json": _json(payload.get("embedded_text") or []),
            "fingerprint_version": int(payload.get("fingerprint_version") or LEGACY_FINGERPRINT_VERSION),
            "fingerprint_json": payload.get("fingerprint_json"),
            "cache_blob": payload.get("cache_blob"),
            "indexed_at": now,
            "updated_at": now,
            "last_seen_at": now,
            "last_seen_scan_id": scan_id,
        }
        columns = list(file_columns)
        placeholders = ", ".join("?" for _ in columns)
        update_columns = [column for column in columns if column not in ("path", "favorite", "user_notes")]
        update_sql = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        sql = (
            f"INSERT INTO files({', '.join(columns)}) VALUES({placeholders}) "
            f"ON CONFLICT(path) DO UPDATE SET {update_sql}"
        )
        con.execute(sql, [file_columns[column] for column in columns])
        file_row = con.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        file_id = int(file_row["id"])
        self._apply_file_effective_label(con, file_id)
        self._replace_tracks(con, file_id, payload.get("tracks") or [])
        self._write_predictions(con, file_id, payload)
        self._refresh_fts(con, file_id)
        return file_id

    def _apply_file_effective_label(self, con: sqlite3.Connection, file_id: int) -> None:
        row = con.execute(
            "SELECT auto_instrument, auto_role, auto_instrument_confidence, "
            "auto_role_confidence FROM files WHERE id=?", (file_id,)
        ).fetchone()
        if not row:
            return
        corrections = {
            item["dimension"]: item["value"]
            for item in con.execute(
                "SELECT dimension, value FROM file_corrections WHERE file_id=?", (file_id,)
            ).fetchall()
        }
        instrument = corrections.get("instrument", row["auto_instrument"])
        role = corrections.get("role", row["auto_role"])
        instrument_source = "user" if "instrument" in corrections else "auto"
        role_source = "user" if "role" in corrections else "auto"
        label_source = "user" if corrections else "auto"
        con.execute(
            "UPDATE files SET instrument=?, instrument_confidence=?, instrument_source=?, "
            "role=?, role_confidence=?, role_source=?, label_source=? WHERE id=?",
            (instrument, row["auto_instrument_confidence"], instrument_source,
             role, row["auto_role_confidence"], role_source, label_source, file_id),
        )

    def _replace_tracks(self, con: sqlite3.Connection, file_id: int,
                        tracks: list[dict[str, Any]]) -> None:
        corrections_rows = con.execute(
            "SELECT sequence_index, track_index, dimension, value FROM track_corrections "
            "WHERE file_id=?", (file_id,)
        ).fetchall()
        corrections = {
            (row["sequence_index"], row["track_index"], row["dimension"]): row["value"]
            for row in corrections_rows
        }
        con.execute("DELETE FROM tracks WHERE file_id=?", (file_id,))
        now = utcnow()
        for track in tracks:
            sequence_index = int(track.get("sequence_index", 0))
            track_index = int(track.get("track_index", 0))
            auto_instrument = track.get("auto_instrument", "Unknown")
            auto_role = track.get("auto_role", "Unknown")
            instrument = corrections.get((sequence_index, track_index, "instrument"), auto_instrument)
            role = corrections.get((sequence_index, track_index, "role"), auto_role)
            instrument_source = "user" if (sequence_index, track_index, "instrument") in corrections else "auto"
            role_source = "user" if (sequence_index, track_index, "role") in corrections else "auto"
            con.execute(
                "INSERT INTO tracks("
                "file_id,sequence_index,track_index,chunk_index,channel,name,program,programs_json,"
                "bank_msb,bank_lsb,note_count,pitch_min,pitch_max,sustained_notes,assumed_durations,"
                "controller_json,auto_instrument,auto_instrument_confidence,"
                "auto_instrument_evidence_json,auto_instrument_alternatives_json,"
                "auto_role,auto_role_confidence,auto_role_evidence_json,auto_role_alternatives_json,"
                "instrument,instrument_confidence,instrument_source,role,role_confidence,role_source,"
                "label_source,style_tags,uncertain,conflicts_json,source_text,analysis_json,updated_at"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    file_id, sequence_index, track_index, track.get("chunk_index"),
                    track.get("channel"), track.get("name"), track.get("program"),
                    _json(track.get("programs") or []), track.get("bank_msb"),
                    track.get("bank_lsb"), track.get("note_count"), track.get("pitch_min"),
                    track.get("pitch_max"), track.get("sustained_notes"),
                    track.get("assumed_durations"), _json(track.get("controller_counts") or {}),
                    auto_instrument, track.get("auto_instrument_confidence", 0.0),
                    _json(track.get("auto_instrument_evidence") or []),
                    _json(track.get("auto_instrument_alternatives") or []),
                    auto_role, track.get("auto_role_confidence", 0.0),
                    _json(track.get("auto_role_evidence") or []),
                    _json(track.get("auto_role_alternatives") or []),
                    instrument, track.get("auto_instrument_confidence", 0.0), instrument_source,
                    role, track.get("auto_role_confidence", 0.0), role_source,
                    "user" if instrument_source == "user" or role_source == "user" else "auto",
                    _json(track.get("style_tags") or []),
                    1 if track.get("uncertain") else 0,
                    _json(track.get("conflicts") or []),
                    track.get("source_text") or "",
                    _json(track.get("analysis") or {}),
                    now,
                ),
            )
        # Remove stale corrections whose track no longer exists? Keep them keyed
        # by a stable file/sequence/track/channel identity so they survive reparse.

    def _write_predictions(self, con: sqlite3.Connection, file_id: int,
                           payload: dict[str, Any]) -> None:
        con.execute("DELETE FROM predictions WHERE file_id=?", (file_id,))
        now = utcnow()
        file_corrections = {
            row["dimension"]: row for row in con.execute(
                "SELECT dimension, action FROM file_corrections WHERE file_id=?", (file_id,)
            ).fetchall()
        }
        for dimension, category, confidence, evidence, alternatives in (
            ("instrument", payload.get("auto_instrument"), payload.get("auto_instrument_confidence"),
             payload.get("auto_instrument_evidence"), payload.get("auto_instrument_alternatives")),
            ("role", payload.get("auto_role"), payload.get("auto_role_confidence"),
             payload.get("auto_role_evidence"), payload.get("auto_role_alternatives")),
        ):
            correction = file_corrections.get(dimension)
            con.execute(
                "INSERT INTO predictions(file_id,sequence_index,track_index,dimension,predicted,"
                "confidence,evidence_json,alternatives_json,method,version,user_action,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (file_id, -1, -1, dimension, category, confidence,
                 _json(evidence or []), _json(alternatives or []),
                 payload.get("classifier_method"), str(payload.get("classifier_version")),
                 correction["action"] if correction else None, now),
            )
        track_corrections = {
            (row["sequence_index"], row["track_index"], row["dimension"]): row["action"]
            for row in con.execute(
                "SELECT sequence_index, track_index, dimension, action FROM track_corrections "
                "WHERE file_id=?", (file_id,)
            ).fetchall()
        }
        for track in payload.get("tracks") or []:
            sequence_index = int(track.get("sequence_index", 0))
            track_index = int(track.get("track_index", 0))
            for dimension, category, confidence, evidence, alternatives in (
                ("instrument", track.get("auto_instrument"),
                 track.get("auto_instrument_confidence"),
                 track.get("auto_instrument_evidence"),
                 track.get("auto_instrument_alternatives")),
                ("role", track.get("auto_role"), track.get("auto_role_confidence"),
                 track.get("auto_role_evidence"), track.get("auto_role_alternatives")),
            ):
                action = track_corrections.get((sequence_index, track_index, dimension))
                con.execute(
                    "INSERT INTO predictions(file_id,sequence_index,track_index,dimension,predicted,"
                    "confidence,evidence_json,alternatives_json,method,version,user_action,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (file_id, sequence_index, track_index, dimension, category, confidence,
                     _json(evidence or []), _json(alternatives or []),
                     payload.get("classifier_method"), str(payload.get("classifier_version")),
                     action, now),
                )

    def _refresh_fts(self, con: sqlite3.Connection, file_id: int) -> None:
        row = con.execute(
            "SELECT filename,path,user_notes,style_tags,embedded_text_json,instrument,role,"
            "auto_instrument,auto_role FROM files WHERE id=?", (file_id,)
        ).fetchone()
        if not row:
            return
        track_names = con.execute(
            "SELECT GROUP_CONCAT(COALESCE(name,''), ' ') AS names FROM tracks WHERE file_id=?",
            (file_id,),
        ).fetchone()["names"] or ""
        tags = con.execute(
            "SELECT GROUP_CONCAT(t.name, ' ') AS tags FROM tags t "
            "JOIN file_tags ft ON ft.tag_id=t.id WHERE ft.file_id=?", (file_id,)
        ).fetchone()["tags"] or ""
        track_labels = con.execute(
            "SELECT GROUP_CONCAT(COALESCE(instrument,'') || ' ' || COALESCE(role,''), ' ') "
            "AS labels FROM tracks WHERE file_id=?", (file_id,)
        ).fetchone()["labels"] or ""
        embedded = " ".join(_decode_json(row["embedded_text_json"], []))
        style = " ".join(_decode_json(row["style_tags"], []))
        labels = " ".join(filter(None, [
            row["instrument"], row["role"], row["auto_instrument"], row["auto_role"],
            track_labels,
        ]))
        search_blob = " ".join(filter(None, [
            row["filename"], row["path"], track_names, tags, row["user_notes"] or "",
            embedded, style, labels,
        ])).casefold()
        con.execute("UPDATE files SET search_blob=? WHERE id=?", (search_blob, file_id))
        if not self.fts_enabled:
            return
        con.execute("DELETE FROM files_fts WHERE rowid=?", (file_id,))
        con.execute(
            "INSERT INTO files_fts(rowid,filename,path,track_names,tags,notes,embedded_text,auto_labels) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (file_id, row["filename"], row["path"], track_names, tags,
             row["user_notes"] or "", embedded, labels),
        )

    def record_file_failure(self, path: str, source_id: int | None, error: str,
                            *,
                            size: int | None = None, mtime_ns: int | None = None,
                            content_hash: str | None = None,
                            scan_id: int | None = None) -> None:
        with self.connection(write=True) as con:
            self._record_file_failure_conn(
                con, path, source_id, error, size=size, mtime_ns=mtime_ns,
                content_hash=content_hash, scan_id=scan_id, now=utcnow(),
            )

    def _record_file_failure_conn(self, con: sqlite3.Connection, path: str,
                                  source_id: int | None, error: str, *,
                                  size: int | None = None,
                                  mtime_ns: int | None = None,
                                  content_hash: str | None = None,
                                  scan_id: int | None = None,
                                  now: str | None = None) -> None:
        now = now or utcnow()
        dirname = os.path.dirname(path)
        filename = os.path.basename(path)
        existing = con.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        if existing:
            con.execute(
                "UPDATE files SET scan_state='failed', error=?, updated_at=?, "
                "last_seen_at=?, last_seen_scan_id=?, is_missing=0"
                + (", size=?, mtime_ns=?, content_hash=?" if size is not None else "")
                + " WHERE id=?",
                (error[:1000], now, now, scan_id, size, mtime_ns, content_hash, existing["id"])
                if size is not None else
                (error[:1000], now, now, scan_id, existing["id"]),
            )
            self._refresh_fts(con, int(existing["id"]))
        else:
            con.execute(
                "INSERT INTO files(path,source_id,dirname,filename,extension,size,mtime_ns,"
                "content_hash,scan_state,error,is_missing,updated_at,last_seen_at,last_seen_scan_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
                (path, source_id, dirname, filename,
                 os.path.splitext(filename)[1].lower(), size, mtime_ns, content_hash,
                 "failed", error[:1000], now, now, scan_id),
            )
            file_id = int(con.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()["id"])
            self._refresh_fts(con, file_id)

    def apply_scan_batch(self, successes: list[tuple[dict[str, Any], int | None]],
                         failures: list[dict[str, Any]],
                         skipped_paths: Iterable[str], scan_id: int) -> dict[str, Any]:
        """Commit a batch of scan results in one short SQLite transaction.

        On a slow drive, committing once per MIDI file dominates scan time. This
        method preserves per-item failure isolation with savepoints while sharing
        one WAL commit across the batch.
        """
        now = utcnow()
        skipped_list = list(skipped_paths)
        indexed = 0
        failed = 0
        errors: list[dict[str, str]] = []
        with self.connection(write=True) as con:
            for path in skipped_list:
                con.execute(
                    "UPDATE files SET last_seen_at=?, last_seen_scan_id=?, is_missing=0, "
                    "scan_state=CASE WHEN scan_state='missing' THEN 'indexed' ELSE scan_state END "
                    "WHERE path=?",
                    (now, scan_id, path),
                )
            for payload, source_id in successes:
                con.execute("SAVEPOINT scan_item")
                try:
                    self._apply_index_result_conn(con, payload, source_id, scan_id, now)
                    con.execute("RELEASE scan_item")
                    indexed += 1
                except Exception as exc:  # one hostile item must not lose the batch
                    con.execute("ROLLBACK TO scan_item")
                    con.execute("RELEASE scan_item")
                    message = f"Database write failed: {type(exc).__name__}: {exc}"
                    self._record_file_failure_conn(
                        con, payload.get("path", "?"), source_id, message,
                        size=payload.get("size"), mtime_ns=payload.get("mtime_ns"),
                        content_hash=payload.get("content_hash"), scan_id=scan_id, now=now,
                    )
                    con.execute(
                        "INSERT INTO scan_issues(scan_run_id,kind,path,message,created_at) "
                        "VALUES(?,?,?,?,?)",
                        (scan_id, "database", payload.get("path", "?"), message[:1000], now),
                    )
                    failed += 1
                    errors.append({"path": payload.get("path", "?"), "error": message})
            for failure in failures:
                self._record_file_failure_conn(
                    con, failure["path"], failure.get("source_id"), failure["error"],
                    size=failure.get("size"), mtime_ns=failure.get("mtime_ns"),
                    content_hash=failure.get("content_hash"), scan_id=scan_id, now=now,
                )
                con.execute(
                    "INSERT INTO scan_issues(scan_run_id,kind,path,message,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (scan_id, "file", failure["path"], failure["error"][:1000], now),
                )
                failed += 1
        return {
            "indexed": indexed,
            "failed": failed,
            "skipped": len(skipped_list),
            "errors": errors,
        }

    def mark_missing_not_seen(self, scan_id: int, source_id: int,
                              skip_prefixes: list[str] | None = None) -> int:
        query = (
            "UPDATE files SET is_missing=1, scan_state=CASE WHEN scan_state='indexed' "
            "THEN 'missing' ELSE scan_state END, updated_at=? "
            "WHERE source_id=? AND last_seen_scan_id IS NOT ? AND scan_state IN ('indexed','missing')"
        )
        params: list[Any] = [utcnow(), source_id, scan_id]
        for prefix in skip_prefixes or []:
            query += " AND path NOT LIKE ?"
            params.append(prefix + os.sep + "%")
        with self.connection(write=True) as con:
            cursor = con.execute(query, params)
            return cursor.rowcount

    def count_files_for_paths(self) -> dict[str, int]:
        with self.connection() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM files").fetchone()
        return {"files": row["n"] if row else 0}

    # ---------------------------------------------------------- duplicate scan
    def finalise_duplicate_groups(self) -> dict[str, int]:
        with self.connection() as con:
            rows = [
                dict(row) for row in con.execute(
                    "SELECT id,path,filename,content_hash,scan_state,instrument,role,tempo_bpm,"
                    "duration_seconds,note_count,fingerprint_version,parser_version,"
                    "classifier_version,fingerprint_json FROM files "
                    "WHERE scan_state='indexed' AND content_hash IS NOT NULL"
                ).fetchall()
            ]
        exact = exact_groups(rows)
        exact_ids = {file["id"] for group in exact for file in group}
        similar = similar_groups(rows, excluded_ids=exact_ids)
        stale = sum(
            1 for row in rows
            if row.get("fingerprint_json")
            and int(row.get("fingerprint_version") or LEGACY_FINGERPRINT_VERSION)
            != FINGERPRINT_VERSION
        )
        now = utcnow()
        with self.connection(write=True) as con:
            con.execute("DELETE FROM duplicate_groups")
            con.execute(
                "UPDATE files SET exact_group_id=NULL, exact_copy_count=0, "
                "similar_group_id=NULL, similar_copy_count=0"
            )
            for group in exact:
                cursor = con.execute(
                    "INSERT INTO duplicate_groups(kind,group_key,file_count,created_at) "
                    "VALUES('exact',?,?,?)",
                    (group[0].get("content_hash"), len(group), now),
                )
                group_id = int(cursor.lastrowid)
                for file in group:
                    con.execute(
                        "INSERT OR IGNORE INTO duplicate_members(group_id,file_id) VALUES(?,?)",
                        (group_id, file["id"]),
                    )
                    con.execute(
                        "UPDATE files SET exact_group_id=?, exact_copy_count=? WHERE id=?",
                        (group_id, len(group), file["id"]),
                    )
            for index, group in enumerate(similar, start=1):
                cursor = con.execute(
                    "INSERT INTO duplicate_groups(kind,group_key,file_count,created_at) "
                    "VALUES('similar',?,?,?)",
                    (f"similar-{index}-{group[0].get('instrument','')}-{group[0].get('role','')}",
                     len(group), now),
                )
                group_id = int(cursor.lastrowid)
                for file in group:
                    con.execute(
                        "INSERT OR IGNORE INTO duplicate_members(group_id,file_id) VALUES(?,?)",
                        (group_id, file["id"]),
                    )
                    con.execute(
                        "UPDATE files SET similar_group_id=?, similar_copy_count=? WHERE id=?",
                        (group_id, len(group), file["id"]),
                    )
        return {
            "exact_groups": len(exact),
            "exact_files": sum(len(group) for group in exact),
            "similar_groups": len(similar),
            "similar_files": sum(len(group) for group in similar),
            "stale_fingerprints": stale,
        }

    # --------------------------------------------------------------- library
    def query_library(self, **params: Any) -> dict[str, Any]:
        page = max(1, int(params.get("page") or 1))
        page_size = max(1, min(200, int(params.get("page_size") or 50)))
        q = (params.get("q") or "").strip()
        join_fts = bool(q and self.fts_enabled)
        where: list[str] = []
        values: list[Any] = []
        if params.get("include_failed") not in (True, "true", "1"):
            where.append("f.scan_state != 'failed'")
        if q:
            if join_fts:
                where.append("files_fts MATCH ?")
                values.append(self._fts_query(q))
            else:
                where.append("f.search_blob LIKE ?")
                values.append(f"%{q.casefold()}%")
        instrument = params.get("instrument")
        if instrument:
            values_list = [item for item in str(instrument).split(",") if item]
            where.append("f.instrument IN (" + ",".join("?" for _ in values_list) + ")")
            values.extend(values_list)
        role = params.get("role")
        if role:
            values_list = [item for item in str(role).split(",") if item]
            where.append("f.role IN (" + ",".join("?" for _ in values_list) + ")")
            values.extend(values_list)
        style = params.get("style") or params.get("feel")
        if style:
            values_list = [item for item in str(style).split(",") if item]
            clauses = ["f.style_tags LIKE ?" for _ in values_list]
            where.append("(" + " OR ".join(clauses) + ")")
            values.extend(f'%"{item}"%' for item in values_list)
        if params.get("tempo_min") not in (None, ""):
            # Match the whole tempo map, not just the initial tempo: a file
            # that visits 150 BPM should be found by a 140–160 BPM filter even
            # if it starts at 90 BPM.
            where.append("COALESCE(f.tempo_max_bpm, f.tempo_bpm, 0) >= ?")
            values.append(float(params["tempo_min"]))
        if params.get("tempo_max") not in (None, ""):
            where.append("COALESCE(f.tempo_min_bpm, f.tempo_bpm, 100000) <= ?")
            values.append(float(params["tempo_max"]))
        if params.get("time_sig"):
            values_list = [item for item in str(params["time_sig"]).split(",") if item]
            where.append("f.time_sig IN (" + ",".join("?" for _ in values_list) + ")")
            values.extend(values_list)
        if params.get("key"):
            values_list = [item for item in str(params["key"]).split(",") if item]
            where.append("f.key_name IN (" + ",".join("?" for _ in values_list) + ")")
            values.extend(values_list)
        if params.get("key_source"):
            where.append("f.key_source=?")
            values.append(params["key_source"])
        if params.get("duration_min") not in (None, ""):
            where.append("f.duration_seconds >= ?")
            values.append(float(params["duration_min"]))
        if params.get("duration_max") not in (None, ""):
            where.append("f.duration_seconds <= ?")
            values.append(float(params["duration_max"]))
        if params.get("bars_min") not in (None, ""):
            where.append("f.bars >= ?")
            values.append(float(params["bars_min"]))
        if params.get("bars_max") not in (None, ""):
            where.append("f.bars <= ?")
            values.append(float(params["bars_max"]))
        if params.get("pitch_min") not in (None, ""):
            where.append("f.pitch_min >= ?")
            values.append(int(params["pitch_min"]))
        if params.get("pitch_max") not in (None, ""):
            where.append("f.pitch_max <= ?")
            values.append(int(params["pitch_max"]))
        if params.get("density_min") not in (None, ""):
            where.append("f.note_density >= ?")
            values.append(float(params["density_min"]))
        if params.get("density_max") not in (None, ""):
            where.append("f.note_density <= ?")
            values.append(float(params["density_max"]))
        if params.get("confidence_min") not in (None, ""):
            where.append("f.confidence >= ?")
            values.append(float(params["confidence_min"]))
        if params.get("folder"):
            folder = str(params["folder"]).rstrip("\\/")
            where.append("(f.dirname = ? OR f.dirname LIKE ?)")
            values.append(os.path.normpath(folder))
            values.append(os.path.normpath(folder) + os.sep + "%")
        if params.get("source_id") not in (None, ""):
            where.append("f.source_id = ?")
            values.append(int(params["source_id"]))
        if params.get("favorite") in (True, "true", "1", 1):
            where.append("f.favorite = 1")
        if params.get("collection_id") not in (None, ""):
            where.append("f.id IN (SELECT file_id FROM collection_files WHERE collection_id=?)")
            values.append(int(params["collection_id"]))
        if params.get("tag"):
            where.append("f.id IN (SELECT ft.file_id FROM file_tags ft JOIN tags t ON t.id=ft.tag_id WHERE t.name=?)")
            values.append(str(params["tag"]))
        duplicate = params.get("duplicate")
        if duplicate == "exact":
            where.append("f.exact_group_id IS NOT NULL")
        elif duplicate == "similar":
            where.append("f.similar_group_id IS NOT NULL")
        elif duplicate == "unique":
            where.append("f.exact_group_id IS NULL AND f.similar_group_id IS NULL")
        elif duplicate in ("any",):
            where.append("(f.exact_group_id IS NOT NULL OR f.similar_group_id IS NOT NULL)")
        if params.get("uncertain") in (True, "true", "1", 1):
            where.append("f.uncertain = 1")
        if params.get("scan_state"):
            states = [item for item in str(params["scan_state"]).split(",") if item]
            where.append("f.scan_state IN (" + ",".join("?" for _ in states) + ")")
            values.extend(states)
        if params.get("missing") in (True, "true", "1", 1):
            where.append("f.is_missing = 1")
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        join_sql = " JOIN files_fts ON files_fts.rowid = f.id" if join_fts else ""
        count_sql = f"SELECT COUNT(*) AS n FROM files f{join_sql}{where_sql}"
        sort = str(params.get("sort") or ("relevance" if q else "name"))
        order_map = {
            "name": "f.filename COLLATE NOCASE ASC, f.path COLLATE NOCASE ASC",
            "recent": "f.updated_at DESC, f.filename COLLATE NOCASE ASC",
            "duration": "f.duration_seconds DESC, f.filename COLLATE NOCASE ASC",
            "tempo": "f.tempo_bpm ASC, f.filename COLLATE NOCASE ASC",
            "confidence": "f.confidence DESC, f.filename COLLATE NOCASE ASC",
            "bars": "f.bars DESC, f.filename COLLATE NOCASE ASC",
        }
        order_sql = order_map.get(sort, order_map["name"])
        if sort == "relevance" and join_fts:
            order_sql = "bm25(files_fts) ASC"
        columns = (
            "f.id,f.path,f.dirname,f.filename,f.extension,f.source_id,f.size,f.scan_state,"
            "f.error,f.is_missing,f.parser_version,f.classifier_version,f.content_hash,f.format,f.timing_type,"
            "f.sequence_count,f.duration_seconds,f.duration_beats,f.bars,f.tempo_bpm,tempo_source,"
            "f.tempo_min_bpm,f.tempo_max_bpm,f.tempo_change_count,f.time_sig,f.time_sig_source,"
            "f.key_name,f.key_source,f.key_confidence,f.note_count,f.track_count,"
            "f.pitch_min,f.pitch_max,f.velocity_min,f.velocity_max,f.note_density,f.polyphony_max,"
            "f.instrument,f.instrument_confidence,f.instrument_source,f.role,f.role_confidence,"
            "f.role_source,f.auto_instrument,f.auto_instrument_confidence,f.auto_role,"
            "f.auto_role_confidence,f.style_tags,f.genre_hint,f.genre_confidence,f.uncertain,"
            "f.confidence,f.favorite,f.user_notes,f.exact_group_id,f.exact_copy_count,"
            "f.similar_group_id,f.similar_copy_count,f.embedded_text_json,f.updated_at,"
            "f.indexed_at, s.label AS source_label, s.available AS source_available,"
            "s.enabled AS source_enabled"
        )
        query_sql = (
            f"SELECT {columns} FROM files f{join_sql} "
            f"LEFT JOIN sources s ON s.id=f.source_id{where_sql} "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?"
        )
        with self.connection() as con:
            total = con.execute(count_sql, values).fetchone()["n"]
            rows = con.execute(query_sql, [*values, page_size, (page - 1) * page_size]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["favorite"] = bool(item["favorite"])
            item["uncertain"] = bool(item["uncertain"])
            item["source_available"] = bool(item["source_available"]) if item["source_available"] is not None else None
            item["style_tags"] = _decode_json(item["style_tags"], [])
            item["embedded_text"] = _decode_json(item.pop("embedded_text_json", "[]"), [])
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "fts": self.fts_enabled,
        }

    def _fts_query(self, text: str) -> str:
        tokens = re.findall(r"[A-Za-z0-9_]+", text)
        if not tokens:
            return '""'
        parts = []
        for token in tokens[:12]:
            parts.append(f'"{token}"*')
        return " AND ".join(parts)

    def get_file_row(self, file_id: int) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute(
                "SELECT f.*, s.label AS source_label, s.available AS source_available, "
                "s.kind AS source_kind, s.enabled AS source_enabled "
                "FROM files f LEFT JOIN sources s ON s.id=f.source_id WHERE f.id=?",
                (file_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["favorite"] = bool(item["favorite"])
        item["uncertain"] = bool(item["uncertain"])
        for key in (
            "style_tags", "embedded_text_json", "conflicts_json", "uncertainty_json",
            "warnings_json",
        ):
            if key in item:
                item[key] = _decode_json(item[key], [])
        if item.get("source_available") is not None:
            item["source_available"] = bool(item["source_available"])
        return item

    def get_file_details(self, file_id: int) -> dict[str, Any] | None:
        file = self.get_file_row(file_id)
        if not file:
            return None
        cache = None
        if file.get("cache_blob"):
            try:
                cache = json.loads(gzip.decompress(file["cache_blob"]).decode("utf-8"))
            except Exception:
                cache = None
        file.pop("cache_blob", None)
        with self.connection() as con:
            track_rows = [
                dict(row) for row in con.execute(
                    "SELECT * FROM tracks WHERE file_id=? ORDER BY sequence_index,track_index",
                    (file_id,),
                ).fetchall()
            ]
            tags = [dict(row) for row in con.execute(
                "SELECT t.id,t.name,t.color FROM tags t JOIN file_tags ft ON ft.tag_id=t.id "
                "WHERE ft.file_id=? ORDER BY t.name", (file_id,)
            ).fetchall()]
            collections = [dict(row) for row in con.execute(
                "SELECT c.id,c.name FROM collections c JOIN collection_files cf "
                "ON cf.collection_id=c.id WHERE cf.file_id=? ORDER BY c.name", (file_id,)
            ).fetchall()]
            file_corrections = [dict(row) for row in con.execute(
                "SELECT * FROM file_corrections WHERE file_id=?", (file_id,)
            ).fetchall()]
            track_corrections = [dict(row) for row in con.execute(
                "SELECT * FROM track_corrections WHERE file_id=?", (file_id,)
            ).fetchall()]
            exact_members = []
            similar_members = []
            if file.get("exact_group_id"):
                exact_members = [dict(row) for row in con.execute(
                    "SELECT f.id,f.path,f.filename,f.dirname,f.source_id,s.available AS source_available "
                    "FROM duplicate_members dm JOIN files f ON f.id=dm.file_id "
                    "LEFT JOIN sources s ON s.id=f.source_id WHERE dm.group_id=?",
                    (file["exact_group_id"],),
                ).fetchall()]
            if file.get("similar_group_id"):
                similar_members = [dict(row) for row in con.execute(
                    "SELECT f.id,f.path,f.filename,f.dirname,f.instrument,f.role,"
                    "f.tempo_bpm,f.duration_seconds FROM duplicate_members dm "
                    "JOIN files f ON f.id=dm.file_id WHERE dm.group_id=?",
                    (file["similar_group_id"],),
                ).fetchall()]
        for track in track_rows:
            track["programs"] = _decode_json(track.get("programs_json"), [])
            track["controller_counts"] = _decode_json(track.get("controller_json"), {})
            track["auto_instrument_evidence"] = _decode_json(
                track.get("auto_instrument_evidence_json"), []
            )
            track["auto_instrument_alternatives"] = _decode_json(
                track.get("auto_instrument_alternatives_json"), []
            )
            track["auto_role_evidence"] = _decode_json(track.get("auto_role_evidence_json"), [])
            track["auto_role_alternatives"] = _decode_json(
                track.get("auto_role_alternatives_json"), []
            )
            track["style_tags"] = _decode_json(track.get("style_tags"), [])
            track["conflicts"] = _decode_json(track.get("conflicts_json"), [])
            track["analysis"] = _decode_json(track.get("analysis_json"), {})
            for key in (
                "programs_json", "controller_json", "auto_instrument_evidence_json",
                "auto_instrument_alternatives_json", "auto_role_evidence_json",
                "auto_role_alternatives_json", "conflicts_json", "analysis_json",
            ):
                track.pop(key, None)
        # Expose latest automatic predictions separately from effective labels.
        predictions = []
        with self.connection() as con:
            for row in con.execute(
                "SELECT * FROM predictions WHERE file_id=? ORDER BY sequence_index,track_index,dimension",
                (file_id,),
            ).fetchall():
                item = dict(row)
                item["evidence_json"] = _decode_json(item.get("evidence_json"), [])
                item["alternatives_json"] = _decode_json(item.get("alternatives_json"), [])
                predictions.append(item)
        return {
            "file": file,
            "tracks": track_rows,
            "cache": cache,
            "tags": tags,
            "collections": collections,
            "corrections": {
                "file": file_corrections,
                "tracks": track_corrections,
            },
            "predictions": predictions,
            "duplicates": {
                "exact_members": exact_members,
                "similar_members": similar_members,
            },
        }

    def raw_file_path(self, file_id: int) -> str | None:
        with self.connection() as con:
            row = con.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
        return row["path"] if row else None

    def facets(self) -> dict[str, Any]:
        with self.connection() as con:
            instruments = [
                dict(row) for row in con.execute(
                    "SELECT instrument AS value, COUNT(*) AS count FROM files "
                    "WHERE scan_state != 'failed' GROUP BY instrument ORDER BY count DESC"
                ).fetchall()
            ]
            roles = [
                dict(row) for row in con.execute(
                    "SELECT role AS value, COUNT(*) AS count FROM files "
                    "WHERE scan_state != 'failed' GROUP BY role ORDER BY count DESC"
                ).fetchall()
            ]
            style_rows = con.execute(
                "SELECT style_tags FROM files WHERE scan_state != 'failed' AND style_tags IS NOT NULL"
            ).fetchall()
            totals = con.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) AS favorites, "
                "SUM(CASE WHEN uncertain=1 THEN 1 ELSE 0 END) AS uncertain, "
                "SUM(CASE WHEN is_missing=1 THEN 1 ELSE 0 END) AS missing, "
                "SUM(CASE WHEN scan_state='failed' THEN 1 ELSE 0 END) AS failed, "
                "SUM(CASE WHEN exact_group_id IS NOT NULL THEN 1 ELSE 0 END) AS exact_duplicates, "
                "SUM(CASE WHEN similar_group_id IS NOT NULL THEN 1 ELSE 0 END) AS similar_duplicates "
                "FROM files"
            ).fetchone()
            sources = [
                dict(row) for row in con.execute(
                    "SELECT s.id,s.label,s.path,s.available,s.kind,s.enabled,COUNT(f.id) AS count "
                    "FROM sources s LEFT JOIN files f ON f.source_id=s.id GROUP BY s.id ORDER BY s.path"
                ).fetchall()
            ]
            collections = [
                dict(row) for row in con.execute(
                    "SELECT c.id,c.name,COUNT(cf.file_id) AS count FROM collections c "
                    "LEFT JOIN collection_files cf ON cf.collection_id=c.id "
                    "GROUP BY c.id ORDER BY c.name"
                ).fetchall()
            ]
            tags = [
                dict(row) for row in con.execute(
                    "SELECT t.id,t.name,t.color,COUNT(ft.file_id) AS count FROM tags t "
                    "LEFT JOIN file_tags ft ON ft.tag_id=t.id GROUP BY t.id ORDER BY t.name"
                ).fetchall()
            ]
        style_counts: dict[str, int] = {}
        for row in style_rows:
            for style in _decode_json(row["style_tags"], []):
                style_counts[style] = style_counts.get(style, 0) + 1
        totals = dict(totals) if totals else {}
        for key in ("total", "favorites", "uncertain", "missing", "failed",
                    "exact_duplicates", "similar_duplicates"):
            totals[key] = totals.get(key) or 0
        return {
            "totals": totals,
            "instruments": [item for item in instruments if item["value"]],
            "roles": [item for item in roles if item["value"]],
            "styles": [{"value": key, "count": value} for key, value in
                       sorted(style_counts.items(), key=lambda item: -item[1])],
            "sources": sources,
            "collections": collections,
            "tags": tags,
        }

    def list_folders(self, limit: int = 8000) -> dict[str, Any]:
        with self.connection() as con:
            rows = [
                dict(row) for row in con.execute(
                    "SELECT dirname AS path, source_id, COUNT(*) AS count FROM files "
                    "WHERE scan_state != 'failed' GROUP BY dirname, source_id "
                    "ORDER BY dirname COLLATE NOCASE LIMIT ?", (limit + 1,)
                ).fetchall()
            ]
            sources = [dict(row) for row in con.execute(
                "SELECT id,label,path,kind,available FROM sources ORDER BY path"
            ).fetchall()]
        truncated = len(rows) > limit
        return {
            "folders": rows[:limit],
            "sources": sources,
            "truncated": truncated,
            "limit": limit,
        }

    def stats(self) -> dict[str, Any]:
        with self.connection() as con:
            row = con.execute(
                "SELECT COUNT(*) AS files, "
                "SUM(CASE WHEN scan_state='indexed' THEN 1 ELSE 0 END) AS indexed, "
                "SUM(CASE WHEN scan_state='failed' THEN 1 ELSE 0 END) AS failed, "
                "SUM(CASE WHEN is_missing=1 THEN 1 ELSE 0 END) AS missing, "
                "SUM(CASE WHEN uncertain=1 THEN 1 ELSE 0 END) AS uncertain, "
                "SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) AS favorites, "
                "SUM(CASE WHEN exact_group_id IS NOT NULL THEN 1 ELSE 0 END) AS exact_duplicates, "
                "SUM(CASE WHEN similar_group_id IS NOT NULL THEN 1 ELSE 0 END) AS similar_duplicates, "
                "SUM(note_count) AS notes FROM files"
            ).fetchone()
        result = dict(row) if row else {}
        for key in list(result):
            result[key] = result[key] or 0
        result["db_path"] = self.db_path
        result["db_size_bytes"] = self.path.stat().st_size if self.path.exists() else 0
        result["fts_enabled"] = self.fts_enabled
        return result

    # --------------------------------------------------------- file metadata
    def set_favorite(self, file_id: int, value: bool) -> bool:
        with self.connection(write=True) as con:
            cursor = con.execute(
                "UPDATE files SET favorite=?, updated_at=? WHERE id=?",
                (1 if value else 0, utcnow(), file_id),
            )
            return cursor.rowcount > 0

    def set_user_notes(self, file_id: int, notes: str) -> bool:
        with self.connection(write=True) as con:
            cursor = con.execute(
                "UPDATE files SET user_notes=?, updated_at=? WHERE id=?",
                (notes[:10000], utcnow(), file_id),
            )
            self._refresh_fts(con, file_id)
            return cursor.rowcount > 0

    def _apply_file_label(self, con: sqlite3.Connection, file_id: int, dimension: str,
                          value: str, *, clear: bool) -> bool:
        row = con.execute(
            "SELECT auto_instrument, auto_role FROM files WHERE id=?", (file_id,)
        ).fetchone()
        if not row:
            return False
        if clear:
            con.execute(
                "DELETE FROM file_corrections WHERE file_id=? AND dimension=?",
                (file_id, dimension),
            )
        else:
            auto_value = row["auto_instrument"] if dimension == "instrument" else row["auto_role"]
            action = "accepted" if value == auto_value else "corrected"
            con.execute(
                "INSERT INTO file_corrections(file_id,dimension,value,action,created_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(file_id,dimension) DO UPDATE SET "
                "value=excluded.value, action=excluded.action, created_at=excluded.created_at",
                (file_id, dimension, value, action, utcnow()),
            )
            con.execute(
                "UPDATE predictions SET user_action=? WHERE file_id=? AND sequence_index=-1 "
                "AND track_index=-1 AND dimension=?",
                (action, file_id, dimension),
            )
        self._apply_file_effective_label(con, file_id)
        self._refresh_fts(con, file_id)
        return True

    def set_file_label(self, file_id: int, dimension: str, value: str,
                       *, clear: bool = False) -> dict[str, Any] | None:
        if dimension not in ("instrument", "role"):
            raise ValueError("dimension must be instrument or role")
        with self.connection(write=True) as con:
            found = self._apply_file_label(con, file_id, dimension, value, clear=clear)
        return self.get_file_details(file_id) if found else None

    def set_track_label(self, file_id: int, sequence_index: int, track_index: int,
                        dimension: str, value: str, *, clear: bool = False) -> dict[str, Any] | None:
        if dimension not in ("instrument", "role"):
            raise ValueError("dimension must be instrument or role")
        with self.connection(write=True) as con:
            track = con.execute(
                "SELECT id,auto_instrument,auto_role FROM tracks WHERE file_id=? "
                "AND sequence_index=? AND track_index=?",
                (file_id, sequence_index, track_index),
            ).fetchone()
            if not track:
                return None
            if clear:
                con.execute(
                    "DELETE FROM track_corrections WHERE file_id=? AND sequence_index=? "
                    "AND track_index=? AND dimension=?",
                    (file_id, sequence_index, track_index, dimension),
                )
            else:
                auto_value = track["auto_instrument"] if dimension == "instrument" else track["auto_role"]
                action = "accepted" if value == auto_value else "corrected"
                con.execute(
                    "INSERT INTO track_corrections(file_id,sequence_index,track_index,dimension,"
                    "value,action,created_at) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(file_id,sequence_index,track_index,dimension) DO UPDATE SET "
                    "value=excluded.value, action=excluded.action, created_at=excluded.created_at",
                    (file_id, sequence_index, track_index, dimension, value, action, utcnow()),
                )
                con.execute(
                    "UPDATE predictions SET user_action=? WHERE file_id=? AND sequence_index=? "
                    "AND track_index=? AND dimension=?",
                    (action, file_id, sequence_index, track_index, dimension),
                )
            row = con.execute(
                "SELECT auto_instrument, auto_role FROM tracks WHERE id=?", (track["id"],)
            ).fetchone()
            corrections = {
                item["dimension"]: item["value"] for item in con.execute(
                    "SELECT dimension, value FROM track_corrections WHERE file_id=? "
                    "AND sequence_index=? AND track_index=?",
                    (file_id, sequence_index, track_index),
                ).fetchall()
            }
            con.execute(
                "UPDATE tracks SET instrument=?, instrument_source=?, role=?, role_source=?, "
                "label_source=? WHERE id=?",
                (
                    corrections.get("instrument", row["auto_instrument"]),
                    "user" if "instrument" in corrections else "auto",
                    corrections.get("role", row["auto_role"]),
                    "user" if "role" in corrections else "auto",
                    "user" if corrections else "auto",
                    track["id"],
                ),
            )
            self._refresh_fts(con, file_id)
        return self.get_file_details(file_id)

    def bulk_file_labels(self, file_ids: Iterable[int], dimension: str, value: str) -> int:
        """Apply one label across many files in a single write transaction.

        Per-file transactions made this O(n) in connection churn plus a
        get_file_details() whose result was thrown away; a bulk label edit took
        ~16 ms per file instead of ~0.1 ms.
        """
        if dimension not in ("instrument", "role"):
            raise ValueError("dimension must be instrument or role")
        count = 0
        with self.connection(write=True) as con:
            for file_id in file_ids:
                if self._apply_file_label(con, int(file_id), dimension, value, clear=False):
                    count += 1
        return count

    def bulk_favorite(self, file_ids: Iterable[int], value: bool) -> int:
        now = utcnow()
        with self.connection(write=True) as con:
            count = 0
            for file_id in file_ids:
                cursor = con.execute(
                    "UPDATE files SET favorite=?, updated_at=? WHERE id=?",
                    (1 if value else 0, now, int(file_id)),
                )
                count += cursor.rowcount
            return count

    # -------------------------------------------------------------------- tags
    def add_tag(self, file_id: int, name: str, color: str | None = None) -> dict[str, Any]:
        clean = name.strip()[:60]
        if not clean:
            raise ValueError("Tag name cannot be empty")
        with self.connection(write=True) as con:
            con.execute(
                "INSERT INTO tags(name,color,created_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET color=COALESCE(excluded.color, tags.color)",
                (clean, color, utcnow()),
            )
            row = con.execute("SELECT id,name,color FROM tags WHERE name=?", (clean,)).fetchone()
            con.execute(
                "INSERT OR IGNORE INTO file_tags(file_id,tag_id) VALUES(?,?)",
                (file_id, row["id"]),
            )
            self._refresh_fts(con, file_id)
        return dict(row)

    def remove_tag(self, file_id: int, tag_id: int) -> None:
        with self.connection(write=True) as con:
            con.execute(
                "DELETE FROM file_tags WHERE file_id=? AND tag_id=?", (file_id, tag_id)
            )
            self._refresh_fts(con, file_id)

    def list_tags(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute(
                "SELECT t.id,t.name,t.color,COUNT(ft.file_id) AS count FROM tags t "
                "LEFT JOIN file_tags ft ON ft.tag_id=t.id GROUP BY t.id ORDER BY t.name"
            ).fetchall()]

    # ------------------------------------------------------------- collections
    def list_collections(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute(
                "SELECT c.id,c.name,c.description,c.created_at,c.updated_at,"
                "COUNT(cf.file_id) AS count FROM collections c "
                "LEFT JOIN collection_files cf ON cf.collection_id=c.id "
                "GROUP BY c.id ORDER BY c.name COLLATE NOCASE"
            ).fetchall()]

    def create_collection(self, name: str, description: str = "") -> dict[str, Any]:
        clean = name.strip()[:80]
        if not clean:
            raise ValueError("Collection name cannot be empty")
        now = utcnow()
        with self.connection(write=True) as con:
            con.execute(
                "INSERT INTO collections(name,description,created_at,updated_at) VALUES(?,?,?,?)",
                (clean, description[:500], now, now),
            )
            row = con.execute("SELECT * FROM collections WHERE name=?", (clean,)).fetchone()
        return dict(row) if row else {}

    def update_collection(self, collection_id: int, name: str | None = None,
                          description: str | None = None) -> dict[str, Any] | None:
        with self.connection(write=True) as con:
            if name is not None:
                con.execute(
                    "UPDATE collections SET name=?, updated_at=? WHERE id=?",
                    (name.strip()[:80], utcnow(), collection_id),
                )
            if description is not None:
                con.execute(
                    "UPDATE collections SET description=?, updated_at=? WHERE id=?",
                    (description[:500], utcnow(), collection_id),
                )
            row = con.execute("SELECT * FROM collections WHERE id=?", (collection_id,)).fetchone()
        return dict(row) if row else None

    def delete_collection(self, collection_id: int) -> None:
        with self.connection(write=True) as con:
            con.execute("DELETE FROM collections WHERE id=?", (collection_id,))

    def add_to_collection(self, collection_id: int, file_ids: Iterable[int]) -> int:
        now = utcnow()
        with self.connection(write=True) as con:
            count = 0
            for file_id in file_ids:
                cursor = con.execute(
                    "INSERT OR IGNORE INTO collection_files(collection_id,file_id,added_at) "
                    "VALUES(?,?,?)", (collection_id, int(file_id), now)
                )
                count += cursor.rowcount
            con.execute("UPDATE collections SET updated_at=? WHERE id=?", (now, collection_id))
            return count

    def remove_from_collection(self, collection_id: int, file_ids: Iterable[int]) -> int:
        with self.connection(write=True) as con:
            count = 0
            for file_id in file_ids:
                cursor = con.execute(
                    "DELETE FROM collection_files WHERE collection_id=? AND file_id=?",
                    (collection_id, int(file_id)),
                )
                count += cursor.rowcount
            con.execute("UPDATE collections SET updated_at=? WHERE id=?", (utcnow(), collection_id))
            return count

    # -------------------------------------------------------------- duplicates
    def duplicate_groups(self, kind: str = "exact", limit: int = 200) -> dict[str, Any]:
        with self.connection() as con:
            groups = [
                dict(row) for row in con.execute(
                    "SELECT * FROM duplicate_groups WHERE kind=? ORDER BY id LIMIT ?",
                    (kind, limit),
                ).fetchall()
            ]
            for group in groups:
                members = [dict(row) for row in con.execute(
                    "SELECT f.id,f.path,f.filename,f.dirname,f.source_id,f.instrument,f.role,"
                    "f.tempo_bpm,f.duration_seconds,f.is_missing,s.label AS source_label,"
                    "s.available AS source_available FROM duplicate_members dm "
                    "JOIN files f ON f.id=dm.file_id LEFT JOIN sources s ON s.id=f.source_id "
                    "WHERE dm.group_id=? ORDER BY f.path", (group["id"],)
                ).fetchall()]
                group["members"] = members
        return {"kind": kind, "groups": groups, "group_count": len(groups)}

    # --------------------------------------------------------------- maintenance
    def backup_to(self, destination: str | os.PathLike) -> str:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(destination_path))
        try:
            with self.connection() as source:
                source.backup(target)
        finally:
            # Connection.__exit__ commits but does not close; on Windows an
            # unresolved handle would keep the backup file locked.
            target.close()
        return str(destination_path)

    def invalidate_sources(self, source_ids: Iterable[int]) -> int:
        """Zero the derived analysis for the sources one scan run owns.

        Scoped deliberately. A global invalidation also drops the version stamp
        on rows under a source that is disabled or unplugged, and no scan in
        this run will rewrite them, so the index is left permanently legacy.
        """
        ids = [int(value) for value in source_ids]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        with self.connection(write=True) as con:
            cursor = con.execute(
                "UPDATE files SET parser_version=0, classifier_version=0, "
                f"fingerprint_version=0 WHERE source_id IN ({placeholders})", ids)
            con.execute(
                "UPDATE tracks SET auto_instrument='Unknown', auto_role='Unknown' "
                "WHERE file_id IN (SELECT id FROM files WHERE source_id IN ("
                f"{placeholders}))", ids)
            return cursor.rowcount

    def clear_scan_issues(self) -> None:
        with self.connection(write=True) as con:
            con.execute("DELETE FROM scan_issues")

    def fingerprint_coverage(self) -> dict[str, int]:
        """How much of the index can similarity actually speak about.

        ``legacy`` counts files whose fingerprint predates the current
        generation. Those files are skipped by the comparison, so this is the
        number of files a re-scan still owes — not a bug count.
        """
        with self.connection() as con:
            row = con.execute(
                "SELECT "
                "SUM(CASE WHEN fingerprint_version=? THEN 1 ELSE 0 END) AS current,"
                "SUM(CASE WHEN COALESCE(fingerprint_version,?)<>? THEN 1 ELSE 0 END) AS legacy,"
                "COUNT(*) AS total FROM files WHERE scan_state='indexed'",
                (FINGERPRINT_VERSION, LEGACY_FINGERPRINT_VERSION, FINGERPRINT_VERSION),
            ).fetchone()
        return {
            "current": int(row["current"] or 0) if row else 0,
            "legacy": int(row["legacy"] or 0) if row else 0,
            "indexed": int(row["total"] or 0) if row else 0,
        }

    def db_health(self) -> dict[str, Any]:
        with self.connection() as con:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        with self.connection() as con:
            migration = con.execute("SELECT value FROM meta WHERE key='last_migration'").fetchone()
        return {
            "integrity": integrity,
            "foreign_key_issues": len(fk),
            "fts_enabled": self.fts_enabled,
            "schema_version": self.schema_version,
            "fingerprint_version": FINGERPRINT_VERSION,
            "fingerprint_coverage": self.fingerprint_coverage(),
            "last_migration": _decode_json(migration["value"] if migration else None, None),
        }


def _migrate_schema_1_to_2(con: sqlite3.Connection) -> None:
    """Add ``files.fingerprint_version`` and mark every existing row legacy.

    Fingerprint vectors written before versioning carry no ``fv``, so they
    cannot be compared against current ones. Each pre-existing row is stamped
    ``LEGACY_FINGERPRINT_VERSION``: similarity refuses it, and the next scan
    re-indexes it once. That one-time pass is the point — a silently mixed
    index would under- or over-report duplicates with no way to tell.
    """
    columns = {row["name"] for row in con.execute("PRAGMA table_info(files)").fetchall()}
    if "fingerprint_version" not in columns:
        con.execute("ALTER TABLE files ADD COLUMN fingerprint_version INTEGER")
    con.execute(
        "UPDATE files SET fingerprint_version=? WHERE fingerprint_version IS NULL",
        (LEGACY_FINGERPRINT_VERSION,),
    )


MIGRATIONS: dict[int, Any] = {1: _migrate_schema_1_to_2}

# Statements that need the *final* column set, so they run after migrations:
# an index naming a column a migration adds would otherwise fail on upgrade.
POST_SCHEMA_SQL = """
CREATE INDEX IF NOT EXISTS idx_files_fingerprint_version ON files(fingerprint_version);
"""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    label TEXT,
    kind TEXT NOT NULL DEFAULT 'folder',
    optional INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS excludes (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    note TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    ended_at TEXT,
    state TEXT NOT NULL,
    mode TEXT NOT NULL,
    sources_json TEXT,
    total_sources INTEGER DEFAULT 0,
    discovered INTEGER DEFAULT 0,
    indexed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    completion REAL DEFAULT 0,
    current_path TEXT DEFAULT '',
    message TEXT DEFAULT '',
    options_json TEXT
);
CREATE TABLE IF NOT EXISTS scan_issues (
    id INTEGER PRIMARY KEY,
    scan_run_id INTEGER REFERENCES scan_runs(id) ON DELETE CASCADE,
    kind TEXT,
    path TEXT,
    message TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    dirname TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    extension TEXT,
    size INTEGER,
    mtime_ns INTEGER,
    content_hash TEXT,
    parser_version INTEGER,
    classifier_version INTEGER,
    scan_state TEXT NOT NULL DEFAULT 'failed',
    error TEXT,
    is_missing INTEGER NOT NULL DEFAULT 0,
    format INTEGER,
    declared_tracks INTEGER,
    actual_tracks INTEGER,
    sequence_count INTEGER,
    division INTEGER,
    timing_type TEXT,
    duration_seconds REAL,
    duration_beats REAL,
    bars REAL,
    ticks_per_quarter INTEGER,
    tempo_bpm REAL,
    tempo_source TEXT,
    tempo_min_bpm REAL,
    tempo_max_bpm REAL,
    tempo_change_count INTEGER,
    time_sig TEXT,
    time_sig_source TEXT,
    time_sig_change_count INTEGER,
    key_name TEXT,
    key_source TEXT,
    key_confidence REAL,
    key_embedded TEXT,
    key_mode TEXT,
    note_count INTEGER DEFAULT 0,
    track_count INTEGER DEFAULT 0,
    channel_count INTEGER DEFAULT 0,
    program_count INTEGER DEFAULT 0,
    pitch_min INTEGER,
    pitch_max INTEGER,
    velocity_min INTEGER,
    velocity_max INTEGER,
    velocity_mean REAL,
    note_density REAL,
    polyphony_max INTEGER,
    polyphony_mean REAL,
    auto_instrument TEXT,
    auto_instrument_confidence REAL,
    auto_role TEXT,
    auto_role_confidence REAL,
    instrument TEXT,
    instrument_confidence REAL,
    instrument_source TEXT DEFAULT 'auto',
    role TEXT,
    role_confidence REAL,
    role_source TEXT DEFAULT 'auto',
    label_source TEXT DEFAULT 'auto',
    style_tags TEXT,
    genre_hint TEXT,
    genre_confidence REAL,
    classifier_method TEXT,
    uncertain INTEGER NOT NULL DEFAULT 0,
    confidence REAL,
    conflicts_json TEXT,
    uncertainty_json TEXT,
    warnings_json TEXT,
    embedded_text_json TEXT,
    fingerprint_json TEXT,
    fingerprint_version INTEGER,
    favorite INTEGER NOT NULL DEFAULT 0,
    user_notes TEXT NOT NULL DEFAULT '',
    search_blob TEXT,
    cache_blob BLOB,
    exact_group_id INTEGER,
    exact_copy_count INTEGER DEFAULT 0,
    similar_group_id INTEGER,
    similar_copy_count INTEGER DEFAULT 0,
    indexed_at TEXT,
    updated_at TEXT,
    last_seen_at TEXT,
    last_seen_scan_id INTEGER
);
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sequence_index INTEGER NOT NULL DEFAULT 0,
    track_index INTEGER NOT NULL DEFAULT 0,
    chunk_index INTEGER,
    channel INTEGER,
    name TEXT,
    program INTEGER,
    programs_json TEXT,
    bank_msb INTEGER,
    bank_lsb INTEGER,
    note_count INTEGER,
    pitch_min INTEGER,
    pitch_max INTEGER,
    sustained_notes INTEGER,
    assumed_durations INTEGER,
    controller_json TEXT,
    auto_instrument TEXT,
    auto_instrument_confidence REAL,
    auto_instrument_evidence_json TEXT,
    auto_instrument_alternatives_json TEXT,
    auto_role TEXT,
    auto_role_confidence REAL,
    auto_role_evidence_json TEXT,
    auto_role_alternatives_json TEXT,
    instrument TEXT,
    instrument_confidence REAL,
    instrument_source TEXT DEFAULT 'auto',
    role TEXT,
    role_confidence REAL,
    role_source TEXT DEFAULT 'auto',
    label_source TEXT DEFAULT 'auto',
    style_tags TEXT,
    uncertain INTEGER NOT NULL DEFAULT 0,
    conflicts_json TEXT,
    source_text TEXT,
    analysis_json TEXT,
    updated_at TEXT,
    UNIQUE(file_id, sequence_index, track_index)
);
CREATE TABLE IF NOT EXISTS file_corrections (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'corrected',
    created_at TEXT,
    UNIQUE(file_id, dimension)
);
CREATE TABLE IF NOT EXISTS track_corrections (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sequence_index INTEGER NOT NULL,
    track_index INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'corrected',
    created_at TEXT,
    UNIQUE(file_id, sequence_index, track_index, dimension)
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sequence_index INTEGER NOT NULL DEFAULT -1,
    track_index INTEGER NOT NULL DEFAULT -1,
    dimension TEXT NOT NULL,
    predicted TEXT,
    confidence REAL,
    evidence_json TEXT,
    alternatives_json TEXT,
    method TEXT,
    version TEXT,
    user_action TEXT,
    created_at TEXT,
    UNIQUE(file_id, sequence_index, track_index, dimension)
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS file_tags (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY(file_id, tag_id)
);
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS collection_files (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    added_at TEXT,
    PRIMARY KEY(collection_id, file_id)
);
CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    group_key TEXT,
    file_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    PRIMARY KEY(group_id, file_id)
);
CREATE INDEX IF NOT EXISTS idx_files_dirname ON files(dirname);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_files_state ON files(scan_state);
CREATE INDEX IF NOT EXISTS idx_files_instrument ON files(instrument);
CREATE INDEX IF NOT EXISTS idx_files_role ON files(role);
CREATE INDEX IF NOT EXISTS idx_files_source ON files(source_id);
CREATE INDEX IF NOT EXISTS idx_files_favorite ON files(favorite);
CREATE INDEX IF NOT EXISTS idx_files_uncertain ON files(uncertain);
CREATE INDEX IF NOT EXISTS idx_files_updated ON files(updated_at);
CREATE INDEX IF NOT EXISTS idx_tracks_file ON tracks(file_id);
CREATE INDEX IF NOT EXISTS idx_scan_issues_run ON scan_issues(scan_run_id);
"""
