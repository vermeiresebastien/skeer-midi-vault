"""Loopback HTTP API and static bundle server for SKEER MIDI VAULT."""
from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import __version__
from .db import Database
from .engine.taxonomy import INSTRUMENT_CATEGORIES, ROLE_CATEGORIES
from .engine.versions import (
    CLASSIFIER_METHOD,
    CLASSIFIER_RULESET,
    CLASSIFIER_VERSION,
    FINGERPRINT_VERSION,
    PARSER_VERSION,
    SCHEMA_VERSION,
    SUPPORTED_EXTENSIONS,
)
from .platform import discover_drives
from .scanner import ScanError, ScanManager


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
        self.message = message


# The service binds loopback only, but a browser will happily send a request to
# 127.0.0.1 from a page whose DNS record was rebound to it. Checking the ``Host``
# header is the only defence that survives that, because after the flip the
# attacker's page is same-origin and no CORS rule or ``Origin`` check applies.
# Any port is accepted so the Vite dev proxy (which forwards the browser's
# ``Host: 127.0.0.1:5173``) keeps working.
LOOPBACK_HOST_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})
UNSAFE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
TOKEN_HEADER = "X-SKEER-Token"


class AppContext:
    def __init__(self, db: Database, scanner: ScanManager, data_dir: Path,
                 web_dir: Path, config: dict[str, Any]):
        self.db = db
        self.scanner = scanner
        self.data_dir = data_dir
        self.web_dir = web_dir
        self.config = config
        # Empty means the caller opted out of session tokens (tests, scripting).
        # When set, every unsafe method must echo it back in ``TOKEN_HEADER``.
        self.session_token = str(config.get("session_token") or "")
        self.started_at = time.time()


def _bool(value: Any) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on")


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _numbered_backup_name() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"skeer-midi-vault-backup-{stamp}.sqlite3"


