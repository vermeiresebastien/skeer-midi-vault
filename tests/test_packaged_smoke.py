"""Smoke-test the packaged Windows executable.

Runs the windowed PyInstaller build as a server, performs a real demo scan with
the frozen process pool, checks the shipped service's HTTP framing and settings
defaults over a keep-alive socket, then asks the embedded desktop service to quit.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from midivault.engine.versions import PARSER_VERSION  # noqa: E402

EXE = Path(os.environ.get(
    "SKEER_PACKAGED_EXE",
    ROOT / "launch" / "SKEER MIDI VAULT" / "SKEER MIDI VAULT.exe",
))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_session: dict[str, object] = {}


def session_token(base: str) -> str:
    """The token the frozen service hands this client, fetched like the page does.

    Every write to the packaged service requires it, so a harness that posts
    without it is rejected for the same reason a foreign page is.
    """
    if not _session:
        _session.update(api(base, "/session"))
    return str(_session.get("token") or "")


def api(base: str, path: str, method: str = "GET", payload: dict | None = None) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if method not in ("GET", "HEAD"):
        headers["X-SKEER-Token"] = session_token(base)
    request = urllib.request.Request(
        f"{base}/api{path}",
        data=body,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _request(method: str, path: str, body: bytes = b"", **headers: str) -> bytes:
    lines = [
        f"{method} {path} HTTP/1.1",
        "Host: 127.0.0.1",
        "Connection: keep-alive",
        f"Content-Length: {len(body)}",
    ]
    lines += [f"{key.replace('_', '-')}: {value}" for key, value in headers.items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


def framing_roundtrip(port: int, first: bytes, second: bytes) -> tuple[int, int, bytes]:
    """Two requests down one connection, parsed straight off the socket.

    This is what the unit suite cannot prove about the deliverable: a refused
    request that leaves its body on the wire makes the service read those bytes
    as the next request line. The second answer is the one that matters.
    """
    with socket.create_connection(("127.0.0.1", port), timeout=6) as sock:
        stream = sock.makefile("rb")

        def answer() -> tuple[int, bytes]:
            line = stream.readline()
            status = int(line.split()[1]) if line else 0
            length = 0
            while True:
                head = stream.readline()
                if head in (b"\r\n", b"\n", b""):
                    break
                key, _, value = head.decode("latin-1").partition(":")
                if key.strip().lower() == "content-length":
                    length = int(value.strip() or 0)
            return status, (stream.read(length) if length else b"")

        sock.sendall(first)
        first_status, _ = answer()
        sock.sendall(second)
        second_status, body = answer()
        return first_status, second_status, body


def main() -> int:
    if not EXE.exists():
        print(f"FAIL: packaged executable missing: {EXE}")
        return 1
    smoke_root = Path(os.environ.get(
        "SKEER_SMOKE_DATA",
        ROOT / "tests" / "packaged-smoke-data",
    ))
    if smoke_root.exists():
        import shutil
        shutil.rmtree(smoke_root, ignore_errors=True)
    smoke_root.mkdir(parents=True)
    data = smoke_root / "data"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            str(EXE), "--server-only", "--no-open",
            "--port", str(port), "--data-dir", str(data),
            "--run-seconds", "180",
        ],
        cwd=str(EXE.parent),
        close_fds=True,
    )
    print("launched", process.pid, base)
    try:
        health = None
        for _ in range(120):
            try:
                health = api(base, "/health")
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.25)
        if not health:
            print("FAIL: packaged service did not become healthy")
            return 2
        print("health", health.get("app"), health.get("version"))

        session = api(base, "/session")
        print("session protected:", session.get("protected"))
        if not session.get("protected"):
            print("FAIL: packaged service accepts writes without a session token")
            return 3
        if not str(session.get("token") or ""):
            print("FAIL: packaged service reports itself protected but hands out no token")
            return 3

        api(base, "/bootstrap")
        source = api(base, "/sources", "POST", {
            "path": str(ROOT / "fixtures" / "demo_library"),
            "label": "Packaged demo",
            "enabled": True,
        })
        source_id = source["source"]["id"]
        sources = api(base, "/sources")
        for item in sources["sources"]:
            if item["id"] != source_id and item["enabled"]:
                api(base, f"/sources/{item['id']}", "PATCH", {"enabled": False})

        api(base, "/scan/start", "POST", {
            "source_ids": [source_id], "mode": "incremental", "intensity": "balanced",
        })
        status = None
        for _ in range(240):
            status = api(base, "/scan/status")
            if not status["active"]:
                break
            time.sleep(0.25)
        print(
            "scan", status["state"],
            "indexed", status["indexed"],
            "failed", status["failed"],
            "issues", status["issues"],
        )
        assert status["indexed"] == 36, status
        assert status["failed"] == 1, status
        assert status["active"] is False

        details = api(base, "/scan/status")
        fatal_issues = [
            issue for issue in details.get("issues_detail", [])
            if issue.get("kind") == "fatal"
        ]
        print("fatal issues", fatal_issues)
        assert not fatal_issues

        # ---- the artifact must behave like the source that was tested.
        bootstrap = api(base, "/bootstrap")
        print("frozen parser generation", bootstrap["versions"]["parser"])
        assert bootstrap["versions"]["parser"] == PARSER_VERSION, bootstrap["versions"]
        assert bootstrap["settings"].get("verify_unchanged") == "1", bootstrap["settings"]
        refused, follow, body = framing_roundtrip(
            port,
            _request("POST", "/api/library/1/favorite", b'{"favorite":true}'),
            _request("GET", "/api/health"),
        )
        print("keep-alive after a tokenless write", refused, follow)
        assert (refused, follow) == (403, 200), (refused, follow, body[:80])
        assert b'"app"' in body, body[:80]
        refused2, follow2, body2 = framing_roundtrip(
            port,
            _request("PATCH", "/api/settings", b"not-json",
                     Content_Type="text/plain", X_SKEER_Token=session_token(base)),
            _request("GET", "/api/session"),
        )
        print("keep-alive after a rejected content type", refused2, follow2)
        assert (refused2, follow2) == (415, 200), (refused2, follow2, body2[:80])
        assert b'"token"' in body2, body2[:80]

        api(base, "/app/quit", "POST", {})
        for _ in range(300):
            if process.poll() is not None:
                break
            time.sleep(0.1)
        code = process.poll()
        print("exit", code)
        assert code == 0, code
        assert not (data / "runtime.json").exists(), "runtime file not cleaned up"
        try:
            import psutil  # type: ignore
            leftovers = [
                item.info
                for item in psutil.process_iter(["pid", "name", "cmdline", "exe"])
                if "SKEER MIDI VAULT.exe" in " ".join(item.info.get("cmdline") or [])
                and "--multiprocessing-fork" in " ".join(item.info.get("cmdline") or [])
            ]
            print("orphan workers", leftovers)
            assert not leftovers, "scan worker descendants survived app exit"
        except ImportError:
            print("psutil not installed; skipped orphan-worker assertion")
        print("PASS packaged smoke test")
        return 0
    finally:
        if process.poll() is None:
            process.kill()
        import shutil
        shutil.rmtree(smoke_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
