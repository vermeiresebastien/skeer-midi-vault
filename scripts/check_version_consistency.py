"""One release number, six files.

A version bump is not done until every file that states the version states the same one,
and the sixth is easy to forget because it is not a string in a Python file: CMake writes
`project(... VERSION)` into the built bundle's `moduleinfo.json` and into the binary, so a
host lists the plug-in by it. Ship an app at 1.0.1 beside a plug-in still claiming 1.0.0
and the product contradicts itself in the one place a DAW reads.

Ten values live across six files:

    midivault/__init__.py                 __version__
    packaging/skeer-midi-vault.iss        AppVersion, VersionInfoVersion
    build/version_info.txt                filevers
    desktop.py                            VERSION
    web/package.json                      version
    plugin/CMakeLists.txt                 project(... VERSION)

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
suite prove the gate can fail without editing a tracked file. Exit 0 means all ten values
agree; 1 means at least one disagrees or a literal the checker looks for has moved.
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


def main(root: Path = ROOT) -> int:
    found = [entry for entry in (read_probe(root, *probe) for probe in PROBES)
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

    disagreeing = [entry for entry in found if entry["value"] != expected]

    files = len({entry["file"] for entry in found})
    agreed = f"one version {'.'.join(str(part) for part in expected)}"

    if not disagreeing:
        print(f"\n{files} files, {len(found)} values, {agreed}.")
        return 0

    print(f"\n{len(disagreeing)} of {len(found)} values disagree with "
          f"{reference['file']}:{reference['line']} "
          f"({'.'.join(str(part) for part in expected)}):")

    for entry in disagreeing:
        print(f"  {entry['file']}:{entry['line']}  {entry['label']}: {entry['raw']}")

    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check that every stated version is the same one.")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="directory holding the six probe targets (default: the repo this script lives in)",
    )
    sys.exit(main(parser.parse_args().root))
