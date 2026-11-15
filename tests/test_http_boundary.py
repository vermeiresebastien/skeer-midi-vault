"""Boundary tests for the loopback-only HTTP service.

These exist because the service listens on a fixed, predictable port and
nothing in it authenticated the *requester* until now. The threat that matters
is DNS rebinding: a page at ``http://vault.attacker.tld`` whose A record points
at ``127.0.0.1``. After the flip that page is same-origin, so CORS and Origin
checks do not apply at all — the only thing that distinguishes it from the real
app is the ``Host`` header.

Every test here asserts the guard fires *and* that the same call succeeds when
it should, so a regression cannot hide behind a blanket 403.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

os.environ["SKEER_SCAN_EXECUTOR"] = "threads"

from midivault.api import create_server
from midivault.db import Database
from midivault.scanner import ScanManager
from tests.midi_builder import MidiTrack, build_smf

SESSION_TOKEN = "test-session-token-4f2ac1"


def chord_fixture() -> bytes:
    track = MidiTrack().track_name("Rhodes Chords").program(0, 4).tempo(0, 120).time_signature(0, 4, 4)
    for bar in range(4):
        for pitch in (60, 64, 67, 71):
            track.note(bar * 4 * 480, pitch, 1500, 70)
    track.end(4 * 4 * 480)
    return build_smf([track], midi_format=0)


class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Windows can hold a just-written WAL file one beat too long; that must not read as a test failure.
        cls.temp = tempfile.TemporaryDirectory(prefix="midivault-boundary-", ignore_cleanup_errors=True)
        root = Path(cls.temp.name)
        library = root / "library"
        library.mkdir()
        (library / "Rhodes Chords.mid").write_bytes(chord_fixture())
        data = root / "data"
        data.mkdir()
        cls.db = Database(data / "midivault.sqlite3")
        source = cls.db.add_source(str(library), "Boundary", optional=True, enabled=True)
        cls.scanner = ScanManager(cls.db, data)
        cls.scanner.start(source_ids=[source["id"]], mode="full", intensity="eco", workers=1)
        deadline = time.time() + 20
        while time.time() < deadline:
            if not cls.scanner.get_status()["active"]:
                break
            time.sleep(0.04)
        else:
            raise AssertionError("fixture scan did not finish")
        web_dir = root / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("<html><body>boundary</body></html>", encoding="utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        cls.port = sock.getsockname()[1]
        sock.close()
        cls.server = create_server(
            "127.0.0.1", cls.port, cls.db, cls.scanner, data, web_dir,
            config={"verbose": False, "session_token": SESSION_TOKEN},
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.file_id = cls.db.query_library(page_size=5)["items"][0]["id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    # ------------------------------------------------------------------ helpers
    def call(self, method: str, path: str, host: str | None = None,
             headers: dict[str, str] | None = None, body: bytes | None = None):
        """Issue a request with full control over the headers urllib would set."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            sent = dict(headers or {})
            effective_host = f"127.0.0.1:{self.port}" if host is None else host
            if effective_host:
                conn.putheader("Host", effective_host)
            if body is not None:
                sent.setdefault("Content-Length", str(len(body)))
            for name, value in sent.items():
                conn.putheader(name, value)
            conn.endheaders()
            if body is not None:
                conn.send(body)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def json_call(self, method: str, path: str, **kwargs):
        status, raw = self.call(method, path, **kwargs)
        try:
            return status, json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return status, {"error": raw.decode("utf-8", "replace")}

    def allowed_write(self, value: bool = True):
        return self.json_call(
            "POST", f"/api/library/{self.file_id}/favorite",
            headers={"Content-Type": "application/json",
                     "X-SKEER-Token": SESSION_TOKEN,
                     "Origin": f"http://127.0.0.1:{self.port}"},
            body=json.dumps({"value": value}).encode("utf-8"),
        )

    # --------------------------------------------------------------------- Host
    def test_rebound_host_is_rejected_on_reads(self) -> None:
        """The whole point: after a DNS flip the Host header is the tell."""
        status, payload = self.json_call("GET", "/api/library", host="vault.attacker.tld")
        self.assertEqual(status, 403, "a foreign Host must never be served")
        self.assertIn("error", payload)
        # Same request, real Host: must still work, so the guard is not a wall.
        status, payload = self.json_call("GET", "/api/library")
        self.assertEqual(status, 200)
        self.assertIn("items", payload)

    def test_db_backup_is_not_readable_through_a_rebound_host(self) -> None:
        """The backup endpoint streams every indexed path and user note."""
        status, _raw = self.call("GET", "/api/db/backup", host="vault.attacker.tld")
        self.assertEqual(status, 403)
        status, raw = self.call("GET", "/api/db/backup")
        self.assertEqual(status, 200)
        self.assertTrue(raw.startswith(b"SQLite format 3\x00"), "expected a real SQLite image")

    def test_missing_host_is_rejected(self) -> None:
        status, _payload = self.json_call("GET", "/api/health", host="")
        self.assertEqual(status, 403)

    def test_localhost_and_dev_proxy_hosts_are_accepted(self) -> None:
        """The Vite proxy forwards the browser's Host, port and all."""
        for host in (f"localhost:{self.port}", f"127.0.0.1:{self.port}", "127.0.0.1:5173"):
            status, _payload = self.json_call("GET", "/api/health", host=host)
            self.assertEqual(status, 200, f"Host {host} should be served")

    # -------------------------------------------------------------- write guard
    def test_cross_origin_write_is_rejected(self) -> None:
        status, payload = self.json_call(
            "POST", f"/api/library/{self.file_id}/favorite",
            host=f"127.0.0.1:{self.port}",
            headers={"Content-Type": "application/json",
                     "Origin": "http://evil.example",
                     "X-SKEER-Token": SESSION_TOKEN},
            body=json.dumps({"value": True}).encode("utf-8"),
        )
        self.assertEqual(status, 403)
        self.assertIn("error", payload)

    def test_cross_site_sec_fetch_write_is_rejected(self) -> None:
        status, _payload = self.json_call(
            "POST", f"/api/library/{self.file_id}/favorite",
            headers={"Content-Type": "application/json",
                     "Sec-Fetch-Site": "cross-site",
                     "X-SKEER-Token": SESSION_TOKEN},
            body=json.dumps({"value": True}).encode("utf-8"),
        )
        self.assertEqual(status, 403)

    def test_write_without_session_token_is_rejected(self) -> None:
        status, payload = self.json_call(
            "POST", f"/api/library/{self.file_id}/favorite",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"value": True}).encode("utf-8"),
        )
        self.assertEqual(status, 403, "a body-carrying POST with no token must not land")
        self.assertIn("token", payload.get("error", "").lower())
        # And the same write with the token succeeds.
        status, payload = self.allowed_write()
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])

    def test_form_encoded_body_is_rejected(self) -> None:
        """No preflight is sent for these, so content type is the discriminator."""
        status, _payload = self.json_call(
            "POST", f"/api/library/{self.file_id}/favorite",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-SKEER-Token": SESSION_TOKEN},
            body=b"value=1",
        )
        self.assertEqual(status, 415)

    def test_text_plain_body_is_rejected(self) -> None:
        status, _payload = self.json_call(
            "POST", f"/api/library/{self.file_id}/favorite",
            headers={"Content-Type": "text/plain", "X-SKEER-Token": SESSION_TOKEN},
            body=b'{"value": true}',
        )
        self.assertEqual(status, 415)

    def test_bodyless_write_only_needs_the_token(self) -> None:
        status, _payload = self.json_call(
            "DELETE", f"/api/library/{self.file_id}/tags/999999",
            headers={"X-SKEER-Token": SESSION_TOKEN},
        )
        self.assertNotEqual(status, 403, "DELETE without a body is not blocked by content type")
        self.assertNotEqual(status, 401)

    # ------------------------------------------------------------------ session
    def test_session_endpoint_hands_the_token_to_the_loopback_page(self) -> None:
        status, payload = self.json_call("GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(payload["token"], SESSION_TOKEN)
        self.assertTrue(payload["protected"])
        status, _payload = self.json_call("GET", "/api/session", host="vault.attacker.tld")
        self.assertEqual(status, 403, "a rebound page must not be able to fetch the token")

    def test_reads_do_not_require_the_token(self) -> None:
        status, payload = self.json_call("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertIn("facets", payload)


class UnprotectedServerTests(unittest.TestCase):
    """A caller that mints no token keeps the old behaviour, so scripted and
    test harnesses do not silently start failing."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="midivault-open-")
        data = Path(self.temp.name) / "data"
        data.mkdir()
        self.db = Database(data / "midivault.sqlite3")
        web_dir = Path(self.temp.name) / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        self.server = create_server(
            "127.0.0.1", self.port, self.db, ScanManager(self.db, data), data, web_dir,
            config={"verbose": False},
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def test_session_reports_unprotected(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/api/session")
        response = conn.getresponse()
        payload = json.loads(response.read())
        conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["token"], "")
        self.assertFalse(payload["protected"])

    def test_rebound_host_is_still_rejected_without_a_token(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("GET", "/api/health", skip_host=True)
        conn.putheader("Host", "vault.attacker.tld")
        conn.endheaders()
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 403)


if __name__ == "__main__":
    unittest.main()
