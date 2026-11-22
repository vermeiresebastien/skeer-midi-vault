# Deliverable status: completed, partial, missing

Scoped to the version 1.0.0 brief, re-checked against the 1.1.0 tree on
2026-11-17 and against the 1.1.1 tree on 2026-11-21. "Completed" means implemented
in this workspace and exercised by
tests where the environment permits. Environment-blocked verification is called
out explicitly.

## Completed

### Scanning and indexing

- [x] Add and remember drives and arbitrary folders.
- [x] Optional network/removable/optical source handling and local-only defaults.
- [x] Incremental scan using size/mtime/parser/classifier versions, confirmed
      against the stored content hash before a file is skipped.
- [x] Persistent SQLite index with scan history and issues.
- [x] Explicit pause, resume and cancel with committed results preserved.
- [x] Background scan worker pool independent of the UI thread.
- [x] Bounded scheduler intensity (Eco/Balanced/Turbo) and configurable parse workers.
- [x] Skip symlinks/junctions, protected locations, excluded folders, archives and
      cloud placeholders (availability heuristic documented in limitations).
- [x] Unreadable and corrupt files become durable failures; scan continues.
- [x] Unavailable drives remain remembered; their entries are retained.
- [x] Missing-file detection only after a completed source traversal.
- [x] Detection and recovery from interrupted scans.
- [x] Batched SQLite commit path for slow drives (24-item/650 ms batches with
      savepoints).
- [x] Source files opened read-only; no rename/move/delete/unpack operation.
- [x] On-demand and incremental index maintenance.

### MIDI reading

- [x] SMF formats 0, 1 and independent format-2 sequences.
- [x] Running status and variable-length quantities.
- [x] PPQN and SMPTE divisions.
- [x] Tempo maps, multiple time/key signatures, embedded text.
- [x] Sustain CC64, CC120/CC123, overlapping-note repair, assumed durations.
- [x] Malformed/truncated files with warnings and safety caps.
- [x] Sequence tabs for format-2 files instead of incorrect merging.
- [x] Original file streamed with Range support.

### Library and metadata

- [x] Left collections/folders/category navigation.
- [x] Searchable, sortable, paged center list.
- [x] Right details panel with source, metadata, confidence, evidence and piano roll.
- [x] Bottom transport and scan status.
- [x] Instrument/role/style summary per file and per logical track.
- [x] Confidence, evidence, alternatives and conflict explanations.
- [x] Separate "why it is uncertain" notes and an Uncertain collection.
- [x] Favorites, tags, notes and custom collections.
- [x] One-click manual correction, revert-to-auto and bulk file classification.
- [x] Manual corrections stored separately and preserved through upgrades/rebuilds.
- [x] Exact duplicate groups (SHA-256) and separate conservative similar-music groups.
- [x] Duplicate never auto-deleted.
- [x] Full-text search over names, paths, track names, tags, notes and embedded text.
- [x] Filters for family, role, tempo range, meter, key + key evidence, duration,
      bar length, pitch range, density, feel, confidence, duplicate status,
      favorites, source, issues and user tags.
- [x] Folder tree and source filter; multi-select bulk favorite/tag/collection/label.

### Preview and transport

- [x] Canvas piano roll with track colors, velocity lane, playhead and bar grid.
- [x] Play/pause, stop-to-zero, seek by slider and roll, loop, audition tempo knob.
- [x] Per-track mute/solo and jump-to-track.
- [x] Drum preview.
- [x] Preview voice follows the classification (file or track) and can be
      overridden per track, or for a whole sequence, from the details panel.
      Overrides live in the browser, not the index.
- [x] Web MIDI output selector, generated program changes + note on/off.
- [x] Scheduler independent of rendering; all-notes-off on stop/switch/output change.
- [x] Preview-timbre disclaimer.
- [x] Format-2 sequence switching in the preview/transport.
- [x] Playback remains stable while scanning and filtering in the measured test.

### Data and maintenance

- [x] SQLite WAL + FTS5 with schema versioning/migration.
- [x] Downloadable online database backup.
- [x] Index rebuild that preserves user data and corrections.
- [x] Copy/export originals without overwriting; numbered duplicates.
- [x] Browser folder picker export on Chromium.
- [x] Reveal original in File Explorer.
- [x] Drag-to-DAW download-URL path on Chromium.
- [x] Settings for default scan behavior and data/privacy information.

