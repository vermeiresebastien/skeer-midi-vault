# Known limitations

This is version 1.1.2, re-checked against that tree on 2026-11-22. The list is deliberately explicit: the application is
useful, but it is not a DAW, a commercial MIDI catalog and it does not claim
general-purpose classification accuracy.

## Classification and musical analysis

- **Rules, not a learned model.** Instrument, role and style are inferred from
  General MIDI programs, track names, note statistics and filename patterns. The
  included 31-file evaluation is synthetic, controlled and written alongside its
  labels. Do not read its 100% file-level result as real-world accuracy.
- **Genre is a hint.** The style hint (for example "House / techno 22%") has no
  ground truth, no accuracy claim and is intentionally displayed as speculative.
- **Ambiguous music is allowed to be uncertain.** Layered synths, mixed GM
  programs, unnamed tracks, drums with pitched content and tracks that change
  instrument mid-file produce uncertainty or an `Unknown` result. That is a
  feature, not a hidden failure.
- **Format-2 file classification uses the primary sequence.** Individual
  sequences are available separately; a whole-file label is not invented by
  merging independent sequences.
- **Track roles are less reliable than families.** The controlled sample classifies
  13/13 track families but only 11/13 track roles. A cello pad can be read as a
  bassline, and a viola chord bed as an arpeggio.
- **Bars are approximate.** Pickups, mid-file meter changes, tempo changes and
  SMPTE timecode make exact bar numbering impossible without a score. The UI says
  approximate.
- **Key is either embedded or estimated.** The interface distinguishes the two;
  estimated keys can be wrong on modal, atonal or very sparse material.
- **Tempo filtering matches the tempo map's range**, not only the first tempo.
  The displayed BPM is the primary/initial tempo.
- **Time-signature display uses the first meter plus a change count.** The full
  event list is stored, but a full notation view is not provided.

## File and format coverage

- Only Standard MIDI Files with `.mid`/`.midi` are indexed. RIFF/RMID, MIDI 2.0 /
  UMP, `.kar`, trackers, DAW projects and compressed archives are out of scope.
  Archives are never unpacked.
- Files over 64 MB and files exceeding parser safety caps are recorded as failed
  rather than truncated silently.
- Some malformed files are only partially recoverable. They may be indexed with
  warnings and an uncertain classification; the source is never repaired.
- SysEx is skipped. Sustain is interpreted for note lengths but not forwarded over
  Web MIDI.
- Playback sends program changes and notes to Web MIDI; it does not forward
  sustain, pitch bend, modulation, aftertouch or SysEx in this version.
- SMF format 2 playback plays one independent sequence at a time. There is no
  "play all sequences simultaneously" mode.

## Scanning and file systems

- Drive discovery and protected-location rules target **Windows 10/11**. The
  service may run on macOS/Linux, but those platforms are not validated here and
  drive enumeration differs.
- Network, removable and optical sources are treated as optional. Detection of
  mapped UNC paths and email-style cloud-drive labels is **heuristic**. It avoids
  scanning such drives by default, but it cannot prove that every source is
  remote or cloud-backed.
- Cloud-placeholder detection is best effort using Windows attributes and
  reparse-point flags. A provider that materializes files without those flags
  can make the scanner open cloud content. Download-on-access behavior remains a
  provider policy, not something this app can guarantee.
- Inaccessible files/folders become durable failures or traversal issues when the
  OS reports them; a path that hangs inside a third-party file-system driver can
  still delay traversal.
- Excluded paths are prefix/subtree excludes. There is no per-file ignore syntax
  or per-source override of the global skip rules.
- Folders with millions of entries, very deep trees or multi-million-file
  libraries have not been benchmarked. The tested documented result is 1,000
  generated files. The scanner is bounded in memory but large scans take time.
- Duplicate similarity is intentionally conservative. It surfaces likely related
  music; it is not a musicological equivalence proof.
- Source files are never modified, moved, renamed or deleted. Consequently a file
  deleted outside the app remains in the index and is marked missing on the next
  completed scan; it is not removed from your library automatically.

