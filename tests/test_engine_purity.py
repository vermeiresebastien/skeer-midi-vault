"""Engine purity: `midivault/engine/` takes bytes and returns dataclasses, and imports nothing
from the layers above it.

AGENTS.md states this as a non-negotiable, and until this file the only thing enforcing it was a
human remembering to grep - which is how a rule survives exactly as long as the person who wrote
it. So the gate here reads the *same sentence* out of AGENTS.md, and compares it against the list
this test enforces, in both directions: a name deleted from the sentence shrinks the rule and
must fail here, and a name added to this list without being stated in the rule must fail too. That
pair is the point; see tests/test_version_consistency.py for the same shape against the version
checker.

The green case on the real tree is nearly free. The red cases are what make it mean anything: each
one copies the package into a temporary directory, plants one import, and requires the scanner to
name that file. A scanner that parsed nothing would report a clean engine and pass every green
assertion forever, so the copy tests double as proof that the parser sees function-local and
package-relative imports, not just a top-of-file spelling.

Nothing tracked is edited. The copy keeps the bytes exactly (`shutil.copyfile`), because a text
round trip would rewrite every line ending on Windows.
"""
from __future__ import annotations

import ast
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
PACKAGE = ROOT / "midivault" / "engine"

# The package whose imports are gated, and the top-level package it must stay out of touching.
GATED_PACKAGE = "midivault.engine"
LOCAL_PACKAGE = "midivault"

# What the rule in AGENTS.md must name. `SQLITE_MARKERS` is what "know about SQLite" means in code:
# the stdlib driver, spelled the only way it is ever imported.
FORBIDDEN_NAMES = {"db", "api", "scanner"}
SQLITE_MARKERS = {"sqlite3"}


def stated_rule() -> tuple[str, set[str], bool]:
    """The engine-purity sentence as AGENTS.md actually words it: (scanned path, names, sqlite).

    Every part of this parse is required, not optional: if the sentence moves or is reworded so a
    name is no longer inside it, that is the rule shrinking, and the test fails loudly rather than
    quietly gating less.
    """
    text = AGENTS.read_text(encoding="utf-8")
    match = re.search(
        r"(?s)^-\s+\*\*Engine purity:\*\*\s*(.*?)\n-\s+\*\*", text, re.MULTILINE
    )
    if match is None:
        raise AssertionError(
            "AGENTS.md no longer holds an '- **Engine purity:**' bullet, so this test cannot read "
            "the rule it exists to enforce"
        )
    sentence = " ".join(match.group(1).split())

    scanned = re.search(r"`([^`]+/)`", sentence)
    if scanned is None:
        raise AssertionError("the engine-purity rule does not name the package it scans in backticks")

    imports = re.search(r"must not import\s+(.*?)\s+or\b", sentence)
    if imports is None:
        raise AssertionError(
            "the engine-purity rule no longer words the forbidden imports as 'must not import X, Y "
            "or ...', so a name may have been dropped from the rule"
        )
    names = {n.strip().strip("`") for n in imports.group(1).split(",")}
    sqlite = re.search(r"know about\s+SQLite", sentence) is not None

    return scanned.group(1), {n for n in names if n}, sqlite


def module_of(node: ast.AST) -> list[str]:
    """Every absolute module name one import statement can pull in, relative imports resolved."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []

    if node.level == 0:
        base = node.module or ""
        names = [f"{base}.{alias.name}" for alias in node.names]
        return ([base] if base else []) + names

    # Relative: `.` is the module's own package, so `from . import x` stays inside the engine and
    # `from .. import x` reaches one level above it. The `level - 1` is the dot count past the
    # first; reading `level` as "levels up" resolves `from .. import db` to `engine.db`, which is
    # nothing, and the violation escapes. A level that walks out of LOCAL_PACKAGE names a module
    # that is not a sibling of the engine, so there is no forbidden name to match and it is skipped.
    pkg_parts = GATED_PACKAGE.split(".")
    up = pkg_parts[: len(pkg_parts) - (node.level - 1)]
    if not up:
        return []
    base = ".".join([*up, node.module] if node.module else up)
    return [base] + [f"{base}.{alias.name}" for alias in node.names]


def violations_for(source: str) -> list[tuple[int, str]]:
    """Forbidden imports in one module's source: (line, statement).

    An unparseable file is a finding, never a skip - a scanner that silently returned nothing on a
    syntax error it disliked would certify anything.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [(error.lineno or 1, f"UNPARSEABLE: {error.msg}")]

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        stmt = ast.get_source_segment(source, node) or ast.dump(node)
        for name in module_of(node):
            top = name.split(".")[0]
            if top in SQLITE_MARKERS:
                found.append((node.lineno, stmt))
                break
            if top == LOCAL_PACKAGE and name.split(".")[1:2] and name.split(".")[1] in FORBIDDEN_NAMES:
                found.append((node.lineno, stmt))
                break
    return found


