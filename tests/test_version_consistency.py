"""The version gate: one release number, eight files, twelve checks.

Runs the repo's own checker, `scripts/check_version_consistency.py`, inside
`python -m unittest discover -s tests` so a bump that misses a file fails here instead of
shipping. The checker owns the parsing; this file owns the contract about what it must parse:
`REQUIRED` and `FORBIDDEN_REQUIRED` are written out here, independently of the checker's tables,
and `test_the_contract_matches_the_tables_the_checker_reads` compares them. That pair of
directions is the point. A probe deleted from the checker shrinks the gate silently and would
still leave every other test green; a probe added to the checker without being stated here
widens the gate without anyone agreeing to it. Either one fails a test now.

The red cases are the reason the green cases mean anything: a checker that probed nothing would
exit 0 on every run and pass all of them. Each red case builds a copy of the probe targets in a
temporary directory, moves one thing in the copy, and requires exit 1 naming it. `make_copy`
runs the checker on the pristine copy first, because a copy missing a file fails for a reason
that has nothing to do with the mutation -- and, seen the other way, that first run is the
positive control that the copy is complete enough to gate.

Nothing tracked is ever edited. The copy keeps the bytes exactly (`shutil.copyfile`, never a
read/write text round trip, which would rewrite every line ending on Windows).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_version_consistency.py"
BUILD_SCRIPT = ROOT / "packaging" / "build_installer.ps1"
REFERENCE = ROOT / "midivault" / "__init__.py"

sys.path.insert(0, str(ROOT / "scripts"))
import check_version_consistency as gate  # noqa: E402

# Every file the checker opens, so a copy can be made complete by construction.
WATCHED = (
    "midivault/__init__.py",
    "packaging/skeer-midi-vault.iss",
    "build/version_info.txt",
    "desktop.py",
    "web/package.json",
    "plugin/CMakeLists.txt",
    "packaging/EULA.txt",
    "packaging/build_installer.ps1",
)

# (file, label) pairs whose *value* must be read and compared. Eight files carry eleven of them:
# build/version_info.txt states four, because Windows reads the fixed file info and the string
# table separately, and packaging/skeer-midi-vault.iss states two.
REQUIRED = (
    ("midivault/__init__.py", "__version__"),
    ("packaging/skeer-midi-vault.iss", "AppVersion"),
    ("packaging/skeer-midi-vault.iss", "VersionInfoVersion"),
    ("build/version_info.txt", "filevers"),
    ("build/version_info.txt", "prodvers"),
    ("build/version_info.txt", "FileVersion"),
    ("build/version_info.txt", "ProductVersion"),
    ("desktop.py", "VERSION"),
    ("web/package.json", "version"),
    ("plugin/CMakeLists.txt", "project VERSION"),
    ("packaging/EULA.txt", "licence page version"),
)

# (file, label) pairs where a match is the finding, not a value to compare.
FORBIDDEN_REQUIRED = (
    ("packaging/build_installer.ps1", "own version literal"),
)

EXPECTED_VALUES = len(REQUIRED)
EXPECTED_FILES = len({*[what[0] for what in REQUIRED], *[what[0] for what in FORBIDDEN_REQUIRED]})


def stated_version() -> str:
    """The release the tree is on, read out of the reference file.

    The red cases move this version, never a version written into this file: a test that
    hardcoded 1.0.0 stops being a red case the moment the tree is bumped, and passes for the
    wrong reason forever after.
    """
    text = REFERENCE.read_text(encoding="utf-8")
    match = re.search(r'(?m)^__version__ = "([^"]+)"$', text)
    if match is None:
        raise AssertionError("midivault/__init__.py does not state __version__ in the expected form")
    return match.group(1)


VERSION = stated_version()
# build/version_info.txt states the fixed file info as a four-part tuple ending in 0.
FILEVERS = "(" + ", ".join(VERSION.split(".")) + ", 0)"


def value_row(file: str, label: str) -> str:
    """The checker's report row for one probed value: `file:line  label  value`."""
    return re.escape(file) + r":\d+\s+" + r"\s+".join(map(re.escape, label.split())) + r"\s+\S"


def negative_row(file: str, label: str) -> str:
    """The report row for one forbidden check that came back clean."""
    return re.escape(file) + r"\s+" + r"\s+".join(map(re.escape, label.split())) + r"\s+absent"