### Interface and delivery

- [x] Approved palette, typography, logo and surface language.
- [x] Studio Clean and Studio Tactile skins over shared components.
- [x] Accent, meter color, texture, contrast, border, tile finish, knob finish,
      interface scale and reduced motion settings.
- [x] Responsive layout at 1440×1000 and narrow breakpoints; 80–125% scale.
- [x] One-command source launch (`start.bat`/`start.ps1`) and manual server command.
- [x] Standalone PyInstaller application containing the Python runtime and web
      interface; packaged smoke test passes (health, frozen process-worker scan,
      quit, no orphan workers).
- [x] Per-user Windows installer (`SKEER-MIDI-VAULT-Setup-1.1.1.exe`) that stages the
      app, the interface, the provenance stamp and the VST3 bundle, with the EULA page
      (both fields filled and compiled in on 2026-11-18) and the application icon and
      version metadata; no Python, Node.js or admin rights required. The licence page was
      then **seen as a buyer sees it**, rendered by the Setup built from `c520d03eed51`:
      §6 shows `Licence and support enquiries: sebastienvermeire@gmail.com`, §7 shows
      `This agreement is governed by the law of Belgium`, no `<<<FILL:` token appears, and
      the wizard defaults to *I do not accept the agreement* with **Next** disabled until
      the buyer chooses. The Start Menu shortcut, the uninstall entry and the first launch
      of the installed executable are implemented in `packaging/skeer-midi-vault.iss` and
      are graded by `packaging/install_cycle_check.ps1` — see **Partial** for which legs
      this machine could not execute.
- [x] VST3 plug-in (`SKEER MIDI VAULT.vst3`, same 1.1.1 version as the app) shipped
      inside both deliverables: an editor panel with a filter box, the library list and
      three exported controls, reading the app's own index read-only. It is placed in
      `{app}\VST3` for a per-user install and additionally in
      `Common Files\VST3` when Setup runs with `/ALLUSERS` — the machine-wide placement
      that 1.1.0 got wrong, graded on the 1.1.1 artifact by an executed `-AllUsers` cycle
      rather than asserted (see **Partial**).
- [x] Build provenance: `_internal/buildinfo/BUILDINFO.json` inside the bundle
      (commit, dirty flag, status/diff/untracked digests, `web/dist` hash), published
      by `/api/health` and the debug surface.
- [x] Portable standalone ZIP with SHA-256 release checksums (LF-only manifest, so
      `sha256sum -c` exits 0); the ZIP and the installer carry the same 198 files.
- [x] One release number asserted by a gate: `scripts/check_version_consistency.py`
      reads 11 values across 8 files, including the licence page and the *absence* of a
      literal in the build script.
- [x] `scripts/release_check.ps1`: eleven stages, one exit code
      (0 READY / 1 failed / 2 could not run), per-stage logs, and a falsifier
      (`python scripts/check_release_gate.py`) that plants one defect per case.
- [x] Desktop launcher: single-instance mutex, tray Open/Quit, Settings quit,
      automatic browser open, per-user runtime/log files.
- [x] Local-only loopback binding and privacy notice.
- [x] Interaction hardening: rasterized paper texture (no full-screen SVG filter
      or blend mode), static canvas with DOM playhead, scrub pause/resume,
      debounced tempo changes, defensive numeric guards and a branded React error
      boundary instead of a blank white page.
- [x] Generated demo library, evaluation, unit/integration/browser tests,
      screenshots, benchmark and playback stability reports.
- [x] Documentation: README, architecture, formats, design, limitations, status,
      test report, classification evaluation, benchmark, packaging and signing
      notes.

## Partial

- **Real-world classification validation.** Rules are tested on hand-labelled
  synthetic fixtures. Real commercial MIDI, layered GM programs and unnamed tracks
  are expected to produce more uncertainty. No broad real-world corpus was
  labelled and used for accuracy claims.
- **Track-level bulk reclassification.** File-level bulk labeling is implemented;
  track-level edits are one track at a time and do not have a multi-track bulk UI.
- **Collection management.** Create, add, remove and filter works. Rename/delete
  exist in the API but have no dedicated collection-management screen.
- **Prediction audit history.** Predictions are stored per classifier version and
  current evidence is shown, but there is no full historical prediction browser.
