"""One release number, in every file that states one.

A version bump is not done until every file that states the version states the same one, and
the ones that get missed are not Python strings: CMake writes `project(... VERSION)` into the
built bundle's `moduleinfo.json` and into the binary, so a host lists the plug-in by it, and
`packaging/EULA.txt` states the version on the licence page a user must accept before the
Install button enables. Ship an app at 1.1.0 beside a plug-in still claiming 1.0.0, or inside an
installer whose own licence page says 1.0.0, and the product contradicts itself.

What is probed is the PROBES table below and nothing else, and this file deliberately does not
repeat it in prose: a hand-counted tally of the coverage was stale the day it was written and
was short by the literal that mattered most. The run prints the table it actually read, and
`tests/test_version_consistency.py` holds its own REQUIRED list of (file, label) pairs, so a
probe that is deleted fails a test instead of quietly shrinking the gate.

`build/version_info.txt` alone carries four of them, and that is why it gets four probes:
Windows reads the fixed file info (`filevers`, `prodvers`) and the string table
(`FileVersion`, `ProductVersion`) separately, so a bump can reach one and miss the others
and still produce an installer whose product version disagrees with the binary it installs.
One probe does not see the other three.

`midivault/__init__.py` is the reference because it is the one the interface can see:
`/api/bootstrap` publishes it as `app.version`. Every other value is compared to it as a
numeric tuple, so `1.0.0`, `1.0.0.0` and `1, 0, 0, 0` are the same version and only a real
difference is a failure.

Run from anywhere: `python scripts/check_version_consistency.py`. `--root <dir>` points the
same probes at a copy (default: the repo this script lives in), which is what lets the test
suite prove the gate can fail without editing a tracked file. Exit 0 means every probed value
agrees and no FORBIDDEN literal has come back; 1 means one disagrees, a forbidden literal is
present, or a literal the checker looks for has moved.

FORBIDDEN is the other direction, and it exists because of a specific failure. The build script
used to state its own `$Version`, which named the portable ZIP and selected the files whose
hashes go in `SHA256SUMS.txt`, and nothing checked it: a bump that reached the installer script
and missed that one line produced a manifest with no rows in it and exit code 0. The build
script must derive its version from the reference file, so a literal assignment there is a
finding by itself.
`tests/test_version_consistency.py` runs this so the gate is part of
`python -m unittest discover -s tests`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (file, pattern, label). Each pattern must match exactly once: a literal that has been
# reformatted is reported as a missing value, not quietly skipped. The capture group is the
# version itself, which is what makes the file:line in the report useful.
PROBES = (
    ("midivault/__init__.py",
     r'(?m)^__version__ = "([^"]+)"$',
     "__version__"),
    ("packaging/skeer-midi-vault.iss",
     r'(?m)^#define AppVersion "([^"]+)"$',
     "AppVersion"),
    ("packaging/skeer-midi-vault.iss",
     r"(?m)^VersionInfoVersion=(\d[\d.]*)$",
     "VersionInfoVersion"),
    ("build/version_info.txt",
     r"(?m)^\s*filevers=\(([\d,\s]+)\)",
     "filevers"),
    ("build/version_info.txt",
     r"(?m)^\s*prodvers=\(([\d,\s]+)\)",
     "prodvers"),
    ("build/version_info.txt",
     r"(?m)^\s*StringStruct\(u'FileVersion',\s*u'([^']+)'\)",
     "FileVersion"),
    ("build/version_info.txt",
     r"(?m)^\s*StringStruct\(u'ProductVersion',\s*u'([^']+)'\)",
     "ProductVersion"),
    ("desktop.py",
     r'(?m)^VERSION = "([^"]+)"$',
     "VERSION"),
    ("web/package.json",
     r'(?m)^  "version": "([^"]+)",?$',
     "version"),
    ("plugin/CMakeLists.txt",
     r"(?m)^project\(\s*SkeerMidiVaultPlugin\s+VERSION\s+(\d[\d.]*)(?=\s|\))",
     "project VERSION"),
    ("packaging/EULA.txt",
     r"(?m)^\s*This version is (\d[\d.]+)\.\s*$",
     "licence page version"),
)

# (file, pattern, label, what a match means). A forbidden pattern that MATCHES is the finding;
# unlike PROBES there is no value to compare, so an unreadable file is reported and passed over
# rather than failing - the copy in a temp directory may legitimately hold only some targets.
FORBIDDEN = (
    ("packaging/build_installer.ps1",
     # (?i) because PowerShell variables are case-insensitive: $VERSION = "1.0.0" is the same
     # literal assignment as $Version = "1.0.0", and a case-sensitive probe would miss it.
     r'(?im)^\s*\$Version\s*=\s*["\x27]',
     "own version literal",
     "the build script must read the version from midivault/__init__.py"),
)

REFERENCE = "midivault/__init__.py"


def as_tuple(raw: str) -> tuple[int, ...] | None:
    """`1.0.0`, `1.0.0.0` and `1, 0, 0, 0` all normalise to (1, 0, 0)."""
    parts = [part.strip() for part in re.split(r"[.,\s]+", raw.strip()) if part.strip()]

    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None

    while len(numbers) > 3 and numbers[-1] == 0:
        numbers.pop()

    while len(numbers) < 3:
        numbers.append(0)

    return tuple(numbers)


def read_probe(root: Path, relpath: str, pattern: str, label: str) -> dict | None:
    path = root / relpath

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"  {relpath}: cannot be read ({exc})")
        return None

    match = re.search(pattern, text)

    if match is None:
        print(f"  {relpath}: no {label} here any more -- this gate would no longer see it")
        return None

    if re.search(pattern, text[match.end():]) is not None:
        print(f"  {relpath}: {label} appears more than once -- refusing to pick one")
        return None

    raw = match.group(1)
    line = text.count("\n", 0, match.start(1)) + 1

    return {
        "file": relpath,
        "line": line,
        "label": label,
        "raw": raw,
        "value": as_tuple(raw),
    }


def read_forbidden(root: Path, relpath: str, pattern: str, label: str, reason: str) -> dict | None:
    """One FORBIDDEN entry: a match is the finding, an absent match is what we want."""
    path = root / relpath

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"  {relpath}: cannot be read ({exc})")
        return None

    match = re.search(pattern, text)
    line = text.count("\n", 0, match.start()) + 1 if match else None

    return {"file": relpath, "line": line, "label": label, "reason": reason,
            "present": match is not None}


def main(root: Path = ROOT) -> int:
    found = [entry for entry in (read_probe(root, *probe) for probe in PROBES)
             if entry is not None]
    forbidden = [entry for entry in (read_forbidden(root, *probe) for probe in FORBIDDEN)
                 if entry is not None]

    if len(found) != len(PROBES):
        print(f"\n{len(found)} of {len(PROBES)} values found; the rest moved or vanished.")
        return 1

    unreadable = [entry for entry in found if entry["value"] is None]

    if unreadable:
        for entry in unreadable:
            print(f"  {entry['file']}:{entry['line']}  {entry['label']}: "
                  f"'{entry['raw']}' is not a version")
        return 1

    reference = next(entry for entry in found if entry["file"] == REFERENCE)
    expected = reference["value"]

    print("  file:line                              literal               value")

    for entry in found:
        print(f"  {entry['file'] + ':' + str(entry['line']):<38} "
              f"{entry['label']:<20}  {entry['raw']}")

    for entry in forbidden:
        where = f"{entry['file']}:{entry['line']}" if entry["present"] else entry["file"]
        state = "PRESENT - forbidden" if entry["present"] else "absent"
        print(f"  {where:<38} {entry['label']:<20}  {state}: {entry['reason']}")

    disagreeing = [entry for entry in found if entry["value"] != expected]

    files = len({entry["file"] for entry in found} | {entry["file"] for entry in forbidden})
    agreed = f"one version {'.'.join(str(part) for part in expected)}"

    if not disagreeing and not any(entry["present"] for entry in forbidden):
        print(f"\n{files} files, {len(found)} values, {agreed}.")
        return 0

    if disagreeing:
        print(f"\n{len(disagreeing)} of {len(found)} values disagree with "
              f"{reference['file']}:{reference['line']} "
              f"({'.'.join(str(part) for part in expected)}):")

        for entry in disagreeing:
            print(f"  {entry['file']}:{entry['line']}  {entry['label']}: {entry['raw']}")

    for entry in (entry for entry in forbidden if entry["present"]):
        print(f"  {entry['file']}:{entry['line']}  {entry['label']}: {entry['reason']}")

    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check that every stated version is the same one.")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="directory holding the probe targets (default: the repo this script lives in)",
    )
    sys.exit(main(parser.parse_args().root))
