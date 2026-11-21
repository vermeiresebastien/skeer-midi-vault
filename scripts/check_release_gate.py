"""Prove `scripts/release_check.ps1` can be trusted: green on a clean tree, red per defect.

A gate nobody has seen go red is not known to be a gate, and this one cannot be falsified in
place: bumping a version literal to force a red `gate` row would break the eleven-literal
agreement the rest of the tree depends on, and the real `launch/` can never satisfy the
checksums stage while it holds another release's artifacts. So the shadow repo gets byte copies
of the files the gate reads, plus a `launch/` of throwaway artifacts, and each case mutates one
thing.

The expensive stages are driven the same way. `plugin\build.ps1`, `packaging\build_installer.ps1`,
`tests\test_packaged_smoke.py` and `packaging\install_cycle_check.ps1` are replaced in the shadow
by stubs that print a chosen verdict and exit with a chosen code, so the stage logic that reads
them - the part that can be wrong while every build is fine - runs against real output. This is
how the ctest parse was caught: ctest prints "100% tests passed out of 6" when nothing failed and
only adds the ", N tests failed" clause when something did, so a regex demanding that clause makes
the stage permanently red, which reads exactly like a caught defect.

Case A is the load-bearing control: it is the only place the gate's PASS rows are ever seen.

    python scripts/check_release_gate.py

Exit 0 means every row moved for its own cause and every exit code matched the documented
contract (0 READY, 1 failed stage, 2 skipped stage).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHADOW = REPO / "build" / "work" / "release-gate-falsifier"
LAUNCH = SHADOW / "launch"
STAGES = ["-Stages"]
MARK = {"ok  ": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}
PROBLEMS: list[str] = []

# The files the gate reads; the copy is what makes a mutation harmless.
TARGETS = [
    "midivault/__init__.py",
    "packaging/skeer-midi-vault.iss",
    "packaging/EULA.txt",
    "packaging/build_installer.ps1",
    "desktop.py",
    "build/version_info.txt",
    "web/package.json",
    "plugin/CMakeLists.txt",
    "scripts/check_version_consistency.py",
    "scripts/release_check.ps1",
]
VERSION = re.search(
    rb'__version__ = "([^"]+)"', (REPO / "midivault/__init__.py").read_bytes()
).group(1).decode()
SETUP = f"SKEER-MIDI-VAULT-Setup-{VERSION}.exe"
PORTABLE = f"SKEER-MIDI-VAULT-Portable-{VERSION}.zip"
HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                      capture_output=True, check=True).stdout.decode().strip()

# The plug-in and interface stages reach for tools and checkouts this harness cannot create, so
# their cases only run where the real stage would. Which tree the gate looks at is fixed inside
# release_check.ps1, so these paths have to be the same ones.
JUCE_804 = Path("D:/Projects/skeer-audio/skulpt/external/JUCE")
JUCE_808 = Path("D:/Projects/skeer-audio/pulsekit/build/_deps/juce-src")
PLUGIN_RUNNABLE = JUCE_804.is_dir() and bool(shutil.which("cmake"))
NPM = bool(shutil.which("npm"))


def sha256sum() -> str | None:
    """The publisher's verifier, or None.

    The gate treats its absence as a stated limitation rather than a pass, and so does this
    harness: case A only asserts the interop row when the tool actually ran.
    """
    for candidate in ("sha256sum", r"C:\Program Files\Git\usr\bin\sha256sum.exe",
                      r"C:\Program Files\Git\coreutils\bin\sha256sum.exe"):
        found = shutil.which(candidate)
        if found:
            return found
        if Path(candidate).is_file():
            return candidate
    return None


def write_manifest(*, crlf: bool = False, corrupt: bool = False) -> None:
    """Rows for the artifacts, never for the manifest itself, as build_installer.ps1 writes it.

    A manifest that lists itself is unsatisfiable - hashing it changes the file being hashed -
    and an early draft of this harness produced one, which the gate reported as a plain "hash
    differs". Keeping it out is what makes each case's failure attributable to its own cause.
    """
    rows = []
    for name in sorted(p.name for p in LAUNCH.iterdir()
                       if p.is_file() and p.name != "SHA256SUMS.txt"):
        digest = hashlib.sha256((LAUNCH / name).read_bytes()).hexdigest()
        if corrupt and name.endswith(".exe"):
            digest = "0" * 64
        rows.append(f"{digest}  {name}")
    sep = "\r\n" if crlf else "\n"
    (LAUNCH / "SHA256SUMS.txt").write_bytes((sep.join(rows) + sep).encode("ascii"))


def stub(rel: str, body: str) -> None:
    path = SHADOW / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def build_tree(*, ctest: str = "", build_exit: int = 0) -> None:
    """A pristine shadow repo. `ctest` is the line the stub plug-in build prints, if any."""
    if SHADOW.exists():
        shutil.rmtree(SHADOW)
    for rel in TARGETS:
        source = REPO / rel
        if not source.is_file():
            raise SystemExit(f"FAIL: the gate is meant to read {rel}, which is not in this tree")
        dest = SHADOW / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
    LAUNCH.mkdir(parents=True)
    (LAUNCH / SETUP).write_bytes(b"\x00" * 4096)
    (LAUNCH / PORTABLE).write_bytes(b"\x00" * 8192)
    write_manifest()
    # The control's licence page must be green whatever the real page holds, so the two
    # human-answer lines are pinned to sentinels here rather than by replacing a placeholder
    # marker. Pinning by marker left the control dependent on a defect: the day a seller filled
    # EULA.txt, this assert failed and case F's plant found nothing to redden.
    eula = SHADOW / "packaging/EULA.txt"
    text = eula.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^([ \t]*Licence and support enquiries:).*$",
                  r"\1 legal@example.test", text)
    text = re.sub(r"(?m)^([ \t]*This agreement is governed by the law of).*$",
                  r"\1 the Netherlands", text)
    assert "<<<FILL:" not in text, "the control EULA must hold no unfilled field"
    eula.write_text(text, encoding="utf-8")

    # The stubs the expensive stages drive. The plug-in stub takes the same parameters as the
    # real script, because release_check passes them positionally by name.
    if ctest:
        stub("plugin/build.ps1", f"""
