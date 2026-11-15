"""Background parse → analyse → classify worker function.

This module is imported by scanner worker processes. It must not open SQLite,
touch the UI, or modify source files. It returns a fully-serialisable payload.
"""
from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Any

from .engine.analytics import analyze
from .engine.classifier import classify
from .engine.smf_parser import MidiParseError, parse_smf
from .engine.versions import (
    CLASSIFIER_METHOD,
    CLASSIFIER_VERSION,
    FINGERPRINT_VERSION,
    MAX_FILE_BYTES,
    PARSER_VERSION,
)
from .hashing import sha256_bytes


def _fingerprint(parse_result, analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Compact musical fingerprint used for *similarity*, never identity.

    ``fv`` stamps the generation of the vector. Any change to the components or
    their scaling must bump ``FINGERPRINT_VERSION``; comparing across
    generations is meaningless and is refused downstream.
    """
    primary_index = analysis.get("primary_sequence_index", 0)
    sequence = next(
        (item for item in parse_result.sequences if item.index == primary_index),
        parse_result.sequences[0] if parse_result.sequences else None,
    )
    if not sequence:
        return None
    notes = [note for track in sequence.tracks for note in track.notes]
    if not notes:
        return None
    pc = [0.0] * 12
    onset = [0.0] * 16
    pitch_total = 0.0
    weight_total = 0.0
    bar_beats = sequence.time_signatures[0].beats_per_bar if sequence.time_signatures else 4.0
    for note in notes:
        weight = min(4.0, max(0.1, note.end_beat - note.start_beat))
        pc[note.pitch % 12] += weight
        pitch_total += note.pitch * weight
        weight_total += weight
        if sequence.timing_type == "metrical":
            unit = note.start_beat
        else:
            unit = note.start_seconds * 2.0
        step = int(round((unit % max(0.25, bar_beats)) * 4)) % 16
        onset[step] += 1.0
    pc_sum = sum(pc) or 1.0
    onset_sum = sum(onset) or 1.0
    return {
        "fv": FINGERPRINT_VERSION,
        "pc": [round(value / pc_sum, 6) for value in pc],
        "on": [round(value / onset_sum, 6) for value in onset],
        "pitch_mean": round(pitch_total / weight_total, 3) if weight_total else None,
        "density": analysis["file"].get("note_density"),
        "duration": analysis["file"].get("duration_seconds"),
        "tempo": analysis["file"]["tempo"].get("initial_bpm"),
    }


def _search_fields(filename: str, path: str, analysis: dict[str, Any],
                   classification: dict[str, Any]) -> dict[str, str]:
    file_info = analysis["file"]
    track_names: list[str] = []
    for track in analysis["tracks"]:
        for value in (track.get("name"), track.get("instrument_name")):
            if value and value not in track_names:
                track_names.append(value)
    embedded = [item.get("text", "") for item in file_info.get("embedded_text", [])]
    embedded.extend(track_names)
    style_tags = classification["file"].get("style_tags") or []
    labels = [
        classification["file"].get("instrument", ""),
        classification["file"].get("role", ""),
        *[track.get("instrument", "") for track in classification.get("tracks", [])],
        *[track.get("role", "") for track in classification.get("tracks", [])],
    ]
    return {
        "filename": filename,
        "path": path,
        "track_names": " ".join(track_names),
        "tags": " ".join(style_tags),
        "notes": "",
        "embedded_text": " ".join(str(item) for item in embedded),
        "auto_labels": " ".join(sorted(set(str(item) for item in labels if item))),
    }


def parse_and_classify_file(job: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point: read, hash, parse, analyze and classify one file."""
    path = job["path"]
    filename = job.get("filename") or os.path.basename(path)
    relative_folder = job.get("relative_folder") or ""
    started = time.perf_counter()
    try:
        try:
            stat = os.stat(path)
        except OSError as exc:
            return {"ok": False, "path": path, "error": f"Cannot access file: {exc}", "code": "unreadable"}
        if stat.st_size > MAX_FILE_BYTES:
            return {
                "ok": False,
                "path": path,
                "error": f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB safety limit",
                "code": "file_too_large",
            }
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            return {"ok": False, "path": path, "error": f"Cannot read file: {exc}", "code": "unreadable"}
        content_hash = sha256_bytes(data)
        try:
            parse_result = parse_smf(data)
        except MidiParseError as exc:
            return {
                "ok": False,
                "path": path,
                "error": f"{exc} [{exc.code}]",
                "code": exc.code,
                "size": stat.st_size,
                "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)),
                "content_hash": content_hash,
            }
        analysis = analyze(parse_result, filename, relative_folder)
        classification = classify(parse_result, analysis, filename, relative_folder)
        preview = parse_result.preview_dict()
        file_info = analysis["file"]
        file_class = classification["file"]
        tracks = []
        analysis_tracks = {
            (track["sequence_index"], track["track_index"]): track
            for track in analysis["tracks"]
        }
        classification_tracks = {
            (track["sequence_index"], track["track_index"]): track
            for track in classification["tracks"]
        }
        for sequence in parse_result.sequences:
            for track in sequence.tracks:
                if not track.notes:
                    continue
                track_analysis = analysis_tracks.get((sequence.index, track.track_index), {})
                track_class = classification_tracks.get((sequence.index, track.track_index), {})
                tracks.append({
                    "sequence_index": sequence.index,
                    "track_index": track.track_index,
                    "chunk_index": track.chunk_index,
                    "channel": track.channel,
                    "name": track.name,
                    "program": track.program,
                    "programs": sorted(set(track.programs)),
                    "bank_msb": track.bank_msb,
                    "bank_lsb": track.bank_lsb,
                    "note_count": len(track.notes),
                    "pitch_min": track.pitch_min,
                    "pitch_max": track.pitch_max,
                    "sustained_notes": track.sustained_notes,
                    "assumed_durations": track.assumed_durations,
                    "controller_counts": {str(k): v for k, v in track.controller_counts.items()},
                    "auto_instrument": track_class.get("instrument", "Unknown"),
                    "auto_instrument_confidence": float(track_class.get("instrument_confidence", 0.0)),
                    "auto_instrument_evidence": track_class.get("instrument_evidence", []),
                    "auto_instrument_alternatives": track_class.get("instrument_alternatives", []),
                    "auto_role": track_class.get("role", "Unknown"),
                    "auto_role_confidence": float(track_class.get("role_confidence", 0.0)),
                    "auto_role_evidence": track_class.get("role_evidence", []),
                    "auto_role_alternatives": track_class.get("role_alternatives", []),
                    "style_tags": track_class.get("feel_tags", []),
                    "uncertain": bool(track_class.get("uncertain", True)),
                    "conflicts": track_class.get("conflicts", []),
                    "source_text": track_analysis.get("source_text", ""),
                    "analysis": {
                        "note_count": track_analysis.get("note_count", len(track.notes)),
                        "pitch_min": track.pitch_min,
                        "pitch_max": track.pitch_max,
                        "pitch_min_name": track_analysis.get("pitch_min_name"),
                        "pitch_max_name": track_analysis.get("pitch_max_name"),
                        "monophonic_ratio": track_analysis.get("monophonic_ratio"),
                        "polyphony_max": track_analysis.get("polyphony_max"),
                        "note_density": track_analysis.get("note_density"),
                        "program_names": track_analysis.get("program_names", []),
                        "bar_span": track_analysis.get("bar_span"),
                    },
                })
        cache_payload = {
            "preview": preview,
            "analysis": analysis,
            "classification": classification,
            "parser_version": PARSER_VERSION,
            "classifier_version": CLASSIFIER_VERSION,
            "fingerprint_version": FINGERPRINT_VERSION,
        }
        cache_blob = gzip.compress(
            json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            compresslevel=6,
        )
        file_warnings = list(dict.fromkeys(file_info.get("warnings", [])))
        fingerprint = _fingerprint(parse_result, analysis)
        tempo = file_info["tempo"]
        time_signature = file_info["time_signature"]
        key = file_info["key"]
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))
        return {
            "ok": True,
            "path": path,
            "filename": filename,
            "size": int(stat.st_size),
            "mtime_ns": int(mtime_ns),
            "content_hash": content_hash,
            "parser_version": PARSER_VERSION,
            "classifier_version": CLASSIFIER_VERSION,
            "format": parse_result.format,
            "declared_tracks": parse_result.declared_track_count,
            "actual_tracks": parse_result.actual_track_count,
            "sequence_count": len(parse_result.sequences),
            "division": parse_result.division,
            "timing_type": parse_result.timing_type,
            "duration_seconds": file_info["duration_seconds"],
            "duration_beats": file_info["duration_beats"],
            "bars": file_info["bars"],
            "ticks_per_quarter": file_info["ticks_per_quarter"],
            "tempo_bpm": tempo["initial_bpm"],
            "tempo_source": tempo["source"],
            "tempo_min_bpm": tempo["min_bpm"],
            "tempo_max_bpm": tempo["max_bpm"],
            "tempo_change_count": tempo["change_count"],
            "time_sig": time_signature["initial"],
            "time_sig_source": time_signature["source"],
            "time_sig_change_count": time_signature["change_count"],
            "key_name": key["label"],
            "key_source": key["source"],
            "key_confidence": key["confidence"],
            "key_embedded": key["embedded"],
            "key_mode": (key["label"].split(" ")[-1] if key.get("label") else None),
            "note_count": file_info["note_count"],
            "track_count": file_info["track_count"],
            "channel_count": file_info["channel_count"],
            "program_count": len(file_info["programs"]),
            "pitch_min": file_info["pitch_min"],
            "pitch_max": file_info["pitch_max"],
            "velocity_min": file_info["velocity_min"],
            "velocity_max": file_info["velocity_max"],
            "velocity_mean": file_info["velocity_mean"],
            "note_density": file_info["note_density"],
            "polyphony_max": file_info["polyphony_max"],
            "polyphony_mean": file_info["polyphony_mean"],
            "auto_instrument": file_class["instrument"],
            "auto_instrument_confidence": file_class["instrument_confidence"],
            "auto_role": file_class["role"],
            "auto_role_confidence": file_class["role_confidence"],
            "style_tags": file_class.get("style_tags", []),
            "genre_hint": file_class.get("genre_hint"),
            "genre_confidence": file_class.get("genre_confidence", 0.0),
            "classifier_method": file_class.get("classifier_method", CLASSIFIER_METHOD),
            "uncertain": bool(file_class.get("uncertain", True)),
            "confidence": float(file_class.get("confidence", 0.0)),
            "conflicts": file_class.get("conflicts", []),
            "uncertainty_notes": file_class.get("uncertainty_notes", []),
            "warnings": file_warnings,
            "embedded_text": [item.get("text", "") for item in file_info.get("embedded_text", [])],
            "tracks": tracks,
            "fingerprint_version": FINGERPRINT_VERSION,
            "fingerprint_json": json.dumps(fingerprint, separators=(",", ":")) if fingerprint else None,
            "search_fields": _search_fields(filename, path, analysis, classification),
            "cache_blob": cache_blob,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }
    except Exception as exc:  # Keep one hostile file from killing a scan worker.
        return {
            "ok": False,
            "path": path,
            "error": f"{type(exc).__name__}: {exc}",
            "code": "worker_exception",
        }


def classifier_versions() -> dict[str, Any]:
    return {
        "parser_version": PARSER_VERSION,
        "classifier_version": CLASSIFIER_VERSION,
        "classifier_method": CLASSIFIER_METHOD,
    }
