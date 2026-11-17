"""Write and re-derive the provenance stamp a packaged build carries.

An artifact used to be attributable only by mtime, which proves nothing: a bundle can be
older than the source it was built from, or newer than a rebuild that was never run. This
module turns "the shipped bytes came from this tree" into a value the smoke test can assert.

The stamp records the commit, whether the tree was dirty at build time, and a digest of the
uncommitted diff, so a dirty build is still attributable to the exact working tree it came
from rather than being waved through because HEAD happens to match. `web_dist` is a digest
over the built interface, which is the half a stale bundle actually hides: the Python side is
recompiled by every run, while `web/dist` is a `--add-data` copy of a directory someone else
may have rebuilt afterwards.

Run from anywhere:

    python scripts/build_stamp.py --out build/BUILDINFO.json

Exits non-zero when git cannot be read. A release artifact that cannot name its commit is not
a release artifact; the build script fails loudly rather than shipping an anonymous binary.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str | None:
    """stdout of a git command, or None when git is unavailable or the call fails."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=str(ROOT), capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.decode("utf-8", "replace")


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def digest_tree(root: Path) -> str | None:
    """One hash over a directory: every file's own hash, keyed by sorted posix path.

    Content only, never mtime - a checkout rewrites timestamps without changing bytes, and a
    rebuild can rewrite bytes without changing them.
    """
    if not root.is_dir():
        return None

    hasher = hashlib.sha256()

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        hasher.update(b"\n")

    return hasher.hexdigest()


def digest_untracked() -> str:
    """Content of every untracked, non-ignored file, so a new source file cannot hide.

    `git status -uno` was the obvious first cut here and it is wrong for this: work-in-progress
    on a release is usually an untracked file, and a stamp that calls that tree clean makes the
    gate affirm the one thing it is supposed to refuse. Ignored paths (build output, `launch/`,
    `web/dist`) stay out, which is what keeps this cheap.
    """
    listing = git("ls-files", "--others", "--exclude-standard", "-z")

    if listing is None:
        return digest_text("")

    hasher = hashlib.sha256()

    for relative in sorted(part for part in listing.split("\0") if part):
        path = ROOT / relative
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(path.read_bytes() if path.is_file() else b"").hexdigest().encode("ascii"))
        hasher.update(b"\n")

    return hasher.hexdigest()


def stamp() -> dict[str, object]:
    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain") or ""
    diff = git("diff", "HEAD", "--binary") or ""

    return {
        "commit": commit.strip() if commit else None,
        "dirty": bool(status.strip()),
        "status_digest": digest_text(status),
        "diff_digest": digest_text(diff),
        "untracked_digest": digest_untracked(),
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "web_dist": digest_tree(ROOT / "web" / "dist"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the packaged build's provenance stamp.")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "BUILDINFO.json")
    parser.add_argument("--print", action="store_true", help="print the stamp instead of writing it")
    args = parser.parse_args(argv)

    value = stamp()

    if not value["commit"]:
        print("FAIL: git could not read this tree; a release build must name its commit.",
              file=sys.stderr)
        return 1

    if not value["web_dist"]:
        print("FAIL: web/dist is missing - build the interface before stamping the bundle.",
              file=sys.stderr)
        return 1

    text = json.dumps(value, indent=2, sort_keys=True) + "\n"

    if args.print:
        print(text, end="")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}: {value['commit'][:12]} "
          f"{'dirty' if value['dirty'] else 'clean'} "
          f"web/dist {str(value['web_dist'])[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