## Preview and playback

- Preview timbres are generated approximations. They are not the original
  instrument sounds, samples, articulations or effects in the source file.
- Web MIDI requires a Chromium-based browser, user permission and an available
  hardware or virtual MIDI port. **No physical MIDI device was available for
  this release**, so device round-trip behavior is implemented but unverified.
- The scheduler runs in the browser tab. Very long hidden-tab sessions can be
  throttled by browser timer policy; scheduled lookahead covers normal
  backgrounding but this is not a real-time DAW audio engine.
- No offline audio bounce, stem render, MIDI export of auditioned material or
  sample-exact playback is provided.
- Looping wraps the selected sequence in source time. Tempo changes inside the
  file are honored, while the audition tempo knob scales the entire preview.
- DAW drag uses Chromium's download-URL drag flavor. Some DAWs, browsers or
  security policies may produce a copied file instead of a native drag. A real
  DAW drag-and-drop test is not included in this release; Reveal and Copy/export
  are the guaranteed paths.
- **Preview sounds are approximations, not samples.** Each voice is a small
  oscillator recipe (waveform, filter, envelope, one or two extra partials). It
  stands in for a category so you can tell a bass line from a pad at a glance; it
  is not a piano, and it is not the sound the file was authored with.
- **The category→voice mapping is opinionated.** Ten sounds cover a hundred-plus
  GM programs, so several instruments deliberately share one voice, and a track
  classified `Unknown` inherits the file's category. When you disagree, pick the
  sound yourself.
- **Correcting a file category re-voices the whole file.** It is meant to rescue
  misread loops and one-part files, and it does so by outranking each part's
  automatic label. On a genuinely multi-instrument arrangement that can be too
  blunt: the machine's per-part guess was probably better. Fix the individual
  parts, or use *follow analysis* in the Tracks card. Merely **accepting** an
  automatic prediction never re-voices anything — only a real correction does.
- **Sound picks live in the browser, not the library.** They are stored under the
  file's path in this browser's local storage. They are not in the SQLite index,
  so they are not in a database backup, do not follow the library to another
  machine or browser profile, and are lost when local storage is cleared.
  Renaming or moving a source file orphans its picks.
- **The GM program sent to hardware is a stand-in.** When a Web MIDI output is
  selected, an explicitly chosen sound maps to one GM program number; `Auto`, the
  neutral default and the drum kit leave the file's own program untouched. Your
  hardware's patch for program 24 is not this app's `pluck`, and a kit still
  depends on the receiving device mapping channel 10 to percussion.

- **The autoplay deck is bounded by what the list shows.** With Autoplay on, a
  preview that ends by itself opens the next row — your selection if the open file
  is part of a multi-selection, otherwise the page of results on screen. It stops
  at the end of that list instead of fetching the next page, so a 400-file pack is
  ear-scanned a page at a time. Pause, Stop or a seek ends the run as well: only a
  clip that plays out advances, and a clip you interrupted is not silently skipped.
  Stepping with the transport's previous/next buttons works with Autoplay off, but
  only moves the selection — it does not start playing.
- A file that has nothing to hear (no notes, or a zero-length sequence) is stepped
  over rather than left to stall the deck; a file that failed to parse is not in
  the list to begin with.

## Interface and accessibility

- The canvas piano roll is mouse/touch driven; it is not fully keyboard-navigable
  and it is not a screen-reader substitute for a score. Standard controls,
  dialogs, tables and the transport have labels and keyboard focus states.
- A full assistive-technology audit (NVDA/Narrator/VoiceOver) was not performed.
- English only. No localization or right-to-left layout pass.
- Chrome and Edge are the validated browsers. Safari/Firefox may lack Web MIDI or
  Chromium's file-picker/drag behavior.
- The interface-scale control relies on CSS zoom. At unusual OS/browser zoom
  combinations, text can render slightly differently.

## Data, privacy and deployment

