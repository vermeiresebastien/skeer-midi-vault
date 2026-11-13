from __future__ import annotations

import json
import unittest
from pathlib import Path

from midivault.engine.analytics import analyze
from midivault.engine.classifier import classify
from midivault.engine.smf_parser import parse_smf

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "fixtures" / "demo_library"
LABELS = ROOT / "fixtures" / "demo_labels.json"


class DemoAccuracyTests(unittest.TestCase):
    def test_evaluation_sample_remains_above_threshold(self) -> None:
        labels = json.loads(LABELS.read_text(encoding="utf-8"))["files"]
        evaluation = [item for item in labels if item.get("category") == "evaluation"]
        self.assertGreaterEqual(len(evaluation), 25)
        instrument_correct = 0
        role_correct = 0
        for item in evaluation:
            path = LIBRARY / item["path"]
            parse_result = parse_smf(path.read_bytes())
            analysis = analyze(parse_result, path.name, str(path.parent.name))
            classification = classify(parse_result, analysis, path.name, str(path.parent.name))
            instrument_correct += int(classification["file"]["instrument"] == item["instrument"])
            role_correct += int(classification["file"]["role"] == item["role"])
        total = len(evaluation)
        self.assertGreaterEqual(instrument_correct / total, 0.9)
        self.assertGreaterEqual(role_correct / total, 0.9)


if __name__ == "__main__":
    unittest.main()
