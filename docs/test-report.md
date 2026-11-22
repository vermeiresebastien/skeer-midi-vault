# Test report

Date: 2026-11-02<br>
Version: 1.0.0<br>
Platform: Windows 10 22H2, AMD Ryzen 9 3900X, 24 logical cores, 63.9 GB RAM

Re-verification: `python -m unittest discover -s tests` was run again on
2026-11-15 and reported **Ran 97 tests — OK** in ~20 s, after the index-correctness,
engine and HTTP-framing fixes landed (`test_scanner_db.py` 10 → 19,
`test_http_boundary.py` 14 → 18, `test_api.py` 10 → 12, `test_parser.py` 18 → 19,
`test_classifier.py` 10 → 11, `test_duplicates.py` 3 → 4) and four browser
harnesses were added under `tests/`. An earlier re-run the same day reported 79,
and one on 2026-11-14 reported 55. Everything before the Python table is the
original 2026-11-02 session and keeps the numbers that session produced.

Re-verification for 1.1.0 (2026-11-17): the header and the tables below this
paragraph are the 2026-11-02/11-15 records and are left exactly as those sessions
produced them. Against the 1.1.0 tree at commit `862bb16`,
`python -m unittest discover -s tests` reported **Ran 104 tests — OK** in 19.9 s,
`plugin/build.ps1` reported exit 0 and **ctest 6/6** on both the 8.0.4 and the 8.0.8
JUCE tree, and `python tests/test_packaged_smoke.py` reported
**PASS packaged smoke test** against `launch\SKEER MIDI VAULT\SKEER MIDI VAULT.exe`
(health `SKEER MIDI VAULT 1.1.0`, 36 files indexed / 1 failed / 0 issues, 403 and 415
boundary responses honored on a keep-alive connection, no orphan
`--multiprocessing-fork` workers). The browser harnesses were not re-run for this
build; their 11-15 figures are the most recent measurement that exists for them. The
release-gate, version-consistency and installer-cycle checks that 1.1.0 added are not
unittest suites and are reported in
[`release-notes-1.1.0.md`](release-notes-1.1.0.md) and
[`../packaging/README.md`](../packaging/README.md).