- The service binds to loopback only and has no account system. It has **no
  authentication**, so any process or user that can reach the loopback port on a
  shared machine can query the local index while the app is running. Do not run it
  on a shared untrusted machine if that matters. Requests whose `Host` is not a
  loopback name are refused, cross-site writes are rejected, and writes from the
  interface carry a per-process session token — that closes a webpage reaching
  this port (DNS rebinding), not another local process. See
  `docs/architecture.md`, "The loopback boundary".
- All data is in one SQLite database. Backups are downloaded from the UI; there is
  no in-app restore screen and no cloud sync. To restore, quit the app and replace
  `midivault.sqlite3` with a downloaded backup. A schema migration writes one more
  copy automatically, `midivault-index-v<from>-before-migration-<utc>.sqlite3`,
  beside the index before it changes anything; nothing deletes or restores them.
- An index built before fingerprints were versioned needs one re-scan before
  similar-music grouping speaks again. Until then the Duplicates view
  under-reports on purpose: those vectors carry no generation and are never
  compared against current ones.
- "Rebuild index" preserves user data but has no progress rollback: if a source is
  offline during the rebuild, its records remain as last indexed/missing
  depending on source availability.
- The standalone installer is a per-user, unsigned Inno Setup package. Windows
  SmartScreen may warn until it is Authenticode-signed by the seller. A certificate,
  auto-update mechanism and enterprise MSI package are not included.
- The installed app runs as a hidden local service with a system-tray icon and
  opens the interface in the **system default browser**. It is not a custom
  Electron/WinUI window. A browser (Edge/Chrome) is therefore required; the tray
  icon needs an interactive Windows desktop session.
- **A second instance calls the first one dead, and a headless launch can stop on a
  modal.** Measured 2026-11-19 against the `1c17f6a` bundle: while one instance was
  answering `/api/health` on `127.0.0.1:8937`, a second `SKEER MIDI VAULT.exe --server-only
  --no-open --port 8941 --data-dir <another folder>` raised "SKEER MIDI VAULT is already
  running, but its local service is not responding." The sentence was false. `MUTEX_NAME`
  ([desktop.py:41](../desktop.py)) is a fixed `Local\SkeerMidiVaultDesktopV1`, so the
  single-instance lock is per session and ignores `--data-dir` and `--port`, while
  `_show_existing_instance()` then reads `runtime.json` from **its own** data directory
  ([desktop.py](../desktop.py)) — a second library therefore cannot see the first one's
  runtime file, waits five seconds, and concludes the service is dead. Worse, that branch's
  `_message_box` ([desktop.py](../desktop.py)) is not gated on `open_browser` the way the
  two branches above it are, and it calls `MessageBoxW(0, …)`: a launch asked to be headless
  blocks on a dialog with no owner. **The release gate was exposed to exactly that**, because
  `tests/test_packaged_smoke.py` starts the packaged exe with its own `--data-dir` and a free
  port — if the app was already running, the `smoke` stage waited on a dialog nobody can see
  instead of exiting non-zero, and it passed on every earlier 2026-11-19 run only because no
  other instance was up. That half is now closed in the harness: `running_instances()` lists
  the image through `tasklist`, and when one holds the mutex the script prints its pid and
  exits 1 before it spawns anything, so there is no second instance left to raise a dialog.
  Measured both ways against the same `1c17f6a` bundle on 2026-11-19 — with a probe instance
  up (pid 30620) the stage went red naming that pid; with none up it still reached
  `PASS packaged smoke test` and exit 0, which is what proves the new check is not vacuous.
  **The product is unchanged.** The false sentence and the ungated modal are still what a user
  gets on a double-launch, and the remedy is not decided: key the mutex to the resolved data
  directory (which lets two instances each own a tray icon), or stop treating the mutex as
  evidence about a service whose runtime file lives elsewhere — and in either case print to
  stderr and exit non-zero when `--server-only`/`--no-open` was requested.

