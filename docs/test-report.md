# Test report

Date: 2026-11-02<br>
Version: 1.0.0<br>
Platform: Windows 10 22H2, AMD Ryzen 9 3900X, 24 logical cores, 63.9 GB RAM

Re-verification: `python -m unittest discover -s tests` was run again on
2026-11-15 and reported **Ran 79 tests — OK** in ~16 s, after the loopback-boundary
(`test_http_boundary.py`, 14) and schema-migration (`test_schema_migration.py`, 9)
suites landed and `test_api.py`, `test_classifier.py`, `test_duplicates.py` grew.
An earlier re-run on 2026-11-14 reported 55. Everything below is the original
2026-11-02 session and keeps the numbers that session produced, except the Python
table, which was refreshed on 2026-11-15.

Machine-readable results: [`e2e-results.json`](e2e-results.json),
[`playback-stability.json`](playback-stability.json),
[`benchmark-results.json`](benchmark-results.json),
[`classification-evaluation.json`](classification-evaluation.json).

## Summary

| Suite | Result | Time |
| --- | --- | --- |
| Python unit/integration (`unittest`) | **79/79 passed** | ~16 s |
| Browser end-to-end (Playwright + Chrome) | **16/16 checks passed** | full isolated scan + interaction run |
| Autoplay deck (Playwright + Chrome) | **8/8 checks passed** | auto-advance, bounded run, manual stop, selection survives filtering |
| Classification regression | 31/31 family, 31/31 role, 13/13 track family, 11/13 track role | < 1 s |
| Playback stability while scanning/filtering | **0 late, 0 skipped** scheduled notes; drift 0.989× | 7.6 s audition |
| Packaged standalone app (Windows) | **passed** health + frozen process-worker scan + quit + zero orphan workers | onedir EXE smoke test |
| Scan/search benchmark | 83 files/s full, 255 files/s incremental, 88.2 MB peak tree RSS, ~13.5 ms search p50 | 12.0 s scan |

## Python tests

Command:

```powershell
python -m unittest discover -s tests
```

Result: **Ran 79 tests — OK** (2026-11-15).

| Module | Tests | What is covered |
| --- | ---: | --- |
| `test_parser.py` | 18 | Format 0/1/2, running status, VLQ, tempo map, SMPTE, sustain, overlapping notes, malformed chunks, missing EOT, text events, warnings, safety caps, fixture parsing |
| `test_classifier.py` | 10 | Family/role rules, confidence caps, misleading-name conflicts, uncertainty, embedded-vs-estimated key, assumed tempo and meter, format-2 per-sequence track labels, genre never high-confidence, unnamed-track channel fallback, silent bars in rhythm analysis |
| `test_scanner_db.py` | 10 | Full and incremental scans, exclusions, protected folders, junction/symlink skip, corrupt file isolation, pause/resume, cancel, user data preservation, unavailable sources, file modification check |
| `test_api.py` | 10 | Health/bootstrap, search/details/Range streaming, labels/favorites/notes/tags, collections/bulk/facets, the autoplay setting persists, unknown setting keys are dropped, scan settings, export-without-overwrite, backup download and static host, rebuild preserving user data, validation errors |
| `test_http_boundary.py` | 14 | Rebound `Host` rejected on reads and on the database backup, missing `Host`, `localhost`/dev-proxy hosts accepted, cross-origin and cross-site `Sec-Fetch-Site` writes rejected, write without a session token rejected, form-encoded and `text/plain` bodies rejected, bodyless write needs only the token, `/api/session` hands the token to a loopback page, reads never need it |
| `test_schema_migration.py` | 9 | A v1 index advances to current and keeps every user edit, the old index is backed up before migration, reopening a current index does not back up again, a fresh index is not migrated, a newer index is refused untouched, an unmapped version jump is refused, legacy fingerprints are skipped until reindexed, the pipeline stamps its generation, only the current generation is compared |
| `test_duplicates.py` | 3 | Exact content duplicates, conservative similar-music grouping, a fingerprint with no generation is never compared |
| `test_platform.py` | 4 | Protected locations, cloud/reparse flags, optional source heuristics |
| `test_demo_accuracy.py` | 1 | Generated demo labels still match the current parser/classifier |

Notable safety checks executed:

- Source file bytes are identical before and after scans and icon edits.
- Existing destination files are never overwritten by export; a numbered name is
  used instead.
- Pause/resume does not lose committed rows; cancel leaves the index consistent.
- Rebuild invalidates analysis caches but keeps manual role/collection/favorite
  data and repopulates automatic labels.
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
- Known cosmetic defect, unchanged by this session: at quit the HTTP thread logs
  `OSError: [WinError 10038]` to stderr from `serve_forever`
  ([midivault/server.py:101](../midivault/server.py)) because the listening
  socket closes under the selector. The process still exits 0 with no orphans.

## Installer

`packaging/build_installer.ps1` builds `SKEER-MIDI-VAULT-Setup-1.0.0.exe` (Inno Setup)
and the portable ZIP into `launch/` with SHA-256 checksums. Rebuilt 2026-11-15 after
the boundary, migration and deck work: Setup 23,361,854 bytes (22.3 MiB,
`c2afd2a0f6f932eb…`), portable ZIP 31,303,849 bytes (29.9 MiB, `572086aa04723f26…`).
Both hashes were recomputed independently against `launch/SHA256SUMS.txt`, and the
interface payload inside the bundle is byte-identical to `web/dist` — including the
new deck code — so what was verified is what ships.

A full interactive install → shortcuts → uninstall cycle could **not** be completed
inside this sandboxed build session: the setup child process is denied writes to
`HKCU` and the user Start Menu by the sandbox token. Inno’s own minimal test
installer fails the same way, confirming it is environmental rather than an
application-payload failure. Test the Setup once on a normal user desktop before
selling. The portable build is fully tested.

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
