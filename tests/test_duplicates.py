from __future__ import annotations

import json
import unittest

from midivault.engine.duplicates import exact_groups, similar_groups
from midivault.engine.versions import FINGERPRINT_VERSION


class DuplicateTests(unittest.TestCase):
    def test_exact_groups_use_content_hash(self) -> None:
        files = [
            {"id": 1, "content_hash": "aaa", "scan_state": "indexed"},
            {"id": 2, "content_hash": "aaa", "scan_state": "indexed"},
            {"id": 3, "content_hash": "bbb", "scan_state": "indexed"},
            {"id": 4, "content_hash": None, "scan_state": "indexed"},
            {"id": 5, "content_hash": "ccc", "scan_state": "failed"},
        ]
        groups = exact_groups(files)
        self.assertEqual(len(groups), 1)
        self.assertEqual({item["id"] for item in groups[0]}, {1, 2})

    def test_similarity_is_conservative_and_separate(self) -> None:
        def make(file_id: int, pc: list[float], onset: list[float], *, tempo: float = 108.0):
            return {
                "id": file_id,
                "instrument": "Bass",
                "role": "Bassline",
                "tempo_bpm": tempo,
                "duration_seconds": 18.0,
                "note_count": 32,
                "scan_state": "indexed",
                "fingerprint_json": json.dumps({
                    "fv": FINGERPRINT_VERSION,
                    "pc": pc, "on": onset, "pitch_mean": 40, "density": 1.8,
                }),
            }

        pc_a = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.7, 0.0]
        pc_b = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.28, 0.0, 0.0, 0.72, 0.0]
        onset_a = [0.25, 0, 0, 0, 0.25, 0, 0, 0, 0.25, 0, 0, 0, 0.25, 0, 0, 0]
        onset_b = [0.24, 0, 0, 0, 0.26, 0, 0, 0, 0.25, 0, 0, 0, 0.25, 0, 0, 0]
        files = [make(1, pc_a, onset_a), make(2, pc_b, onset_b), make(3, pc_a, onset_a, tempo=150)]
        groups = similar_groups(files)
        self.assertEqual(len(groups), 1)
        self.assertEqual({item["id"] for item in groups[0]}, {1, 2})
        # A clearly different tempo must not be grouped.
        self.assertFalse(any(3 in {item["id"] for item in group} for group in groups))

    def test_a_fingerprint_without_a_generation_is_never_compared(self) -> None:
        """Identical vectors, one stamped and one not, must not be matched.

        The unstamped one came from a build that did not version fingerprints;
        there is no way to know what its numbers mean.
        """
        def make(file_id: int, payload: dict) -> dict:
            return {
                "id": file_id,
                "instrument": "Bass",
                "role": "Bassline",
                "tempo_bpm": 108.0,
                "duration_seconds": 18.0,
                "note_count": 32,
                "scan_state": "indexed",
                "fingerprint_json": json.dumps(payload),
            }

        core = {"pc": [0.5, 0, 0, 0, 0, 0, 0, 0.5, 0, 0, 0, 0], "on": [1.0] + [0.0] * 15,
                "pitch_mean": 40, "density": 1.8}
        stamped = make(1, {**core, "fv": FINGERPRINT_VERSION})
        unstamped = make(2, dict(core))
        other_generation = make(3, {**core, "fv": FINGERPRINT_VERSION + 7})

        self.assertEqual(similar_groups([stamped, unstamped]), [])
        self.assertEqual(similar_groups([stamped, other_generation]), [])
        self.assertEqual(similar_groups([unstamped, dict(make(4, core))]), [])
        # Same generation, same numbers: the signal itself still works.
        self.assertEqual(len(similar_groups([stamped, make(5, {**core, "fv": FINGERPRINT_VERSION})])), 1)


if __name__ == "__main__":
    unittest.main()
