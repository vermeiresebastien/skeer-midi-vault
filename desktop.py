"""Standalone SKEER MIDI VAULT desktop launcher.

The packaged build contains the Python service, the compiled interface and all
runtime assets. It starts the loopback service, opens the interface in the
system browser and stays available from a small tray icon so users do not need
Python, Node.js or a terminal.

Run from source:
    python desktop.py

Packaged build:
    SKEER MIDI VAULT.exe
"""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from midivault.api import create_server
from midivault.db import Database
from midivault.platform import discover_drives
from midivault.scanner import ScanManager
from midivault.server import _default_data_dir

APP_NAME = "SKEER MIDI VAULT"
VERSION = "1.0.0"
MUTEX_NAME = "Local\\SkeerMidiVaultDesktopV1"
PREFERRED_PORT = 8737


def _bundle_root() -> Path:
    """Directory that holds bundled runtime data."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _web_dir() -> Path:
    return _bundle_root() / "web" / "dist"


def _icon_path() -> Path:
    return _web_dir() / "brand" / "skeer-favicon.png"


def _log_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "midivault-desktop.log"


def _message_box(message: str, title: str = APP_NAME, error: bool = True) -> None:
    if os.name != "nt":
        print(f"{title}: {message}", file=sys.stderr)
        return
    try:
        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)


def _windows_mutex() -> Any | None:
    """Return a held named mutex, or None when this is the first instance."""
    if os.name != "nt":
        return None
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        already_exists = ctypes.windll.kernel32.GetLastError() == 183
        return None if already_exists else handle
    except Exception:
        return None


def _read_runtime(data_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((data_dir / "runtime.json").read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("url"):
            return payload
    except (OSError, ValueError):
        pass
    return None


def _write_runtime(data_dir: Path, url: str, port: int) -> None:
    try:
        (data_dir / "runtime.json").write_text(
            json.dumps({"url": url, "port": port, "pid": os.getpid(), "version": VERSION}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _remove_runtime(data_dir: Path) -> None:
    try:
        (data_dir / "runtime.json").unlink()
    except OSError:
        pass


def _health(url: str, timeout: float = 1.2) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("app") == APP_NAME
    except Exception:
        return False


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url, new=1, autoraise=True)
    except Exception:
        _message_box(f"Open this address in your browser:\n\n{url}", error=False)


def _show_existing_instance(data_dir: Path, open_browser: bool) -> None:
    runtime = _read_runtime(data_dir)
    if runtime and _health(str(runtime["url"])):
        if open_browser:
            _open_browser(str(runtime["url"]))
        return
    # The mutex is held but the runtime file is missing or the service is still
    # booting. Wait briefly for the other instance instead of starting a duplicate.
    for _ in range(20):
        time.sleep(0.25)
        runtime = _read_runtime(data_dir)
        if runtime and _health(str(runtime["url"])):
            if open_browser:
                _open_browser(str(runtime["url"]))
            return
    _message_box(
        "SKEER MIDI VAULT is already running, but its local service is not responding.\n\n"
        "Open it from the tray icon, or quit the existing process and try again.",
    )


def _find_free_requested_port(port: int) -> int:
    if port == 0:
        return 0
    for candidate in range(port, port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                return candidate
            except OSError:
                continue
    return 0


def _load_icon_image() -> Any:
    from PIL import Image

    path = _icon_path()
    if path.exists():
        return Image.open(path).convert("RGBA")
    image = Image.new("RGBA", (64, 64), (255, 101, 0, 255))
    return image


def run(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).expanduser().resolve()
    log_path = _log_path(data_dir)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logger = logging.getLogger("skeer.desktop")

    mutex = _windows_mutex()
    if os.name == "nt" and mutex is None:
        _show_existing_instance(data_dir, open_browser=not args.no_open)
        return 0

    logger.info("Starting %s %s", APP_NAME, VERSION)
    quit_event = threading.Event()
    server_holder: dict[str, Any] = {}
    icon_holder: dict[str, Any] = {}

    def request_quit() -> None:
        quit_event.set()

    try:
        drives = discover_drives()
        db = Database(data_dir / "midivault.sqlite3")
        scanner = ScanManager(db, data_dir)
        try:
            db.sync_drives(drives)
        except Exception:
            logger.exception("Drive discovery failed; continuing without drive sync")

        requested_port = _find_free_requested_port(int(args.port))
        server = None
        last_error: Exception | None = None
        for candidate in (requested_port, 0):
            try:
                server = create_server(
                    "127.0.0.1",
                    candidate,
                    db,
                    scanner,
                    data_dir,
                    _web_dir(),
                    config={
                        "verbose": False,
                        "desktop_mode": True,
                        "quit_callback": request_quit,
                    },
                )
                break
            except OSError as exc:
                last_error = exc
                if candidate == 0:
                    raise
        if server is None:
            raise last_error or RuntimeError("The local service could not start")
        server_holder["server"] = server
        actual_port = int(server.server_address[1])
        url = f"http://127.0.0.1:{actual_port}/"
        _write_runtime(data_dir, url, actual_port)

        thread = threading.Thread(
            target=server.serve_forever,
            name="midivault-http",
            kwargs={"poll_interval": 0.25},
            daemon=True,
        )
        thread.start()

        for _ in range(80):
            if _health(url):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("The local service started but did not answer its health check")

        logger.info("Service listening at %s; data at %s", url, data_dir)
        if sys.stdout is not None:
            try:
                print(f"SKEER MIDI VAULT\n  App: {url}\n  Data: {data_dir}")
            except OSError:
                pass

        if not args.no_open and not args.server_only:
            threading.Timer(0.8, lambda: _open_browser(url)).start()

        def shutdown_service() -> None:
            quit_event.set()
            try:
                status = scanner.get_status()
                if status.get("active"):
                    scanner.cancel()
                if not scanner.wait_idle(20.0):
                    logger.warning("Scan worker pool did not finish within the shutdown window")
            except Exception:
                logger.exception("Could not wait for the scan worker pool")
            try:
                server.shutdown()
            except Exception:
                logger.exception("HTTP server shutdown failed")
            try:
                if thread.is_alive():
                    thread.join(timeout=3.0)
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
            logger.info("Local service stopped")

        def quit_watcher() -> None:
            quit_event.wait()
            shutdown_service()
            icon = icon_holder.get("icon")
            if icon is not None:
                try:
                    icon.stop()
                except Exception:
                    logger.exception("Could not stop the tray icon")
            _remove_runtime(data_dir)
            logger.info("Quit complete")
            logging.shutdown()
            # Frozen multiprocessing/HTTP helper threads can keep the Python
            # interpreter alive after the service is stopped. This is an
            # explicit user-requested application exit, so terminate cleanly at
            # the process level instead of leaving a hidden zombie in Task Manager.
            os._exit(0)

        threading.Thread(target=quit_watcher, name="midivault-quit", daemon=True).start()

        if args.run_seconds > 0:
            threading.Timer(args.run_seconds, request_quit).start()

        if args.server_only:
            # Used by packaging smoke tests and advanced users.
            try:
                while not quit_event.wait(0.5):
                    pass
            except KeyboardInterrupt:
                request_quit()
        else:
            try:
                import pystray

                def open_app(_icon: Any | None = None, _item: Any | None = None) -> None:
                    _open_browser(url)

                def open_data(_icon: Any | None = None, _item: Any | None = None) -> None:
                    try:
                        os.startfile(str(data_dir))  # type: ignore[attr-defined]
                    except Exception:
                        logger.exception("Could not open data folder")

                def quit_from_tray(_icon: Any | None = None, _item: Any | None = None) -> None:
                    request_quit()

                menu = pystray.Menu(
                    pystray.MenuItem("Open SKEER MIDI VAULT", open_app, default=True),
                    pystray.MenuItem("Open data folder", open_data),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Quit", quit_from_tray),
                )
                icon = pystray.Icon("skeer-midi-vault", _load_icon_image(), APP_NAME, menu)
                icon_holder["icon"] = icon
                logger.info("Tray icon starting")
                icon.run()
                # icon.run returns when quit_from_tray stops it.
                request_quit()
            except Exception:
                logger.exception("Tray icon unavailable; keeping the local service alive")
                _message_box(
                    "The SKEER MIDI VAULT tray icon could not start.\n\n"
                    "The library is still open in your browser. Use "
                    "Settings > Data & privacy > Quit SKEER MIDI VAULT to close it.",
                    error=False,
                )
                try:
                    while not quit_event.wait(0.5):
                        pass
                except KeyboardInterrupt:
                    request_quit()

        # Give the watcher a moment to shut down before the process exits.
        quit_event.set()
        deadline = time.time() + 5
        while time.time() < deadline and "server" in server_holder:
            server = server_holder.get("server")
            if server is None:
                break
            try:
                server.server_close()
            except Exception:
                pass
            break
        return 0
    except Exception as exc:
        logger.error("Startup failed: %s\n%s", exc, traceback.format_exc())
        _message_box(
            f"SKEER MIDI VAULT could not start.\n\n{type(exc).__name__}: {exc}\n\n"
            f"Log file:\n{log_path}",
        )
        return 1
    finally:
        _remove_runtime(data_dir)
        if mutex and os.name == "nt":
            try:
                ctypes.windll.kernel32.ReleaseMutex(mutex)
                ctypes.windll.kernel32.CloseHandle(mutex)
            except Exception:
                pass
        logger.info("Desktop launcher exiting")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} desktop launcher")
    parser.add_argument("--port", type=int, default=PREFERRED_PORT, help="Preferred loopback port")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("SKEER_MIDIVAULT_DATA") or str(_default_data_dir()),
        help="Where the SQLite index and runtime files live",
    )
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    parser.add_argument("--server-only", action="store_true", help="Run the local service only")
    parser.add_argument("--run-seconds", type=float, default=0, help="Quit automatically after N seconds (tests)")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