- **A library past roughly 30,000 files could not start the packaged app at all.**
  Measured 2026-11-22 against the owner's own index (450 MB, 48,516 files, schema 2)
  and the shipped `10fbc15aeb07` bundle. `%LOCALAPPDATA%\Skeer\MIDI Vault\midivault-desktop.log`
  reads `Starting SKEER MIDI VAULT 1.1.1` at 05:34:41, then `ERROR Startup failed: The
  local service started but did not answer its health check` at 05:36:31, then nothing
  until `Desktop launcher exiting` at 16:20:51 — the modal, open on his desktop for ten
  hours. It is not a crash and the index is not at fault. The launcher polls
  `/api/health` up to 80 times with a **1.2 s** socket timeout per attempt, and that
  endpoint answered by running `PRAGMA integrity_check` and `PRAGMA foreign_key_check`
  over the whole library. Timed on a copy of that database: 1.72 s + 0.42 s + a 0.13 s
  coverage scan = **2.27 s**, with the file cache warm, so that is a floor. Every attempt
  therefore gave up about a second early; 80 × (1.2 + 0.1) = 104 s, and the index's last
  migration write at 05:34:46 plus 104 s is the 05:36:31 failure to the second. The
  service ran in a thread of the launcher's own process, so the `raise` in `_health`'s
  caller took a healthy service down with the dialog. The same sentence appears on
  2026-11-14 for 1.0.0, so this is a size cliff and not a 1.1.1 regression — and because
  `_log_path()` resolves inside the data directory, the gate's launches (which pass
  `tests\packaged-smoke-data`) never wrote a line into the file above: `smoke` was green
  against a fixture index of a handful of files, where `integrity_check` costs
  microseconds. **A green `smoke` stage says the bundle runs, not that it runs against a
  library a customer would have.**
  **Fixed here.** `/api/health` now reports state without auditing the pages
  (`Database.db_health(deep=False)`), and the audit stays where it already had a route:
  `GET /api/db/health`. Re-measured over real HTTP against the same 450 MB index after
  the change: `/api/health` **0.17 s**, `/api/bootstrap` 1.40 s, `/api/library?limit=50`
  0.23 s — the library is not too big for the interface, it was only ever too big for the
  readiness question. The wait is now a monotonic 45 s budget with a 10 s per-attempt
  timeout (`_wait_until_ready`), so a late-but-real first answer becomes ready instead of
  being called dead. Two checks pin it: `tests/test_api.py` records the SQL the readiness
  route actually executes and fails if either PRAGMA comes back, while requiring the audit
  route to still perform one; `tests/test_desktop_ready.py` pins both directions of the
  budget. **What this did not fix at the time: the shipped bytes.** `launch/` and the published
  v1.1.1 assets carried the defect and no argument avoided it, because the readiness
  loop runs before `--server-only`/`--no-open` branches — so 1.1.1 could not be launched from
  a large library by anyone until a release was built from this tree. In the meantime
  `python -m midivault.server --open` serves the same default data directory with no
  launcher and therefore no self-imposed gate.
  **No longer true of `launch/`.** The 1.1.2 bundle stamped there names commit `d8110db06738`,
  built `2026-11-22T18:15:13+00:00`, clean, and that commit descends from `f2dff96` (`git
  merge-base --is-ancestor f2dff96 d8110db06738` exits 0). The Setup and ZIP in `launch/` are
  those bytes, digests recorded in [docs/release-notes-1.1.2.md](release-notes-1.1.2.md); a
  v1.1.2 release page does not exist yet, so as of
  this writing the newest published assets are still 1.1.1's and still carry the defect. So is
  anyone on 1.1.1, whatever gets published. What is *still* not witnessed
  is the end of the story rather than its middle: no packaged launch has been run against the
  owner's 48,516-file index. The 0.17 s above is that database served over real HTTP by the
  fixed code, and every packaged launch this repo performs — the `smoke` stage and both
  install-cycle arms included — passes a fixture `--data-dir`, which is the hole that let the
  defect ship twice. The first `SKEER MIDI VAULT.exe` start on the real index is the measurement
  that closes it.