- **Web MIDI device verification.** Program changes and note messages are
  implemented, but no physical MIDI device was available for a round-trip test.
- **DAW drag target verification.** The Chromium download-URL drag path is
  implemented; actual drag into a DAW was not verified in this environment.
- **Network, removable and cloud sources.** Detection, opt-out and skip paths are
  implemented and unit-tested; live cloud-provider files and physical media were
  not available for end-to-end tests.
- **Unreadable permission test.** Error handling is unit-tested through scan
  failure records, but a live ACL-denied directory owned by another user was not
  created on this workstation.
- **Large-library scale.** 1,000 files were benchmarked. Tens/hundreds of
  thousands of files and enormous folder trees are not benchmarked; expect
  proportionally longer scans and slower search.
- **Accessibility.** Keyboard focus, labels, switch semantics, reduced motion and
  scale are implemented. A full screen-reader/keyboard-only audit and full canvas
  piano-roll keyboard navigation are not included.
- **Platform coverage.** Windows 10/11 is the tested platform. The Python service
  is portable, but drive discovery and skip behavior are Windows-specific.
- **Installer verification.** The payload is proven on the shipped bytes; the registration legs were
  unreachable from this shell and were completed from an elevated one on 2026-11-21.
  `packaging/install_cycle_check.ps1` ran against the real
  `SKEER-MIDI-VAULT-Setup-1.1.0.exe` on 2026-11-17 (the `766aa311c5d0` build) and again on
  2026-11-18 against the `c520d03eed51` rebuild that carries the filled licence page, and once
  more at 16:28 against the `a4708a87ec6d` Setup the final gate built (`hash matches the
  manifest`), so this leg
  now covers the artifact that is in `launch/`: with `-FilesOnly -Dir` pointed inside the
  workspace it graded `files PASS - 199 file(s) installed, including the app, the stamp, the
  interface and the VST3 bundle - all 198 payload file(s), nothing extra, and Setup could not
  finish registering`, and a second run of that same Setup in **GUI** mode copied all 199
  destinations into a workspace folder before the identical refusal rolled the whole thing back
  (`0` files left behind, `HKCU` still holding no entry). Setup exits 4 either way, because the
  agent shell's child-process policy refuses Setup everything outside the workspace — measured
  the same afternoon at the cycle's `%LOCALAPPDATA%` target and at the `%APPDATA%` Start Menu
  folder, each `Error 5: Access is denied`, in silent and in interactive mode alike; and at
  `HKCU\...\Uninstall`, which Setup's own log has been refusing since the 2026-11-17 silent run
  that pointed `/DIR` inside the workspace — that one copied the payload, failed the desktop
  shortcut with `IPersistFile::Save failed; code 0x80070005`, then `RegCreateKeyEx failed;
  code 5` on `Creating new uninstall key`, and rolled back; the 2026-11-18 interactive run
  reached the same two. A per-user install puts its files
  under `%LOCALAPPDATA%` too, so that is the leg
  this machine cannot exercise; it says nothing about the buyer's. **That limit was crossed on
  2026-11-21:** the Add/Remove Programs entry, both shortcuts, the first launch from a
  Setup-registered folder and the uninstall comparison all completed, in an elevated terminal, twice
  — `install-cycle-20261121-153747` (tasks declined) and `install-cycle-20261121-153801`
  (`-WithShortcuts`), each `CYCLE OK - 17 phases passed` against the 1.1.0 shipping Setup, with the
  shared-VST3 census reading 1317 entries before and after both. See
  `packaging/README.md`, "The install → run → uninstall cycle". The one leg narrower than that —
  `/ALLUSERS`, and with it the `Common Files\VST3` copy — ran at 18:56Z the same day from an elevated
  terminal, against the Setup the 1.1.1 certification had just built, and ended
  `CYCLE OK - 18 phases passed`: `shared-folder PASS` with 2 files placed under
  `C:\Program Files\Common Files\VST3`, every one inside our own bundle, nothing else in that folder
  moved, and the folder back at its censused 1317 entries after the uninstall. It took two runs
  eighteen minutes apart because the first graded that row **FAIL** on a defect in the grader rather
  than in the installer: Setup's own log had already listed both files created and both deleted
  again. The command still refuses from this shell — it is not elevated (`IsAdmin=False`, measured
  2026-11-18) and the consent prompt is the owner's to answer, so `-AllUsers` fails in preflight with
  `CYCLE NOT RUN - preflight refused; nothing was installed` rather than half-installing. What this
  machine could reach on its own was a *relocated* copy of that payload:
  `python tests/test_packaged_smoke.py` under `SKEER_PACKAGED_EXE` PASSed against a hand-copied
  install tree with `built from c520d03eed51 clean`, and the 2026-11-21 cycles' `installed-run`
  rows do the same from a folder Setup actually registered — so the executable has now been run from
  `launch/`, from a hand-copied tree, and from installed locations in both install modes. What is still
  unwitnessed has narrowed to one verb. A host has now been shown *reading* the bundle — Live 12.3.2
  scanned the machine-wide copy on 2026-11-22, logged a `found:` record naming
  `C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3`, and persisted one device row carrying our
  class ID — but no host has been shown *instantiating* it, and those are different claims. The second is
  the "Plug-in interaction in a real host" bullet below.
