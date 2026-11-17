# Deliverable status: completed, partial, missing

Scoped to the version 1.0.0 brief and re-checked against the 1.1.0 tree on
2026-11-17. "Completed" means implemented in this workspace and exercised by
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
- [x] Per-user Windows installer (`SKEER-MIDI-VAULT-Setup-1.1.0.exe`) that stages the
      app, the interface, the provenance stamp and the VST3 bundle, with the EULA page
      (two seller fields still unfilled — see **Partial**) and the application icon and
      version metadata; no Python, Node.js or admin rights required. The Start Menu
      shortcut, the uninstall entry and the first launch of the installed executable are
      implemented in `packaging/skeer-midi-vault.iss` and are graded by
      `packaging/install_cycle_check.ps1` — see **Partial** for which legs this
      machine could not execute.
- [x] VST3 plug-in (`SKEER MIDI VAULT.vst3`, same 1.1.0 version as the app) shipped
      inside both deliverables: an editor panel with a filter box, the library list and
      three exported controls, reading the app's own index read-only. It is placed in
      `{app}\VST3` for a per-user install and additionally in
      `Common Files\VST3` when Setup runs with `/ALLUSERS`.
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
- **Installer verification.** The payload is proven and the registration legs are not.
  `packaging/install_cycle_check.ps1` ran against the real
  `SKEER-MIDI-VAULT-Setup-1.1.0.exe` on 2026-11-17: Setup copied **all 198 payload
  files** — app exe, `BUILDINFO.json`, `web/dist/index.html`, both checked VST3 files and
  everything else — with nothing missing and nothing written outside the requested
  directory, and that row goes red when one file is added to `launch/`. Setup then exited 4
  and rolled back, because the agent shell's child-process policy refuses Setup's own
  writes to `%LOCALAPPDATA%\Programs`, to the `%APPDATA%` Start Menu folder and to
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall`. The Add/Remove Programs
  entry, the shortcuts, the first launch of the installed executable and the uninstall
  comparison therefore have never completed anywhere. They need one run of
  `powershell -File packaging\install_cycle_check.ps1` from a normal user terminal. The
  `/ALLUSERS` leg — including the `Common Files\VST3` copy — has never run at all, because
  elevation is not available in this environment.
- **Licence page fields.** `packaging/EULA.txt` section 6 and section 7 still hold
  `<<<FILL: contact>>>` and `<<<FILL: jurisdiction>>>`. The gate treats a placeholder as a
  failed stage, so `licence` is FAIL and `scripts/release_check.ps1` reports NOT READY
  until the seller fills both.
- **Installer signing.** The Setup EXE is unsigned (`NotSigned`). Windows SmartScreen
  warning is expected until an Authenticode certificate is applied. `build_installer.ps1`
  is signing-ready through an inert-by-default `-Sign` switch that signs the app before
  ISCC and the Setup after, runs `signtool verify /pa`, and writes `SHA256SUMS.txt` last —
  but that code path has never executed, because no certificate exists yet.
- **Plug-in interaction in a real host.** Six headless suites drive the editor tree,
  including the message loop a `TextEditor` needs, but no window is ever created: a real
  OLE drag, the operating system's own overwrite prompt and keyboard focus inside a host
  window are unproven. Taking focus is a decision the owner has not yet ratified — see
  `docs/limitations.md`.
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
