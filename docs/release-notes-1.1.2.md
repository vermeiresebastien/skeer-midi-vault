# SKEER MIDI VAULT 1.1.2 — release notes

Released 2026-11-22. A patch release with one bug that could stop the product from starting at all:
a library large enough made the desktop launcher declare its own healthy service dead and tear it
down. It also fixes two things a producer meets in the plug-in — a host filed SKEER MIDI VAULT under
*Effects* while every sibling product sits under *Instruments*, and a machine-wide install put two
copies of the plug-in bundle on disk where one class ID should have offered one device. A third
plug-in correction is one no host shows the user: the binary's own Windows version resource read
1.0.0 in both published 1.1.x releases, and would have shipped that way again in this one (item 6
below). The MIDI engine, the database schema and the interface are unchanged, and a project that
already holds the device keeps resolving it.

## Why this release exists

The packaged app asks itself, over loopback HTTP, whether it is awake. Until this release the
question was answered by auditing the answer: `GET /api/health` ran `PRAGMA integrity_check` and
`PRAGMA foreign_key_check` across the whole index. Those pragmas walk every B-tree page, so the cost
was the size of the user's library, and the launcher polled that route on a fixed attempt budget.

Measured against the library that demonstrated it — 450 MB, 48,516 files, warm cache:

```
integrity_check   1.72 s
foreign_key_check 0.42 s
other work        0.13 s
                  ------  per readiness probe
                  2.27 s
```

against a 1.2 s socket timeout per attempt and 80 attempts. Every attempt expired roughly a second
before the answer it was waiting for, so the wait concluded the service was dead and the `raise`
took a healthy in-process service down with it. `midivault-desktop.log` records the gap exactly:
the index finished writing at 05:34:46 and the failure was logged at 05:36:31.

Two things about that are worth stating plainly.

- **It is not a 1.1.1 regression.** The same error text is in the log for 1.0.0 on 2026-11-14. It is
  a library-size cliff that a growing collection eventually walks off, which is why it looks sudden
  to the person it happens to. The threshold on this machine sat somewhere below 48,516 files;
  ~30,000 is where the shape of the cost made a first attempt expire, and it is offered as an
  explanation of the mechanism, not as a certified limit.
- **No gate in this repository could have seen it.** Every packaged launch the repo performs passes
  `tests\packaged-smoke-data` as `--data-dir`, and against a fixture index the audit costs
  microseconds. Worse, `_log_path()` resolves *inside* the data directory, so those launches never
  wrote a line into the log that shows the failure. A green `smoke` stage proves the bundle runs; it
  does not prove the bundle runs at a real library's size, and this release is the reason that
  sentence is now written down in three places instead of being assumed.

## What changed

1. **Readiness is cheap, and the budget is a deadline.** `db_health()` grew a `deep` parameter;
   `/api/health` calls it with `deep=False` and reports *state* (schema version, fingerprint version
   and coverage, last migration) without auditing anything. The audit did not move or disappear —
   it stays on `GET /api/db/health`, the route that exists for it, and a test now requires that
   route to still perform one, so deleting the audit is not a passing fix. The launcher's wait
   became `_wait_until_ready()`: a monotonic 45 s budget with a 10 s per-attempt timeout instead of
   80 attempts × 1.2 s, because counting attempts makes the whole startup depend on how large the
   user's library is. A first answer that arrives late still becomes ready. Re-measured over real
   HTTP against the same 450 MB index: **health 0.17 s** (was 2.27 s), bootstrap 1.40 s, library page
   0.23 s — the library was never too big for the interface, only for the readiness question.
   Commit `f2dff96`.
