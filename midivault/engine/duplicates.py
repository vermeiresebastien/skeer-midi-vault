"""Exact and approximate duplicate grouping.

Exact duplicate identity is the SHA-256 of the whole file. Similarity is a
clearly separate, lower-confidence signal computed from a compact musical
fingerprint. Similar files are never presented as byte-identical copies and are
never deleted.

Similarity only ever compares fingerprints of the current generation: a vector
from an older ``fv`` format, or one derived from another parser or classifier
generation, is dropped from the candidate set rather than scored, so a change in
how notes are extracted can never produce a plausible-looking wrong answer.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Iterable

from .versions import (
    CLASSIFIER_VERSION,
    FINGERPRINT_VERSION,
    LEGACY_FINGERPRINT_VERSION,
    PARSER_VERSION,
)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    numerator = sum(x * y for x, y in zip(a, b))
    denom_a = math.sqrt(sum(x * x for x in a))
    denom_b = math.sqrt(sum(y * y for y in b))
    if denom_a == 0 or denom_b == 0:
        return 0.0
    return numerator / (denom_a * denom_b)


def exact_groups(files: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file in files:
        content_hash = file.get("content_hash")
        if content_hash and file.get("scan_state") == "indexed":
            by_hash[content_hash].append(file)
    return [group for group in by_hash.values() if len(group) > 1]


def _fingerprint(file: dict[str, Any]) -> dict[str, Any] | None:
    raw = file.get("fingerprint_json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


def fingerprint_generation(file: dict[str, Any]) -> int:
    """Generation stamp of a file's stored fingerprint.

    ``LEGACY_FINGERPRINT_VERSION`` is returned for fingerprints written before
    versioning existed (no ``fv``) as well as for files with no fingerprint at
    all; neither is comparable.
    """
    fingerprint = _fingerprint(file)
    if not fingerprint:
        return LEGACY_FINGERPRINT_VERSION
    try:
        return int(fingerprint.get("fv") or LEGACY_FINGERPRINT_VERSION)
    except (TypeError, ValueError):
        return LEGACY_FINGERPRINT_VERSION


def _similarity(a: dict[str, Any], b: dict[str, Any], fa: dict[str, Any],
                fb: dict[str, Any]) -> float:
    if a.get("instrument") != b.get("instrument"):
        return 0.0
    if a.get("role") != b.get("role"):
        return 0.0
    tempo_a = float(a.get("tempo_bpm") or 0)
    tempo_b = float(b.get("tempo_bpm") or 0)
    if tempo_a <= 0 or tempo_b <= 0:
        return 0.0
    tempo_diff = abs(tempo_a - tempo_b) / max(tempo_a, tempo_b)
    if tempo_diff > 0.025:
        return 0.0
    duration_a = float(a.get("duration_seconds") or 0)
    duration_b = float(b.get("duration_seconds") or 0)
    if duration_a <= 0 or duration_b <= 0:
        return 0.0
    duration_ratio = min(duration_a, duration_b) / max(duration_a, duration_b)
    if duration_ratio < 0.88:
        return 0.0
    notes_a = int(a.get("note_count") or 0)
    notes_b = int(b.get("note_count") or 0)
    if notes_a <= 0 or notes_b <= 0:
        return 0.0
    note_ratio = min(notes_a, notes_b) / max(notes_a, notes_b)
    if note_ratio < 0.82:
        return 0.0
    pc_score = _cosine(list(fa.get("pc") or []), list(fb.get("pc") or []))
    onset_score = _cosine(list(fa.get("on") or []), list(fb.get("on") or []))
    pitch_a = fa.get("pitch_mean") or 64
    pitch_b = fb.get("pitch_mean") or 64
    pitch_score = max(0.0, 1.0 - abs(float(pitch_a) - float(pitch_b)) / 24.0)
    density_a = fa.get("density") or 0
    density_b = fb.get("density") or 0
    density_score = (
        min(density_a, density_b) / max(density_a, density_b)
        if max(density_a, density_b) > 0 else 0.0
    )
    score = (
        0.34 * pc_score
        + 0.28 * onset_score
        + 0.14 * note_ratio
        + 0.10 * duration_ratio
        + 0.08 * pitch_score
        + 0.06 * density_score
    )
    return score


def similar_groups(files: Iterable[dict[str, Any]],
                   excluded_ids: set[int] | None = None,
                   threshold: float = 0.955,
                   bucket_limit: int = 240,
                   current_version: int = FINGERPRINT_VERSION) -> list[list[dict[str, Any]]]:
    """Group musically similar files within practical candidate buckets.

    This is an intentionally conservative, O(bucket²) comparison over
    role/instrument/tempo buckets. It is a practical similarity signal, not an
    identity claim. Very large same-role/same-tempo buckets are capped, which is
    documented as a scalability limitation.

    Files whose fingerprint is not generation ``current_version`` are excluded
    outright, so a mixed-generation index under-reports instead of inventing
    matches.
    """
    excluded = excluded_ids or set()
    candidates: list[dict[str, Any]] = []
    for file in files:
        if file.get("scan_state") != "indexed":
            continue
        if file.get("id") in excluded:
            continue
        if int(file.get("note_count") or 0) < 5:
            continue
        fingerprint = _fingerprint(file)
        if not fingerprint:
            continue
        if fingerprint_generation(file) != current_version:
            continue
        # ``fv`` stamps the vector format only. The vector is built from parsed
        # notes plus the classifier's primary-sequence choice and tempo, so a
        # byte-identical file analysed by another generation scores a real
        # distance against a vector that means something else.
        if int(file.get("parser_version") or 0) != PARSER_VERSION:
            continue
        if int(file.get("classifier_version") or 0) != CLASSIFIER_VERSION:
            continue
        tempo = float(file.get("tempo_bpm") or 0)
        if tempo <= 0:
            continue
        bucket = (
            file.get("instrument") or "Unknown",
            file.get("role") or "Unknown",
            int(round(tempo / 6.0)),
            int(round(float(file.get("duration_seconds") or 0) / 6.0)),
        )
        candidates.append({**file, "_fingerprint": fingerprint, "_bucket": bucket})

    by_bucket: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_bucket[candidate["_bucket"]].append(candidate)

    parent: dict[int, int] = {}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for candidate in candidates:
        parent[candidate["id"]] = candidate["id"]

    for bucket_files in by_bucket.values():
        if len(bucket_files) > bucket_limit:
            bucket_files = bucket_files[:bucket_limit]
        for index, first in enumerate(bucket_files):
            for second in bucket_files[index + 1:]:
                score = _similarity(first, second, first["_fingerprint"], second["_fingerprint"])
                if score >= threshold:
                    union(first["id"], second["id"])
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        root = find(candidate["id"])
        groups[root].append(candidate)
    return [members for members in groups.values() if len(members) > 1]


def serialise_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "file_count": len(group),
        "file_ids": [item["id"] for item in group],
        "files": [
            {
                "id": item["id"],
                "path": item.get("path"),
                "filename": item.get("filename"),
                "duration_seconds": item.get("duration_seconds"),
            }
            for item in group
        ],
    }
