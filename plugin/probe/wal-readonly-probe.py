"""Decide, on evidence, how a VST3 reader may open the MIDI VAULT index.

The plugin must not write the index. SQLite's read-only connection has a known
corner in WAL mode: a reader that finds an un-checkpointed -wal with no -shm
beside it cannot initialise the shared-memory file, because initialising it is a
write. Which states actually fail is what separates "vendor sqlite3 and open the
live index" from "have the app export a sidecar", so this measures it instead of
arguing about it.

Every state is built from scratch in this workspace. The user's real index is
only ever opened read-only, and only while no writer is running.

Usage:  python plugin/probe/wal-readonly-probe.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_ROOT = Path(__file__).resolve().parent / "tmp"
RESULTS: list[dict[str, object]] = []


def record(state: str, mode: str, ok: bool, detail: str) -> None:
    RESULTS.append({"state": state, "open": mode, "ok": ok, "detail": detail})
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {mode:<28} {detail}", flush=True)


def sidecar_files(db: Path) -> str:
    parts = []
    for suffix in ("-wal", "-shm"):
        peer = db.with_name(db.name + suffix)
        parts.append(f"{suffix}={peer.stat().st_size}" if peer.exists() else f"{suffix}=absent")
    return " ".join(parts)


def open_attempt(db: Path, mode: str, query: str = "SELECT count(*) FROM files",
                 probe_query: str | None = None):
    """Try one connection mode against one database state.

    Returns (ok, detail). An exception is a result, not a crash: the whole point
    is to find out which combinations refuse. The optional probe_query runs on a
    *second connection of the same mode*, because opening read-write to check
    freshness would checkpoint the WAL and destroy the state being measured.
    """
    def connect():
        if mode == "readonly":
            uri = f"file:{db.as_posix()}?mode=ro"
            return sqlite3.connect(uri, uri=True, timeout=2.0)
        if mode == "readonly_immutable":
            uri = f"file:{db.as_posix()}?mode=ro&immutable=1"
            return sqlite3.connect(uri, uri=True, timeout=2.0)
        if mode == "query_only":
            con = sqlite3.connect(db, timeout=2.0)
            con.execute("PRAGMA query_only=ON")
            return con
        raise AssertionError(f"unknown mode {mode}")

    try:
        con = connect()
    except sqlite3.Error as exc:
        return False, f"open refused: {exc}"
    try:
        count = con.execute(query).fetchone()[0]
        journal = con.execute("PRAGMA journal_mode").fetchone()[0]
        detail = f"read {count} files, journal={journal}, {sidecar_files(db)}"
        if probe_query is not None:
            second = connect()
            try:
                detail += f" | fresh connection sees probe_query -> {second.execute(probe_query).fetchone()[0]}"
            except sqlite3.Error as exc:
                detail += f" | probe_query failed: {exc}"
            finally:
                second.close()
        return True, detail
    except sqlite3.Error as exc:
        return False, f"opened but query failed: {exc}"
    finally:
        con.close()


def build_wal_db(db: Path, rows: int) -> None:
    """Create a real WAL database using the app's own schema."""
    sys.path.insert(0, str(ROOT))
    from midivault.db import Database

    Database(db)
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    for index in range(rows):
        con.execute(
            "INSERT OR REPLACE INTO files(path, filename, size) VALUES(?,?,?)",
            (f"D:/lib/probe-{index}.mid", f"probe-{index}.mid", 1024 + index),
        )
    con.commit()
    con.close()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def api(base: str, path: str, method: str = "GET", payload: dict | None = None,
        token: str = "") -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token and method not in ("GET", "HEAD"):
        headers["X-SKEER-Token"] = token
    request = urllib.request.Request(f"{base}{path}", data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def state_clean_exit(workspace: Path) -> Path:
    """Writer opened it, committed, closed cleanly -- the idle-machine case."""
    db = workspace / "clean" / "midivault.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    build_wal_db(db, 12)
    return db


def state_wal_without_shm(workspace: Path, tag: str) -> Path:
    """Uncommitted-to-main -wal with no -shm: the read-only corner case.

    A child writes and exits without closing, which leaves the write-ahead log
    behind, then the -shm is removed to reproduce the state a fresh machine or a
    read-only folder can actually be in. Each mode gets its own freshly built
    state, because a connection that succeeds may checkpoint the log and clean
    the very condition under test.
    """
    db = workspace / f"dirty-{tag}" / "midivault.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    build_wal_db(db, 8)
    child = r"""
import sqlite3, sys, os
con = sqlite3.connect(sys.argv[1])
con.execute("PRAGMA journal_mode=WAL")
con.execute("INSERT OR REPLACE INTO files(path, filename, size) VALUES('D:/lib/late.mid','late.mid',9999)")
con.commit()
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", child, str(db)], check=True)
    db.with_name(db.name + "-shm").unlink(missing_ok=True)
    return db


def state_live_scan(workspace: Path) -> tuple[Path, subprocess.Popen, str]:
    """The app mid-scan: real HTTP service, real process pool, real writer."""
    data_dir = workspace / "live"
    data_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    log = (workspace / "live-service.log").open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "midivault.server", "--host", "127.0.0.1", "--port", str(port),
         "--data-dir", str(data_dir), "--no-open"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, "SKEER_MIDIVAULT_DATA": str(data_dir)},
    )
    base = f"http://127.0.0.1:{port}/api"
    deadline = time.time() + 20
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("service exited during startup; see live-service.log")
        try:
            api(base, "/session")
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.2)
    else:
        raise RuntimeError("service never answered /session")
    token = str(api(base, "/session").get("token") or "")
    api(base, "/bootstrap")
    source = api(base, "/sources", "POST", {
        "path": str(ROOT / "fixtures" / "demo_library"),
        "label": "Probe library", "enabled": True,
    }, token=token)
    api(base, "/scan/start", "POST", {
        "source_ids": [source["source"]["id"]], "mode": "full", "intensity": "balanced",
    }, token=token)
    return data_dir / "midivault.sqlite3", process, base


def main() -> int:
    if PROBE_ROOT.exists():
        shutil.rmtree(PROBE_ROOT, ignore_errors=True)
    PROBE_ROOT.mkdir(parents=True, exist_ok=True)

    print("STATE 1 -- writer closed cleanly (no -wal, no -shm)", flush=True)
    db = state_clean_exit(PROBE_ROOT)
    print(f"  files=12 {sidecar_files(db)}", flush=True)
    for mode in ("readonly", "query_only"):
        ok, detail = open_attempt(db, mode)
        record("clean-exit", mode, ok, detail)

    print("STATE 2 -- un-checkpointed -wal, -shm removed (the corner case)", flush=True)
    for mode in ("readonly", "readonly_immutable", "query_only"):
        db = state_wal_without_shm(PROBE_ROOT, mode)
        print(f"  rebuilt for {mode}: {sidecar_files(db)}", flush=True)
        ok, detail = open_attempt(
            db, mode,
            probe_query="SELECT count(*) FROM files WHERE filename='late.mid'",
        )
        record("wal-without-shm", mode, ok, detail)

    print("STATE 3 -- the real service mid-scan (writer alive, -shm present)", flush=True)
    db, service, base = state_live_scan(PROBE_ROOT)
    try:
        for mode in ("readonly", "query_only"):
            ok, detail = open_attempt(db, mode)
            record("during-scan", mode, ok, detail)
        for _ in range(120):
            status = api(base, "/scan/status")
            if not status["active"]:
                break
            time.sleep(0.25)
        print(f"  scan state={status['state']} indexed={status['indexed']} "
              f"{sidecar_files(db)}", flush=True)
        for mode in ("readonly", "query_only"):
            ok, detail = open_attempt(db, mode)
            record("live-after-scan", mode, ok, detail)
    finally:
        try:
            api(base, "/app/quit", "POST", {}, token=str(_session_token(base)))
        except Exception:
            pass
        for _ in range(120):
            if service.poll() is not None:
                break
            time.sleep(0.1)
        if service.poll() is None:
            service.kill()

    print("STATE 4 -- the user's own index, read-only, no writer running", flush=True)
    real = Path(os.environ.get("LOCALAPPDATA", "")) / "Skeer" / "MIDI Vault" / "midivault.sqlite3"
    if real.exists():
        print(f"  size={real.stat().st_size:,} bytes {sidecar_files(real)}", flush=True)
        ok, detail = open_attempt(real, "readonly",
                                 "SELECT count(*) FROM files WHERE indexed_at IS NOT NULL")
        record("user-real-index", "readonly", ok, detail)
    else:
        print("  (no real index on this machine; skipped)", flush=True)

    print("", flush=True)
    print(json.dumps(RESULTS, indent=1), flush=True)
    failures = [r for r in RESULTS if not r["ok"]]
    print(f"VERDICT: {len(RESULTS) - len(failures)}/{len(RESULTS)} attempts succeeded, "
          f"{len(failures)} refused", flush=True)
    return 0


def _session_token(base: str) -> str:
    return str(api(base, "/session").get("token") or "")


if __name__ == "__main__":
    sys.exit(main())