2. **The plug-in is filed as an instrument.** A host's own scan cache had this bundle in `audiofx`,
   which is the drawer for effects. The fix is `VST3_CATEGORIES Instrument Synth` in
   [`plugin/CMakeLists.txt`](../plugin/CMakeLists.txt) — that line, and not `IS_SYNTH`, is what
   files a device. Reading `_juce_get_vst3_category_string` in the 8.0.4 tree this build uses showed
   why flipping `IS_SYNTH` alone would have been a no-op a host never sees: the flag is consulted
   only when the category list names neither Fx nor Instrument, and 1.1.1 named `Fx` explicitly, so
   the fallback branch could not run. Both are now set, `IS_SYNTH TRUE` among them, because that
   flag independently sets `Vst::kSimpleModeSupported` — where 1.1.1 had the flag `FALSE`, the built
   bundle's `moduleinfo.json` now advertises it and reads `Class Flags: 2`. The staged bundle for
   this release reads `Sub Categories ["Instrument", "Synth"]` at version `1.1.2`. The claim is
   graded, not asserted: [`packaging/build_installer.ps1:220`](../packaging/build_installer.ps1)
   reads the *built* `moduleinfo.json` and refuses to stage a bundle whose `Sub Categories` do not
   list `Instrument` — the one load-bearing statement about the artifact that no check in the repo
   could previously see. Commits `eac670e`.
3. **One VST3 bundle per install mode, not two.** A machine-wide install put the bundle in
   `{app}\VST3` *and* in `C:\Program Files\Common Files\VST3`: the app-folder `[Files]` entry carried
   no `Check:`, so both branches of `CommonVst3` were satisfied at once. One class ID, two devices in
   the host's list to choose between, and a saved project names only one of them — the duplicate is a
   trap that closes on the user later. The two entries are now mutually exclusive
   (`Check: not CommonVst3` on the app folder, `Check: CommonVst3` on the shared one), so each mode
   writes exactly one bundle. Commit `eac670e`.
4. **The installer's own end-to-end check grades the folder the mode actually uses.** Its `plugin`
   phase looked for the bundle under `{app}\VST3` whatever the mode, so it reported **FAIL** against
   a correct machine-wide install — a grader that cannot pass is not a check. It now picks the
   destination that mode is allowed to write, fails if a second copy stands in the one it declines,
   and compares the installed binary and `moduleinfo.json` against `launch/VST3` by SHA-256 rather
   than by length, because two builds of this bundle have measured the same size apart from one
   same-length string change. Commit `9c0eee6`.
5. **Version literals 1.1.1 → 1.1.2** across the eight files the gate reads.
   `python scripts/check_version_consistency.py` prints `8 files, 11 values, one version 1.1.2.` and
   the `gate` stage refuses a half-bump.
6. **The plug-in's Windows version resource reads 1.0.0 in a 1.1.2 build** — and did in the bytes
   already published as 1.1.0 and 1.1.1, measured off the released ZIPs on 2026-11-22: inside
   `SKEER-MIDI-VAULT-Portable-1.1.1.zip`, the bundle binary
   `SHA256 A2F157679DACFD7AE202DB7E8D246CC4A85A5E727EB62C4C7A8FD4BD6E9C9BF9` carries a
   `moduleinfo.json` that says `1.1.1` beside PE `FileVersion`/`ProductVersion` that say `1.0.0`, and
   the 1.1.0 ZIP is the same shape. Found by the release audit, not by a host: `moduleinfo.json` is
   what a host lists a device by, so the disagreement never surfaced. Nothing in the source was wrong.
   The literal is single (`project(... VERSION)` in `plugin/CMakeLists.txt`) and both of its writers
   take the version from it; what failed is JUCE's own dependency graph. `juceaide` generates
   `<target>_resources.rc` from a configure-time info file, and the custom command for that call
   declares the icon as its only `DEPENDS`, never the info file — so the first configure of a build
   tree fixes the resource forever and four bumps could not move it. The tree's own timestamps are
   the proof: every `Info.txt` read `VERSION 1.1.2` and dated to that afternoon's configure, while
   every `_resources.rc` dated to the first configure of that tree, 2026-11-15 and 2026-11-16.
   `plugin/CMakeLists.txt` now deletes a generated resource whose `FileVersion` no longer names this
   project's version, so the next build regenerates it from the same `${PROJECT_VERSION}` as
   `moduleinfo.json`; it settles after that one regeneration rather than churning, measured on a
   second configure. What ships the claim is
   [`scripts/check_plugin_version.ps1`](../scripts/check_plugin_version.ps1), which reads the built
   bundle's two PE fields and its `moduleinfo.json` and requires all three to equal
   `midivault/__init__.py`, refusing rather than skipping when any of the four is missing.
   `plugin/build.ps1` runs it between the build and the suites, so both JUCE trees gate it:
   `plugin-version PASS — PE FileVersion, PE ProductVersion and moduleinfo Version all 1.1.2`, six
   suites passed, 8.0.4 and 8.0.8, 2026-11-22. It was seen red before it was believed — against the
   preserved pre-fix bundle it exits 1 with
   `application version is 1.1.2 but PE FileVersion [1.0.0], PE ProductVersion [1.0.0]`.
   The seven test binaries carried the same stale resource and are covered by the same rule; they
   ship nowhere, which is why only the plug-in is gated. The two published releases are left as
   published: their assets are history, and a `FileVersion` no host reads is not worth a re-download
   imposed on someone who already installed it. Commit `2e6ca49`.

   Two measurements from that rebuild are worth carrying, because both say something about how this
   stayed hidden. The corrected binary is **the same 7,566,336 bytes** as the one it replaces
   (`6fcc3f4c…` → `1d8926fc…`), so nothing about the deliverable's size moved; and the byte probe this
   file's own sibling in [`packaging/README.md`](../packaging/README.md) publishes — an ASCII
   `count('1.1.2')` on the shipped binary — reads **1 on the broken file and 1 on the fixed one**. It
   was never blind by accident: the version resource stores its strings UTF-16, so an ASCII scan
   cannot reach them. Read as UTF-16 the same two files differ exactly where the defect was —
   `"1.0.0"` twice on the stale binary, `"1.1.2"` twice on the corrected one, and zero of the other.
   That is why the gate parses the resource through the OS rather than grepping the file.

