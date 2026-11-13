"""Entry point for the local SKEER MIDI VAULT service."""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .api import create_server
from .db import Database
from .platform import discover_drives
from .scanner import ScanManager


ROOT = Path(__file__).resolve().parents[1]


def _default_data_dir() -> Path:
    """Keep the local index on the user's fast application-data drive.

    The project folder may live on a slower archive or mechanical drive. A
    SQLite WAL is write-heavy during a scan, so the standard per-user app-data
    location is used by default. ``--data-dir`` or ``SKEER_MIDIVAULT_DATA`` can
    override it for portable or test installations.
    """
    configured = os.environ.get("SKEER_MIDIVAULT_DATA")
    if configured:
        return Path(configured)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Skeer" / "MIDI Vault"
    return Path.home() / ".local" / "share" / "skeer-midi-vault"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SKEER MIDI VAULT local service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (loopback only by default)")
    parser.add_argument("--port", type=int, default=8737, help="Local HTTP port")
    parser.add_argument("--data-dir", default=str(_default_data_dir()), help="Where the SQLite index lives")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Open the application in the default browser")
    parser.add_argument("--no-open", dest="open_browser", action="store_false")
    parser.set_defaults(open_browser=False)
    parser.add_argument("--verbose", action="store_true", help="Log HTTP requests")
    args = parser.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("Refusing to bind MIDI Vault outside loopback. The library is private and local-only.", file=sys.stderr)
        return 2

    data_dir = Path(args.data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(data_dir / "midivault.sqlite3")
    scanner = ScanManager(db, data_dir)
    try:
        drives = discover_drives()
        if drives:
            db.sync_drives(drives)
    except Exception:
        # Drive discovery is optional; the library remains usable.
        pass
    web_dir = ROOT / "web" / "dist"
    try:
        server = create_server(
            args.host, args.port, db, scanner, data_dir, web_dir,
            config={"verbose": args.verbose},
        )
    except OSError as exc:
        print(f"Could not start MIDI Vault on {args.host}:{args.port}: {exc}", file=sys.stderr)
        print("Close the other process or launch with --port <number>.", file=sys.stderr)
        return 2
    url = f"http://{args.host}:{args.port}/"
    print("SKEER MIDI VAULT")
    print(f"  App:       {url}")
    print(f"  Data:      {db.db_path}")
    print(f"  Web build: {web_dir}")
    print("  Privacy:   local-only; source files are read, never modified.")
    print("  Press Ctrl+C to stop.")
    if args.open_browser:
        def _open() -> None:
            time.sleep(0.7)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping MIDI Vault…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
