from __future__ import annotations

import contextlib
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ["SKEER_SCAN_EXECUTOR"] = "threads"

from midivault.api import create_server
from midivault.db import Database
from midivault.engine.versions import FINGERPRINT_VERSION, PARSER_VERSION, SCHEMA_VERSION
from midivault.scanner import ScanManager
from tests.midi_builder import MidiTrack, build_smf


def show(midi_format: int = 0) -> bytes:
    track = MidiTrack().track_name("Rhodes Chords").program(0, 4).tempo(0, 120).time_signature(0, 4, 4)
    for bar in range(4):
        for pitch in (60, 64, 67, 71):
            track.note(bar * 4 * 480, pitch, 1500, 70)
    track.end(4 * 4 * 480)
    return build_smf([track], midi_format=midi_format)


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        # Windows can hold a just-written WAL file one beat too long; that must not read as a test failure.
        self.temp = tempfile.TemporaryDirectory(prefix="midivault-api-", ignore_cleanup_errors=True)
        root = Path(self.temp.name)
        self.library = root / "library"
        self.library.mkdir()
        (self.library / "Rhodes Chords.mid").write_bytes(show())
        self.data = root / "data"
        self.data.mkdir()
        self.db = Database(self.data / "midivault.sqlite3")
        self.source = self.db.add_source(str(self.library), "API Fixture", optional=True, enabled=True)
        self.scanner = ScanManager(self.db, self.data)
        self.scanner.start(source_ids=[self.source["id"]], mode="full", intensity="eco", workers=1)
        self._wait_scan()
        self.web_dir = root / "web"
        self.web_dir.mkdir()
        (self.web_dir / "index.html").write_text("<html><body>test</body></html>", encoding="utf-8")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.close()
        self.server = create_server(
            "127.0.0.1", self.port, self.db, self.scanner, self.data, self.web_dir,
            config={"verbose": False},
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}/api"
        self.file_id = self._get_library()["items"][0]["id"]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def _wait_scan(self, timeout: float = 20) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.scanner.get_status()["active"]:
                return
            time.sleep(0.04)
        raise AssertionError("scan did not finish")

    def _request(self, path: str, method: str = "GET", payload: dict | None = None,
                 headers: dict | None = None) -> tuple[int, dict | bytes, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base}{path}", data=body, method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
                parsed = json.loads(data) if "application/json" in content_type else data
                return response.status, parsed, dict(response.headers)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            try:
                parsed = json.loads(data)
            except Exception:
                parsed = {"error": data.decode("utf-8", "replace")}
            return exc.code, parsed, dict(exc.headers)

    def _get_library(self, query: str = "") -> dict:
        status, payload, _headers = self._request(f"/library?page_size=50&{query}")
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        return payload

    def test_a_refused_rebuild_leaves_the_index_intact(self) -> None:
        """The route used to clear the cache and only then try to start a scan.

        A rebuild with nothing selected answered 409 and had already zeroed every
        parser version, fingerprint and automatic label in the index — and because
        a full scan had run moments before, no later incremental pass would touch
        those files again. The library kept serving rows whose labels had been
        reset to Unknown with nothing queued to restore them.
        """
        status, payload, _headers = self._request(
            "/rebuild", method="POST", payload={"source_ids": [9999]})
        self.assertEqual(status, 409)
        self.assertIn("error", payload)
        item = self._get_library()["items"][0]
        self.assertEqual(item["parser_version"], PARSER_VERSION)
        with self.db.connection() as con:
            unknown = con.execute(
                "SELECT COUNT(*) AS n FROM tracks WHERE auto_instrument='Unknown'"
            ).fetchone()["n"]
            cleared = con.execute(
                "SELECT COUNT(*) AS n FROM files WHERE parser_version=0"
            ).fetchone()["n"]
        self.assertEqual((unknown, cleared), (0, 0), "a refused rebuild mutated the index")

    def test_rebuild_invalidates_and_reindexes_in_one_call(self) -> None:
        status, payload, _headers = self._request(
            "/rebuild", method="POST", payload={"source_ids": [self.source["id"]]})
        self.assertEqual(status, 202, payload)
        self.assertTrue(payload["scan"]["active"])
        self._wait_scan()
        self.assertEqual(self.db.stats()["indexed"], 1)
        item = self._get_library()["items"][0]
        self.assertEqual(item["parser_version"], PARSER_VERSION)
        self.assertNotEqual(item["instrument"], "Unknown")

    def test_health_and_bootstrap(self) -> None:
        status, health, _ = self._request("/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertEqual(health["versions"]["parser"], PARSER_VERSION)
        self.assertEqual(health["versions"]["schema"], SCHEMA_VERSION)
        # The interface must be able to see which fingerprint generation the
        # index is speaking, and whether anything is still waiting on a re-scan.
        self.assertEqual(health["versions"]["fingerprint"], FINGERPRINT_VERSION)
        coverage = health["db"]["fingerprint_coverage"]
        self.assertEqual(coverage["legacy"], 0)
        self.assertGreaterEqual(coverage["current"], 1)
        self.assertIn("local-only", health["privacy"])
        status, bootstrap, _ = self._request("/bootstrap")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(bootstrap["facets"]["totals"]["total"], 1)
        self.assertTrue(bootstrap["default_export_dir"])
        self.assertIn("scan", bootstrap)

    def test_health_never_runs_a_full_index_audit(self) -> None:
        """`/health` is the launcher's readiness question, so it must be cheap.

        `PRAGMA integrity_check` walks every page: measured at 1.72 s against a
        450 MB / 48,516-file index, beside a per-attempt probe timeout that was
        1.2 s. The two together meant a real user's healthy service could never
        be pronounced started, and the launcher shut it down. The audit still
        has to happen on the route that exists for it, which is what the second
        half of this test guards.
        """
        sink: list[str] = []
        real_connection = Database.connection

        class Recorder:
            def __init__(self, con) -> None:
                self._con = con

            def execute(self, sql, *args, **kwargs):
                sink.append(" ".join(str(sql).split()).lower())
                return self._con.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._con, name)

        @contextlib.contextmanager
        def recording_connection(db, write: bool = False):
            with real_connection(db, write=write) as con:
                yield Recorder(con)

        with mock.patch.object(Database, "connection", recording_connection):
            status, health, _ = self._request("/health")
            self.assertEqual(status, 200)
            readiness_sql = list(sink)
            sink.clear()
            status, audit, _ = self._request("/db/health")
            self.assertEqual(status, 200)
            audit_sql = list(sink)

        page_scans = [s for s in readiness_sql if "integrity_check" in s or "foreign_key_check" in s]
        self.assertEqual(page_scans, [], f"/health scanned the index: {page_scans}")
        self.assertNotIn("integrity", health["db"])
        self.assertNotIn("foreign_key_issues", health["db"])
        self.assertGreaterEqual(health["db"]["fingerprint_coverage"]["current"], 1)
        self.assertEqual(audit["integrity"], "ok",
                         "GET /api/db/health stopped auditing, which is that route's only purpose")

    def test_library_search_details_and_range(self) -> None:
        library = self._get_library("q=rhodes")
        self.assertEqual(library["total"], 1)
        item = library["items"][0]
        status, details, _ = self._request(f"/library/{item['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(details["cache"])
        self.assertEqual(details["cache"]["preview"]["format"], 0)
        self.assertEqual(details["file"]["instrument"], "Piano/keys")
        self.assertEqual(len(details["tracks"]), 1)
        self.assertEqual(details["tracks"][0]["name"], "Rhodes Chords")
        status, raw, headers = self._request(f"/library/{item['id']}/raw", headers={"Range": "bytes=0-9"})
        self.assertEqual(status, 206)
        self.assertIsInstance(raw, bytes)
        self.assertEqual(len(raw), 10)
        self.assertIn("Content-Range", headers)

    def test_editable_labels_favorites_notes_and_tags(self) -> None:
        status, updated, _ = self._request(
            f"/library/{self.file_id}/labels", "POST",
            {"dimension": "instrument", "value": "Synth"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["file"]["instrument"], "Synth")
        self.assertEqual(updated["file"]["instrument_source"], "user")
        self.assertEqual(updated["file"]["auto_instrument"], "Piano/keys")
        status, updated, _ = self._request(
            f"/library/{self.file_id}/labels", "POST",
            {"dimension": "instrument", "value": "", "clear": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["file"]["instrument"], "Piano/keys")
        status, _payload, _ = self._request(
            f"/library/{self.file_id}/favorite", "POST", {"value": True}
        )
        self.assertEqual(status, 200)
        status, _payload, _ = self._request(
            f"/library/{self.file_id}", "PATCH", {"notes": "Checked in the API test"}
        )
        self.assertEqual(status, 200)
        status, payload, _ = self._request(
            f"/library/{self.file_id}/tags", "POST", {"name": "test-tag"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["tag"]["name"], "test-tag")
        status, details, _ = self._request(f"/library/{self.file_id}")
        self.assertTrue(details["file"]["favorite"])
        self.assertEqual(details["file"]["user_notes"], "Checked in the API test")
        self.assertTrue(any(tag["name"] == "test-tag" for tag in details["tags"]))
        library = self._get_library("q=checked")
        self.assertEqual(library["total"], 1)
        # Track label editing
        track = details["tracks"][0]
        status, updated, _ = self._request(
            f"/library/{self.file_id}/tracks/{track['sequence_index']}/{track['track_index']}/labels",
            "POST", {"dimension": "role", "value": "Pad/sustained harmony"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(any(
            item["role"] == "Pad/sustained harmony" and item["role_source"] == "user"
            for item in updated["tracks"]
        ))

    def test_collections_bulk_and_facets(self) -> None:
        status, payload, _ = self._request("/collections", "POST", {"name": "API picks"})
        self.assertEqual(status, 201)
        collection_id = payload["collection"]["id"]
        status, payload, _ = self._request(
            f"/collections/{collection_id}/files", "POST", {"file_ids": [self.file_id]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["added"], 1)
        status, payload, _ = self._request("/collections")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["name"] == "API picks" and item["count"] == 1 for item in payload["collections"]))
        status, payload, _ = self._request(
            "/library/bulk", "POST",
            {"file_ids": [self.file_id], "action": "label", "dimension": "role", "value": "Arpeggio"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["updated"], 1)
        library = self._get_library("role=Arpeggio")
        self.assertGreaterEqual(library["total"], 1)
        status, facets, _ = self._request("/facets")
        self.assertEqual(status, 200)
        self.assertIn("instruments", facets)

    def test_preview_autoplay_persists(self) -> None:
        status, payload, _ = self._request("/settings")
        self.assertEqual(status, 200)
        self.assertEqual(payload["settings"]["preview_autoplay"], "0")
        status, payload, _ = self._request("/settings", "PATCH", {"preview_autoplay": "1"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["settings"]["preview_autoplay"], "1")
        reopened = Database(self.data / "midivault.sqlite3")
        self.assertEqual(reopened.get_settings()["preview_autoplay"], "1")

    def test_unknown_setting_keys_are_dropped(self) -> None:
        status, payload, _ = self._request("/settings", "PATCH", {"not_a_setting": "x"})
        self.assertEqual(status, 200)
        self.assertNotIn("not_a_setting", payload["settings"])

    def test_scan_settings_and_export(self) -> None:
        status, payload, _ = self._request(
            "/settings", "PATCH", {"scan_intensity": "eco", "parse_workers": "1"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["settings"]["scan_intensity"], "eco")
        export_dir = Path(self.temp.name) / "exports"
        status, payload, _ = self._request(
            "/files/export", "POST",
            {"file_ids": [self.file_id], "destination": str(export_dir)},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["copied"], 1)
        exported = export_dir / "Rhodes Chords.mid"
        self.assertTrue(exported.exists())
        self.assertEqual(exported.read_bytes(), (self.library / "Rhodes Chords.mid").read_bytes())
        # Never overwrite a source across a copy request naming the same file.
        status, payload, _ = self._request(
            "/files/export", "POST",
            {"file_ids": [self.file_id], "destination": str(self.library)},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["results"][0]["ok"])
        self.assertEqual((self.library / "Rhodes Chords.mid").read_bytes(), show())

    def test_backup_and_static_host(self) -> None:
        status, payload, headers = self._request("/db/backup")
        self.assertEqual(status, 200)
        self.assertIsInstance(payload, bytes)
        self.assertGreater(len(payload), 1000)
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"test", response.read())

    def test_rebuild_preserves_user_labels_and_favorites(self) -> None:
        status, _payload, _ = self._request(
            f"/library/{self.file_id}/labels", "POST",
            {"dimension": "role", "value": "Arpeggio"},
        )
        self.assertEqual(status, 200)
        status, _payload, _ = self._request(
            f"/library/{self.file_id}/favorite", "POST", {"value": True}
        )
        self.assertEqual(status, 200)
        status, payload, _ = self._request("/rebuild", "POST", {})
        self.assertEqual(status, 202)
        self.assertIn("preserved", payload["message"])
        deadline = time.time() + 30
        while time.time() < deadline:
            scan_status = self.scanner.get_status()
            if not scan_status["active"]:
                break
            time.sleep(0.1)
        status, details, _ = self._request(f"/library/{self.file_id}")
        self.assertEqual(status, 200)
        self.assertEqual(details["file"]["role"], "Arpeggio")
        self.assertEqual(details["file"]["role_source"], "user")
        self.assertTrue(details["file"]["favorite"])
        self.assertEqual(details["tracks"][0]["auto_instrument"], "Piano/keys")

    def test_api_validation_errors(self) -> None:
        status, payload, _ = self._request("/library/999999")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)
        status, payload, _ = self._request("/files/export", "POST", {"file_ids": [], "destination": ""})
        self.assertEqual(status, 400)
        self.assertIn("error", payload)
        status, payload, _ = self._request("/scan/start", "POST", {"source_ids": [9999]})
        self.assertEqual(status, 409)
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