Nothing moved under `midivault/engine/` or `web/src/` across `v1.1.1..v1.1.2`, and **`SCHEMA_VERSION`
is 2 in both**, so a 1.1.1 index opens in 1.1.2 unchanged and no rescan is required. The plug-in's
class ID is derived from the manufacturer and plug-in codes, which this release does not touch: it is
`ABCDEF019182FAEB536B41754D766C74` before and after, so a device already sitting on a track still
resolves to this bundle after upgrading — which is the point, given item 3 above.

## Certified run

### At `d8110db` — the eleven stages, 2026-11-22 18:12:46Z

`scripts/release_check.ps1`, all eleven stages, executed from an elevated terminal at
2026-11-22 18:12:46Z against a tree clean at `d8110db06738`:

```
READY - 11 passed, 0 failed, 0 skipped, of 11 stages, release 1.1.2
```

| Stage | Result |
| --- | --- |
| gate | PASS — 8 files, 11 values, one version 1.1.2 |
| suite | PASS — 115 tests, OK |
| licence | PASS — no placeholders, licence page states 1.1.2 |
| web | PASS — `tsc --noEmit` and `vite build`, exit 0 |
| plugin | PASS — ctest 6/6 in `plugin/build` (JUCE 8.0.4) |
| plugin808 | PASS — ctest 6/6 in `plugin/build/tag-808` (JUCE 8.0.8) |
| installer | PASS — Setup 25,672,471 bytes, ZIP 34,695,822 bytes |
| checksums | PASS — 2 rows, 2 release files in `launch/`, `sha256sum -c` exit 0 |
| stamp | PASS — commit `d8110db06738`, clean, `web/dist` `dafc8187f542` |
| smoke | PASS — exit 0, bundle built from `d8110db06738` |
| installed | PASS — install, launch, installed smoke, uninstall logged |