class VersionConsistencyTest(unittest.TestCase):
    def run_checker(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), *arguments],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def make_copy(self, copy: Path) -> Path:
        """Every probe target, byte for byte, and proof the untouched copy already passes.

        Without that proof a red case could be the copy being incomplete rather than the
        mutation, which is how a red case stops meaning anything.
        """
        for name in WATCHED:
            target = copy / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

        control = self.run_checker("--root", str(copy))
        self.assertEqual(
            0,
            control.returncode,
            "the pristine copy is not green, so nothing edited after this proves anything:\n"
            + control.stdout + control.stderr,
        )
        return copy

    def tamper(self, copy: Path, name: str, old: bytes, new: bytes) -> None:
        """Replace one literal in the copy, and fail loudly if that literal was not there."""
        path = copy / name
        original = path.read_bytes()
        self.assertIn(old, original, f"the copy's {name} does not hold the literal this test moves")
        path.write_bytes(original.replace(old, new, 1))

    def test_the_contract_matches_the_tables_the_checker_reads(self) -> None:
        """Neither direction of drift: the checker cannot shrink or grow this contract."""
        checker_values = [(probe[0], probe[2]) for probe in gate.PROBES]
        self.assertEqual(
            sorted(REQUIRED),
            sorted(checker_values),
            "the gate and this test no longer read the same literals; "
            "a probe deleted from the checker shrinks the gate unnoticed",
        )

        checker_negative = [(probe[0], probe[2]) for probe in gate.FORBIDDEN]
        self.assertEqual(
            sorted(FORBIDDEN_REQUIRED),
            sorted(checker_negative),
            "the gate and this test no longer forbid the same thing",
        )

    def test_the_literals_agree(self) -> None:
        result = self.run_checker()
        self.assertEqual(
            0,
            result.returncode,
            "the version literals disagree:\n" + result.stdout + result.stderr,
        )

    def test_the_gate_reports_every_required_literal(self) -> None:
        result = self.run_checker()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        for file, label in REQUIRED:
            self.assertRegex(
                result.stdout,
                value_row(file, label),
                f"{file} {label} was not reported, so it is not being gated:\n{result.stdout}",
            )

        for file, label in FORBIDDEN_REQUIRED:
            self.assertRegex(
                result.stdout,
                negative_row(file, label),
                f"{file} was never checked for its {label}:\n{result.stdout}",
            )

        self.assertIn(f"{EXPECTED_FILES} files", result.stdout, result.stdout)
        self.assertIn(f"{EXPECTED_VALUES} values", result.stdout, result.stdout)

    def test_a_bumped_copy_fails(self) -> None:
        """One literal moved in a copy must fail the gate, and name the line it moved on."""
        with tempfile.TemporaryDirectory() as scratch:
            copy = self.make_copy(Path(scratch))
            self.tamper(copy, "build/version_info.txt",
                        f"filevers={FILEVERS}".encode(), f"filevers={FILEVERS.replace(', 0)', ', 1)')}".encode())
            result = self.run_checker("--root", str(copy))

        self.assertEqual(
            1,
            result.returncode,
            "a copy with one moved literal passed the gate:\n" + result.stdout + result.stderr,
        )
        self.assertIn(f"1 of {EXPECTED_VALUES} values disagree", result.stdout, result.stdout)
        self.assertIn("build/version_info.txt:3", result.stdout, result.stdout)

    def test_a_probe_that_stopped_matching_is_a_failure_not_a_shrink(self) -> None:
        """A literal the checker can no longer find must be a finding.

        Otherwise reformatting one file takes that value out of the gate and every later bump of
        it passes forever. The message asserted here is the one that says the coverage shrank.
        """
        with tempfile.TemporaryDirectory() as scratch:
            copy = self.make_copy(Path(scratch))
            self.tamper(copy, "packaging/EULA.txt",
                        f"This version is {VERSION}.".encode(), f"Release {VERSION} of this agreement.".encode())
            result = self.run_checker("--root", str(copy))

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("packaging/EULA.txt: no licence page version here any more",
                      result.stdout, result.stdout)
        self.assertIn(f"{EXPECTED_VALUES - 1} of {EXPECTED_VALUES} values found; "
                      "the rest moved or vanished", result.stdout, result.stdout)

    def test_a_version_literal_in_the_build_script_fails(self) -> None:
        """The forbidden direction, spelled the way PowerShell does not care about.

        `$VERSION` and `$Version` are one variable, so the probe has to be case-insensitive. This
        plants the differently-cased form: a probe that only caught today's spelling would pass a
        script that renamed it.
        """
        with tempfile.TemporaryDirectory() as scratch:
            copy = self.make_copy(Path(scratch))
            script = copy / "packaging" / "build_installer.ps1"
            script.write_bytes(script.read_bytes() + b'\n$VERSION = "9.9.9"\n')
            self.assertIn(b'$VERSION = "9.9.9"', script.read_bytes())
            result = self.run_checker("--root", str(copy))

        self.assertEqual(
            1,
            result.returncode,
            "a build script stating its own version passed the gate:\n" + result.stdout + result.stderr,
        )
        self.assertIn("packaging/build_installer.ps1", result.stdout, result.stdout)
        self.assertIn("PRESENT - forbidden", result.stdout, result.stdout)

    def test_the_build_script_derives_its_version_from_the_reference(self) -> None:
        """The positive half of the check above: the script's own derivation actually works.

        The gate proves no literal assignment; this proves the script then *finds* a version. An
        empty `$Version` would name every artifact `SKEER-MIDI-VAULT-Setup-.exe` and leave the
        release-file count as the only thing noticing.
        """
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        assignment = re.search(r"(?im)^[ \t]*\$Version[ \t]*=[ \t]*\[regex\]::Match[^\r\n]*", script)
        self.assertIsNotNone(
            assignment,
            "build_installer.ps1 no longer derives $Version with [regex]::Match, so this test "
            "cannot see what it derives it from",
        )

        pattern = re.search(r"'([^']+)'", assignment.group(0))
        self.assertIsNotNone(pattern, "the $Version assignment holds no PowerShell regex literal")
        self.assertIn("__version__", pattern.group(1),
                      "the $Version assignment does not read __version__ from the reference file")

        derived = re.search(pattern.group(1), REFERENCE.read_text(encoding="utf-8"))
        self.assertIsNotNone(derived, f"{pattern.group(1)!r} matches nothing in midivault/__init__.py")

        reference = re.search(r'(?m)^__version__ = "([^"]+)"$', REFERENCE.read_text(encoding="utf-8"))
        self.assertEqual(
            reference.group(1),
            derived.group(1),
            "the build script derives a version the interface does not publish",
        )



if __name__ == "__main__":
    unittest.main()