param([string] $BuildDir, [string] $Juce, [string] $Config)
Write-Output 'Building 100% done'
Write-Output '{ctest}'
exit {build_exit}
""")
    stub("packaging/install_cycle_check.ps1", "exit 0\n")


def stamp(commit: str | None = HEAD, dirty: bool = False) -> None:
    """Write a BUILDINFO.json the stamp stage can read; commit=None drops the key entirely."""
    path = SHADOW / "build/BUILDINFO.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if commit == "":
        path.write_text('{"commit": "a", "dirty": fal', encoding="utf-8")  # not JSON
        return
    fields = [] if commit is None else [f'"commit": "{commit}"']
    fields.append('"dirty": ' + ("true" if dirty else "false"))
    for key in ("status_digest", "diff_digest", "untracked_digest", "web_dist"):
        fields.append(f'"{key}": "{hashlib.sha256(key.encode()).hexdigest()}"')
    fields.append('"built_at": "2026-11-17T00:00:00+00:00"')
    path.write_text("{\n  " + ",\n  ".join(fields) + "\n}\n", encoding="utf-8")


def check(label: str, args: list[str], want: dict[str, str], want_exit: int,
          snippets: tuple[str, ...] = ()) -> None:
    done = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(SHADOW / "scripts/release_check.ps1"), *args],
        capture_output=True, cwd=str(REPO))
    out = done.stdout.decode("utf-8", "replace")
    print("=" * 78)
    print(label)
    for line in out.splitlines():
        if line.startswith("[") or "READY" in line or "stage(s)" in line or "stages selected" in line:
            print("   ", line)
    print("    exit:", done.returncode)

    seen = {m.group(2): MARK[m.group(1)] for m in
            re.finditer(r"\[(ok  |FAIL|SKIP)\] (\w+) - ", out)}
    for stage, want_state in want.items():
        if seen.get(stage) != want_state:
            PROBLEMS.append(f"{label}: {stage} row is {seen.get(stage)!r}, wanted {want_state!r}")
    for extra in sorted(set(seen) - set(want)):
        PROBLEMS.append(f"{label}: printed a row for {extra}, which this case did not select")
    for snippet in snippets:
        if snippet not in out:
            PROBLEMS.append(f"{label}: output does not contain {snippet!r}")
    if done.returncode != want_exit:
        PROBLEMS.append(f"{label}: exit {done.returncode}, wanted {want_exit}")


def main() -> int:
    cheap()
    expensive()
    print()
    if PROBLEMS:
        print("FALSIFIER PROBLEMS")
        for problem in PROBLEMS:
            print("  -", problem)
        return 1
    print("FALSIFIER OK: every row moved for its own reason and the exit codes are as documented")
    return 0


def cheap() -> None:
    control = ("no placeholders", "READY - 3 passed, 0 failed, 0 skipped")
    if sha256sum():
        control += ("sha256sum -c exit 0",)
    else:
        print("note: sha256sum is not on this machine, so case A cannot assert the interop row")

    build_tree()
    check("A control: a clean tree reads READY", STAGES + ["gate,licence,checksums"],
          {"gate": "PASS", "licence": "PASS", "checksums": "PASS"}, 0, control)

    build_tree()
    broken = SHADOW / "build/version_info.txt"
    text = broken.read_text(encoding="utf-8")
    # Move whatever the tree's own FileVersion literal reads, not a number written here. This
    # case used to replace the string u'1.1.0', so the day the release moved to 1.1.1 the
    # substitution changed nothing: the gate correctly read a clean tree, printed its PASS row,
    # and the case went red as if the gate were blind. A plant that cannot be located has to
    # say so, or the case is decoration.
    plant = re.search(r"(StringStruct\(u'FileVersion', u')([^']+)('\))", text)
    if not plant:
        PROBLEMS.append("B gate: no FileVersion literal in the form this case plants, so it "
                        "moved nothing and cannot prove the gate reads the version checker")
    else:
        broken.write_text(text[:plant.start(2)] + "9.9.9" + text[plant.end(2):], encoding="utf-8")
        line = text[:plant.start()].count("\n") + 1
        check("B gate: one literal out of step", STAGES + ["gate"], {"gate": "FAIL"}, 1,
              (f"build/version_info.txt:{line}", "FileVersion: 9.9.9"))

    build_tree()
    script = SHADOW / "packaging/build_installer.ps1"
    script.write_text('$Version = "9.9.9"\r\n' + script.read_text(encoding="utf-8"),
                      encoding="utf-8")
    check("B2 gate: a version literal re-appears in the build script",
          STAGES + ["gate"], {"gate": "FAIL"}, 1,
          ("own version literal", "packaging/build_installer.ps1:1"))

    build_tree()
    write_manifest(crlf=True)
    check("C checksums: CRLF manifest", STAGES + ["checksums"], {"checksums": "FAIL"}, 1,
          ("CRLF in the manifest",))

    build_tree()
    write_manifest(corrupt=True)
    check("D checksums: a hash that does not match the bytes",
          STAGES + ["checksums"], {"checksums": "FAIL"}, 1, ("hash differs",))

    build_tree()
    (LAUNCH / "SHA256SUMS.txt").write_bytes(
        (hashlib.sha256((LAUNCH / PORTABLE).read_bytes()).hexdigest() + "  " + PORTABLE + "\n")
        .encode("ascii"))
    check("E checksums: an artifact the manifest does not name",
          STAGES + ["checksums"], {"checksums": "FAIL"}, 1,
          ("missing from the manifest", "1 row(s)"))

    build_tree()
    (LAUNCH / "SKEER-MIDI-VAULT-Setup-1.0.0.exe").write_bytes(b"\x00" * 512)
    write_manifest()
    check("E2 checksums: a previous release still sitting in launch/",
          STAGES + ["checksums"], {"checksums": "FAIL"}, 1,
          ("named but not a " + VERSION + " release file",))

    build_tree()
    eula = SHADOW / "packaging/EULA.txt"
    eula.write_text(eula.read_text(encoding="utf-8").replace(
        "legal@example.test", "<<<FILL: contact>>>"), encoding="utf-8")
    check("F licence: a placeholder left in", STAGES + ["licence"], {"licence": "FAIL"}, 1,
          ("unfilled field",))

    build_tree()
    eula = SHADOW / "packaging/EULA.txt"
    eula.write_text(eula.read_text(encoding="utf-8").replace(
        f"This version is {VERSION}.", "This version is 0.0.0."), encoding="utf-8")
    check("F2 licence: the page states another release", STAGES + ["licence"],
          {"licence": "FAIL"}, 1, ("the licence page states '0.0.0'",))

    build_tree()
    (SHADOW / "packaging/install_cycle_check.ps1").unlink()
    check("G skip: a stage that cannot run is INCOMPLETE, never READY",
          STAGES + ["gate,installed"], {"gate": "PASS", "installed": "SKIP"}, 2,
          ("INCOMPLETE - 1 passed, 0 failed, 1 skipped", "not verified: installed"))

    build_tree()
    check("H guard: an unknown stage name is refused", STAGES + ["nonsense"], {}, 1,
          ("unknown stage(s)",))

    build_tree()
    check("I guard: a blank stage list is refused, not an empty pass", STAGES + [" "], {}, 1,
          ("no stages selected",))


def expensive() -> None:
    """Every stage that drives a child process, against output this harness controls."""

    if not PLUGIN_RUNNABLE:
        print("note: no cmake or no JUCE tree at " + str(JUCE_804) +
              ", so the plug-in stages cannot be driven here")
    else:
        plugin_cases()

    installer_and_provenance_cases()


def plugin_cases() -> None:
    build_tree(ctest="100% tests passed out of 6")
    check("J plugin: ctest's green form has no failure clause", STAGES + ["plugin"],
          {"plugin": "PASS"}, 0, ("ctest 6/6 passed",))

    build_tree(ctest="67% tests passed, 2 tests failed out of 6", build_exit=1)
    check("K plugin: a red suite cannot read green", STAGES + ["plugin"], {"plugin": "FAIL"}, 1,
          ("2 tests failed out of 6",))

    build_tree(ctest="100% tests passed out of 5")
    check("L plugin: a suite that shrank is a failure, not a pass", STAGES + ["plugin"],
          {"plugin": "FAIL"}, 1, ("out of 5",))

    build_tree(ctest="100% tests passed out of 6", build_exit=1)
    check("M plugin: a build that exits non-zero after a green summary",
          STAGES + ["plugin"], {"plugin": "FAIL"}, 1, ("exit 1",))

    build_tree()
    (SHADOW / "plugin").mkdir(parents=True, exist_ok=True)
    (SHADOW / "plugin/build.ps1").write_text(
        "param([string] $BuildDir, [string] $Juce, [string] $Config)\n"
        "Write-Output 'cmake configure failed'\nexit 1\n", encoding="utf-8")
    check("N plugin: no ctest summary at all", STAGES + ["plugin"], {"plugin": "FAIL"}, 1,
          ("nothing that looks like a ctest summary",))

    if not JUCE_808.is_dir():
        build_tree()
        check("O plugin808: no second JUCE tree is a stated skip, not a pass",
              STAGES + ["plugin808"], {"plugin808": "SKIP"}, 2, ("no JUCE tree at",))


def installer_and_provenance_cases() -> None:
    build_tree()
    stub("packaging/build_installer.ps1", "exit 0\n")
    check("P installer: exit 0 with both artifacts present", STAGES + ["installer"],
          {"installer": "PASS"}, 0, ("Setup ", "bytes, ZIP "))

    build_tree()
    stub("packaging/build_installer.ps1", "exit 0\n")
    (LAUNCH / PORTABLE).unlink()
    check("P2 installer: exit 0 but the ZIP was never produced",
          STAGES + ["installer"], {"installer": "FAIL"}, 1, ("ZIP False",))

    build_tree()
    stub("packaging/build_installer.ps1", "exit 3\n")
    check("Q installer: a non-zero build cannot be talked into passing",
          STAGES + ["installer"], {"installer": "FAIL"}, 1, ("exit 3",))

    build_tree()
    stamp()
    check("R stamp: the artifact names this commit and a clean tree", STAGES + ["stamp"],
          {"stamp": "PASS"}, 0, ("commit " + HEAD[:12] + ", clean",))

    build_tree()
    stamp(commit="0" * 40)
    check("R2 stamp: built from another commit", STAGES + ["stamp"], {"stamp": "FAIL"}, 1,
          ("the artifact is not this commit",))

    build_tree()
    stamp(dirty=True)
    check("R3 stamp: built from a dirty tree", STAGES + ["stamp"], {"stamp": "FAIL"}, 1,
          ("dirty tree",))

    build_tree()
    check("R4 stamp: no stamp at all", STAGES + ["stamp"], {"stamp": "FAIL"}, 1,
          ("BUILDINFO.json is missing",))

    build_tree()
    stamp(commit="")
    check("R5 stamp: a stamp that is not readable JSON", STAGES + ["stamp"],
          {"stamp": "FAIL"}, 1, ("not readable JSON",))

    build_tree()
    stamp(commit=None)
    check("R6 stamp: a stamp with no commit key", STAGES + ["stamp"], {"stamp": "FAIL"}, 1,
          ("names no commit",))

    build_tree()
    stub("tests/test_packaged_smoke.py", """import sys