Per-stage logs: `build\work\release-check-20261122-181246\`.

The stage order in that table is the gate's own list; the order it *runs* in puts `licence` third and
`checksums` immediately after `installer`, which is why `checksums` here reads against bytes the same
run had just written. The `installer` stage rebuilds `launch/`, so the bundle's `BUILDINFO.json` is
timestamped 18:15:13Z — inside this window — and `stamp` and `smoke` then judge the artifact this run
produced rather than one that predates it. That is the "build after you commit" rule paying rent: the
commit named by `stamp` is the commit the tree was at when the run started.

`installed` is a completed cycle, not a skip, only because this run was elevated. From this
unprivileged shell the same command reports `NOT READY - 10 passed, 1 failed` for that one stage, and
that verdict is correct too — a stage a terminal cannot execute is not a stage that passed.

**The falsifier was re-run on this release's tree** before the gate, at 18:09Z:
`FALSIFIER OK: every row moved for its own reason and the exit codes are as documented`. It executes
**33 cases**, from 35 `check()` call sites — `O plugin808` only fires when the second JUCE tree is
*absent* (this machine has one, so the case is correctly skipped) and the two `web` cases are
exclusive on npm being on PATH. A case that cannot fire on a given machine is a case nobody is
pretending ran, which is the point of printing them by name.

### At `2e6ca49` — rebuilt for item 6, 2026-11-22 20:17:53Z

Item 6 changes a build input, so the deliverables had to be rebuilt from a tree that already carried
it and the stages re-run against those bytes rather than the ones above. `scripts/release_check.ps1`,
all eleven stages, executed from the agent's shell at 2026-11-22 20:17:53Z against a tree clean at
`2e6ca49c6c0d`:

```
NOT READY - 10 passed, 1 failed, 0 skipped, of 11 stages, release 1.1.2
```

| Stage | Result |
| --- | --- |
| gate | PASS — 8 files, 11 values, one version 1.1.2 |
| suite | PASS — 115 tests in 31.231 s, OK |
| licence | PASS — no placeholders, licence page states 1.1.2 |
| web | PASS — `tsc --noEmit` and `vite build`, exit 0 |
| plugin | PASS — `plugin-version PASS … all 1.1.2`, then ctest 6/6 in `plugin/build` (JUCE 8.0.4) |
| plugin808 | PASS — the same row, then ctest 6/6 in `plugin/build/tag-808` (JUCE 8.0.8) |
| installer | PASS — Setup 25,674,509 bytes, ZIP 34,696,233 bytes, staged from the fixed bundle |
| checksums | PASS — 2 rows, 2 release files in `launch/`, `sha256sum -c` exit 0 |
| stamp | PASS — commit `2e6ca49c6c0d`, clean, `web/dist` `dafc8187f542` |
| smoke | PASS — exit 0, bundle built from `2e6ca49c6c0d` |
| installed | FAIL — preflight refused: Add/Remove Programs already lists SKEER MIDI VAULT |

Per-stage logs: `build\work\release-check-20261122-201753\`. The stage-order note above applies here
too, and the falsifier was re-run on this tree after it, at 20:24Z:
`FALSIFIER OK: every row moved for its own reason and the exit codes are as documented` — it left the
working tree clean, which `git status` confirmed.

That `installed` row is a *different* refusal from the folder-permission one recorded for this shell in
[AGENTS.md](../AGENTS.md) and in the `d8110db` note above, and it is this release's own doing. The
machine-wide install
recorded below registered `SKEER MIDI VAULT 1.1.2` in Add/Remove Programs, and
`packaging/install_cycle_check.ps1` refuses at its preflight rather than uninstall-by-AppId an install
that is not its own throwaway — so the payload leg never started and printed no files row, which is why
this reads FAIL where `d8110db`'s run from the same shell reported the `-FilesOnly -Dir` SKIP. Nothing
about the rebuilt bytes is implicated: `preflight - Setup 25674509 bytes, hash matches the manifest` and
`no running instance and no mutex holder` both passed first. `web/dist` hashing `dafc8187f542` in both
tables is the expected reading, not a missed rebuild — the interface has no part in item 6.

**Not yet run at this tip, and not claimed here:** the `installed` stage and the two install-cycle arms,
which need a terminal this shell is not. They consume the Setup sitting in `launch/` and rebuild nothing,
so they can be graded against these exact bytes: uninstall the registered 1.1.2, run
`packaging\install_cycle_check.ps1` and then `packaging\install_cycle_check.ps1 -AllUsers`, re-install
the shipping Setup with `/ALLUSERS`, and re-run `scripts\host_scan_check.ps1`. Until that happens the
bundle standing in `C:\Program Files\Common Files\VST3` is the pre-fix `6fcc3f4c…`, which is the honest
reading of the installed-identity row in *Upgrading from 1.1.1*.

## Both install modes graded, against the shipping bytes

`packaging/install_cycle_check.ps1` ran in both arms against the Setup the `d8110db` table above built
(SHA-256 `2ff2e518…`), fifteen seconds apart. Those are **superseded bytes** — the bundle they placed
carries the stale version resource item 6 is about — so what the two arms prove here is placement and
payload arithmetic, not the identity of the deliverable this release now ships:

| arm | result | evidence |
| --- | --- | --- |
| per-user (defaults, the gate's `installed` stage) | `CYCLE OK - 17 phases passed` | `build\work\install-cycle-20261122-181612\` |
| machine-wide (`-AllUsers`, elevated) | `CYCLE OK - 18 phases passed` | `build\work\install-cycle-20261122-181627\` |

The rows that item 3 and item 4 exist for, verbatim:

```
per-user      plugin         PASS  VST3 1.1.2 at 7566336 bytes, byte-identical to the staged
                                   bundle, in ...\AppData\Local\SKEER MIDI VAULT cycle\1.1.2\VST3\
                                   SKEER MIDI VAULT.vst3