- The installer's payload is proven on every build in `launch/`; its registration is not.
  `packaging/install_cycle_check.ps1` ran the real Setup on 2026-11-17, against the
  `766aa311c5d0` build, against the `c520d03eed51` rebuild and against the `a4708a87ec6d`
  deliverables that the last gate rebuilt, all on 2026-11-18, and confirmed
  **all 198 payload
  files** land with nothing missing and nothing written outside the target directory — that
  row goes red when one file is added to `launch/`. Setup then exits 4 and rolls back, because
  this shell's policy refuses **Setup** every write outside the workspace — first seen as the
  creation of a new folder under `%LOCALAPPDATA%` and in the Start Menu (`Error 5: Access is
  denied`), and confirmed as something broader: with both folders pre-created by the shell, so
  Setup had nothing to make, it copied 0 files and failed at `CreateFile failed; code 5`. The
  account's ACLs on those folders are FullControl and a `powershell` child of the same shell
  writes there freely, so the refusal follows the executable, not the path and not the artifact.
  The registry **is** a block to Setup as well, and the log that proves it predates this week:
  the 2026-11-17 silent run that pointed `/DIR` inside the workspace copied the payload, then
  failed at the desktop shortcut (`IPersistFile::Save failed; code 0x80070005`) and at
  `Creating new uninstall key: HKEY_CURRENT_USER\...\Uninstall\{B7E2D5A8-…}_is1`
  (`RegCreateKeyEx failed; code 5`) before `Rolling back changes`; the 2026-11-18 interactive run
  reached the same two refusals. An earlier version of this bullet claimed Setup "never reached
  that key" — wrong, because it generalised from the runs refused a folder first and never quoted
  the one that got furthest. Even the extraction folder is refused: Setup cannot make its
  `is-XXXX.tmp` under `%TEMP%` here, which is why an interactive run needs the child's
  `TMP`/`TEMP` pointed inside the workspace — something `install_cycle_check.ps1` has done since
  its own line 198, so only a hand-run Setup has to be told. From this shell the payload leg
  therefore needs
  `-FilesOnly -Dir <a path inside the workspace>` — and that path has to reach PowerShell with
  its backslashes intact, since an unquoted `D:\…` loses them in a POSIX shell and Setup then
  installs into a mangled relative folder and `files` reports 199 destinations outside the
  requested directory. Run without `-Dir`, Setup never reaches its
  target and `files` reports FAIL for that reason alone. The Add/Remove Programs entry, the
  shortcuts, the first launch of the installed executable and the uninstall comparison
  have therefore never completed *from this shell* — they completed on 2026-11-21 from an elevated
  terminal, twice, `CYCLE OK - 17 phases passed` each way, with the shared VST3 folder read back at
  the same 1317 entries it started with; the runs and what each row proved are recorded in
  `packaging/README.md`. One leg is still open: `/ALLUSERS`, whose consent prompt is the owner's to
  answer. The portable ZIP and the packaged app do pass their smoke tests, and so does a
  hand-copied relocated payload under `SKEER_PACKAGED_EXE` — but that is the executable running
  from a folder, not from a registered install, and the registered case is now the elevated one.
- No local model is installed or downloaded. The optional local-model integration
  point is an architecture seam for later work.
- Third-party npm packages are used to build/serve the interface
  (React, Vite, font packages, Playwright only for tests). Runtime Python is
  standard-library only; the standalone build bundles the Python runtime.
