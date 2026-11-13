"""Smoke-test the packaged Windows executable.

Runs the windowed PyInstaller build as a server, performs a real demo scan with
the frozen process pool, then asks the embedded desktop service to quit.
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
EXE = Path(os.environ.get(
    "SKEER_PACKAGED_EXE",
    ROOT / "launch" / "SKEER MIDI VAULT" / "SKEER MIDI VAULT.exe",
))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def api(base: str, path: str, method: str = "GET", payload: dict | None = None) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{base}/api{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


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