class MidiVaultHandler(BaseHTTPRequestHandler):
    server_version = "SkeerMidiVault/1.0"
    protocol_version = "HTTP/1.1"
    context: AppContext

    # --------------------------------------------------------------- HTTP verbs
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch("OPTIONS")

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.context.config.get("verbose"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---------------------------------------------------------------- transport
    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        if not origin:
            return None
        parsed = urlparse(origin)
        if parsed.scheme in ("http", "https") and parsed.hostname in ("127.0.0.1", "localhost"):
            return origin
        return None

    def _host_is_allowed(self) -> bool:
        """True when the request addressed this service by a loopback name.

        A rebinding attack reaches the port with ``Host: attacker.tld``; the
        real app always carries ``127.0.0.1`` or ``localhost``. Port is ignored
        so the Vite dev proxy still works.
        """
        host = self.headers.get("Host", "")
        if not host:
            return False
        # A leading "//" makes urlparse treat the value as a netloc, which
        # handles bracketed IPv6 literals and ports without hand-parsing.
        return urlparse(f"//{host}").hostname in LOOPBACK_HOST_NAMES

    def _check_write_guard(self) -> None:
        """Reject any state-changing request that a remote page could forge."""
        sec_fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sec_fetch_site and sec_fetch_site not in ("same-origin", "same-site", "none"):
            raise ApiError("Cross-site requests are not accepted.", 403)
        origin = self.headers.get("Origin", "")
        if origin and urlparse(origin).hostname not in LOOPBACK_HOST_NAMES:
            raise ApiError("Cross-origin writes are not accepted.", 403)
        token = self.context.session_token
        if token and self.headers.get(TOKEN_HEADER, "") != token:
            raise ApiError("Missing or invalid session token.", 403)

    def _common_headers(self) -> None:
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, Content-Disposition")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self._common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError("Invalid Content-Length")
        if length > 4 * 1024 * 1024:
            raise ApiError("Request body too large", 413)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        # A browser sends a form or a plain-text fetch without a preflight, so a
        # lax content type here is what turns "read the library" into "run any
        # POST". The app always sends application/json.
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ApiError("Request body must be JSON (Content-Type: application/json).", 415)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("Request body must be valid JSON")
        if not isinstance(payload, dict):
            raise ApiError("Request body must be a JSON object")
        return payload

    def _dispatch(self, method: str) -> None:
        if not self._host_is_allowed():
            self.send_json({"error": "This service only answers on its loopback address."}, 403)
            return
        if method == "OPTIONS":
            self._send_empty(HTTPStatus.NO_CONTENT)
            return
        parsed = urlparse(self.path)
        try:
            if method in UNSAFE_METHODS:
                self._check_write_guard()
            if parsed.path.startswith("/api/"):
                self._handle_api(method, parsed.path, parse_qs(parsed.query))
            elif method == "GET":
                self._serve_static(parsed.path)
            else:
                raise ApiError("Only GET is allowed for static files", 405)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except BrokenPipeError:
            pass
        except Exception as exc:  # Return a useful message instead of killing the server.
            traceback.print_exc()
            try:
                self.send_json({"error": f"Internal server error: {type(exc).__name__}: {exc}"}, 500)
            except Exception:
                pass

    # ------------------------------------------------------------------ routing
    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        ctx = self.context
        if not path.startswith("/api/"):
            raise ApiError("Not found", 404)
        route = path[5:].strip("/")
        parts = route.split("/") if route else []
        q = {key: values[0] for key, values in query.items()}

        if method == "GET" and route == "health":
            self.send_json(self._health())
            return
        if method == "GET" and route == "session":
            # Handing out the token over a GET is only safe because the Host
            # check above already rejected any request that arrived under a
            # foreign hostname, which is the rebinding case this defends.
            self.send_json({"token": ctx.session_token, "protected": bool(ctx.session_token)})
            return
        if method == "GET" and route == "bootstrap":
            self.send_json(self._bootstrap())
            return
        if method == "POST" and route == "app/quit":
            quit_callback = ctx.config.get("quit_callback")
            if not callable(quit_callback):
                raise ApiError("The desktop session manager is not available.", 404)
            quit_callback()
            self.send_json({"ok": True})
            return
        if method == "GET" and route == "drives":
            drives = discover_drives()
            sources = ctx.db.sync_drives(drives)
            self.send_json({"drives": drives, "sources": sources})
            return
        if route == "sources":
            if method == "GET":
                self.send_json({"sources": ctx.db.list_sources()})
                return
            if method == "POST":
                payload = self._read_json()
                path_value = (payload.get("path") or "").strip()
                if not path_value:
                    raise ApiError("Folder path is required")
                source = ctx.db.add_source(
                    path_value, payload.get("label"),
                    optional=_bool(payload.get("optional", True)),
                    enabled=_bool(payload.get("enabled", True)),
                )
                self.send_json({"source": source}, 201)
                return
        if parts and parts[0] == "sources" and len(parts) == 2:
            source_id = int(parts[1])
            if method == "PATCH":
                payload = self._read_json()
                fields = {key: payload[key] for key in ("enabled", "optional", "label")
                          if key in payload}
                if "enabled" in fields:
                    fields["enabled"] = 1 if _bool(fields["enabled"]) else 0
                if "optional" in fields:
                    fields["optional"] = 1 if _bool(fields["optional"]) else 0
                source = ctx.db.update_source(source_id, **fields)
                if not source:
                    raise ApiError("Source not found", 404)
                self.send_json({"source": source})
                return
            if method == "DELETE":
                ctx.db.delete_source(source_id)
                self.send_json({"ok": True, "note": "Indexed entries were retained."})
                return
        if route == "excludes":
            if method == "GET":
                self.send_json({"excludes": ctx.db.list_excludes()})
                return
            if method == "POST":
                payload = self._read_json()
                path_value = (payload.get("path") or "").strip()
                if not path_value:
                    raise ApiError("Excluded folder path is required")
                self.send_json({"exclude": ctx.db.add_exclude(path_value, payload.get("note"))}, 201)
                return
        if parts and parts[0] == "excludes" and len(parts) == 2 and method == "DELETE":
            ctx.db.delete_exclude(int(parts[1]))
            self.send_json({"ok": True})
            return
        if route == "scan/options":
            if method == "GET":
                self.send_json({
                    "sources": ctx.db.list_sources(),
                    "excludes": ctx.db.list_excludes(),
                    "settings": ctx.db.get_settings(),
                    "last_scan": ctx.db.latest_scan_run(),
                    "drives": discover_drives(),
                })
                return
        if route == "scan/start" and method == "POST":
            payload = self._read_json()
            raw_ids = payload.get("source_ids")
            source_ids = [int(value) for value in raw_ids] if isinstance(raw_ids, list) else None
            try:
                status = ctx.scanner.start(
                    source_ids=source_ids,
                    mode=payload.get("mode") or ctx.db.get_settings().get("scan_mode", "incremental"),
                    intensity=payload.get("intensity") or ctx.db.get_settings().get("scan_intensity", "balanced"),
                    workers=payload.get("workers"),
                )
            except ScanError as exc:
                raise ApiError(str(exc), 409)
            self.send_json({"scan": status}, 202)
            return
        if route == "scan/status" and method == "GET":
            self.send_json(ctx.scanner.get_status())
            return
        if route in ("scan/pause", "scan/resume", "scan/cancel") and method == "POST":
            action = route.split("/")[-1]
            self.send_json(getattr(ctx.scanner, action)())
            return
        if route == "scan/issues" and method == "GET":
            scan_id = int(q["scan_id"]) if q.get("scan_id") else None
            self.send_json({"issues": ctx.db.list_scan_issues(scan_id, limit=int(q.get("limit", "200")))})
            return
        if route == "library" and method == "GET":
            self.send_json(ctx.db.query_library(**q))
            return
        if route == "library/bulk" and method == "POST":
            payload = self._read_json()
            file_ids = [int(value) for value in payload.get("file_ids") or []][:5000]
            if not file_ids:
                raise ApiError("file_ids is required")
            action = payload.get("action")
            if action == "favorite":
                count = ctx.db.bulk_favorite(file_ids, _bool(payload.get("value", True)))
                self.send_json({"updated": count})
                return
            if action == "label":
                dimension = payload.get("dimension")
                value = payload.get("value")
                if dimension not in ("instrument", "role") or not value:
                    raise ApiError("dimension and value are required")
                if value not in INSTRUMENT_CATEGORIES + ROLE_CATEGORIES:
                    raise ApiError("Unknown classification value")
                count = ctx.db.bulk_file_labels(file_ids, dimension, value)
                self.send_json({"updated": count})
                return
            if action == "collection":
                collection_id = int(payload.get("collection_id") or 0)
                count = ctx.db.add_to_collection(collection_id, file_ids)
                self.send_json({"updated": count})
                return
            if action == "tag":
                tag = (payload.get("tag") or "").strip()
                if not tag:
                    raise ApiError("Tag is required")
                for file_id in file_ids:
                    ctx.db.add_tag(file_id, tag, payload.get("color"))
                self.send_json({"updated": len(file_ids)})
                return
            raise ApiError("Unsupported bulk action")
        if parts and parts[0] == "library" and len(parts) >= 2:
            file_id = int(parts[1])
            if len(parts) == 2 and method == "GET":
                details = ctx.db.get_file_details(file_id)
                if not details:
                    raise ApiError("File not found", 404)
                self.send_json(details)
                return
            if len(parts) == 2 and method == "PATCH":
                payload = self._read_json()
                if "favorite" in payload:
                    ctx.db.set_favorite(file_id, _bool(payload["favorite"]))
                if "notes" in payload:
                    ctx.db.set_user_notes(file_id, str(payload["notes"]))
                self.send_json({"ok": True})
                return
            if len(parts) == 2 and method == "DELETE":
                raise ApiError("MIDI Vault never deletes indexed source files", 405)
            if len(parts) == 3 and parts[2] == "favorite" and method == "POST":
                payload = self._read_json()
                ctx.db.set_favorite(file_id, _bool(payload.get("value", True)))
                self.send_json({"ok": True})
                return
            if len(parts) == 3 and parts[2] == "tags" and method == "POST":
                payload = self._read_json()
                tag = ctx.db.add_tag(file_id, str(payload.get("name") or ""), payload.get("color"))
                self.send_json({"tag": tag}, 201)
                return
            if len(parts) == 4 and parts[2] == "tags" and method == "DELETE":
                ctx.db.remove_tag(file_id, int(parts[3]))
                self.send_json({"ok": True})
                return
            if len(parts) == 3 and parts[2] == "collections" and method == "POST":
                payload = self._read_json()
                count = ctx.db.add_to_collection(int(payload.get("collection_id") or 0), [file_id])
                self.send_json({"added": count})
                return
            if len(parts) == 4 and parts[2] == "collections" and method == "DELETE":
                count = ctx.db.remove_from_collection(int(parts[3]), [file_id])
                self.send_json({"removed": count})
                return
            if len(parts) == 3 and parts[2] == "labels" and method == "POST":
                payload = self._read_json()
                details = ctx.db.set_file_label(
                    file_id, str(payload.get("dimension") or ""),
                    str(payload.get("value") or ""),
                    clear=_bool(payload.get("clear", False)),
                )
                if not details:
                    raise ApiError("File not found", 404)
                self.send_json(details)
                return
            if len(parts) == 4 and parts[2] == "reveal" and method == "POST":
                self._reveal_file(file_id)
                self.send_json({"ok": True})
                return
            if len(parts) == 3 and parts[2] == "raw" and method == "GET":
                self._serve_file(file_id, download=False)
                return
            if len(parts) == 3 and parts[2] == "download" and method == "GET":
                self._serve_file(file_id, download=True)
                return
        if parts and parts[0] == "tracks" and len(parts) == 6:
            # /api/tracks/{file_id}/{sequence}/{track}/{dimension}? kept as a
            # compatibility convenience; the library route is canonical.
            raise ApiError("Use /api/library/{id}/tracks/... route", 404)
        if parts and parts[0] == "library" and len(parts) == 6:
            # /api/library/{file_id}/tracks/{sequence}/{track}/labels
            if parts[2] == "tracks" and parts[5] == "labels" and method == "POST":
                file_id = int(parts[1])
                sequence_index = int(parts[3])
                track_index = int(parts[4])
                payload = self._read_json()
                details = ctx.db.set_track_label(
                    file_id, sequence_index, track_index,
                    str(payload.get("dimension") or ""),
                    str(payload.get("value") or ""),
                    clear=_bool(payload.get("clear", False)),
                )
                if not details:
                    raise ApiError("Track not found", 404)
                self.send_json(details)
                return
        if route == "files/export" and method == "POST":
            payload = self._read_json()
            self.send_json(self._export_files(payload))
            return
        if route == "facets" and method == "GET":
            self.send_json(ctx.db.facets())
            return
        if route == "folders" and method == "GET":
            self.send_json(ctx.db.list_folders())
            return
        if route == "stats" and method == "GET":
            self.send_json(ctx.db.stats())
            return
        if route == "collections":
            if method == "GET":
                self.send_json({"collections": ctx.db.list_collections()})
                return
            if method == "POST":
                payload = self._read_json()
                self.send_json({"collection": ctx.db.create_collection(
                    str(payload.get("name") or ""), str(payload.get("description") or "")
                )}, 201)
                return
        if parts and parts[0] == "collections" and len(parts) >= 2:
            collection_id = int(parts[1])
            if len(parts) == 2 and method == "PATCH":
                payload = self._read_json()
                collection = ctx.db.update_collection(
                    collection_id, payload.get("name"), payload.get("description")
                )
                if not collection:
                    raise ApiError("Collection not found", 404)
                self.send_json({"collection": collection})
                return
            if len(parts) == 2 and method == "DELETE":
                ctx.db.delete_collection(collection_id)
                self.send_json({"ok": True})
                return
            if len(parts) == 3 and parts[2] == "files":
                payload = self._read_json()
                file_ids = [int(value) for value in payload.get("file_ids") or []]
                if method == "POST":
                    self.send_json({"added": ctx.db.add_to_collection(collection_id, file_ids)})
                    return
                if method == "DELETE":
                    self.send_json({"removed": ctx.db.remove_from_collection(collection_id, file_ids)})
                    return
        if route == "tags" and method == "GET":
            self.send_json({"tags": ctx.db.list_tags()})
            return
        if route == "duplicates" and method == "GET":
            kind = q.get("kind", "exact")
            if kind not in ("exact", "similar"):
                raise ApiError("kind must be exact or similar")
            self.send_json(ctx.db.duplicate_groups(kind))
            return
        if route == "settings":
            if method == "GET":
                self.send_json({"settings": ctx.db.get_settings()})
                return
            if method == "PATCH":
                self.send_json({"settings": ctx.db.update_settings(self._read_json())})
                return
        if route == "db/health" and method == "GET":
            self.send_json(ctx.db.db_health())
            return
        if route == "db/backup" and method == "GET":
            self._serve_backup()
            return
        if route == "rebuild" and method == "POST":
            payload = self._read_json() if self.headers.get("Content-Length") else {}
            try:
                ctx.db.invalidate_index()
                status = ctx.scanner.start(
                    source_ids=payload.get("source_ids"),
                    mode="full",
                    intensity=payload.get("intensity")
                    or ctx.db.get_settings().get("scan_intensity", "balanced"),
                )
            except ScanError as exc:
                raise ApiError(str(exc), 409)
            self.send_json({"scan": status, "message": "Index cache invalidated; full rescan started. User data was preserved."}, 202)
            return
        if route == "maintenance/clear-issues" and method == "POST":
            ctx.db.clear_scan_issues()
            self.send_json({"ok": True})
            return
        raise ApiError("API route not found", 404)

    # ------------------------------------------------------------------ payloads
    def _versions(self) -> dict[str, Any]:
        ctx = self.context
        return {
            "parser": PARSER_VERSION,
            "classifier": CLASSIFIER_VERSION,
            "schema": getattr(ctx.db, "schema_version", SCHEMA_VERSION),
            "schema_supported": SCHEMA_VERSION,
            "fingerprint": FINGERPRINT_VERSION,
            "classifier_method": CLASSIFIER_METHOD,
            "ruleset": CLASSIFIER_RULESET,
        }

    def _health(self) -> dict[str, Any]:
        ctx = self.context
        return {
            "ok": True,
            "app": "SKEER MIDI VAULT",
            "version": __version__,
            "uptime_seconds": round(time.time() - ctx.started_at, 1),
            "privacy": "local-only; no MIDI file, path or library content leaves this machine",
            "versions": self._versions(),
            "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
            "supported_formats": [0, 1, 2],
            "db": ctx.db.db_health(),
        }

    def _bootstrap(self) -> dict[str, Any]:
        ctx = self.context
        drives = discover_drives()
        sources = ctx.db.sync_drives(drives)
        music_dir = Path.home() / "Music"
        default_export = (music_dir if music_dir.exists() else Path.home() / "Documents") / "SKEER MIDI Exports"
        return {
            "default_export_dir": str(default_export),
            "home_dir": str(Path.home()),
            "app": {
                "name": "SKEER MIDI VAULT",
                "version": __version__,
                "privacy": "Local only. No uploads, telemetry or cloud processing.",
            },
            "desktop": {
                "mode": bool(ctx.config.get("desktop_mode")),
                "can_quit": callable(ctx.config.get("quit_callback")),
            },
            "versions": self._versions(),
            "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
            "sources": sources,
            "drives": drives,
            "facets": ctx.db.facets(),
            "stats": ctx.db.stats(),
            "scan": ctx.scanner.get_status(),
            "settings": ctx.db.get_settings(),
            "excludes": ctx.db.list_excludes(),
            "collections": ctx.db.list_collections(),
            "tags": ctx.db.list_tags(),
            "db": {
                "path": ctx.db.db_path,
                "fts_enabled": ctx.db.fts_enabled,
                "size_bytes": ctx.db.path.stat().st_size if ctx.db.path.exists() else 0,
                "schema_version": ctx.db.schema_version,
                "fingerprint_version": FINGERPRINT_VERSION,
                # Similarity only compares same-generation vectors, so the
                # interface can say how much of the index it cannot yet judge.
                "fingerprint_coverage": ctx.db.fingerprint_coverage(),
                "last_migration": ctx.db.last_migration,
            },
        }

    # ---------------------------------------------------------------- file serving
    def _serve_file(self, file_id: int, download: bool) -> None:
        ctx = self.context
        path = ctx.db.raw_file_path(file_id)
        if not path:
            raise ApiError("File not found", 404)
        if not os.path.isfile(path):
            raise ApiError("Original source file is unavailable", 410)
        try:
            size = os.path.getsize(path)
            start = 0
            end = size - 1
            range_header = self.headers.get("Range")
            status = 200
            if range_header:
                match = re.match(r"bytes=(\d*)-(\d*)", range_header)
                if match:
                    if match.group(1):
                        start = int(match.group(1))
                        if match.group(2):
                            end = int(match.group(2))
                    elif match.group(2):
                        start = max(0, size - int(match.group(2)))
                    end = min(end, size - 1)
                    if start > end or start >= size:
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self._common_headers()
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206
            length = end - start + 1
            filename = os.path.basename(path)
            content_type = mimetypes.guess_type(path)[0] or "audio/midi"
            self.send_response(status)
            self._common_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            disposition = "attachment" if download else "inline"
            ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
            self.send_header(
                "Content-Disposition",
                f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}',
            )
            self.end_headers()
            with open(path, "rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except PermissionError:
            raise ApiError("Original source file is not readable", 403)
        except OSError as exc:
            raise ApiError(f"Could not read source file: {exc}", 500)

    def _serve_backup(self) -> None:
        ctx = self.context
        backup_dir = ctx.data_dir / "backups"
        backup_path = backup_dir / _numbered_backup_name()
        try:
            ctx.db.backup_to(backup_path)
            data = backup_path.read_bytes()
        finally:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass
        self.send_response(200)
        self._common_headers()
        self.send_header("Content-Type", "application/vnd.sqlite3")
        self.send_header("Content-Disposition", f'attachment; filename="{backup_path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _reveal_file(self, file_id: int) -> None:
        path = self.context.db.raw_file_path(file_id)
        if not path:
            raise ApiError("File not found", 404)
        if not os.path.exists(path):
            raise ApiError("Original source file is unavailable", 410)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def _export_files(self, payload: dict[str, Any]) -> dict[str, Any]:
        ctx = self.context
        file_ids = [int(value) for value in payload.get("file_ids") or []][:500]
        destination = str(payload.get("destination") or "").strip()
        if not file_ids:
            raise ApiError("file_ids is required")
        if not destination:
            raise ApiError("A destination folder is required")
        destination_path = Path(os.path.abspath(os.path.expanduser(destination)))
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ApiError(f"Could not create destination folder: {exc}")
        if not destination_path.is_dir():
            raise ApiError("Destination is not a folder")
        results = []
        for file_id in file_ids:
            source = ctx.db.raw_file_path(file_id)
            if not source:
                results.append({"file_id": file_id, "ok": False, "error": "File not found"})
                continue
            if not os.path.isfile(source):
                results.append({"file_id": file_id, "ok": False, "error": "Source unavailable"})
                continue
            source_abs = os.path.normcase(os.path.abspath(source))
            target = destination_path / Path(source).name
            if os.path.normcase(os.path.abspath(target)) == source_abs:
                results.append({
                    "file_id": file_id, "ok": False,
                    "error": "Destination is the original file; source was not overwritten",
                })
                continue
            counter = 1
            while True:
                if not target.exists():
                    break
                if os.path.normcase(os.path.abspath(target)) == source_abs:
                    break
                target = destination_path / f"{Path(source).stem} ({counter}){Path(source).suffix}"
                counter += 1
            try:
                if os.path.normcase(os.path.abspath(target)) == source_abs:
                    results.append({"file_id": file_id, "ok": False,
                                    "error": "Source and destination are identical"})
                    continue
                shutil.copy2(source, target)
                results.append({
                    "file_id": file_id, "ok": True, "destination": str(target),
                    "filename": target.name,
                })
            except OSError as exc:
                results.append({"file_id": file_id, "ok": False, "error": str(exc)})
        return {
            "destination": str(destination_path),
            "copied": sum(1 for item in results if item["ok"]),
            "failed": sum(1 for item in results if not item["ok"]),
            "results": results,
        }

    # -------------------------------------------------------------------- static
    def _serve_static(self, url_path: str) -> None:
        ctx = self.context
        web_dir = ctx.web_dir.resolve()
        if not web_dir.exists():
            raise ApiError(
                "Web build not found. Run `npm install && npm run build` in web/, "
                "or use the Vite dev server.",
                503,
            )
        requested = unquote(url_path).split("?", 1)[0]
        if requested in ("", "/"):
            requested = "/index.html"
        normalised = posixpath.normpath(requested).lstrip("/")
        candidate = (web_dir / normalised).resolve()
        if web_dir not in candidate.parents and candidate != web_dir:
            raise ApiError("Not found", 404)
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists() or not candidate.is_file():
            # SPA fallback for non-asset paths.
            if "." not in Path(normalised).name:
                candidate = web_dir / "index.html"
            else:
                raise ApiError("Not found", 404)
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(200)
        self._common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if candidate.name == "index.html" else "public, max-age=3600")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


class MidiVaultServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(host: str, port: int, db: Database, scanner: ScanManager,
                  data_dir: Path, web_dir: Path,
                  config: dict[str, Any] | None = None) -> MidiVaultServer:
    context = AppContext(db, scanner, data_dir, web_dir, config or {})
    handler = type("BoundMidiVaultHandler", (MidiVaultHandler,), {"context": context})
    server = MidiVaultServer((host, port), handler)
    return server