- **One open Dependabot alert on the default branch, with no fix available to take.**
  `picomatch@4.0.7` — GHSA-fc5q-39xc-vjpf / CVE-2026-112366, a ReDoS through a
  single-branch repeated extglob **pattern** — reaches this project transitively and in
  `development` scope only, through `vite@7.3.7`, `fdir`, `tinyglobby` and `vitest`.
  There is nothing newer to install: `npm view picomatch dist-tags` is `latest: 4.0.7`,
  the advisory's `first_patched_version` is null, and upstream has the fix in a pull
  request, not a release. What was measured here on 2026-11-18 instead of assumed: no
  `picomatch` file exists anywhere under `launch/` or `web/dist`, so nothing the customer
  runs carries it; and instrumenting the module for one real `npm --prefix web run build`
  (exit 0, module restored and hash-checked afterwards) shows that build compiling exactly
  five patterns — `**/.env`, `**/.env.*`, `**/.env,**/.env.*,**/*.{crt,pem},**/.git/**`,
  `**/*.{crt,pem}` and `**/.git/**` — every one a literal inside vite's own dist, none of
  them an extglob, and none derived from `web/vite.config.ts`, which sets no alias,
  `optimizeDeps` or `ssr` entry that could feed one. The vector therefore needs someone to
  hand the tooling a repeated-extglob pattern; hostile *file names* are the other input and
  cost 0.1 ms against an ordinary glob at 4,805 characters. Re-check with
  `npm view picomatch dist-tags`, and when a publish newer than 4.0.7 exists run
  `npm --prefix web update picomatch` followed by the release gate.

## The VST3 plug-in

Since 1.1.0 the plug-in ships with the app: `packaging/build_installer.ps1` stages the
built bundle into `launch/VST3`, and Setup installs it — so **installing SKEER MIDI VAULT
now does put a VST3 somewhere**. Where it lands is the remaining caveat, and it depends on
how Setup was run. At the default lowest privileges it goes into
`{app}\VST3`, a folder no host scans automatically, so add it to the host's VST3 search
paths or re-run Setup with `/ALLUSERS`, which puts it in
`%ProgramFiles%\Common Files\VST3` where every host looks. Through 1.1.1 an all-users install did
*both*: the app-folder `[Files]` entry carried no `Check:`, so a machine-wide install left two
byte-identical bundles on disk under one class ID. That duplicate is what 1.1.2 removes — the two
entries are now mutually exclusive (`Check: not CommonVst3` on the app folder, `Check: CommonVst3`
on the shared one), so either install mode places exactly one bundle. Separately, 1.1.0 sent the
machine-wide copy to `%ProgramFiles%\VST3`, a folder no host scans by default, while
its own Setup log and these pages said "Common Files". The log now prints the expanded path, so the
log — not the documentation — is the authority on where a given install put it. Either way nothing
in the installer edits, adds or removes a host's own scan
path. The `/ALLUSERS` leg is no longer unexecuted: from an elevated terminal on 2026-11-21,
`packaging\install_cycle_check.ps1 -AllUsers` ended `CYCLE OK - 18 phases passed` against the 1.1.1
Setup, with the bundle placed under `C:\Program Files\Common Files\VST3`, nothing else in that folder
moved, and the uninstall returning it to the 1317 entries it was censused at. The same command
refuses rather than half-installs when the terminal is not elevated; see `packaging/README.md`.
The chain gained a link on 2026-11-22, and a shell did substitute for it after all. Ableton Live keeps two
files beside its preferences — a per-pass scan log and a scan cache — both readable without starting the DAW,
and together they record this machine's `Live 12.3.2` enumerating our bundle out of
`C:\Program Files\Common Files\VST3`, at version 1.1.1, and keeping one device row for its class ID. The log
also names the roots a scan actually reads, which is how "`{app}\VST3` is a folder no host scans
automatically" stopped being an assumption on this machine. `scripts/host_scan_check.ps1` reads both files and
prints what each one proves. So *placed* and *found* are witnessed; the last link still needs a person at a
running host: **no instance has been loaded on a track**, which means no editor window has ever opened on a
desktop, no clip has been emitted through a real transport, and nobody has heard what it does to a song.

- It has a browser panel over the app's own index — filter box, one list, the three
  exported controls (Follow Host Tempo, Transpose, Loop), and a status strip that says
  which file is playing, which file the project asked for, and how long the clip is.
  **Nothing in the plug-in reads the index until you press Connect.** Building or
  resizing the window opens no file — measured by `plugin/tests/VaultEditorTest.cpp`,
  which lists the index folder on both sides of those clicks — and the panel keeps no
  connection between clicks: every query opens its own read-only connection and closes
  it before returning, which is why a host-driven state restore cannot leave a stale
  handle behind and the browser still answers after one.
