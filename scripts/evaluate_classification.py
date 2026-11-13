"""Evaluate instrument and role classification against the hand-labelled demo set.

This is a small, deliberately constructed sample of original generated fixtures.
It is useful for finding rule regressions, not for claiming general-world
accuracy. Genre has no ground-truth labels and is intentionally not evaluated.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from midivault.engine.analytics import analyze  # noqa: E402
from midivault.engine.classifier import classify  # noqa: E402
from midivault.engine.smf_parser import MidiParseError, parse_smf  # noqa: E402

LABELS_PATH = ROOT / "fixtures" / "demo_labels.json"
LIBRARY = ROOT / "fixtures" / "demo_library"
OUT_JSON = ROOT / "docs" / "classification-evaluation.json"
OUT_MD = ROOT / "docs" / "classification-evaluation.md"


def render_markdown(report: dict) -> str:
    lines = [
        "# Classification evaluation",
        "",
        "This evaluation uses the generated, hand-labelled fixture library in",
        "`fixtures/demo_library` (labels authored alongside the MIDI by",
        "`scripts/generate_demo_library.py`). It is a controlled regression sample,",
        "not a claim about arbitrary real-world MIDI libraries.",
        "",
        "## File-level accuracy",
        "",
        f"- Sample: **{report['sample_size']}** files with labels marked as evaluation files.",
        f"- Sound family accuracy: **{report['instrument_accuracy'] * 100:.1f}%** "
        f"({report['instrument_correct']}/{report['sample_size']}).",
        f"- Musical role accuracy: **{report['role_accuracy'] * 100:.1f}%** "
        f"({report['role_correct']}/{report['sample_size']}).",
        f"- Files flagged uncertain: **{report['uncertain_count']}**.",
        f"- Mean automatic confidence: sound family "
        f"**{(report['mean_instrument_confidence'] or 0) * 100:.1f}%**, role "
        f"**{(report['mean_role_confidence'] or 0) * 100:.1f}%**.",
        "",
        "## Track-level accuracy (multi-track fixture subset)",
        "",
        f"- Manually labelled tracks: **{report['track_sample_size']}**.",
        f"- Track sound family accuracy: **{report['track_instrument_accuracy'] * 100:.1f}%** "
        f"({report['track_instrument_correct']}/{report['track_sample_size']}).",
        f"- Track role accuracy: **{report['track_role_accuracy'] * 100:.1f}%** "
        f"({report['track_role_correct']}/{report['track_sample_size']}).",
        "",
        "## Correctly classified",
        "",
        "| File | Family | Role | Confidence |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["correct"]:
        lines.append(
            f"| {item['path']} | {item['instrument']} | {item['role']} | "
            f"{(item['confidence'] or 0) * 100:.0f}% |"
        )
    lines.extend(["", "## Misclassifications / ambiguous cases", ""])
    if report["mistakes"]:
        lines.append("| File | Expected family / role | Predicted family / role | Why it is hard |")
        lines.append("| --- | --- | --- | --- |")
        for item in report["mistakes"]:
            lines.append(
                f"| {item['path']} | {item['expected_instrument']} / {item['expected_role']} | "
                f"{item['predicted_instrument']} / {item['predicted_role']} | {item['note']} |"
            )
    else:
        lines.append("No misclassifications in this sample.")
    lines.extend(["", "## Uncertain cases", ""])
    if report["uncertain"]:
        lines.append("| File | Family | Role | Confidence | Flags |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in report["uncertain"]:
            lines.append(
                f"| {item['path']} | {item['instrument']} | {item['role']} | "
                f"{item['confidence'] * 100:.0f}% | {', '.join(item['flags']) or '—'} |"
            )
    else:
        lines.append("No files were flagged uncertain in this sample.")
    lines.extend(["", "## Track-level mismatches", ""])
    if report.get("track_mistakes"):
        lines.append("| File | Track | Expected | Predicted |")
        lines.append("| --- | --- | --- | --- |")
        for item in report["track_mistakes"]:
            lines.append(
                f"| {item['path']} | {item['name']} | {item['expected']} | {item['predicted']} |"
            )
    else:
        lines.append("No track-level role mismatches in this subset.")
    lines.extend([
        "",
        "## What is not measured",
        "",
        "- Genre: there is no ground truth and the app itself reports it only as a",
        "  low-confidence style hint. No genre accuracy is claimed.",
        "- Real-world commercial MIDI: this sample is synthetically constructed from",
        "  explicit author intent. Real files with misleading track names, layered",
        "  instruments or mixed GM programs will produce more uncertainty.",
        "- Correctness of *accepted* user corrections: corrections are stored",
        "  separately and never evaluated against their original prediction as if",
        "  they were model accuracy.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["files"]
    evaluation = [item for item in labels if item.get("category") == "evaluation"]
    results = []
    correct = 0
    track_total = 0
    track_instrument_correct = 0
    track_role_correct = 0
    uncertain = []
    mistakes = []
    track_mistakes = []
    confidences_instrument = []
    confidences_role = []

    for item in evaluation:
        path = LIBRARY / item["path"]
        try:
            parse_result = parse_smf(path.read_bytes())
            analysis = analyze(parse_result, path.name, str(path.parent.relative_to(LIBRARY)))
            classification = classify(parse_result, analysis, path.name, str(path.parent.relative_to(LIBRARY)))
        except MidiParseError as exc:
            results.append({**item, "error": str(exc)})
            continue
        file_prediction = classification["file"]
        instrument_ok = file_prediction["instrument"] == item["instrument"]
        role_ok = file_prediction["role"] == item["role"]
        correct += int(instrument_ok and role_ok)
        confidences_instrument.append(file_prediction["instrument_confidence"])
        confidences_role.append(file_prediction["role_confidence"])
        result = {
            "path": item["path"],
            "expected_instrument": item["instrument"],
            "expected_role": item["role"],
            "predicted_instrument": file_prediction["instrument"],
            "predicted_role": file_prediction["role"],
            "instrument_correct": instrument_ok,
            "role_correct": role_ok,
            "confidence": min(
                file_prediction["instrument_confidence"],
                file_prediction["role_confidence"],
            ),
            "uncertain": file_prediction["uncertain"],
            "conflicts": [conflict["label"] for conflict in file_prediction.get("conflicts", [])],
            "instrument_evidence": [
                evidence["label"] for evidence in file_prediction.get("instrument_evidence", [])[:4]
            ],
            "role_evidence": [
                evidence["label"] for evidence in file_prediction.get("role_evidence", [])[:4]
            ],
            "note": item.get("note", ""),
        }
        if not (instrument_ok and role_ok):
            mistakes.append({
                **result,
                "note": item.get("note", "") or "Ambiguous evidence in this fixture.",
            })
        if file_prediction["uncertain"]:
            uncertain.append({
                "path": item["path"],
                "instrument": file_prediction["instrument"],
                "role": file_prediction["role"],
                "confidence": min(
                    file_prediction["instrument_confidence"],
                    file_prediction["role_confidence"],
                ),
                "flags": result["conflicts"] + file_prediction.get("uncertainty_notes", []),
            })
        expected_tracks = item.get("expected_tracks") or []
        for expected_track in expected_tracks:
            track = next(
                (
                    candidate for candidate in classification["tracks"]
                    if candidate.get("name") == expected_track["name"]
                ),
                None,
            )
            if not track:
                continue
            track_total += 1
            track_instrument_correct += int(track["instrument"] == expected_track["instrument"])
            track_role_correct += int(track["role"] == expected_track["role"])
            track_result = {
                "name": expected_track["name"],
                "expected": f"{expected_track['instrument']} / {expected_track['role']}",
                "predicted": f"{track['instrument']} / {track['role']}",
                "instrument_correct": track["instrument"] == expected_track["instrument"],
                "role_correct": track["role"] == expected_track["role"],
            }
            result.setdefault("tracks", []).append(track_result)
            if not (track_result["instrument_correct"] and track_result["role_correct"]):
                track_mistakes.append({
                    "path": item["path"],
                    **track_result,
                })
        results.append(result)

    sample_size = len(evaluation)
    instrument_correct = sum(1 for item in results if item.get("instrument_correct"))
    role_correct = sum(1 for item in results if item.get("role_correct"))
    report = {
        "sample_size": sample_size,
        "instrument_correct": instrument_correct,
        "role_correct": role_correct,
        "instrument_accuracy": instrument_correct / sample_size if sample_size else 0.0,
        "role_accuracy": role_correct / sample_size if sample_size else 0.0,
        "uncertain_count": len(uncertain),
        "mean_instrument_confidence": (
            sum(confidences_instrument) / len(confidences_instrument)
            if confidences_instrument else 0.0
        ),
        "mean_role_confidence": (
            sum(confidences_role) / len(confidences_role)
            if confidences_role else 0.0
        ),
        "track_sample_size": track_total,
        "track_instrument_correct": track_instrument_correct,
        "track_role_correct": track_role_correct,
        "track_instrument_accuracy": track_instrument_correct / track_total if track_total else 0.0,
        "track_role_accuracy": track_role_correct / track_total if track_total else 0.0,
        "labels": dict(Counter(item["instrument"] for item in evaluation)),
        "role_labels": dict(Counter(item["role"] for item in evaluation)),
        "correct": [
            {
                "path": item["path"],
                "instrument": item["predicted_instrument"],
                "role": item["predicted_role"],
                "confidence": item["confidence"],
            }
            for item in results
            if item.get("instrument_correct") and item.get("role_correct")
        ],
        "mistakes": mistakes,
        "track_mistakes": track_mistakes,
        "uncertain": uncertain,
        "results": results,
        "genre_evaluated": False,
        "method": "SKEER transparent rules, classifier version 1",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"sample={sample_size} instrument={instrument_correct}/{sample_size} "
        f"role={role_correct}/{sample_size} uncertain={len(uncertain)} "
        f"tracks={track_instrument_correct}/{track_total} family, "
        f"{track_role_correct}/{track_total} role"
    )
    if mistakes:
        print("Mismatches:")
        for mistake in mistakes:
            print(
                f"  {mistake['path']}: expected {mistake['expected_instrument']} / "
                f"{mistake['expected_role']}, got {mistake['predicted_instrument']} / "
                f"{mistake['predicted_role']}"
            )
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