print("built from abc123def clean")
print("PASS packaged smoke test")
sys.exit(0)
""")
    check("S smoke: the packaged run says PASS", STAGES + ["smoke"], {"smoke": "PASS"}, 0,
          ("bundle built from abc123def",))

    build_tree()
    stub("tests/test_packaged_smoke.py", """import sys
print("FAIL: packaged executable missing")
sys.exit(1)
""")
    check("S2 smoke: the packaged run fails", STAGES + ["smoke"], {"smoke": "FAIL"}, 1,
          ("exit 1",))

    build_tree()
    check("T installed: the cycle script passes when it exits 0", STAGES + ["installed"],
          {"installed": "PASS"}, 0, ())

    build_tree()
    stub("packaging/install_cycle_check.ps1", "exit 1\n")
    check("T2 installed: the cycle script reddens on its own exit code",
          STAGES + ["installed"], {"installed": "FAIL"}, 1, ("exit 1",))

    # The gate's restricted-shell path: when the full cycle cannot run, it asks the same script for
    # the payload-only pass inside the workspace. That pass may downgrade FAIL to SKIP -- never to a
    # PASS, and never when the payload itself is broken. Both directions are required: the branch is
    # only worth having if a red payload row still reddens the stage.
    refused = (
        "param([switch]$FilesOnly, [string]$Dir)\n"
        "if ($FilesOnly) {\n"
        "  Write-Output '[ok  ] files - 199 file(s) installed, all 198 payload file(s), nothing extra'\n"
        "  Write-Output 'CYCLE INCOMPLETE - 3 phase(s) skipped, of 8'\n"
        "  exit 2\n"
        "}\n"
        "Write-Output 'CYCLE FAILED - Setup did not install: Error 5 creating the uninstall key'\n"
        "exit 1\n"
    )
    build_tree()
    stub("packaging/install_cycle_check.ps1", refused)
    check("T3 installed: registration refused but the payload graded intact is a SKIP, not a FAIL",
          STAGES + ["installed"], {"installed": "SKIP"}, 2,
          ("payload intact", "198 payload file(s)"))

    broken = refused.replace("[ok  ] files - 199 file(s) installed, all 198 payload file(s),"
                             " nothing extra",
                             "[FAIL] files - 3 of 198 payload file(s) are missing")
    build_tree()
    stub("packaging/install_cycle_check.ps1", broken)
    check("T4 installed: a broken payload cannot be softened into a SKIP",
          STAGES + ["installed"], {"installed": "FAIL"}, 1,
          ("payload pass exit 2", "3 of 198 payload file(s) are missing"))

    if NPM:
        # The shadow has a package.json and no node_modules, so the real npm run fails and the
        # stage must follow the exit code. Its PASS branch is a bare `$code -eq 0` and is covered
        # by the full run on the real tree, not by anything here.
        build_tree()
        check("U web: npm cannot build an interface with no dependencies installed",
              STAGES + ["web"], {"web": "FAIL"}, 1, ())
    else:
        build_tree()
        check("U web: no npm is a stated skip, not a pass",
              STAGES + ["web"], {"web": "SKIP"}, 2, ())


if __name__ == "__main__":
    raise SystemExit(main())