- A query that fails does **not** undo the Connect. The strip keeps naming the index
  and where it came from, and adds that this read did not come off; the rows go,
  because showing yesterday's list over an index this build just refused is worse than
  an empty list. **Rescan** is the retry and **Disconnect** is the only click that
  forgets the path. "Not connected" and "could not read it this time" are therefore two
  different sentences on screen, and `vault-editor-test` asserts both — plus that a
  Rescan after a failure comes back to the same index without pressing Connect again.
- The filter query runs on **every keystroke**: each one opens a connection and issues
  two statements, a `count(*)` over the usable rows and the `SELECT` whose text filter
  is a leading-wildcard `LIKE` over both `filename` and `path`
  (`plugin/Source/VaultIndexReader.cpp:246`) — a pattern SQLite cannot satisfy from an
  index. The row set is capped at 200 and the strip says when the cap bites. What the
  pair costs against the real index on this machine, while a DAW holds the audio
  device, has not been measured; the debounce that would soften it also changes how
  typing feels, and that is the owner's call — so the behaviour stands and is stated
  here rather than changed quietly.
- The note the save buttons leave on the strip ("Saved …" / "Not saved …") is cleared
  by the next action that means something else — a row click, a query, a Disconnect.
  It is a note about the last clip and the last target, not a permanent banner.
- The panel **takes keyboard focus** while it is open: `EDITOR_WANTS_KEYBOARD_FOCUS` is TRUE in
  `plugin/CMakeLists.txt`, so during the moment the filter box has focus the host's own shortcuts do
  not fire. That is what every plug-in with a search field does, and the host gets its keys back as
  soon as focus leaves — but the value used to be FALSE, it changes how a session feels, and putting
  it back is one line at the price of a search box that only sometimes receives typing. The suite
  cannot see this at all: no window is created, so nobody steals or keeps a focus nobody gave.
- Nothing about the panel's **layout** was agreed before it was drawn. One column, filter box on
  top, the library list, the three exported controls always visible, a status strip under them: that
  is a proposal written in C++ (`plugin/Source/VaultEditor.cpp`), not an approved design. What the
  strip says, how tall a row is, and whether those three controls belong on the panel when a host
  already draws its own parameter row for them are all still open. Re-laying the panel out would not
  move a rule: the refusals, the connect-on-click-only rule and the byte-verbatim copy are gated in
  `VaultClipExport` and the processor, not in the geometry — but several checks read the strip's
  exact sentences, so a re-layout has to bring those strings with it deliberately.
- Reading a WAL-mode index over a read-only connection leaves two files beside it:
  `midivault.sqlite3-shm` (32 KiB) and a 0-byte `midivault.sqlite3-wal`. Measured on both
  JUCE trees after a full editor session. The reader **cannot remove them** — cleaning
  up a `-wal` is a write, and this connection is not allowed to write, which is the
  price of a plug-in that provably cannot damage the library. They are inert: SQLite
  reuses or replaces both on the next open, and the index file itself is byte-identical
  after the whole session (asserted by `vault-index-test` and `vault-editor-test`). The
  app's own connection is write-capable, so its next commit-and-close clears them: with
  the pair left standing beside a fixture index, one ordinary write transaction ending
  cleanly left neither file in the folder.
- Connect reads four locations in a fixed priority order (the `SKEER_MIDIVAULT_DATA`
  override, the per-user installed data folder, the machine-wide one, then beside the
  plug-in bundle) and takes **the first index it finds** rather than merging libraries.
  When more than one exists the strip says so — "first of 2 indexes found" — so a second
  library is visible instead of silently ignored.
