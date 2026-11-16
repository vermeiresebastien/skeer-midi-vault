"""The version gate: one release number, six files.

Runs the repo's own checker, `scripts/check_version_consistency.py`, inside
`python -m unittest discover -s tests` so a bump that misses a file fails here
instead of shipping. The checker owns the parsing; this test owns the contract
that all six files and all ten values are actually read, because a gate that
silently reads five of them would pass forever.

`test_a_bumped_copy_fails` is the red case, and it is the reason the green cases
mean anything: a checker that probed nothing would exit 0 on every run and pass
both of them. The red case builds a copy of the six probe targets in a temporary
directory, moves one literal, and requires exit 1 with that literal named.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_version_consistency.py"

# The six files AGENTS.md names, in the order it names them.
WATCHED = (
    "midivault/__init__.py",
    "packaging/skeer-midi-vault.iss",
    "build/version_info.txt",
    "desktop.py",
    "web/package.json",
    "plugin/CMakeLists.txt",
)

# build/version_info.txt states four of the ten values: Windows reads the fixed file info
# and the string table separately, so a bump can reach one and miss the others.
EXPECTED_VALUES = 10


class VersionConsistencyTest(unittest.TestCase):
    def run_checker(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), *arguments],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_all_six_literals_agree(self) -> None:
        result = self.run_checker()
        self.assertEqual(
            0,
            result.returncode,
            "the version literals disagree:\n" + result.stdout + result.stderr,
        )

    def test_the_gate_reads_all_six_files(self) -> None:
        result = self.run_checker()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        never_reported = [name for name in WATCHED if name not in result.stdout]
        self.assertEqual(
            [],
            never_reported,
            "the checker never printed these files, so it is not gating them:\n" + result.stdout,
        )
        self.assertIn(f"{len(WATCHED)} files", result.stdout, result.stdout)
        self.assertIn(f"{EXPECTED_VALUES} values", result.stdout, result.stdout)

    def test_a_bumped_copy_fails(self) -> None:
        """The red case: one literal moved in a copy must fail, named.

        Nothing tracked is edited. The copy keeps the bytes exactly (read_bytes/write_bytes,
        never read_text, which would rewrite every line ending on Windows and make the other
        probes miss for a reason that has nothing to do with the bump).
        """
        with tempfile.TemporaryDirectory() as scratch:
            copy = Path(scratch)

            for name in WATCHED:
                target = copy / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)

            bumped = copy / "build" / "version_info.txt"
            original = bumped.read_bytes()
            bumped.write_bytes(original.replace(b"filevers=(1, 0, 0, 0)",
                                                b"filevers=(1, 0, 0, 1)"))
            self.assertNotEqual(original, bumped.read_bytes(),
                                "the copy's filevers was not the literal this test moves")

            result = self.run_checker("--root", str(copy))

        self.assertEqual(
            1,
            result.returncode,
            "a copy with one moved literal passed the gate:\n" + result.stdout + result.stderr,
        )
        self.assertIn(f"1 of {EXPECTED_VALUES} values disagree", result.stdout, result.stdout)
        self.assertIn("build/version_info.txt:3", result.stdout, result.stdout)


if __name__ == "__main__":
    unittest.main()