Re-verification for 1.1.2 (2026-11-22): taken from the certification run
`build\work\release-check-20261122-181246\`, executed elevated against a tree clean at
`d8110db06738`. `python -m unittest discover -s tests` reported **Ran 115 tests — OK** in
24.791 s. The 104 → 115 delta is the readiness work, attributed by counting `def test_`
per file across `v1.1.1..HEAD`: `tests/test_api.py` 12 → 13 (the readiness route must not
run a page-scanning pragma, and the audit route must still run one), plus two new files —
`tests/test_desktop_ready.py` (2, both directions of the launch budget) and
`tests/test_engine_purity.py` (8). `plugin/build.ps1` reported exit 0 and **ctest 6/6** on
both JUCE trees (8.0.4 and 8.0.8), and `python tests/test_packaged_smoke.py` reported PASS
against `launch\SKEER MIDI VAULT\SKEER MIDI VAULT.exe`, which the same run had just rebuilt
and whose `BUILDINFO.json` names `d8110db06738`, `dirty: false`,
`built_at 2026-11-22T18:15:13+00:00`. Read that row beside the caveat under **Partial →
Large-library scale** in [`completed-partial-missing.md`](completed-partial-missing.md): a
packaged launch passes a fixture `--data-dir`, so it proves the bundle runs, not that it
runs at 48,516 files. The browser harnesses were not re-run for this build, and the
release notes record why that is a small concession this time: nothing under `web/src/`
changed between the two tags. `scripts/release_check.ps1` itself, its falsifier
(33 cases, `FALSIFIER OK` at 18:09Z) and both `install_cycle_check.ps1` arms are reported
in [`release-notes-1.1.2.md`](release-notes-1.1.2.md).

Re-verification after the plug-in version-resource fix (2026-11-22, from 20:17:53Z): that fix is a build
input, so the deliverables and the stages were rebuilt and re-run against a tree clean at
`2e6ca49c6c0d`. Inside that run `python -m unittest discover -s tests` reported **Ran 115 tests — OK** in
31.231 s — the same 115 as above, because the fix changes how a Windows resource is generated and not one
line of Python or TypeScript — and `python -m unittest tests.test_schema_migration` was run again on its
own for the record: **9 tests, OK, 1.888 s**. `plugin/build.ps1` exited 0 on both JUCE trees with **ctest
6/6** each, and each of those two runs now sits behind the new byte-level row
(`plugin-version PASS — PE FileVersion, PE ProductVersion and moduleinfo Version all 1.1.2`), which was
also seen to exit 1 against a preserved pre-fix bundle. `python tests/test_packaged_smoke.py` reported
PASS against the rebuilt bundle (`built from 2e6ca49c6c0d clean at 2026-11-22T20:20:38+00:00`), and
`scripts/check_release_gate.py` reported **FALSIFIER OK** on the tree afterwards and left it clean. One
stage did not complete from this shell: `installed`, whose preflight refused because the release is
actually installed on this machine. That leg and both `install_cycle_check.ps1` arms are open against
these bytes, and *Not yet run at this tip* in the release notes says which commands close them. The
browser harnesses were not re-run and none of this asks them to be: nothing under `web/src/` moved, and
`web/dist` hashed `dafc8187f542` in both certification runs.

Machine-readable results: [`e2e-results.json`](e2e-results.json),
[`playback-stability.json`](playback-stability.json),
[`benchmark-results.json`](benchmark-results.json),
[`classification-evaluation.json`](classification-evaluation.json).

## Summary

| Suite | Result | Time |
| --- | --- | --- |
| Python unit/integration (`unittest`) | **97/97 passed** | ~20 s |
| Browser end-to-end (Playwright + Chrome) | **16/16 checks passed** | full isolated scan + interaction run |
| Autoplay deck (Playwright + Chrome) | **8/8 checks passed** | auto-advance, bounded run, manual stop, selection survives filtering |
| Web MIDI output guard (Playwright + Chrome) | **7/7 checks passed** | refused send, reported disconnect, state-change listener, unload release |
| Keyboard activation (Playwright + Chrome) | **5/5 checks passed** | Space reaches the focused control, still owns the transport elsewhere |
| Deck past a soundless row (Playwright + Chrome) | **6/6 checks passed** | a failed details call or empty preview does not park the deck |
| Scan settings round trip (Playwright + Chrome) | **5/5 checks passed** | the incremental re-hash guard is a visible, persisted control |
| Classification regression | 31/31 family, 31/31 role, 13/13 track family, 11/13 track role | < 1 s |
| Playback stability while scanning/filtering | **0 late, 0 skipped** scheduled notes; drift 0.989× | 7.6 s audition |
| Packaged standalone app (Windows) | **passed** health + frozen process-worker scan + quit + zero orphan workers | onedir EXE smoke test |
| Scan/search benchmark | 83 files/s full, 255 files/s incremental, 88.2 MB peak tree RSS, ~13.5 ms search p50 | 12.0 s scan |

## Python tests

Command:

```powershell
python -m unittest discover -s tests
```

Result: **Ran 97 tests — OK** (2026-11-15).

| Module | Tests | What is covered |
| --- | ---: | --- |
| `test_parser.py` | 19 | Format 0/1/2, running status, VLQ, tempo map, SMPTE, sustain, overlapping notes, malformed chunks, missing EOT, text events, warnings, safety caps, fixture parsing, a conductor track wins a tempo clash at the same tick |
| `test_classifier.py` | 11 | Family/role rules, confidence caps, misleading-name conflicts, uncertainty, embedded-vs-estimated key, assumed tempo and meter, format-2 per-sequence track labels, genre never high-confidence, unnamed-track channel fallback, silent bars in rhythm analysis, a stranded note cannot stretch the rhythm grid |
| `test_scanner_db.py` | 19 | Full and incremental scans, exclusions, protected folders, junction/symlink skip, corrupt file isolation, pause/resume, cancel, user data preservation, unavailable sources, file modification check, a removed source stops ghost rows, orphaned index rows, invalidation scoped to the sources being rescanned, a same-size in-place edit is re-indexed by hash, verification can be turned off, one bulk label edit uses one transaction, a scan reuses one read handle |
| `test_api.py` | 12 | Health/bootstrap, search/details/Range streaming, labels/favorites/notes/tags, collections/bulk/facets, the autoplay setting persists, unknown setting keys are dropped, scan settings, export-without-overwrite, backup download and static host, rebuild preserves user data and invalidates only the selected sources, a refused rebuild keeps the cache, validation errors |
| `test_http_boundary.py` | 18 | Rebound `Host` rejected on reads and on the database backup, missing `Host`, `localhost`/dev-proxy hosts accepted, cross-origin and cross-site `Sec-Fetch-Site` writes rejected, write without a session token rejected, form-encoded and `text/plain` bodies rejected, bodyless write needs only the token, `/api/session` hands the token to a loopback page, reads never need it, and four keep-alive framing checks proving a refused request's body is never parsed as the next request |
| `test_schema_migration.py` | 9 | A v1 index advances to current and keeps every user edit, the old index is backed up before migration, reopening a current index does not back up again, a fresh index is not migrated, a newer index is refused untouched, an unmapped version jump is refused, legacy fingerprints are skipped until reindexed, the pipeline stamps its generation, only the current generation is compared |
| `test_duplicates.py` | 4 | Exact content duplicates, conservative similar-music grouping, a fingerprint with no generation is never compared, a row from another parser or classifier build is not compared |
| `test_platform.py` | 4 | Protected locations, cloud/reparse flags, optional source heuristics |
| `test_demo_accuracy.py` | 1 | Generated demo labels still match the current parser/classifier |

Notable safety checks executed:

- Source file bytes are identical before and after scans and icon edits.
- Existing destination files are never overwritten by export; a numbered name is
  used instead.
- Pause/resume does not lose committed rows; cancel leaves the index consistent.
- Rebuild invalidates the analysis caches of the sources it is actually rescanning,
  and only once the scan has started — a rebuild the scanner refuses leaves the
  index holding its cached analysis rather than an empty one. Manual
  role/collection/favorite data is kept and automatic labels repopulate.
- Backup download is a valid SQLite file and its handle is released after the
  request (Windows file-lock regression test).

## Browser end-to-end

Command (starts its own isolated service, scans only the demo fixture, writes
`docs/screenshots` and `docs/e2e-results.json`):

```powershell
node tests/e2e-web.mjs
```

Result: **E2E RESULT: 16/16 checks passed**, no browser console/page errors.

Checks:

1. Initial empty library state and disabled transport are usable.
2. Scan dialog lists drives/folders and starts an explicit scan.
3. A process-worker scan indexes 36 demo files and records the expected failure.
4. Library and details render after scanning.
5. Appearance switches to Studio Tactile; scale, tile finish, reduced motion and
   Reset appearance work; screenshots of both skins are captured.
6. Manual sound-family correction persists across reload, then reverts to auto.
7. Text search matches filenames, paths and track names.
8. Advanced filters apply and clear with a visible filter chip.
9. Favorite, tag and note edits persist across reload.
10. Playback advances, resets on file switch, pauses and stops; pause/stop state is
    reflected in the transport.
11. Piano-roll drag, seek-bar drag and tempo-knob drag stay stable; rendered root
    remains alive and the audio scrub resumes cleanly.
12. Track mute and solo state updates.
13. Format-2 file shows two independent sequence tabs.
14. Export copies the original bytes to a chosen folder.
15. Scan dialog reports source controls and recent issues.
16. No console or page errors.

Screenshots written by this suite:

- `docs/screenshots/studio-clean.png`
- `docs/screenshots/studio-tactile.png`
- `docs/screenshots/appearance-panel.png`
- `docs/screenshots/scan-computer.png`
- `docs/screenshots/filters.png`
- `docs/screenshots/format-2-sequences.png`

## Autoplay deck

Command (same isolated-service pattern; also exercises every write through the
session token, so it doubles as live proof of the loopback boundary):

```powershell
node tests/autoplay-deck.mjs
```

Result: **8/8 checkpoints passed**, no browser console/page errors. Verified
against HEAD as a negative control: "autoplay walks to the next file when a
preview ends" and "a selection survives a filter change" both fail there and pass
here.

1. The transport reports its position in the list on screen.
2. Autoplay walks to the next file when a preview ends by itself.
3. The deck is bounded and says so at the end of the list — it does not wrap.
4. Next and previous move the deck without waiting for an end.
5. A manual stop ends the deck instead of handing off.
6. Autoplay off leaves a finished preview where it is.
7. A selection survives a filter change.
8. No browser console or page errors.

## Sound path and interaction harnesses

Four harnesses drive the built interface without a Python service: `app-harness.mjs`
serves the real `web/dist` and answers every `/api` call from fixtures, so the
React app under test is the shipped one while the user's index stays untouched.
Each carries an explicit anti-lazy-fix guard, and every one was re-run against a
detached `git worktree` at HEAD (with `SKEER_ENGINE_TS` / `SKEER_DIST` pointing at
the pre-fix sources) to confirm the checks fail there.

```powershell
node tests/midi-output-guard.mjs   # 6 of 7 fail before the fix
node tests/space-activation.mjs    # 3 of 5 fail before the fix
node tests/deck-broken-row.mjs     # 3 of 6 fail before the fix
node tests/scan-settings.mjs       # 4 of 5 fail before the fix
```

**`tests/midi-output-guard.mjs` — 7/7.** The engine bundles into headless Chrome
against a fake `navigator.requestMIDIAccess` whose output can throw and can report
itself disconnected; every accepted byte is logged so a real navigation can be
inspected afterwards. On the pre-fix engine this measured 3 note-ons left in
`midiActive` with no note-off ever landing, 28 unhandled `pageerror`s, no
`onstatechange` handler on the port or the access object, and 2 notes still held
when the page went away. Post-fix: the first refused send drops the output, stops
the transport and empties the bookkeeping; a reported disconnect releases the held
notes; a disconnect that also refuses writes still clears state; a real page
unload silences what is held. The guard — a healthy port still receiving all 6
note-ons and 6 note-offs — passes on both engines, so the failures above are the
fix and not a broken harness.

**`tests/space-activation.mjs` — 5/5.** The engine's `play`/`pause`/`stop` are
wrapped in a call counter, so a check says directly "the global shortcut did not
run" instead of inferring it from transport state. Space on the focused Autoplay
button, the Loop button and an active file row now activates that control and
touches nothing else. The body check is the anti-vacuity guard: it must move the
counter, or the patch is not wired and every other result is meaningless.

**`tests/deck-broken-row.mjs` — 6/6.** One row's details call answers 500 and
another returns an empty `preview.sequences`. The deck walks past both to the next
audible row and reports the end of the crate; before the fix it parked at
`Broken Take.mid` (deck 2/5) with the autoplay arming still armed. The guards:
with Autoplay off a broken row is spent but NOT stepped past, and a healthy row
still plays to its own end.

**`tests/scan-settings.mjs` — 5/5.** Settings → Scanning exposes the incremental
re-hash guard as a switch that is on by default, sends `verify_unchanged:"0"` on
save without dropping its neighbours, reads the value back from the service after a
reload, and can be re-armed. The stub merges each PATCH into what it serves, so the
reload check can only pass if the value really travelled through the API.

## Playback stability

Command:

```powershell
node tests/playback-stability.mjs
```

The probe starts a scan of 1,500 copied MIDI files, auditions a 16.27 s arrangement
for 7.6 s, searches and filters during playback, tests loop wrap and stop.

- Source time advanced 7.52 s over 7.61 s wall time (**0.989×**).
- Scan was still active at the sample (1,185 files indexed).
- Search response 41 ms including API/rendering.
- **0 late notes, 0 skipped notes**; 60 notes scheduled.
- Loop wrapped to 0.731 s and kept playing.
- Stop returned source time to 0 and left 0 active voices.

This validates the scheduler/release path but not audible output or a hardware
MIDI device.

## Packaged application smoke test

Command:

```powershell
python tests/test_packaged_smoke.py
```

Runs the actual frozen `SKEER MIDI VAULT.exe` (plus installed/portable variants via
`SKEER_PACKAGED_EXE`) with a temporary data folder and the frozen process-worker
executor.

- Local `/api/health` answered as `SKEER MIDI VAULT` 1.0.0.
- Demo scan completed with **36 indexed, 1 failed, 0 fatal issues**.
- `/api/app/quit` exited the process with code 0 and removed `runtime.json`.
- **No orphan `--multiprocessing-fork` workers** survived app exit.
- The portable ZIP was extracted and the same smoke test passed.
- Re-run 2026-11-15 against the rebuilt bundle, with the session boundary now in
  the frozen build: `GET /api/session` reports **`protected: true`**, the harness
  authenticates its writes the way the page does, and a tokenless
  `POST /api/sources` is answered with **403** by the shipped EXE. That last
  point is what the earlier run of this same script did by itself, before the
  harness carried a token — the boundary reaches the packaged app, not just the
  source tree.
- Re-run 2026-11-15 against the bundle rebuilt for these fixes, which also put the
  shipped HTTP framing under test rather than only the source: `/api/bootstrap`
  from the EXE reports **parser generation 2** and **`verify_unchanged: "1"`** on a
  fresh index, and two hand-written keep-alive sockets show that a body the service
  refused is drained instead of parsed as the next request —
  tokenless write **403 → 200** `{"ok":true,"app":…}` on the same connection, and
  `Content-Type: text/plain` write **415 → 200** with a session token. The frozen
  `web/dist` asset is byte-identical to the one the browser harnesses just drove
  (`index-HeMrzova.js`), so those checks apply to what actually ships.
- Known cosmetic defect, unchanged by this session: at quit the HTTP thread logs
  `OSError: [WinError 10038]` to stderr from `serve_forever`
  ([midivault/server.py:101](../midivault/server.py)) because the listening
  socket closes under the selector. The process still exits 0 with no orphans.

## Installer

`packaging/build_installer.ps1` builds the Setup executable and the portable ZIP named
for the current release, plus the VST3 bundle they carry, into `launch/` with SHA-256
checksums. Rebuilt 2026-11-15 after
the boundary, migration and deck work: Setup 23,361,854 bytes (22.3 MiB,
`c2afd2a0f6f932eb…`), portable ZIP 31,303,849 bytes (29.9 MiB, `572086aa04723f26…`).
Both hashes were recomputed independently against `launch/SHA256SUMS.txt`, and the
interface payload inside the bundle is byte-identical to `web/dist` — including the
new deck code — so what was verified is what ships.

Rebuilt again 2026-11-17 for 1.1.0: `SKEER-MIDI-VAULT-Setup-1.1.0.exe` 25,672,313 bytes
(`fa94a75a2cb23bce…`) and `SKEER-MIDI-VAULT-Portable-1.1.0.zip` 34,694,635 bytes
(`a08612f2f8fd3546…`); the manifest is LF-only and `sha256sum -c SHA256SUMS.txt` exits 0.
The bundle was stamped `862bb165fe2e…` with `dirty: true` and `python
tests/test_packaged_smoke.py` passed against it. The installer's own payload check found
all 198 files copied by the real Setup with nothing extra; the registration and uninstall
legs are environment-blocked and listed as such in
[`../packaging/README.md`](../packaging/README.md).

A full interactive install → shortcuts → uninstall cycle could **not** be completed
inside this sandboxed build session: the setup child process is denied writes to
`HKCU` and the user Start Menu by the sandbox token. Inno’s own minimal test
installer fails the same way, confirming it is environmental rather than an
application-payload failure. Test the Setup once on a normal user desktop before
selling. The portable build is fully tested.

Measured again on 2026-11-17/18, and one detail of that paragraph is now known to be wrong: the
sandbox does not deny this shell's child process the **registry**. The cycle script's own
preflight reports `a child process of this shell may write HKCU\...\Uninstall` as PASS. What it
does refuse is the creation of a **new folder** — under `%LOCALAPPDATA%`, and in the user Start
Menu — each time with `Error 5: Access is denied`, after which Setup rolls back and exits 4.

The release build was then redone from a clean tree, and those are the bytes the release notes
publish: commit `766aa311c5d0`, `dirty: false`, `built_at 2026-11-17T23:09:47Z`, Setup
25,669,100 bytes (`d7ef9f2d05ab0fa9…`) and ZIP 34,695,007 bytes (`b056e9aa765b42dc…`), manifest
LF-only with `sha256sum -c` exit 0. Against exactly those bytes: `python
tests/test_packaged_smoke.py` PASS, printing `built from 766aa311c5d0 clean`; the payload leg
PASS with `files - 199 file(s) installed … all 198 payload file(s), nothing extra`; and the full
eleven-stage gate `NOT READY - 9 passed, 2 failed, 0 skipped, of 11 stages`, with
`stamp PASS - commit 766aa311c5d0, clean, web/dist dafc8187f542` and the two FAILs being
`licence` (two unfilled fields) and `installed` (the folder refusals above).

Re-run 2026-11-18 against the deliverables the gate itself rebuilt after the licence fill — commit
`c520d03eed51`, `built_at 2026-11-18T14:43:09Z`, Setup 25,671,112 bytes, ZIP 34,693,765 bytes —
the same eleven stages report `NOT READY - 10 passed, 1 failed, 0 skipped, of 11 stages`: `licence`
now `PASS - no placeholders, licence page states 1.1.0`, `stamp PASS - commit c520d03eed51, clean`,
`smoke` exit 0 printing `built from c520d03eed51`, and the one FAIL still `installed` at the same
folder refusal. A third run that evening, 16:22:24Z, judged the deliverables its own `installer`
stage rebuilt from commit `a4708a87ec6d` — Setup 25,671,363 bytes, ZIP 34,694,358,
`stamp PASS - commit a4708a87ec6d, clean`, `plugin` and `plugin808` both 6/6 — and reported the
same `NOT READY - 10 passed, 1 failed, 0 skipped, of 11 stages`, the one FAIL again `installed`.
`-FilesOnly` was then pointed at that Setup too: `preflight PASS - Setup 25671363 bytes, hash
matches the manifest` and `files PASS - 199 file(s) installed … all 198 payload file(s), nothing
extra` (`install-cycle-20261118-162825`), so the payload leg now covers every artifact `launch/`
has held today.

Later that afternoon, against the `c520d03eed51` bytes, the payload leg did run.
`install_cycle_check.ps1 -FilesOnly -Dir <a folder inside the workspace>` reported
`CYCLE INCOMPLETE - 3 phase(s) skipped, of 8` with
`files - 199 file(s) installed, including the app, the stamp, the interface and the VST3 bundle -
all 198 payload file(s), nothing extra, and Setup could not finish registering`.
Two earlier runs of that same check failed, each for a reason this
shell owns rather than the artifact: `-Dir` passed but *unquoted*, so a POSIX shell ate the
backslashes and `files FAIL - Setup wrote 199 file(s) outside the requested directory` named
`D:\Projects\skeer-audio\midi-vault\Projectsskeer-audiomidi-vaultbuildworkpayload-probe-1118`, a
folder Inno resolved against the repo and its own rollback then removed; and the check run with no
`-Dir` at all, `CYCLE FAILED - Setup did not install` carrying `Setup was unable to create the
directory "C:\Users\Sebastien\AppData\Local\SKEER MIDI VAULT cycle". Error 5: Access is denied`.
Driving the shipped Setup
interactively (target and `TMP`/`TEMP` both inside the workspace, because Setup is refused its
`%TEMP%` extraction folder here and `/TMPDIR` is rejected on this command line) reached the licence
page and read §6 and §7 as a buyer does; it then copied all 199 destinations, was refused the
Start Menu folder (`Error 5: Access is denied`), then the desktop `.lnk`
(`IPersistFile::Save failed; code 0x80070005`) and then the uninstall key
(`RegCreateKeyEx failed; code 5`) and rolled back to 0 files with no registry entry left — the
same last two refusals a silent run of this Setup recorded on 2026-11-17 in
`install-cycle-20261117-231426`, which is what an earlier version of these docs got wrong when it
said Setup never reached that key. A second
interactive run stopped at that licence page and was ended with Cancel — its log counts
`0` files installed. `python tests/test_packaged_smoke.py` under `SKEER_PACKAGED_EXE`, pointed at a
hand-copied relocated payload, PASSed with `built from c520d03eed51 clean at
2026-11-18T14:43:09+00:00`, `session protected: True`, `keep-alive` 403→200 and 415→200 and
`orphan workers []`. What remains unproven is only what this shell cannot let Setup do: the
Add/Remove Programs entry, the shortcuts, the first launch of the *registered* executable and the
uninstall comparison.

## Classification evaluation

Command:

```powershell
python scripts/evaluate_classification.py
```

Fixture: 31 hand-labelled generated files, plus a 13-track multi-track subset.

| Metric | Result |
| --- | --- |
| File sound family | 31/31 (100%) |
| File musical role | 31/31 (100%) |
| Files flagged uncertain | 5 |
| Track sound family | 13/13 (100%) |
| Track musical role | 11/13 (84.6%) |

**Interpretation:** these are regression numbers on synthetic fixtures authored
with their labels. They are not evidence of general accuracy on commercial MIDI.
Genre has no ground truth and is not scored. The two track-role misses are a cello
pad read as a bassline and a viola chord bed read as an arpeggio; both are reported
in [`classification-evaluation.md`](classification-evaluation.md).

## Benchmark

Command:

```powershell
python scripts/benchmark.py --files 1000 --workers 2
```

Results: 1,000 files / 100,000 notes; full scan 12.00 s (**83.31 files/s**),
incremental 3.92 s (**255.15 files/s**), peak process-tree RSS **88.2 MB**,
SQLite **19.95 MB**, search p50 13.2–13.7 ms. Full method and caveats:
[`benchmarks.md`](benchmarks.md).

## Environment-blocked / not tested

These are also listed in [Known limitations](limitations.md):

- Physical Web MIDI output (no hardware or virtual port available); program
  changes and note messages compile/run but no device round-trip was observed.
- Drag-and-drop into a real DAW window.
- Live network shares, removable media and actual cloud-only placeholder files.
- A directory denied by another user's Windows ACL.
- Libraries larger than 1,000 files, and non-Windows platforms.
- Screen-reader/keyboard-only audit of the canvas piano roll.
- Audible playback quality (headless browser was muted).

## Cleanup and reproducibility notes

- The E2E and playback scripts use isolated database folders and terminate their
  local services; the delivery workspace does not contain their temporary data.
- The benchmark uses system-temp storage for generated data and removes it by
  default (`--keep` retains it).
- Browser suites need `web/node_modules` plus Chrome/Edge; set `CHROME_PATH` if
  needed.
- The server binds to a random loopback port during tests.
