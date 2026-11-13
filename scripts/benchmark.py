"""Benchmark scan throughput, memory, and search latency on generated MIDI libraries.

Run from the repository root:

    python scripts/benchmark.py --files 1000 --workers 2

psutil is optional (used for process-tree memory); the application itself does
not depend on it. Results are written to docs/benchmark-results.json.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from midivault.db import Database  # noqa: E402
from midivault.scanner import ScanManager  # noqa: E402
from tests.midi_builder import MidiTrack, build_smf  # noqa: E402

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


def hardware_info() -> dict:
    info = {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "logical_cores": os.cpu_count(),
        "processor": platform.processor(),
        "ram_gb": None,
        "cpu_name": None,
    }
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        info["ram_gb"] = round(status.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                info["cpu_name"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except Exception:
            pass
    try:
        info["node"] = subprocess.check_output(["node", "--version"], text=True).strip()
    except Exception:
        info["node"] = None
    return info


def make_midi(rng: random.Random, index: int, files_per_folder: int) -> bytes:
    """Three musically distinct tracks so parsing/classification is realistic."""
    bpm = rng.choice([84, 90, 96, 100, 108, 118, 120, 124, 128])
    drums = MidiTrack().track_name("Drums").tempo(0, bpm).time_signature(0, 4, 4)
    bass = MidiTrack().track_name("Bass").program(0, rng.choice([32, 33, 34, 38]))
    keys = MidiTrack().track_name("Rhodes Chords").program(0, rng.choice([0, 4, 5, 16]))
    for bar in range(4):
        base = bar * 4 * 480
        for beat in range(4):
            drums.note(base + beat * 480, 36, 20, rng.randint(90, 120))
        for beat in (1, 3):
            drums.note(base + beat * 480, 38, 20, rng.randint(88, 112))
        for step in range(8):
            drums.note(base + step * 240, 42, 20, rng.randint(60, 95))
        bass_notes = [0, 0, 3, 5, 7, 5, 3, 0]
        for step, degree in enumerate(bass_notes):
            bass.note(base + step * 240, 36 + degree + rng.choice([0, 0, 0, 2]), 180, rng.randint(70, 105))
        chords = [(60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62)][bar % 4]
        for pitch in chords:
            keys.note(base, pitch, 1500, rng.randint(55, 80))
    for track in (drums, bass, keys):
        track.end(4 * 4 * 480)
    return build_smf([drums, bass, keys], midi_format=1)


def generate_library(root: Path, count: int, seed: int) -> dict:
    rng = random.Random(seed)
    root.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    started = time.perf_counter()
    folders = max(1, count // 50)
    for index in range(count):
        folder = root / f"folder-{index % folders:03d}"
        folder.mkdir(exist_ok=True)
        data = make_midi(rng, index, 50)
        path = folder / f"generated-{index:05d}.mid"
        path.write_bytes(data)
        total_bytes += len(data)
    elapsed = time.perf_counter() - started
    return {
        "root": str(root),
        "files": count,
        "total_bytes": total_bytes,
        "average_bytes": round(total_bytes / max(1, count), 1),
        "folders": folders,
        "generation_seconds": round(elapsed, 3),
    }


def wait_for_scan(scanner: ScanManager, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = scanner.get_status()
        if not status["active"]:
            return status
        time.sleep(0.1)
    raise TimeoutError("scan did not finish in the benchmark window")


def sample_tree_memory(process: "psutil.Process", stop: threading.Event,
                       samples: list[float]) -> None:
    while not stop.is_set():
        total = 0
        try:
            processes = [process, *process.children(recursive=True)]
            for child in processes:
                try:
                    total += child.memory_info().rss
                except Exception:
                    pass
        except Exception:
            pass
        samples.append(total)
        stop.wait(0.2)


def measure_search(db: Database, iterations: int = 120) -> dict:
    queries = [
        {"label": "free text: bass", "kwargs": {"q": "bass"}},
        {"label": "sound family filter", "kwargs": {"instrument": "Mixed arrangement"}},
        {
            "label": "combined: role + tempo + confidence",
            "kwargs": {"role": "Complete song or multi-part arrangement", "tempo_min": "80", "confidence_min": "0.5"},
        },
        {"label": "folder + density", "kwargs": {"density_min": "1", "bars_min": "4"}},
    ]
    results = []
    for query in queries:
        timings = []
        totals = []
        # Warm one query so FTS caches and connections are established.
        db.query_library(page_size=60, **query["kwargs"])
        for _ in range(iterations):
            started = time.perf_counter()
            result = db.query_library(page_size=60, **query["kwargs"])
            timings.append((time.perf_counter() - started) * 1000)
            totals.append(result["total"])
        timings.sort()
        results.append({
            "query": query["label"],
            "iterations": iterations,
            "p50_ms": round(statistics.median(timings), 3),
            "p95_ms": round(timings[int(len(timings) * 0.95) - 1], 3),
            "max_ms": round(max(timings), 3),
            "average_result_count": round(sum(totals) / len(totals), 1),
        })
    return {"platform": os.name, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--keep", action="store_true", help="Keep generated benchmark data")
    args = parser.parse_args()

    os.environ["SKEER_SCAN_EXECUTOR"] = "process"
    hardware = hardware_info()
    import tempfile as _tempfile

    run_root = Path(_tempfile.mkdtemp(prefix=f"skeer-bench-{args.files}-"))
    library_root = run_root / "library"
    data_dir = run_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating {args.files} MIDI files…")
    library = generate_library(library_root, args.files, args.seed)
    print(f"Generating done in {library['generation_seconds']}s · {library['average_bytes']} bytes/file")

    db_path = data_dir / "benchmark.sqlite3"
    db = Database(db_path)
    source = db.add_source(str(library_root), "Generated benchmark library", optional=False, enabled=True)
    scanner = ScanManager(db, data_dir)
    baseline_rss = 0
    process = (
        psutil.Process(os.getpid())
        if psutil and os.environ.get("SKEER_BENCH_NO_SAMPLER") != "1"
        else None
    )
    samples: list[float] = []
    stop_event = threading.Event()
    sampler = None
    if process:
        baseline_rss = process.memory_info().rss
        sampler = threading.Thread(target=sample_tree_memory, args=(process, stop_event, samples), daemon=True)
        sampler.start()

    print("Scanning…")
    scan_started = time.perf_counter()
    scanner.start(
        source_ids=[source["id"]], mode="full", intensity="balanced",
        workers=args.workers,
    )
    status = wait_for_scan(scanner)
    scan_elapsed = time.perf_counter() - scan_started
    if stop_event:
        stop_event.set()
    if sampler:
        sampler.join(timeout=2)
    peak_rss = max(samples) if samples else (process.memory_info().rss if process else 0)
    after_rss = process.memory_info().rss if process else 0
    print(f"Scan complete in {scan_elapsed:.2f}s · {status['indexed']} indexed · {status['failed']} failed")

    # Incremental pass should skip everything without parsing.
    print("Incremental scan…")
    incremental_started = time.perf_counter()
    scanner.start(source_ids=[source["id"]], mode="incremental", intensity="balanced", workers=args.workers)
    incremental = wait_for_scan(scanner)
    incremental_elapsed = time.perf_counter() - incremental_started

    print("Measuring search…")
    search = measure_search(db)
    with db.connection(write=True) as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db_size = db_path.stat().st_size
    stats = db.stats()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hardware": hardware,
        "library": library,
        "scanner": {
            "workers": args.workers,
            "executor": "process",
            "mode": "full",
            "elapsed_seconds": round(scan_elapsed, 3),
            "files_per_second": round(status["indexed"] / max(scan_elapsed, 0.001), 2),
            "discovered": status["discovered"],
            "indexed": status["indexed"],
            "skipped": status["skipped"],
            "failed": status["failed"],
            "issues": status.get("issues", 0),
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 ** 2), 2),
        },
        "incremental": {
            "elapsed_seconds": round(incremental_elapsed, 3),
            "files_per_second": round(incremental["skipped"] / max(incremental_elapsed, 0.001), 2),
            "skipped": incremental["skipped"],
            "indexed": incremental["indexed"],
            "failed": incremental["failed"],
        },
        "memory": {
            "measurement": "process tree RSS via psutil" if psutil else "current process RSS only (psutil unavailable)",
            "baseline_mb": round(baseline_rss / (1024 ** 2), 1) if baseline_rss else None,
            "peak_mb": round(peak_rss / (1024 ** 2), 1) if peak_rss else None,
            "after_mb": round(after_rss / (1024 ** 2), 1) if after_rss else None,
            "samples": len(samples),
        },
        "search": search,
        "database": {
            "files_indexed": stats["indexed"],
            "notes_indexed": stats["notes"],
            "size_mb": round(db_size / (1024 ** 2), 2),
            "fts_enabled": stats["fts_enabled"],
        },
        "limitations": [
            "Synthetic files with similar structure; real libraries may have larger files and slower scans.",
            "Memory is sampled at 200 ms intervals, so the true peak may be slightly higher.",
            "Process executor startup overhead is included in the wall-clock scan time.",
            "Search timings are direct SQLite calls from Python, excluding HTTP and browser rendering.",
        ],
    }
    output = ROOT / "docs" / "benchmark-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote {output.relative_to(ROOT)}")
    if not args.keep:
        try:
            shutil.rmtree(run_root, ignore_errors=True)
        except OSError:
            pass


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