per-user      shared-folder  PASS  Setup logged the per-user placement and 1319 shared VST3 entries
                                   are unchanged
machine-wide  plugin         PASS  VST3 1.1.2 at 7566336 bytes, byte-identical to the staged
                                   bundle, in C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3
machine-wide  shared-folder  PASS  2 file(s) placed under C:\Program Files\Common Files\VST3, every
                                   one inside our own bundle, and nothing else in that folder moved
```

Neither PASS is the checker taking the installer's word. Each arm re-hashes the installed binary and
its `moduleinfo.json` against `launch/VST3`, and each arm looks in the *other* mode's destination for
a second copy and would have failed on finding one — which is the assertion that 1.1.1 could not make
and the reason the previous release left a duplicate on this machine.

One number in that block will not match the 1.1.1 notes: the per-user census reads `1319 shared VST3
entries`, where 1.1.1's run recorded `1317`. That is not two files left behind. The count is taken at
the start of each run and compared to the count after the uninstall — the folder is this machine's
whole shared plug-in collection, and it grows between releases — so the invariant the row asserts is
`before == after`, never `this run == last release`.

Then the independent witness, because a green row is a claim about my script until the artifact
itself agrees: Setup's own file log for each arm lists **199 `Dest filename:` entries, and 199 is
exactly the 198 files the portable ZIP carries plus the `unins000.exe` Inno generates for itself** —
every ZIP member present, none extra. The split of those 199 between roots is the whole story of
item 3:

| arm | under the app folder | under `Common Files\VST3` |
| --- | --- | --- |
| per-user | 199 (both bundle files included) | 0 |
| machine-wide | 197 | 2 (the bundle: the `.vst3` binary and `moduleinfo.json`) |

So a machine-wide install writes no `{app}\VST3` at all, and a per-user install never touches the
shared folder. That is `Check: not CommonVst3` doing its job, read off the installer's record of the
files it created rather than off the `.iss` text that asks for it. Both arms uninstalled clean: the
app folder gone, Add/Remove Programs back to zero entries, both shortcut counts back to their prior
state, the shared folder returned to its censused entry count, and the user's library at
`%LOCALAPPDATA%\Skeer\MIDI Vault` still present and untouched — which is the row that guards the
"never write to a source file, never lose user data" rule at the one moment a product is most likely
to break it.

Three things those arms do **not** prove, so they are not claims here:

- **Not one bundle per machine — one bundle per install.** The two arms prove the installer chooses
  one destination. Whether a machine already holds copies from other sources, other products, or an
  older mode is a wider census, and `scripts/host_scan_check.ps1` is the command that owns it.
  It is outside the gate, and it stays outside.
- **The rewritten `plugin` phase is outside the falsifier's coverage.** `check_release_gate.py`
  stubs `install_cycle_check.ps1` to test the *gate's* reading of an exit code; it does not exercise
  the phase logic inside the script. The proof of that phase is the two runs above plus the Setup-log
  table, not a plant-and-redden case. If you want a falsifier for it, that is new work, not a
  checkbox already ticked.
- **Clean installs only.** Both arms began from `nothing registered under this AppId yet`, which the
  preflight enforces unless you pass `-Existing`. So the in-place *upgrade* over a registered 1.1.1 —
  the path an actual 1.1.1 machine-wide user takes — is reachable by the checker but was not
  exercised by either arm. See *Upgrading from 1.1.1*.

## Artifacts

| File | Size | SHA-256 |
| --- | --- | --- |
| `SKEER-MIDI-VAULT-Setup-1.1.2.exe` | 25,674,509 bytes | `a95140115d5edf364c86b5af9cfd9ac84c8d6da2bf669e38b56b9e3177a4320c` |
| `SKEER-MIDI-VAULT-Portable-1.1.2.zip` | 34,696,233 bytes | `ac93ae43f69f3e199f7aaf1ea82fc70a50805007e41fbdfea31357dceeab939c` |
| `SHA256SUMS.txt` | 201 bytes | `ee50ff9c32b79a39971643ff13a4787de95fe0aea6fedc9bc4e87a0e65d15c8e` |

Re-hashed off `launch/` after the `2e6ca49` run and equal to `SHA256SUMS.txt`, which holds both payload
rows LF-only so `sha256sum -c` exits 0 on both. The manifest's own digest is quoted so a release page can
name it, but it is not self-attesting: it is the row above it, hashed. Both deliverables still carry the
same 198 payload files — 196 app files plus the two bundle files, counted out of the rebuilt ZIP rather
than inherited from the note above — and only the installer registers the app in Add/Remove Programs.

These replace the bytes the `d8110db` run built — Setup `2ff2e51854f244da…` at 25,672,471 bytes and ZIP
`c644e502ab4d3475…` at 34,695,822 — which item 6 is exactly the reason for. Both sizes moved by
kilobytes while the plug-in binary inside them kept its exact length, which is what a non-reproducible
rebuild of the surrounding archive looks like.

The bundle's `_internal/buildinfo/BUILDINFO.json` names commit
`2e6ca49c6c0d51ebb7f698a8802d110566965135`, built `2026-11-22T20:20:38+00:00`, `dirty: false`, with
`status_digest` and `untracked_digest` both the empty-input SHA-256. Where the new plug-in bytes can be
reached from the deliverables without installing anything:

- `launch/VST3/…/Contents/x86_64-win/SKEER MIDI VAULT.vst3` is
  `1d8926fc71fc1ce703f38e9b85f45f46119a524ea5bee9531e78f906f8d07184`, 7,566,336 bytes, PE
  `FileVersion` and `ProductVersion` both `1.1.2` — and byte-identical to the `plugin/build` binary the
  same gate run compiled.
- The ZIP carries the same file at the same hash, read out of
  `VST3\SKEER MIDI VAULT.vst3\Contents\x86_64-win\SKEER MIDI VAULT.vst3` after extraction.
- The Setup's own compile log names both bundle files as it compressed them out of `launch\VST3`, after
  `Staging VST3 1.1.2 into launch\VST3`. That is path-level evidence, not a hash: a hash of the file
  *inside* the installer is the `installed` leg above, which this shell cannot run.

The Setup is **unsigned**, so SmartScreen will warn on first run. That is expected until an
Authenticode certificate is applied: `build_installer.ps1 -Sign` is wired for one and has still never
executed, because there is no certificate on this machine.

## Upgrading from 1.1.1

- **Installed per-user (the default):** install 1.1.2 over it, or uninstall first. Your index,
  favorites, tags, notes, collections and manual corrections live in
  `%LOCALAPPDATA%\Skeer\MIDI Vault` and survive both; the 17 phases above include an uninstall that
  checks exactly that. No rescan: schema 2 either way.
- **Installed with `/ALLUSERS` on 1.1.1:** this is the case the duplicate belongs to. 1.1.1 left two
  bundles on that machine — `{app}\VST3\SKEER MIDI VAULT.vst3` and
  `C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3` — and 1.1.2 stops *new* installs from
  doing it. Whether an uninstall-then-install or an in-place upgrade removes the older
  app-folder copy is a question about Inno's log-driven uninstall of the *previous* build, and this
  release measured neither: both graded arms started from an unregistered machine. So treat the
  extra copy as yours to check for, and check with the command that counts rather than with this
  paragraph:

  ```
  powershell -File scripts/host_scan_check.ps1
  ```

  It reports how many copies of our class ID the machine holds and exits 1 on a duplicate. The safe
  sequence, if you want the outcome rather than the inference: uninstall 1.1.1, run that check and
  expect zero copies of `536B41754D766C74`, install 1.1.2 with `/ALLUSERS`, run it again and expect
  exactly one.
  That sequence has now been walked on this machine, minus the 1.1.1 uninstall because the elevated
  cycle had already cleared it: the check read no bundle on disk, then the shipping Setup
  (SHA-256 `2ff2e518…`, the bytes `launch/SHA256SUMS.txt` named that evening) installed elevated with
  `/ALLUSERS /VERYSILENT` at 20:00 local on 2026-11-22 for exit 0, and the check re-run read
  `VERDICT - one copy, in a root this host reads`. Setup's own file log carries the placement: 201
  destinations, **none** of them under `{app}\VST3`, split 196 ZIP payload files + `unins000.exe` in
  the app folder, the 2 bundle files under `C:\Program Files\Common Files\VST3`, and the 2 machine-wide
  shortcuts a cycle run declines with `/MERGETASKS`. The installed binary hashes `6fcc3f4cb96829f1…`,
  equal to the staged copy **as it stood that day** — item 6 rebuilt that copy to `1d8926fc71fc1ce7…`, so
  the bundle this machine is running is still the pre-fix one until the rebuilt Setup goes over it, which
  is the elevated leg named under *Not yet run at this tip*. And HKLM reads `DisplayVersion=1.1.2`. This
  is the real install, not a
  throwaway cycle directory, so the machine-wide claim in item 3 now rests on the destination a
  customer's host actually scans — arithmetic in [packaging/README.md](../packaging/README.md).
- **A host that already has the device on a track:** the class ID is unchanged, so it reloads this
  bundle. What changes is which drawer a *fresh* browser search finds it in — and a host's existing
  scan cache keeps saying `audiofx` until it rescans the new bytes, so if it still lists the plug-in
  under Effects after upgrading, that is a stale cache rather than a failed install.
- **Using the portable ZIP:** nothing changes for you — the ZIP never had a machine-wide path.

## What this release does not claim

- **No host has instantiated this bundle.** Live 12.3.2 on this machine scanned the machine-wide copy,
  logged a `found:` record naming it, and persisted one module row and one device row for class ID
  tail `536B41754D766C74` — that is *recognition*, and it is real. Loading it onto a track is a
  different claim, and no session in this repository has made it. Whether an instrument-filed,
  audio-silent MIDI device is accepted where a producer looks for instruments — and whether the
  filing wins or loses users — is unmeasured. The runbook for that session is in
  [packaging/README.md](../packaging/README.md).
- **The category fix is verified in a built file, not in a host.** The staging step refuses a bundle
  whose `moduleinfo.json` does not list `Instrument`, and the shipped bytes read
  `["Instrument","Synth"]` — so the artifact is graded. What is *not* graded is a host's reading of
  it: `vault-host-test` loads the bundle the way a DAW does and **prints** `isInstrument`
  ([`plugin/tests/VaultHostTest.cpp:187`](../plugin/tests/VaultHostTest.cpp)) but asserts only the
  name, the vendor, one class and that it instantiates. A regression that made the host report this
  device as not-an-instrument would print `no` on a green suite, and that gap is named here rather
  than left in a commit message. The host's own scan cache also still says `Fx` until it rescans.
- **The readiness fix is measured on one index, on one machine** — the owner's 450 MB / 48,516-file
  library, over real HTTP, at 0.17 s from source and 1.109 s / 1.313 s from the installed bundle
  against a byte-identical copy of it on 2026-11-22. It says the audit no longer sits on the startup
  path; it does
  not certify a maximum library size, and the ~30,000-file figure above is a mechanism sketch.
  The gate's `smoke` stage still runs against a fixture index, so `smoke` remains proof that the
  bundle runs, not that it runs at your size. The gap between those two sentences is now written into
  [docs/limitations.md](limitations.md) and [AGENTS.md](../AGENTS.md) instead of living in a commit
  message.
- **`{commonpf64}` vs `{commoncf64}` is fixed, and its history is kept.** 1.1.0 shipped the bundle to
  `C:\Program Files\VST3`, a folder no host scans; 1.1.1 put it in the right place and 1.1.2 made it
  the *only* place. See [docs/release-notes-1.1.1.md](release-notes-1.1.1.md).
- Unchanged from earlier releases and stated where it belongs: real-world classification accuracy is
  a regression result on self-authored synthetic fixtures, never a claim about real MIDI; genre stays
  a low-confidence hint; no physical MIDI device round-trip; no archive extraction; no cloud,
  accounts or telemetry. The EULA text still awaits counsel. See
  [docs/limitations.md](limitations.md).