- **Installer signing.** The Setup EXE is unsigned (`NotSigned`). Windows SmartScreen
  warning is expected until an Authenticode certificate is applied. `build_installer.ps1`
  is signing-ready through an inert-by-default `-Sign` switch that signs the app before
  ISCC and the Setup after, runs `signtool verify /pa`, and writes `SHA256SUMS.txt` last —
  but that code path has never executed, because no certificate exists yet.
- **Plug-in interaction in a real host.** Six headless suites drive the editor tree,
  including the message loop a `TextEditor` needs, but no window is ever created: a real
  OLE drag, the operating system's own overwrite prompt and keyboard focus inside a host
  window are unproven. Taking focus is a decision the owner has not yet ratified — see
  `docs/limitations.md`. Recognition is off this list as of 2026-11-22: the host scanned the
  machine-wide bundle, logged a record for it and kept one module row plus one device row for
  class-ID tail `536b41754d766c74`, at version `1.1.1`, with the fingerprint it read (`737400:6b01e16a`)
  matching its own scan log — all without anything of ours opening a window. Instantiation is not: the
  live set at measurement carried one audio track, whose devices were a stock `Utility` and a third-party
  `Snap Heap`, and no instance of ours, so the sentence above about *reading* rather than *loading* is a
  read of the running song rather than an absence of evidence. What that same scan did turn up was a scope
  question, not a defect: the host filed this plug-in as `audiofx`/`Fx`, where every sibling in the family
  is `instr`/`Instrument`, because `IS_SYNTH` was `FALSE` in `plugin/CMakeLists.txt`. Decided and built for
  1.1.2: the staged bundle's `moduleinfo.json` now reads `Instrument|Synth` and the host suite sees it as an
  instrument. What remains unmeasured is the part a producer cares about — whether the filing costs or wins
  users — and the host's own cache still says `Fx` until it rescans the new bytes.
- **Native window shell.** The standalone app opens the system browser and runs a
  tray service; it is not a custom Electron/WinUI window. This preserves Web MIDI,
  browser folder picking and drag behavior available in Chrome/Edge.

## Missing / intentionally not included

- Paid or cloud AI classification. The brief explicitly excludes paid AI.
- A bundled local ML model. The engine seam exists, but no model is installed.
- Editing, trimming, quantizing or rewriting source MIDI files.
- A notation/score view, lyrics editor or karaoke `.kar` support.
- RIFF/RMID, MIDI 2.0/UMP, tracker formats, DAW project import.
- Automatic archive extraction.
- MIDI export of an edited/auditioned arrangement or offline audio bounce.
- Stem export, plugin hosting, sample streaming or a full DAW audio engine.
- Recording, MIDI learn, synth preset management.
- Automatic duplicate deletion (by design).
- Cloud sync, user accounts, uploads, telemetry or remote access.
- Code signing, auto-update or a native wrapper.
- macOS/Linux validation, localization and full accessibility certification.
- In-app database restore screen (backup download and manual restore only).

## Feature completeness summary

The requested browse/search/analyze/audition/index workflow is implemented end to
end. The remaining gaps are mostly validation breadth (real-world data, hardware
and large scale) and deliberately out-of-scope editing/DAW/model features. Nothing
in the "missing" section was silently represented as complete.
