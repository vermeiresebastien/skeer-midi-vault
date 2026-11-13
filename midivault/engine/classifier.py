"""Transparent, offline rule-based musical intent classification.

Rules combine independent evidence: embedded MIDI metadata, channel and program
conventions, measured register/polyphony/rhythm, and filename/folder context.
No single source is treated as proof. Every prediction carries evidence,
confidence, alternatives and a classifier method/version. Genre is deliberately
low-confidence and never written as a hard fact.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .gm import GENRE_HINTS, program_name
from .taxonomy import (
    instrument_keyword_categories,
    role_keyword_predictions,
    program_category,
)
from .versions import CLASSIFIER_METHOD, CLASSIFIER_RULESET, CLASSIFIER_VERSION


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _evidence(source: str, kind: str, label: str, weight: float, category: str) -> dict[str, Any]:
    return {
        "source": source,
        "kind": kind,
        "label": label,
        "weight": round(float(weight), 3),
        "category": category,
    }


def _conflict(label: str, category: str | None = None) -> dict[str, Any]:
    return {
        "source": "conflict",
        "kind": "conflict",
        "label": label,
        "weight": -0.15,
        "category": category,
    }


def _add(scores: dict[str, float], evidence: list[dict[str, Any]],
         category: str, weight: float, source: str, kind: str, label: str) -> None:
    if weight <= 0:
        return
    scores[category] += weight
    evidence.append(_evidence(source, kind, label, weight, category))


def _normalized_alternatives(scores: dict[str, float], limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    total = sum(max(0.0, value) for value in scores.values())
    if not ranked:
        return []
    return [
        {"category": category, "share": round(value / total, 3) if total else 0.0,
         "score": round(value, 3)}
        for category, value in ranked
    ]


def _select_prediction(scores: dict[str, float], note_count: int,
                       evidence: list[dict[str, Any]], conflicts: list[dict[str, Any]],
                       *, embedded_support: bool, cap: float, unknown_label: str,
                       minimum: float = 0.22) -> dict[str, Any]:
    if not scores or note_count == 0:
        return {
            "category": unknown_label,
            "confidence": 0.28,
            "evidence": [e for e in evidence if e in conflicts] + [
                _evidence("analysis", "calculated",
                          "No note events or usable musical evidence", 0.0, unknown_label)
            ],
            "alternatives": [],
            "uncertain": True,
            "conflicts": list(conflicts),
        }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_label, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score < minimum or (note_count < 2 and not embedded_support):
        category = unknown_label
        confidence = 0.30
        chosen_evidence = [
            item for item in evidence
            if item["kind"] == "conflict" or item.get("category") == top_label
        ]
        chosen_evidence.append(
            _evidence("analysis", "calculated",
                      f"Strongest apparent signal ({top_label}) was below the evidence threshold",
                      round(top_score, 3), unknown_label)
        )
        return {
            "category": category,
            "confidence": confidence,
            "evidence": chosen_evidence[:12],
            "alternatives": _normalized_alternatives(scores),
            "uncertain": True,
            "conflicts": list(conflicts),
        }
    support_share = top_score / max(1e-6, sum(max(0.0, value) for value in scores.values()))
    margin = (top_score - second_score) / max(1e-6, top_score)
    confidence = (
        0.30
        + 0.28 * min(1.1, top_score) / 1.1
        + 0.20 * margin
        + 0.10 * support_share
        + (0.05 if embedded_support else 0.0)
    )
    if note_count < 4:
        confidence -= 0.06
    confidence_cap = cap
    if not embedded_support:
        confidence_cap = min(confidence_cap, 0.62)
        confidence = min(confidence, confidence_cap)
    if conflicts:
        confidence -= 0.13
        confidence_cap = min(confidence_cap, 0.54)
    confidence = _clamp(confidence, 0.18, confidence_cap)
    # Keep the chosen label's supporting evidence first, then the audit trail.
    chosen_evidence = sorted(
        evidence,
        key=lambda item: (
            0 if item.get("category") == top_label else
            1 if item["kind"] == "conflict" else 2,
            -abs(item["weight"]),
        ),
    )
    if conflicts:
        chosen_evidence = conflicts + chosen_evidence
        # Deduplicate conflicts that already appear.
        seen = set()
        deduped = []
        for item in chosen_evidence:
            key = (item["source"], item["label"])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        chosen_evidence = deduped
    return {
        "category": top_label,
        "confidence": round(confidence, 3),
        "evidence": chosen_evidence[:12],
        "alternatives": _normalized_alternatives(scores),
        "uncertain": confidence < 0.55 or bool(conflicts),
        "conflicts": conflicts,
    }


def _track_text(track: dict[str, Any]) -> str:
    parts = [track.get("name") or "", track.get("instrument_name") or ""]
    parts.extend(track.get("embedded_texts") or [])
    return " ".join(part for part in parts if part)


def _file_context_text(filename: str, relative_folder: str,
                       embedded_texts: list[str]) -> str:
    stem = Path(filename).stem if filename else ""
    folder_parts = Path(relative_folder).parts if relative_folder else ()
    folder_text = " ".join(folder_parts[-2:]) if folder_parts else ""
    return " ".join([stem, folder_text, *embedded_texts[:40]])


def _instrument_for_track(track: dict[str, Any],
                          file_role_conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    scores: dict[str, float] = defaultdict(float)
    evidence: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    notes = track["note_count"]
    programs = [p for p in track["programs"] if p is not None]
    program_cats: list[str] = []
    embedded_support = False

    if track["drum_channel"]:
        _add(scores, evidence, "Drums/percussion", 0.26, "midi_channel", "embedded",
             "MIDI channel 10 percussion convention (not proof)")
        embedded_support = True
    if track.get("is_percussion_program"):
        _add(scores, evidence, "Drums/percussion", 0.30, "midi_program", "embedded",
             "General MIDI percussion program")
        embedded_support = True
    seen_program_categories: set[str] = set()
    for index, program in enumerate(programs):
        category = program_category(program)
        if not category:
            continue
        if category in seen_program_categories:
            continue
        seen_program_categories.add(category)
        program_cats.append(category)
        weight = 0.42 if index == 0 else 0.16
        _add(scores, evidence, category, weight, "midi_program", "embedded",
             f"Program {program + 1} · {program_name(program) or 'unknown'}")
        embedded_support = True
    if len(seen_program_categories) > 1:
        conflicts.append(_conflict(
            "Track changes between different instrument families: "
            + ", ".join(sorted(seen_program_categories))
        ))
    if track["drum_channel"] and any(cat != "Drums/percussion" for cat in program_cats):
        conflicts.append(_conflict(
            "Channel 10 percussion convention conflicts with a tonal program change"
        ))
    if program_cats and "Drums/percussion" in program_cats and track["drum_channel"] is False:
        conflicts.append(_conflict(
            "Percussion program outside channel 10; program and channel evidence disagree"
        ))

    text = _track_text(track)
    keyword_scores = instrument_keyword_categories(text) if text else {}
    for category, weight in sorted(keyword_scores.items()):
        _add(scores, evidence, category, weight, "track_text", "embedded",
             f"Track name/text mentions {category.lower()} material")
        embedded_support = True

    # Track names can disagree with the embedded program. Record that instead
    # of silently picking one; the confidence cap will expose the ambiguity.
    if program_cats and keyword_scores:
        program_cat = program_cats[0]
        keyword_cats = set(keyword_scores)
        if keyword_cats and program_cat not in keyword_cats:
            strongest_name_cat = max(keyword_scores, key=keyword_scores.get)
            if keyword_scores[strongest_name_cat] >= 0.30:
                conflicts.append(_conflict(
                    f"Track name suggests {strongest_name_cat.lower()} while the MIDI "
                    f"program indicates {program_cat.lower()}"
                ))
    for conflict in file_role_conflicts:
        conflicts.append(conflict)

    # Behavioural evidence, intentionally conservative.
    if notes >= 4:
        mono = track["monophonic_ratio"]
        low = track["low_register_ratio"]
        high = track["high_register_ratio"]
        density = track["note_density"]
        avg_group = track["avg_group_size"]
        long_ratio = track["long_note_ratio"]
        median = track["pitch_median"] or 60
        if low >= 0.65 and mono >= 0.55 and median <= 52 and notes >= 6:
            _add(scores, evidence, "Bass", 0.15, "register", "calculated",
                 f"Low register (median {track['pitch_min_name'] or median}) and monophonic rhythm")
        if avg_group >= 2.2 and track["chord_group_count"] >= 3:
            _add(scores, evidence, "Piano/keys", 0.10, "texture", "calculated",
                 "Repeated simultaneous chord onsets")
        if long_ratio >= 0.45 and avg_group >= 1.8:
            _add(scores, evidence, "Strings", 0.07, "texture", "calculated",
                 "Sustained, overlapping harmony")
            _add(scores, evidence, "Synth", 0.05, "texture", "calculated",
                 "Long overlapping tones could be a synth pad")
        if mono >= 0.82 and density >= 1.4 and track["distinct_pitch_classes"] <= 6:
            _add(scores, evidence, "Guitar/plucked", 0.06, "rhythm", "calculated",
                 "Monophonic short-note pattern")
            _add(scores, evidence, "Synth", 0.04, "rhythm", "calculated",
                 "Regular electronic-style single-note pattern")
        if high >= 0.7 and mono >= 0.75:
            del high  # High register alone is not evidence of a specific family.
        if track["programs"] and median <= 50 and programs:
            top_program_cat = program_category(programs[0])
            if top_program_cat and top_program_cat not in ("Bass", "Drums/percussion") and low >= 0.6:
                conflicts.append(_conflict(
                    "Low register conflicts with a higher-register program family"
                ))

    prediction = _select_prediction(
        scores, notes, evidence, conflicts,
        embedded_support=embedded_support, cap=0.9,
        unknown_label="Unknown", minimum=0.22,
    )
    return prediction


def _role_for_track(track: dict[str, Any], instrument: str,
                    instrument_confidence: float) -> dict[str, Any]:
    notes = track["note_count"]
    scores: dict[str, float] = defaultdict(float)
    evidence: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    text = _track_text(track)
    keyword_scores = role_keyword_predictions(text) if text else {}
    for role, weight in keyword_scores.items():
        _add(scores, evidence, role, weight * 0.85, "track_text", "embedded",
             f"Track name/text mentions “{role.lower()}”")
    embedded_support = bool(keyword_scores) or instrument != "Unknown"
    percussive = instrument == "Drums/percussion" or track["drum_channel"]
    density = track["note_density"]
    bars = track.get("bar_span") or 0.0
    if percussive:
        groove_score = (
            0.30
            + 0.18 * track["regularity"]
            + 0.12 * track["pattern_repeat"]
            + (0.08 if bars >= 2 else 0.0)
            + 0.06 * max(track["quarter_note_ratio"], track["eighth_note_ratio"])
        )
        fill_score = (
            0.10
            + (0.16 if density >= 3.2 else 0.0)
            + (0.12 if track["distinct_pitches"] >= 5 else 0.0)
            + (0.10 if track["pattern_repeat"] < 0.30 else 0.0)
            + (0.08 if bars <= 2.0 else 0.0)
            + (0.06 if track["max_group_size"] >= 2 else 0.0)
        )
        _add(scores, evidence, "Drum groove", groove_score, "rhythm", "calculated",
             f"Regular percussion pattern with {density:.2f} notes per beat")
        _add(scores, evidence, "Drum fill", fill_score, "rhythm", "calculated",
             f"Short, varied, low-repetition percussion pattern ({track['distinct_pitches']} pitches)")
        if track["pattern_repeat"] >= 0.55:
            evidence.append(_evidence(
                "rhythm", "calculated", "Repeated bar-level onset pattern supports a groove",
                0.10, "Drum groove",
            ))
            scores["Drum groove"] += 0.06
    else:
        mono = track["monophonic_ratio"]
        avg_group = track["avg_group_size"]
        long_ratio = track["long_note_ratio"]
        if instrument == "Bass" or (track["low_register_ratio"] >= 0.6 and mono >= 0.6):
            _add(scores, evidence, "Bassline", 0.32, "register", "calculated",
                 "Low-register single-note line")
        if avg_group >= 1.7 and track["chord_group_count"] >= 2:
            _add(scores, evidence, "Chord progression", 0.31, "texture", "calculated",
                 "Repeated simultaneous note groups")
        if avg_group >= 2.2 or (long_ratio >= 0.4 and avg_group >= 1.6):
            _add(scores, evidence, "Pad/sustained harmony", 0.16, "texture", "calculated",
                 "Long overlapping harmony")
        if mono >= 0.68:
            _add(scores, evidence, "Lead/melody", 0.25, "texture", "calculated",
                 f"Mostly monophonic line ({mono * 100:.0f}% single-note onsets)")
        if track["arpeggio_score"] >= 0.48:
            _add(scores, evidence, "Arpeggio", 0.34 * track["arpeggio_score"],
                 "arpeggio", "calculated",
                 f"Chord-tone coverage {track['chord_tone_coverage'] * 100:.0f}% with regular onsets")
        if track["scale_score"] >= 0.55:
            _add(scores, evidence, "Exercise or technical pattern", 0.30 * track["scale_score"],
                 "scale", "calculated",
                 f"Stepwise run structure ({track['stepwise_ratio'] * 100:.0f}% stepwise intervals)")
        if instrument in ("Piano/keys", "Guitar/plucked", "Strings", "Synth") and avg_group >= 1.8:
            _add(scores, evidence, "Chord progression", 0.08,
                 "instrument", "calculated", f"{instrument} family with simultaneous notes")
        if instrument == "Brass/woodwinds" and mono >= 0.75:
            _add(scores, evidence, "Lead/melody", 0.08, "instrument", "calculated",
                 "Single-note melodic instrument family")
        if instrument == "Synth" and long_ratio >= 0.4:
            _add(scores, evidence, "Pad/sustained harmony", 0.12,
                 "instrument", "calculated", "Synth family with long sustained notes")
        if instrument == "Strings" and long_ratio >= 0.35:
            _add(scores, evidence, "Pad/sustained harmony", 0.08,
                 "instrument", "calculated", "String sustain suggests sustained harmony")
    prediction = _select_prediction(
        scores, notes, evidence, conflicts,
        embedded_support=embedded_support, cap=0.88,
        unknown_label="Unknown", minimum=0.24,
    )
    # For a monophonic tonal track with no role evidence, melody is a better
    # default than Unknown, but it stays low-confidence.
    if prediction["category"] == "Unknown" and not percussive and notes >= 4 and track["monophonic_ratio"] >= 0.85:
        prediction["category"] = "Lead/melody"
        prediction["confidence"] = 0.32
        prediction["uncertain"] = True
        prediction["evidence"] = prediction["evidence"][:3] + [
            _evidence("texture", "calculated",
                      "Monophonic line with no specific role metadata; low-confidence melody default",
                      0.2, "Lead/melody")
        ]
    return prediction


def _file_instrument(primary_tracks: list[dict[str, Any]],
                     filename_hints: dict[str, float],
                     context_hints: dict[str, float],
                     file_context: str,
                     format_two_multi: bool) -> dict[str, Any]:
    significant = [track for track in primary_tracks if track["note_count"] > 0]
    total_notes = sum(track["note_count"] for track in significant)
    weights: dict[str, float] = defaultdict(float)
    conflicts: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    track_predictions = {id(track): track.get("instrument_prediction") for track in significant}
    known_tracks = [
        track for track in significant
        if (track_predictions.get(id(track)) or {}).get("category") not in (None, "Unknown")
    ]
    for track in known_tracks:
        prediction = track["instrument_prediction"]
        category = prediction["category"]
        weight = track["note_count"] * (0.45 + 0.55 * prediction["confidence"])
        weights[category] += weight
        track_label = track.get("name") or f"ch {track.channel + 1}"
        evidence.append(_evidence(
            "track_analysis", "calculated",
            f"Track “{track_label}” → {category} "
            f"({prediction['confidence'] * 100:.0f}%)",
            round(min(0.5, weight / max(1, total_notes)), 3), category,
        ))
    if not total_notes:
        return {
            "prediction": {
                "category": "Unknown", "confidence": 0.25,
                "evidence": [_evidence("analysis", "calculated", "No MIDI note events", 0.0, "Unknown")],
                "alternatives": [], "uncertain": True, "conflicts": [],
            },
            "track_predictions": track_predictions,
        }
    known_total = sum(weights.values())
    combined_hints = dict(context_hints)
    for category, weight in filename_hints.items():
        combined_hints[category] = max(combined_hints.get(category, 0.0), weight)
    if filename_hints and known_tracks:
        hint_top, hint_weight = max(filename_hints.items(), key=lambda item: item[1])
        if hint_top not in weights and hint_weight >= 0.30:
            conflicts.append(_conflict(
                f"Filename suggests {hint_top.lower()}, while track evidence points to "
                + ", ".join(sorted(weights))
            ))
    for hint_category, hint_weight in sorted(combined_hints.items()):
        if known_tracks and hint_category in weights:
            evidence.append(_evidence(
                "filename_context", "filename",
                f"Filename/folder context is consistent with {hint_category.lower()}",
                round(min(0.15, hint_weight * 0.4), 3), hint_category,
            ))
    category_weights = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    if not category_weights:
        hint_top = max(combined_hints, key=combined_hints.get) if combined_hints else "Unknown"
        confidence = 0.34 if hint_top != "Unknown" and file_context.strip() else 0.24
        prediction = {
            "category": hint_top,
            "confidence": confidence,
            "evidence": [
                _evidence("filename_context", "filename",
                          "Only filename/folder context supports this family", round(
                              combined_hints.get(hint_top, 0.0), 3), hint_top)
            ] if hint_top != "Unknown" else [
                _evidence("analysis", "calculated",
                          "No program, name or usable behavioural evidence", 0.0, "Unknown")
            ],
            "alternatives": [],
            "uncertain": True,
            "conflicts": conflicts,
        }
        if format_two_multi:
            prediction["evidence"].append(_evidence(
                "format", "embedded",
                "Format 2: file label describes the primary sequence only; sequences are independent",
                0.0, hint_top,
            ))
            prediction["uncertain"] = True
        return {"prediction": prediction, "track_predictions": track_predictions}

    # Mixed arrangement requires at least two materially supported families.
    distinct = len(category_weights)
    second_share = 0.0
    if distinct > 1:
        second_share = category_weights[1][1] / max(1e-6, known_total)
    is_mixed = distinct > 1 and second_share >= 0.17 and len(known_tracks) >= 2
    avg_conf = sum(
        track["instrument_prediction"]["confidence"] * track["note_count"] for track in known_tracks
    ) / max(1, sum(track["note_count"] for track in known_tracks))
    if is_mixed:
        category = "Mixed arrangement"
        confidence = _clamp(0.48 + 0.28 * avg_conf + min(0.14, second_share * 0.38), 0.35, 0.88)
        evidence.insert(0, _evidence(
            "track_analysis", "calculated",
            "Multiple significant tracks resolve to different sound families: "
            + ", ".join(category for category, _ in category_weights),
            0.65, category,
        ))
    else:
        category = category_weights[0][0]
        confidence = _clamp(0.44 + 0.42 * avg_conf + 0.05 * min(3, len(known_tracks)) / 3, 0.3, 0.91)
    # Surface the strongest underlying evidence of each leading family so the
    # file-level explanation is auditable without opening every track.
    for category_name, _weight in category_weights[:3]:
        candidates = [
            track for track in known_tracks
            if (track.get("instrument_prediction") or {}).get("category") == category_name
        ]
        if not candidates:
            continue
        representative = max(candidates, key=lambda item: item["note_count"])
        track_label = representative.get("name") or f"channel {representative['channel'] + 1}"
        for item in (representative.get("instrument_prediction") or {}).get("evidence", [])[:2]:
            if item.get("kind") == "conflict":
                continue
            evidence.append(_evidence(
                item.get("source", "track_analysis"), item.get("kind", "calculated"),
                f"{track_label}: {item.get('label', 'supporting evidence')}",
                round(float(item.get("weight") or 0) * 0.55, 3),
                category_name,
            ))
    if conflicts:
        confidence = min(confidence, 0.55)
    if format_two_multi:
        confidence = min(confidence, 0.60)
        evidence.append(_evidence(
            "format", "embedded",
            "Format 2: file label describes the primary independent sequence; other sequences "
            "are indexed and labelled separately",
            0.0, category,
        ))
    alternatives = [
        {"category": cat, "share": round(weight / max(1e-6, known_total), 3),
         "score": round(weight, 3)}
        for cat, weight in category_weights[:3]
    ]
    if is_mixed:
        alternatives.insert(0, {"category": "Mixed arrangement", "share": 1.0,
                                "score": round(known_total, 3)})
    return {
        "prediction": {
            "category": category,
            "confidence": round(confidence, 3),
            "evidence": evidence[:12],
            "alternatives": alternatives,
            "uncertain": confidence < 0.55 or bool(conflicts) or format_two_multi,
            "conflicts": conflicts,
        },
        "track_predictions": track_predictions,
    }


def _file_role(primary_tracks: list[dict[str, Any]], format_two_multi: bool) -> dict[str, Any]:
    significant = [
        track for track in primary_tracks
        if track["note_count"] > 0 and track.get("role_prediction")
    ]
    if not significant:
        return {
            "category": "Unknown",
            "confidence": 0.25,
            "evidence": [_evidence("analysis", "calculated", "No usable track roles", 0.0, "Unknown")],
            "alternatives": [],
            "uncertain": True,
            "conflicts": [],
        }
    weights: dict[str, float] = defaultdict(float)
    evidence: list[dict[str, Any]] = []
    named_roles: list[tuple[str, str, float]] = []
    for track in significant:
        prediction = track["role_prediction"]
        category = prediction["category"]
        if category == "Unknown":
            continue
        weight = track["note_count"] * (0.4 + 0.6 * prediction["confidence"])
        weights[category] += weight
        track_label = track.get("name") or f"Channel {track['channel'] + 1}"
        named_roles.append((track_label, category, prediction["confidence"]))
        evidence.append(_evidence(
            "track_analysis", "calculated",
            f"“{track_label}” → {category} ({prediction['confidence'] * 100:.0f}%)",
            round(min(0.5, weight / max(1, sum(t["note_count"] for t in significant))), 3),
            category,
        ))
        for item in prediction.get("evidence", [])[:1]:
            if item.get("kind") == "conflict":
                continue
            evidence.append(_evidence(
                item.get("source", "track_analysis"), item.get("kind", "calculated"),
                f"{track_label}: {item.get('label', 'supporting evidence')}",
                round(float(item.get("weight") or 0) * 0.5, 3),
                category,
            ))
    if not weights:
        return {
            "category": "Unknown", "confidence": 0.28,
            "evidence": [
                _evidence("track_analysis", "calculated",
                          "Tracks have notes but no role evidence strong enough for a label",
                          0.0, "Unknown")
            ],
            "alternatives": [], "uncertain": True, "conflicts": [],
        }
    distinct_roles = set(weights)
    avg_conf = sum(confidence for _name, _role, confidence in named_roles) / max(1, len(named_roles))
    if len(distinct_roles) >= 2 and len(named_roles) >= 2:
        category = "Complete song or multi-part arrangement"
        confidence = _clamp(0.50 + 0.26 * avg_conf + 0.04 * min(3, len(distinct_roles) - 1), 0.38, 0.87)
        evidence.insert(0, _evidence(
            "arrangement", "calculated",
            "Independent parts: " + ", ".join(f"{role} ({name})" for name, role, _ in named_roles),
            0.7, category,
        ))
    else:
        category = max(weights, key=weights.get)
        confidence = _clamp(0.38 + 0.42 * avg_conf + 0.05, 0.28, 0.84)
    if format_two_multi:
        confidence = min(confidence, 0.58)
        evidence.append(_evidence(
            "format", "embedded",
            "Format 2: role describes the primary sequence only; each sequence is labelled separately",
            0.0, category,
        ))
    alternatives = [
        {"category": role, "share": round(weight / max(1e-6, sum(weights.values())), 3),
         "score": round(weight, 3)}
        for role, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)[:3]
    ]
    if category != "Complete song or multi-part arrangement" and category not in [a["category"] for a in alternatives]:
        alternatives.insert(0, {"category": category, "share": 1.0, "score": sum(weights.values())})
    return {
        "category": category,
        "confidence": round(confidence, 3),
        "evidence": evidence[:12],
        "alternatives": alternatives,
        "uncertain": confidence < 0.55 or format_two_multi,
        "conflicts": [],
    }


def _feel_tags(primary_tracks: list[dict[str, Any]], note_density: float,
               note_count: int) -> list[str]:
    if note_count < 4:
        return []
    total = sum(track["note_count"] for track in primary_tracks) or 1
    swing = sum(track["swing_ratio"] * track["note_count"] for track in primary_tracks) / total
    syncopation = sum(track["syncopation_ratio"] * track["note_count"] for track in primary_tracks) / total
    tags: list[str] = []
    if swing >= 0.32:
        tags.append("swung")
    elif swing <= 0.20:
        tags.append("straight")
    if syncopation >= 0.36:
        tags.append("syncopated")
    if note_density <= 0.85:
        tags.append("sparse")
    elif note_density >= 3.3:
        tags.append("dense")
    order = {"straight": 0, "swung": 1, "sparse": 2, "dense": 3, "syncopated": 4}
    return sorted(set(tags), key=lambda tag: order.get(tag, 9))


def _track_feel_tags(track: dict[str, Any]) -> list[str]:
    if track["note_count"] < 4:
        return []
    tags = []
    if track["swing_ratio"] >= 0.34:
        tags.append("swung")
    elif track["swing_ratio"] <= 0.20:
        tags.append("straight")
    if track["syncopation_ratio"] >= 0.36:
        tags.append("syncopated")
    if track["note_density"] <= 0.55:
        tags.append("sparse")
    elif track["note_density"] >= 3.3:
        tags.append("dense")
    order = {"straight": 0, "swung": 1, "sparse": 2, "dense": 3, "syncopated": 4}
    return sorted(set(tags), key=lambda tag: order.get(tag, 9))


def _genre_hint(context_text: str, instrument: str, role: str,
                tempo: float, tags: list[str], note_count: int) -> dict[str, Any]:
    if note_count < 4:
        return {"label": None, "confidence": 0.0,
                "evidence": "Too little material for a style hint", "method": "none"}
    lowered = f" {context_text.casefold()} "
    keyword_hits: list[tuple[str, int]] = []
    for label, keywords in GENRE_HINTS.items():
        hits = 0
        for keyword in keywords:
            if keyword in lowered:
                hits += 1
        if hits:
            keyword_hits.append((label, hits))
    if keyword_hits:
        keyword_hits.sort(key=lambda item: item[1], reverse=True)
        label = keyword_hits[0][0]
        confidence = min(0.45, 0.30 + 0.04 * keyword_hits[0][1])
        return {
            "label": label,
            "confidence": round(confidence, 3),
            "evidence": "Filename/folder/embedded text mentions a style cue; speculative only",
            "method": "text cue + low-confidence heuristic",
        }
    intensity = "sparse" if "sparse" in tags else ("dense" if "dense" in tags else "medium")
    swing = "swung" in tags
    label = None
    confidence = 0.0
    evidence = "No reliable style evidence"
    if instrument == "Mixed arrangement" and role == "Complete song or multi-part arrangement":
        if tempo and 60 <= tempo <= 105 and swing:
            label, confidence = "Hip-hop / lo-fi beat", 0.24
        elif tempo and 110 <= tempo <= 135 and not swing:
            label, confidence = "House / techno", 0.22
        else:
            label, confidence = "Rock / band", 0.18
        evidence = "Arrangement density, instrument mix and tempo heuristics (speculative)"
    elif instrument in ("Strings", "Piano/keys") and role in (
        "Pad/sustained harmony", "Chord progression", "Lead/melody"
    ) and tempo <= 100:
        label, confidence = "Cinematic / ambient", 0.22
        evidence = "Slow sustained tonal material; no genre metadata (speculative)"
    elif instrument in ("Drums/percussion", "Bass") and swing:
        label, confidence = "Jazz-leaning", 0.18
        evidence = "Swung subdivision heuristic (speculative)"
    elif tempo and (tempo <= 92 or tempo >= 150) and intensity != "medium":
        label, confidence = None, 0.0
    if label:
        confidence = min(0.32, confidence)
        return {
            "label": label,
            "confidence": round(confidence, 3),
            "evidence": evidence,
            "method": "feature heuristic, speculative",
        }
    return {
        "label": None, "confidence": 0.0,
        "evidence": "No genre is claimed without metadata or strong cues; genre is not inferred reliably from MIDI alone",
        "method": "none",
    }


def classify(parse, analysis: dict[str, Any], filename: str = "",
             relative_folder: str = "") -> dict[str, Any]:
    """Classify the file and every logical track.

    The input is the result of :func:`midivault.engine.analytics.analyze`.
    """
    file_info = analysis["file"]
    primary_index = analysis["primary_sequence_index"]
    primary_tracks: list[dict[str, Any]] = [
        track for track in analysis["tracks"] if track["sequence_index"] == primary_index
    ]
    if not primary_tracks and analysis["tracks"]:
        primary_tracks = analysis["tracks"]
    embedded_texts = [item["text"] for item in file_info.get("embedded_text", [])]
    context_text = _file_context_text(filename, relative_folder, embedded_texts)
    filename_hints = instrument_keyword_categories(Path(filename).stem if filename else "")
    folder_text = " ".join(Path(relative_folder).parts[-2:]) if relative_folder else ""
    context_hints = instrument_keyword_categories(
        " ".join([folder_text, *embedded_texts[:20]])
    )
    format_two_multi = bool(parse.format == 2 and len(parse.sequences) > 1)

    # Track classifications first.
    track_outputs: list[dict[str, Any]] = []
    for track in analysis["tracks"]:
        track_role_conflicts: list[dict[str, Any]] = []
        if format_two_multi and track["sequence_index"] != primary_index:
            track_role_conflicts.append(_conflict(
                "This track belongs to an independent format-2 sequence; it is not combined with the primary timeline"
            ))
        instrument_pred = _instrument_for_track(track, track_role_conflicts)
        track["instrument_prediction"] = instrument_pred
        role_pred = _role_for_track(track, instrument_pred["category"], instrument_pred["confidence"])
        track["role_prediction"] = role_pred
        feel_tags = _track_feel_tags(track)
        uncertain = bool(instrument_pred["uncertain"] or role_pred["uncertain"])
        track_output = {
            "sequence_index": track["sequence_index"],
            "track_index": track["track_index"],
            "chunk_index": track["chunk_index"],
            "channel": track["channel"],
            "name": track["name"],
            "instrument": instrument_pred["category"],
            "instrument_confidence": instrument_pred["confidence"],
            "instrument_evidence": instrument_pred["evidence"],
            "instrument_alternatives": instrument_pred["alternatives"],
            "role": role_pred["category"],
            "role_confidence": role_pred["confidence"],
            "role_evidence": role_pred["evidence"],
            "role_alternatives": role_pred["alternatives"],
            "feel_tags": feel_tags,
            "uncertain": uncertain,
            "conflicts": (instrument_pred.get("conflicts") or []) + (role_pred.get("conflicts") or []),
        }
        track_outputs.append(track_output)

    file_instrument = _file_instrument(
        primary_tracks, filename_hints, context_hints, context_text, format_two_multi
    )
    instrument_pred = file_instrument["prediction"]
    role_pred = _file_role(primary_tracks, format_two_multi)
    primary_note_count = sum(track["note_count"] for track in primary_tracks)
    tags = _feel_tags(primary_tracks, file_info["note_density"], primary_note_count)
    tempo_initial = file_info["tempo"]["initial_bpm"]
    genre = _genre_hint(
        context_text, instrument_pred["category"], role_pred["category"],
        tempo_initial, tags, primary_note_count,
    )
    conflicts = list(instrument_pred.get("conflicts") or [])
    if file_info["key"].get("conflict"):
        conflicts.append(_conflict(file_info["key"]["conflict"]))
    unknown_reasons = []
    if file_info["tempo"]["assumed"]:
        unknown_reasons.append("tempo assumed at 120 BPM")
    if file_info["time_signature"]["assumed"]:
        unknown_reasons.append("time signature assumed 4/4")
    if file_info["key"]["uncertain"]:
        unknown_reasons.append("key uncertain")
    if format_two_multi:
        unknown_reasons.append("independent format-2 sequences")
    confidence = min(instrument_pred["confidence"], role_pred["confidence"])
    overall_uncertain = (
        instrument_pred["category"] == "Unknown"
        or role_pred["category"] == "Unknown"
        or instrument_pred["uncertain"]
        or role_pred["uncertain"]
        or bool(conflicts)
        or format_two_multi
        or confidence < 0.55
    )
    file_output = {
        "instrument": instrument_pred["category"],
        "instrument_confidence": instrument_pred["confidence"],
        "instrument_evidence": instrument_pred["evidence"],
        "instrument_alternatives": instrument_pred["alternatives"],
        "role": role_pred["category"],
        "role_confidence": role_pred["confidence"],
        "role_evidence": role_pred["evidence"],
        "role_alternatives": role_pred["alternatives"],
        "style_tags": tags,
        "feel_tags": tags,
        "genre_hint": genre["label"],
        "genre_confidence": genre["confidence"],
        "genre_evidence": genre["evidence"],
        "genre_method": genre["method"],
        "confidence": round(confidence, 3),
        "uncertain": overall_uncertain,
        "conflicts": conflicts,
        "uncertainty_notes": unknown_reasons,
        "classifier_method": CLASSIFIER_METHOD,
        "classifier_ruleset": CLASSIFIER_RULESET,
        "classifier_version": CLASSIFIER_VERSION,
        "primary_sequence_index": primary_index,
        "primary_track_count": len(primary_tracks),
        "primary_note_count": primary_note_count,
        "sequence_count": len(parse.sequences),
        "format_2_multi_sequence": format_two_multi,
    }
    if format_two_multi:
        overall_uncertain = True
        file_output["uncertain"] = True
        file_output["uncertainty_notes"].append(
            "file labels describe the primary sequence only; sequence-level labels are separate"
        )
    # Record the file-level confidence already accounts for role uncertainty.
    file_output["confidence"] = round(min(
        instrument_pred["confidence"], role_pred["confidence"]
    ), 3)
    return {
        "file": file_output,
        "tracks": track_outputs,
        "method": {
            "name": CLASSIFIER_METHOD,
            "ruleset": CLASSIFIER_RULESET,
            "version": CLASSIFIER_VERSION,
            "dimensions": ["instrument", "role", "feel/style tags"],
            "genre": "low-confidence optional hint only",
        },
    }