def scan(package: Path) -> tuple[list[str], list[tuple[str, int, str]]]:
    """(files scanned, violations) for every module under `package`.

    Names are reported with `/` separators (`engine/analytics.py`), because `str()` of a Windows
    relative path yields `engine\\analytics.py` and a finding string is the thing a reader greps
    for and a log has to agree with.
    """
    modules = sorted(p for p in package.rglob("*.py") if "__pycache__" not in p.parts)
    findings: list[tuple[str, int, str]] = []
    for path in modules:
        for line, stmt in violations_for(path.read_text(encoding="utf-8")):
            findings.append((path.relative_to(package.parent).as_posix(), line, stmt))
    return [p.relative_to(package.parent).as_posix() for p in modules], findings


def copy_package(destination: Path) -> Path:
    target = destination / "engine"
    target.mkdir(parents=True)
    for path in PACKAGE.glob("*.py"):
        shutil.copyfile(path, target / path.name)
    return target


class EnginePurityTest(unittest.TestCase):
    def test_the_rule_in_agents_md_is_the_rule_this_test_enforces(self) -> None:
        scanned, names, mentions_sqlite = stated_rule()
        self.assertEqual(
            f"{LOCAL_PACKAGE.replace('.', '/')}/engine/",
            scanned,
            f"AGENTS.md gates `{scanned}` but this test scans midivault/engine/",
        )
        self.assertEqual(
            sorted(FORBIDDEN_NAMES),
            sorted(names),
            "the forbidden names in AGENTS.md and in this test disagree; either the rule shrank "
            "or the gate widened without the rule saying so",
        )
        self.assertTrue(
            mentions_sqlite,
            "AGENTS.md no longer says the engine must not know about SQLite, so this test should "
            "stop claiming it enforces that half",
        )

    def test_a_reworded_rule_is_refused_rather_than_gating_less(self) -> None:
        """Five ways the sentence can lose coverage, each required to redden the contract test.

        The green case above only proves the parse agrees with today's wording. These are the
        mutations that wording has to survive: a name dropped, the SQLite half dropped, the bullet
        renamed, the package un-backticked, the clause reworded. A red case that cannot find its
        literal in the file raises rather than passing - which is how a gate gets silently disarmed.
        """
        mutations = {
            "name dropped from the list": (
                "must not import `db`, `api`, `scanner` or",
                "must not import `db`, `api` or",
            ),
            "SQLite half removed": ("know about SQLite", "know about durations"),
            "bullet renamed": ("**Engine purity:**", "**Engine layering:**"),
            "package no longer named in backticks": (
                "`midivault/engine/` must not import",
                "the engine must not import",
            ),
            "import clause reworded": (
                "must not import `db`, `api`, `scanner` or",
                "may not reference `db`, `api`, `scanner` or",
            ),
        }
        real = AGENTS.read_text(encoding="utf-8")
        original = AGENTS
        module = sys.modules[__name__]
        for label, (old, new) in mutations.items():
            with self.subTest(rule=label):
                self.assertIn(
                    old, real,
                    f"AGENTS.md was reworded, so the {label} case can no longer plant its defect; "
                    "update this pair instead of deleting the check",
                )
                with tempfile.TemporaryDirectory() as scratch:
                    copy = Path(scratch) / "AGENTS.md"
                    copy.write_text(real.replace(old, new, 1), encoding="utf-8")
                    module.AGENTS = copy
                    try:
                        # The contract test, not stated_rule: dropping a name from the sentence
                        # leaves the parser perfectly happy and only the comparison goes red.
                        self.assertRaises(
                            AssertionError,
                            self.test_the_rule_in_agents_md_is_the_rule_this_test_enforces,
                        )
                    finally:
                        module.AGENTS = original
                self.assertEqual(original, AGENTS, "the restore did not take")

    def test_the_engine_is_clean_and_was_actually_read(self) -> None:
        modules, findings = scan(PACKAGE)
        self.assertGreater(
            len(modules), 5, f"only {len(modules)} module(s) scanned, so this is not a gate"
        )
        self.assertEqual(
            sorted(p.name for p in PACKAGE.glob("*.py")),
            sorted(Path(m).name for m in modules),
            "the scan did not read every module in the package",
        )
        self.assertEqual([], findings, f"the engine imports a forbidden module: {findings}")

    def test_a_sibling_import_is_not_a_violation(self) -> None:
        """The gate must pass what the rule allows, or it is a wall and someone will switch it off.

        Asserted against a planted import rather than the clean tree: `findings == []` on real
        source proves only that today's engine happens not to import its own siblings.
        """
        legal, illegal = "from . import versions", "import midivault.db"
        with tempfile.TemporaryDirectory() as scratch:
            copy = copy_package(Path(scratch))
            victim = copy / "model.py"
            victim.write_bytes(victim.read_bytes() + f"\n{legal}\n".encode())
            _, findings = scan(copy)

        self.assertEqual([], findings, f"a legal sibling import was reported: {findings}")

        with tempfile.TemporaryDirectory() as scratch:
            copy = copy_package(Path(scratch))
            victim = copy / "model.py"
            victim.write_bytes(victim.read_bytes() + f"\n{illegal}\n".encode())
            _, findings = scan(copy)

        self.assertTrue(findings, f"{illegal} was planted into the same copy and nothing fired")

    def test_a_planted_import_is_named_with_its_file_and_line(self) -> None:
        spellings = (
            "from midivault import db",
            "import midivault.api",
            "import midivault.scanner as scan",
            "from midivault.db import connect",
            "import sqlite3",
            "import sqlite3 as sql",
        )
        for statement in spellings:
            with self.subTest(statement=statement):
                with tempfile.TemporaryDirectory() as scratch:
                    copy = copy_package(Path(scratch))
                    victim = copy / "analytics.py"
                    victim.write_bytes(victim.read_bytes() + f"\n{statement}\n".encode())
                    _, findings = scan(copy)

                self.assertEqual(
                    1, len(findings), f"{statement} was planted and the scan returned {findings}"
                )
                self.assertIn("engine/analytics.py", findings[0][0], findings)
                self.assertEqual(statement, findings[0][2], findings)

    def test_a_function_local_sqlite_import_is_still_a_violation(self) -> None:
        """`ast.walk`, not a line-matching regex: hiding the import in a body changes nothing."""
        with tempfile.TemporaryDirectory() as scratch:
            copy = copy_package(Path(scratch))
            victim = copy / "classifier.py"
            victim.write_bytes(
                victim.read_bytes()
                + b"\n\ndef _peek(path):\n    import sqlite3\n\n    return sqlite3.connect(path)\n"
            )
            _, findings = scan(copy)

        self.assertTrue(findings, "an import buried in a function body escaped the scan")
        self.assertIn("engine/classifier.py", findings[0][0], findings)

    def test_a_relative_import_out_of_the_package_is_a_violation(self) -> None:
        """`from .. import db` resolves to midivault.db, and a level-relative read must catch it."""
        with tempfile.TemporaryDirectory() as scratch:
            copy = copy_package(Path(scratch))
            victim = copy / "duplicates.py"
            victim.write_bytes(victim.read_bytes() + b"\nfrom .. import db\n")
            _, findings = scan(copy)

        self.assertTrue(findings, "`from .. import db` escaped the scan")
        self.assertIn("engine/duplicates.py", findings[0][0], findings)

    def test_an_unparseable_module_is_a_finding_not_a_skip(self) -> None:
        """A file the parser cannot read must stop the gate, not pass it.

        Planted inside a copy of the engine rather than asserted over `tests/`: a scanner that
        returned nothing on a SyntaxError would certify any tree, and the modules next to this one
        import `midivault.db` on purpose, so scanning them measures the wrong thing.
        """
        with tempfile.TemporaryDirectory() as scratch:
            copy = copy_package(Path(scratch))
            (copy / "broken.py").write_text("def open(:\n    pass\n", encoding="utf-8")
            modules, findings = scan(copy)

        self.assertIn("engine/broken.py", modules, modules)
        self.assertEqual(1, len(findings), findings)
        self.assertEqual("engine/broken.py", findings[0][0], findings)
        self.assertIn("UNPARSEABLE", findings[0][2], findings)


if __name__ == "__main__":
    unittest.main()