- "Save clip as..." writes only to a path you chose, as a byte-for-byte copy of the
  source, verified by re-hashing what landed. It refuses three things: the file the
  clip is playing from; a target that already exists when the caller did not say it
  may be replaced; and a source that is **0 bytes**. The empty-source refusal writes
  nothing and leaves the target alone, because JUCE's `File::replaceWithData` turns a
  zero-length write into `deleteFile()` — that is line 781 of `juce_core/files/juce_File.cpp` in
  the 8.0.8 tree, the checkout `plugin/build.ps1:24` passes as `-Juce`, re-read 2026-11-18 — so
  without the refusal, "Save clip as..." aimed at a 0-byte clip is a delete wearing a save's
  clothes.
- The replace question is asked by the **operating system's save dialog**, not by a box
  this plug-in draws: the chooser is launched with `warnAboutOverwriting`, which
  becomes `FOS_OVERWRITEPROMPT` / `OFN_OVERWRITEPROMPT` on Windows. This used to be an
  in-house `AlertWindow` whose button result was compared the wrong way round — JUCE's
  non-native alert numbers the first button 1 and the second 0, so Cancel replaced the
  file and Replace did nothing. Flipping the compare was not the fix: a dialog this
  repo cannot drive headless, stacked on the OS prompt that is already there, is the
  weaker of the two gates. What the suite proves is the half *after* the answer —
  `handleChosenTarget()` is the dialog-free seam a confirmed replace lands on — and the
  prompt itself is still reachable only by hand, which is step 8.
- The copy is a new file: the index does not know about it until a scan sees it.
- **"Copy path" believes the clipboard, not the call.** `SystemClipboard::copyTextToClipboard`
  returns `void` and skips the whole write when `OpenClipboard` is refused, and
  `getTextFromClipboard` answers the same refusal with an empty `String` — the two are
  `juce_gui_basics/native/juce_Windowing_windows.cpp:5694` and `:5723`, re-read 2026-11-21. The
  clipboard is one desktop-wide resource with a queue of viewers on it, so a refusal is ordinary
  traffic on a producer's machine rather than a fault this panel caused. Measured here before the
  fix: **13 of 60** single-shot write→read round trips lost the write — 10 read back empty and 3
  still held the previous write — while a write verified by readback and retried lost **0 of 30**.
  So the button writes, reads back, and retries up to four times (45 ms of sleeps), and the strip
  says either "The clip's path is on the clipboard" or "Not copied: the clipboard is busy, click
  Copy path again". The sentence that used to print unconditionally is the defect: it named a
  clipboard it had not written. The rate is not a constant — 13 of 60 isolated probes, but 12 of 20
  gate runs and 6 of 10 runs of the reverted product while a build was running alongside, so treat
  the quiet-machine number as the floor and the busy one as what a developer actually hits.
- **What a refusal is not.** An ownerless `OpenClipboard (nullptr)` — the call JUCE itself makes —
  locks nobody out: re-opening on the same thread, from a second thread of the same process, and
  from a second process while a holder had it open all went straight through (each probed
  2026-11-21). Only a hold taken *with a window* refused the next opener, with `ERROR_ACCESS_DENIED`.
  `vault-editor-test` arranges that shape by re-running itself with `--hold-clipboard`, so the
  "Not copied" branch is proven on demand instead of waited for.
- **Not yet accepted in a real host.** The suites load the bundle through JUCE's own VST3
  wrapper, hand it a saved project state naming a clip, drive a synthetic transport and
  assert MIDI comes out — that is measured, and it is not the same thing as a producer
  session in a DAW. Dragging a row onto another application, and auditioning the plug-in
  through a host's own instrument, have not been run; see
  `docs/next-steps-2026-11.md`, row 18, step 8.

## Test scope not covered

The test report distinguishes executed coverage from untested paths. Not covered:
physical Web MIDI devices, actual DAW drag targets, real network shares, cloud-only
files from a live provider, inaccessible permissions owned by another account,
100k+ file libraries, macOS/Linux, screen readers, arbitrary commercial MIDI files,
and an interactive installer/uninstaller run on a normal desktop (blocked by the
sandboxed build session).
