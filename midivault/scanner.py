"""Background file discovery and parse workers.

The UI never waits for a scan. A traversal thread feeds a bounded process pool
(thread pool in test mode), and results are committed in small transactions.
Pause/resume/cancel are cooperative. Source files are opened read-only and are
never modified.
"""
from __future__ import annotations

import concurrent.futures
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import platform as winplatform
from .db import Database
from .engine.versions import (
    CLASSIFIER_VERSION,
    FINGERPRINT_VERSION,
    PARSER_VERSION,
    SUPPORTED_EXTENSIONS,
)
from .pipeline import parse_and_classify_file

INTENSITY = {
    "eco": {"workers": 1, "inflight": 2},
    "balanced": {"workers": 2, "inflight": 6},
    "turbo": {"workers": 4, "inflight": 12},
}


class ScanError(RuntimeError):
    pass


class ScanManager:
    def __init__(self, db: Database, data_dir: str | os.PathLike):
        self.db = db
        self.data_dir = Path(data_dir)
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._paused = False
        self._cancel = False
        self._status: dict[str, Any] = {
            "active": False, "state": "idle", "scan_id": None,
            "message": "No scan has been run yet.", "discovered": 0,
            "indexed": 0, "skipped": 0, "failed": 0, "issues": 0,
            "directory_errors": 0, "current_path": "", "completion": 0,
            "elapsed_seconds": 0, "started_at": None, "ended_at": None,
            "intensity": "balanced", "workers": 2, "mode": "incremental",
            "queue_depth": 0, "files_per_second": 0.0, "skipped_cloud": 0,
            "skipped_links": 0, "sources_completed": 0, "total_sources": 0,
        }

    # ------------------------------------------------------------------ status
    def get_status(self) -> dict[str, Any]:
        with self._lock:
            status = dict(self._status)
            active = bool(self._thread and self._thread.is_alive())
            status["active"] = active and status.get("state") in ("running", "paused", "cancelling")
            if active:
                started = status.get("_started_monotonic")
                if started:
                    status["elapsed_seconds"] = round(time.monotonic() - started, 1)
                processed = status.get("indexed", 0) + status.get("skipped", 0) + status.get("failed", 0)
                if status["elapsed_seconds"] > 0:
                    status["files_per_second"] = round(processed / status["elapsed_seconds"], 2)
            for key in list(status):
                if key.startswith("_"):
                    status.pop(key)
        latest = self.db.latest_scan_run()
        if latest:
            if not status.get("scan_id"):
                status.update({
                    "scan_id": latest["id"], "state": latest["state"],
                    "mode": latest["mode"], "started_at": latest["started_at"],
                    "ended_at": latest["ended_at"], "message": latest["message"],
                    "discovered": latest["discovered"], "indexed": latest["indexed"],
                    "skipped": latest["skipped"], "failed": latest["failed"],
                    "current_path": latest["current_path"], "completion": latest["completion"],
                })
            status["last_scan"] = latest
        else:
            status["last_scan"] = None
        status["issues_detail"] = self.db.list_scan_issues(
            status.get("scan_id") if status.get("scan_id") else None, limit=40
        )
        return status

    def _persist(self, *, force: bool = True) -> None:
        with self._lock:
            status = dict(self._status)
            scan_id = status.get("scan_id")
            if not scan_id:
                return
        self.db.update_scan_run(
            scan_id=scan_id,
            state=status["state"],
            discovered=status["discovered"],
            indexed=status["indexed"],
            skipped=status["skipped"],
            failed=status["failed"],
            current_path=status.get("current_path", "")[:1500],
            completion=status.get("completion", 0),
            message=status.get("message", "")[:1500],
            ended_at=status.get("ended_at"),
        )

    # ------------------------------------------------------------------ control
    def start(self, source_ids: Iterable[int] | None = None,
              mode: str = "incremental", intensity: str = "balanced",
              workers: int | None = None) -> dict[str, Any]:
        previous = self._thread
        if previous and previous.is_alive() and previous is not threading.current_thread():
            with self._lock:
                previous_state = self._status.get("state")
            # A completed scan can still be shutting its worker pool down while
            # status already says active=false. Let that cleanup finish instead
            # of overwriting the shared status from two scan threads.
            if previous_state not in ("running", "paused", "cancelling"):
                previous.join(timeout=15.0)
        with self._lock:
            if self._thread and self._thread.is_alive() and self._status.get("state") in ("running", "paused"):
                raise ScanError("A scan is already running")
            if self._thread and self._thread.is_alive():
                raise ScanError("The previous scan is still shutting down. Try again in a moment.")
            all_sources = self.db.list_sources(with_counts=False)
            sources = self.db.enabled_sources()
            if source_ids is not None:
                wanted = {int(value) for value in source_ids}
                sources = [source for source in all_sources if source["id"] in wanted]
            if not sources:
                raise ScanError("No source selected. Select at least one drive or folder.")
            if mode not in ("incremental", "full"):
                raise ScanError("mode must be incremental or full")
            intensity = intensity if intensity in INTENSITY else "balanced"
            tuning = INTENSITY[intensity]
            worker_count = max(1, min(8, workers or int(self.db.get_settings().get("parse_workers") or tuning["workers"])))
            run_id = self.db.create_scan_run(
                mode, [source["id"] for source in sources],
                {"intensity": intensity, "workers": worker_count,
                 "parser_version": PARSER_VERSION, "classifier_version": CLASSIFIER_VERSION,
                 "fingerprint_version": FINGERPRINT_VERSION},
            )
            now = time.monotonic()
            self._paused = False
            self._cancel = False
            self._stop.clear()
            self._status = {
                "active": True, "state": "running", "scan_id": run_id,
                "message": "Scanning local sources…", "discovered": 0,
                "indexed": 0, "skipped": 0, "failed": 0, "issues": 0,
                "directory_errors": 0, "current_path": "", "completion": 0,
                "elapsed_seconds": 0, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "ended_at": None, "intensity": intensity, "workers": worker_count,
                "mode": mode, "queue_depth": 0, "files_per_second": 0.0,
                "skipped_cloud": 0, "skipped_links": 0, "sources_completed": 0,
                "total_sources": len(sources), "_started_monotonic": now,
            }
            self._thread = threading.Thread(
                target=self._run, name="midivault-scan",
                args=(run_id, sources, mode, intensity, worker_count),
                daemon=True,
            )
            self._thread.start()
        return self.get_status()

    def wait_idle(self, timeout: float = 15.0) -> bool:
        """Wait for the scan thread and its worker pool to finish shutting down."""
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.1, timeout))
        return not (thread and thread.is_alive())

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive() and self._status.get("state") == "running":
                self._paused = True
                self._status["state"] = "paused"
                self._status["message"] = "Scan paused"
        self._persist()
        return self.get_status()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive() and self._paused:
                self._paused = False
                self._status["state"] = "running"
                self._status["message"] = "Scan resumed"
        self._persist()
        return self.get_status()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._cancel = True
                self._paused = False
                self._status["state"] = "cancelling"
                self._status["message"] = "Cancelling scan…"
            elif self._status.get("state") in ("running", "paused"):
                self._status["state"] = "cancelled"
                self._status["message"] = "Scan cancelled"
        self._persist()
        return self.get_status()

    # ------------------------------------------------------------------- runner
    def _set_progress(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)

    def _checkpoint(self) -> bool:
        """Return False when cancelled; block while paused."""
        while self._paused and not self._cancel:
            time.sleep(0.12)
        return not self._cancel

    def _run(self, run_id: int, sources: list[dict[str, Any]], mode: str,
             intensity: str, worker_count: int) -> None:
        started = time.monotonic()
        tuning = INTENSITY.get(intensity, INTENSITY["balanced"])
        inflight_limit = max(worker_count, tuning["inflight"])
        executor_kind = os.environ.get("SKEER_SCAN_EXECUTOR", "process").lower()
        executor: concurrent.futures.Executor | None = None
        futures: dict[concurrent.futures.Future, dict[str, Any]] = {}
        processed = 0
        last_persist = 0.0
        self._source_states = {}
        traversal_done = False
        issue_count = 0
        pending_successes: list[tuple[dict[str, Any], int | None]] = []
        pending_failures: list[dict[str, Any]] = []
        pending_skips: list[str] = []
        last_flush = time.monotonic()

        def flush_pending() -> None:
            """Commit a batch of completed work in one short transaction."""
            nonlocal last_flush
            if not pending_successes and not pending_failures and not pending_skips:
                return
            successes = list(pending_successes)
            failures = list(pending_failures)
            skips = list(pending_skips)
            pending_successes.clear()
            pending_failures.clear()
            pending_skips.clear()
            try:
                summary = self.db.apply_scan_batch(successes, failures, skips, run_id)
                with self._lock:
                    self._status["indexed"] += summary["indexed"]
                    self._status["failed"] += summary["failed"]
                    self._status["skipped"] += summary["skipped"]
                last_flush = time.monotonic()
            except Exception as exc:
                # Batch transaction failure is rare. Preserve the files as
                # durable failures rather than silently dropping their work.
                message = f"Batch index write failed: {type(exc).__name__}: {exc}"
                for payload, source_id in successes:
                    try:
                        self.db.record_file_failure(
                            payload.get("path", "?"), source_id, message,
                            size=payload.get("size"), mtime_ns=payload.get("mtime_ns"),
                            content_hash=payload.get("content_hash"), scan_id=run_id,
                        )
                    except Exception:
                        pass
                for failure in failures:
                    try:
                        self.db.record_file_failure(
                            failure["path"], failure.get("source_id"), failure["error"], scan_id=run_id,
                        )
                    except Exception:
                        pass
                self.db.add_scan_issue(run_id, "database", "", message)
                with self._lock:
                    self._status["failed"] += len(successes) + len(failures)
                    self._status["skipped"] += len(skips)
                last_flush = time.monotonic()

        try:
            if executor_kind == "threads" or os.environ.get("SKEER_SCAN_THREADS") == "1":
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=worker_count)
            else:
                executor = concurrent.futures.ProcessPoolExecutor(max_workers=worker_count)
            excludes = self.db.excluded_paths()
            generator = self._walk_sources(sources, excludes, run_id)
            self._set_progress(message="Scanning local sources…", current_path="")
            while True:
                if (pending_successes or pending_failures or pending_skips) and (
                    self._paused
                    or self._cancel
                    or time.monotonic() - last_flush >= 0.65
                    or len(pending_successes) + len(pending_failures) + len(pending_skips) >= 24
                ):
                    flush_pending()
                if not self._checkpoint():
                    break
                # Fill the bounded queue with discovered files.
                while not traversal_done and len(futures) < inflight_limit:
                    try:
                        file_info = next(generator)
                    except StopIteration:
                        traversal_done = True
                        break
                    except Exception as exc:  # a traversal failure must not kill the scan
                        issue_count += 1
                        self.db.add_scan_issue(run_id, "traversal", "", f"{type(exc).__name__}: {exc}")
                        self._set_progress(message=f"Traversal issue: {exc}", issues=issue_count)
                        traversal_done = True
                        break
                    if not self._checkpoint():
                        break
                    with self._lock:
                        self._status["discovered"] += 1
                    file_info["source_id"] = self._source_for_path(file_info["path"], sources)
                    record = self.db.get_scan_file_record(file_info["path"])
                    untouched = (
                        mode == "incremental"
                        and record is not None
                        and record.get("scan_state") in ("indexed", "missing")
                        and record.get("size") == file_info["size"]
                        and record.get("mtime_ns") == file_info["mtime_ns"]
                        and record.get("parser_version") == PARSER_VERSION
                        and record.get("classifier_version") == CLASSIFIER_VERSION
                        # A legacy fingerprint is not comparable, so the file is
                        # re-indexed once rather than silently skipped forever.
                        and record.get("fingerprint_version") == FINGERPRINT_VERSION
                    )
                    if untouched:
                        pending_skips.append(file_info["path"])
                        if len(pending_skips) >= 24:
                            flush_pending()
                        processed += 1
                        if processed % 50 == 0:
                            self._update_completion(traversal_done, len(futures),
                                                    self._source_states, len(sources))
                        continue
                    job = {
                        "path": file_info["path"],
                        "filename": os.path.basename(file_info["path"]),
                        "relative_folder": file_info.get("relative_folder", ""),
                    }
                    try:
                        future = executor.submit(parse_and_classify_file, job)
                        futures[future] = file_info
                    except Exception as exc:
                        pending_failures.append({
                            "path": file_info["path"],
                            "source_id": file_info.get("source_id"),
                            "error": f"Worker submission failed: {type(exc).__name__}: {exc}",
                        })
                        processed += 1
                if futures:
                    done, _ = concurrent.futures.wait(
                        futures, timeout=0.18,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    for future in done:
                        file_info = futures.pop(future)
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = {"ok": False, "path": file_info["path"],
                                      "error": f"Worker failed: {type(exc).__name__}: {exc}"}
                        if result.get("ok"):
                            pending_successes.append((result, file_info.get("source_id")))
                        else:
                            error = result.get("error", "Unknown parse error")
                            pending_failures.append({
                                "path": file_info["path"],
                                "source_id": file_info.get("source_id"),
                                "error": error,
                                "size": result.get("size"),
                                "mtime_ns": result.get("mtime_ns"),
                                "content_hash": result.get("content_hash"),
                            })
                        processed += 1
                        with self._lock:
                            self._status["queue_depth"] = len(futures)
                        if processed % 40 == 0:
                            self._update_completion(traversal_done, len(futures),
                                                    self._source_states, len(sources))
                        if len(pending_successes) + len(pending_failures) + len(pending_skips) >= 24:
                            flush_pending()
                elif traversal_done:
                    break
                else:
                    time.sleep(0.08)
                now = time.monotonic()
                if now - last_persist >= 0.65:
                    flush_pending()
                    self._update_completion(traversal_done, len(futures), self._source_states, len(sources))
                    self._persist()
                    last_persist = now
                with self._lock:
                    elapsed = time.monotonic() - started
                    current = self._status.get("current_path")
                    self._status["elapsed_seconds"] = round(elapsed, 1)
                    self._status["queue_depth"] = len(futures)
                    self._status["issues"] = issue_count
                    processed_done = (self._status["indexed"] + self._status["skipped"]
                                      + self._status["failed"])
                    if current:
                        self._status["files_per_second"] = round(processed_done / max(elapsed, 0.1), 2)
            # end main loop
            flush_pending()

            if self._cancel:
                self._set_progress(state="cancelled", message="Scan cancelled. Indexed files were kept.",
                                   active=False, ended_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                self._persist()
                self._set_progress(state="cancelled", active=False)
                return

            self._set_progress(message="Finalising index…", completion=92)
            self._persist()
            # Mark missing only for sources whose traversal completed without
            # permission gaps, and only if the whole scan completed.
            scanned_states = dict(self._source_states)
            for source in sources:
                state = scanned_states.get(source["id"])
                if not state or not state.get("completed"):
                    continue
                self.db.mark_missing_not_seen(
                    run_id, source["id"], skip_prefixes=state.get("unreadable", [])
                )
            self._set_progress(message="Finding duplicates…", completion=96)
            self._persist()
            duplicate_counts = self.db.finalise_duplicate_groups()
            elapsed = time.monotonic() - started
            with self._lock:
                final = dict(self._status)
                final.update({
                    "state": "completed", "active": False, "completion": 100,
                    "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "message": (
                        f"Scan complete · {final['indexed']} indexed, "
                        f"{final['skipped']} unchanged, {final['failed']} failed · "
                        f"{duplicate_counts['exact_groups']} exact duplicate group(s)"
                    ),
                    "elapsed_seconds": round(elapsed, 1),
                    "files_per_second": round(
                        (final['indexed'] + final['skipped'] + final['failed'])
                        / max(elapsed, 0.1), 2
                    ),
                    "duplicates": duplicate_counts,
                    "issues": issue_count,
                })
                self._status = final
            self.db.update_scan_run(
                scan_id=run_id, state="completed", ended_at=final["ended_at"],
                completion=100, discovered=final["discovered"], indexed=final["indexed"],
                skipped=final["skipped"], failed=final["failed"],
                current_path=final.get("current_path", ""), message=final["message"],
            )
        except Exception as exc:
            traceback.print_exc()
            self.db.add_scan_issue(run_id, "fatal", "", f"{type(exc).__name__}: {exc}")
            with self._lock:
                self._status.update({
                    "state": "error", "active": False,
                    "message": f"Scan failed: {type(exc).__name__}: {exc}",
                    "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
            self._persist()
        finally:
            if executor is not None:
                try:
                    executor.shutdown(wait=not self._cancel, cancel_futures=True)
                except Exception:
                    pass
            with self._lock:
                if self._status.get("state") in ("running", "paused", "cancelling"):
                    self._status["state"] = "cancelled"
                    self._status["active"] = False
                self._cancel = False
                self._paused = False

    def _source_for_path(self, path: str, sources: list[dict[str, Any]]) -> int | None:
        best = None
        best_len = -1
        normalised = os.path.normcase(os.path.abspath(path))
        for source in sources:
            root = os.path.normcase(os.path.abspath(source["path"]))
            if normalised == root or normalised.startswith(root + os.sep):
                if len(root) > best_len:
                    best = source["id"]
                    best_len = len(root)
        return best

    def _update_completion(self, traversal_done: bool, queue: int,
                           source_states: dict[int, dict[str, Any]],
                           total_sources: int) -> None:
        with self._lock:
            if traversal_done:
                processed = self._status["indexed"] + self._status["skipped"] + self._status["failed"]
                discovered = max(processed + queue, self._status["discovered"])
                completion = min(90.0, 55.0 + 35.0 * (processed / max(1, discovered)))
            else:
                completed = sum(1 for state in source_states.values() if state.get("completed"))
                completion = min(55.0, 5.0 + 50.0 * (completed / max(1, total_sources)))
            self._status["completion"] = round(completion, 1)
            self._status["sources_completed"] = sum(
                1 for state in source_states.values() if state.get("completed")
            )

    # ------------------------------------------------------------------ walker
    def _walk_sources(self, sources: list[dict[str, Any]], excludes: list[str],
                      run_id: int) -> Iterator[dict[str, Any]]:
        """Yield discovered MIDI files safely, one source at a time."""
        visited_dirs: set[Any] = set()
        for source in sources:
            root = source["path"]
            source_id = source["id"]
            state: dict[str, Any] = {"completed": False, "unreadable": []}
            self._source_states[source_id] = state
            root_available = os.path.isdir(root)
            if not root_available:
                self.db.set_source_available(source_id, False)
                self.db.add_scan_issue(
                    run_id, "source", root,
                    "Source is unavailable. Previously indexed entries were kept.",
                )
                self._set_progress(current_path=root)
                continue
            if winplatform.is_protected(root):
                self.db.add_scan_issue(run_id, "protected", root,
                                       "Protected system source skipped")
                continue
            self.db.set_source_available(source_id, True)
            stack = [root]
            source_completed = True
            try:
                while stack:
                    if self._cancel:
                        source_completed = False
                        break
                    directory = stack.pop()
                    self._set_progress(current_path=directory)
                    try:
                        with os.scandir(directory) as entries:
                            subdirs: list[str] = []
                            for entry in entries:
                                if self._cancel:
                                    break
                                try:
                                    if winplatform.is_link_or_junction(entry):
                                        with self._lock:
                                            self._status["skipped_links"] += 1
                                        continue
                                    if entry.is_dir(follow_symlinks=False):
                                        path = entry.path
                                        if winplatform.is_protected(path):
                                            continue
                                        if winplatform.is_excluded(path, excludes):
                                            continue
                                        try:
                                            stat = entry.stat(follow_symlinks=False)
                                            if winplatform.is_cloud_placeholder(stat):
                                                with self._lock:
                                                    self._status["skipped_cloud"] += 1
                                                continue
                                            key = winplatform.safe_dir_key(path)
                                            if key in visited_dirs:
                                                continue
                                            visited_dirs.add(key)
                                        except OSError as exc:
                                            state["unreadable"].append(path)
                                            self.db.add_scan_issue(run_id, "directory", path, str(exc))
                                            with self._lock:
                                                self._status["directory_errors"] += 1
                                            continue
                                        subdirs.append(path)
                                    elif entry.is_file(follow_symlinks=False):
                                        extension = os.path.splitext(entry.name)[1].lower()
                                        if extension not in SUPPORTED_EXTENSIONS:
                                            continue
                                        stat = entry.stat(follow_symlinks=False)
                                        if winplatform.is_cloud_placeholder(stat):
                                            with self._lock:
                                                self._status["skipped_cloud"] += 1
                                            continue
                                        relative = os.path.relpath(
                                            os.path.dirname(entry.path), root
                                        )
                                        if relative == ".":
                                            relative = ""
                                        yield {
                                            "path": entry.path,
                                            "size": int(stat.st_size),
                                            "mtime_ns": int(
                                                getattr(stat, "st_mtime_ns",
                                                        int(stat.st_mtime * 1e9))
                                            ),
                                            "relative_folder": relative,
                                        }
                                except (PermissionError, OSError) as exc:
                                    state["unreadable"].append(directory)
                                    self.db.add_scan_issue(run_id, "directory", directory, str(exc))
                                    with self._lock:
                                        self._status["directory_errors"] += 1
                            stack.extend(reversed(subdirs))
                    except (PermissionError, FileNotFoundError, OSError) as exc:
                        state["unreadable"].append(directory)
                        self.db.add_scan_issue(run_id, "directory", directory, str(exc))
                        with self._lock:
                            self._status["directory_errors"] += 1
            finally:
                state["completed"] = source_completed and not self._cancel
                self._source_states[source_id] = state
                if state["completed"]:
                    self._set_progress(message=f"Finished scanning {source.get('label') or root}")
                else:
                    self._set_progress(message=f"Stopped while scanning {root}")

    # Set by each scan run; only touched by the scan thread.
    _source_states: dict[int, dict[str, Any]] = {}
