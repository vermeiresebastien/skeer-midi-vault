# SKEER MIDI VAULT 1.1.0 — release notes

Built 2026-11-17T23:09:47Z from commit `766aa311c5d0`, and the tree was clean when it was
stamped (`dirty: false`), so the gate's `stamp` stage passes on it. The gate is still NOT READY:
see **What still blocks this release** for the two stages that say so and what they need.

`launch/` is gitignored, so `launch/SHA256SUMS.txt` is the authority for whatever is in that
folder right now. Every byte count and digest below belongs to the build named above. They are a
record, not a checksum of the folder: the build is not byte-reproducible, measured on the two
clean `766aa311c5d0` builds stamped here at 23:05:07Z and 23:09:47Z, which came out 25,671,546
and 25,669,100 bytes.

## Standalone distribution

- Windows per-user installer: `launch/SKEER-MIDI-VAULT-Setup-1.1.0.exe` — 25,669,100 bytes,
  `d7ef9f2d05ab0fa9b5a570bca2d7fb362a24156c6abeccaeb609c047fcfb6f7e`
- Portable ZIP: `launch/SKEER-MIDI-VAULT-Portable-1.1.0.zip` — 34,695,007 bytes,
  `b056e9aa765b42dcd72def7e1d3c23584ed10b895b18b020d382a2e65a1392ec`
- Checksums: `launch/SHA256SUMS.txt` — 201 bytes, two rows, LF-only terminators, so
  `sha256sum -c SHA256SUMS.txt` run inside `launch/` exits 0.

Both deliverables carry the **same 198 files**: the app tree (196) and the VST3 bundle
(2). The ZIP lists 213 entries because it also records the 15 directories.

The application is still onedir, not onefile, and still needs no Python, Node.js,
terminal or admin rights. It opens the library in the default browser and runs a tray
service; **Settings → Data & privacy → Quit SKEER MIDI VAULT** stops it. What 1.0.0
said about the white-screen fix and the audio-graph changes stands — see
[`release-notes-1.0.0.md`](release-notes-1.0.0.md); those are not repeated here.

## New: the VST3 plug-in ships

`SKEER MIDI VAULT.vst3` is now part of both deliverables. It is a MIDI effect: it reads
the same index the app builds, it does not generate audio, and it never opens the
library for writing.

- Three controls, always visible in the panel: **Follow Host Tempo** (Off/On, default
  On), **Transpose** (−24…+24 semitones), **Loop** (Once/Loop, default Loop).
- One column: a filter box, the library list, those three controls, and a status strip
  naming which file is playing and which one the project asked for.
- The index is touched only after an explicit **Connect** click, and every query opens
  its own read-only connection and closes it before returning. SQLite is never queried
  from `processBlock`.
- A clip leaves the plug-in three ways: drag out, **Copy path**, **Save clip as…**.

**Where it lands matters.** Setup installs at `PrivilegesRequired=lowest`, so the
default per-user install puts the bundle in `{app}\VST3` — a folder no host scans
automatically. To have Live/Reaper/FL find it without editing a search path, run
Setup elevated with `/ALLUSERS`, which also copies it to
`%ProgramFiles%\Common Files\VST3`. The Setup log records which of the two happened
(`VST3: installing into …` / `VST3: installed only in …`). Either way, nothing in the
installer adds, removes or rewrites a host's own VST3 scan path.

## New: every artifact says what it was built from

`_internal/buildinfo/BUILDINFO.json` now travels inside the bundle and is published by
`/api/health` and by `window.__SKEER_MIDIVAULT_DEBUG__`: commit, dirty flag, the digest
of `git status`, of the tracked diff, of the untracked set, and a content hash of
`web/dist`. A customer's folder can therefore be matched to a commit without asking
them for a screenshot. Provenance fields are absent-and-said rather than guessed when
the build tree is not a git checkout.

## Changed: one version number, and a gate that holds it there

1.1.0 appears as **11 values across 8 files** — `midivault/__init__.py`,
`packaging/skeer-midi-vault.iss`, `build/version_info.txt`, `desktop.py`,
`web/package.json`, `plugin/CMakeLists.txt`, `packaging/EULA.txt` and, as the absence of
a literal, `packaging/build_installer.ps1`. `python scripts/check_version_consistency.py`
reads them all and exits non-zero on any disagreement, including a version literal that
re-appears in the build script. The plug-in's CMake version is load-bearing, not a build
detail: it is what a host lists the plug-in by, and it reaches the shipped artifact —
the staged bundle's own `Contents/Resources/moduleinfo.json` reads
`"Version": "1.1.0"`. An app at 1.1.0 beside a plug-in still claiming 1.0.0 would be two
products asserting one release, which is why that literal joined the gated set.

## New: a command that owns the answer "is this releasable"

`scripts/release_check.ps1` runs eleven stages — gate, suite, web, plugin, plugin808,
installer, stamp, smoke, checksums, licence, installed — and exits 0 READY, 1 a failed
stage, 2 a stage that could not run. A skipped stage keeps its own row; it is never a
pass. `-Fast` runs the four cheap gates. Per-stage logs go to
`build/work/release-check-<utc>/`.

Its falsifier, `python scripts/check_release_gate.py`, copies the release files into
`build/work/release-gate-falsifier/`, stubs the child commands and plants one defect per
case — 33 cases defined, 31 of which ran on this machine (the two `web` branches are
mutually exclusive, and the no-second-JUCE case cannot fire where the second tree exists).
It is the only place the gate's PASS rows are ever seen, and it printed
`FALSIFIER OK: every row moved for its own reason and the exit codes are as documented`.

`packaging/install_cycle_check.ps1` is the installer's own end-to-end check: preflight →
install → registration → launch → installed smoke → uninstall → comparison, with the same
three-way exit, and `-FilesOnly` to grade just the payload copies where the shell cannot
register anything. Details and the measured result are in
[`../packaging/README.md`](../packaging/README.md).

## Changed: the licence page

The self-announcing "this is a template" note is gone, because a shipped licence should not
tell the buyer it was never reviewed. Section 6 and section 7 now carry two fill-once fields
— contact and governing law — and the licence version line (`This version is 1.1.0.`) is a
checked literal, so the gate reddens when the release moves and the agreement does not. The
"no counsel has reviewed this" warning now lives in `packaging/README.md`, where the seller
reads it, not in the customer's copy.

## Fixed since 1.0.0

- Two crash paths on hostile input: sparse clips and tracks with no name.
- Per-part voices: every part gets a voice, and an automatic choice can always be
  overridden by an explicit one.
- Two ways a manual correction failed to reach the audio.
- The loopback door is sealed against DNS rebinding (every request must name a loopback
  `Host`), the index migrates version-gated with a backup of the old index first, and
  preview loading is queued rather than restarted per click.
- The index now reports what is actually on disk, and the audition deck says what it can
  actually play.
- Plug-in: on **Save clip as…** the replace confirmation had its button answers inverted,
  so *Cancel* replaced the file and *Replace* did nothing. The in-house box is gone; the
  operating system's own chooser prompt asks, and the dialog-free seam is what the suites
  drive.
- Plug-in: saving a 0-byte source **deleted the target**, because `File::replaceWithData`
  turns a zero-length write into a delete. A 0-byte source is now refused before anything
  is read or written, with a message that says the target was left alone.
- Plug-in: a transient index read failure discarded a **Connect** the user had asked for.
  A failed query now keeps the index path and says "not read this time"; only
  **Disconnect** forgets it, and **Rescan** is the retry.
- The scan test that raced itself: the recording spy is installed before the worker starts,
  and the assertion is exact equality against the fixture rather than a floor.

## Verification, measured 2026-11-17

| Check | Result |
| --- | --- |
| Python suite (`python -m unittest discover -s tests`) | **104 tests, OK** in 19.9 s |
| Version gate | **8 files, 11 values, one version 1.1.0** |
| Release-gate falsifier | **FALSIFIER OK**, 31 of 33 cases executed |
| Plug-in, JUCE 8.0.4 tree (`plugin/build.ps1`) | exit 0, **ctest 6/6** |
| Plug-in, JUCE 8.0.8 tree (`-BuildDir build/tag-808`) | exit 0, **ctest 6/6** |
| Packaged smoke (`python tests/test_packaged_smoke.py`) | exit 0, health reports **1.1.0**, 36 files indexed / 1 failed / 0 issues, `keep-alive` 403→200 and 415→200, **no orphan `--multiprocessing-fork` workers** |
| Checksums | `sha256sum -c SHA256SUMS.txt` exit 0, 0 CR bytes in the manifest |
| Installer payload | real Setup installed **all 198 payload files** (199 log destinations, the extra being Inno's own uninstaller), **nothing missing and nothing extra**; proven red by adding one file to `launch/` and restored. Re-run against the `766aa311c5d0` Setup: `CYCLE INCOMPLETE`, `files` PASS, 3 phases skipped |
| Release gate, all eleven stages | `NOT READY - 9 passed, 2 failed, 0 skipped, of 11 stages` (exit 1): `licence` FAIL on the two unfilled fields, `installed` FAIL because this shell is refused Setup's writes. **`stamp` PASS** — `commit 766aa311c5d0, clean, web/dist dafc8187f542` |

The `WinError 10038` traceback the smoke log prints at shutdown is the known interpreter
teardown race in the HTTP thread. It is after `PASS packaged smoke test` and before exit 0;
it is documented in `AGENTS.md` and deliberately not silenced.

## What still blocks this release

1. **Two licence fields are unfilled** — `<<<FILL: contact>>>` and
   `<<<FILL: jurisdiction>>>`. Until the seller fills them, the `licence` stage is FAIL and
   the gate is NOT READY. That is deliberate: the gate reads the same placeholder markers the
   build script refuses to strip.
2. **The full install → run → uninstall cycle has not completed anywhere, and this shell cannot
   complete it.** The payload copy is proven (row above), but the host's policy refuses **Setup**
   every write outside the workspace: first at creating its target under `%LOCALAPPDATA%` and
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\SKEER AUDIO` (`Error 5: Access is denied`),
   and — with both folders pre-created by the shell so that Setup had no directory left to make —
   at `CreateFile failed; code 5`, still with 0 files copied. It follows the executable, not the
   path: the ACLs on those folders are FullControl for this user and a `powershell` child of the
   same shell writes there freely, while the identical Setup copies all 198 files into a workspace
   path. So no `-Dir`, and no pre-made folder, gets the cycle finished from here. Run
   `powershell -File packaging\install_cycle_check.ps1` from a normal user terminal once — the
   three sibling SKEER installs already registered on this machine are proof the same installer
   family registers and uninstalls correctly here — and the `installed` stage can go PASS.
3. **The `/ALLUSERS` leg is untested**: no elevation is available here, so
   `CommonVst3` and the `Common Files\VST3` copy have never run.
4. **The installer is unsigned.** `Get-AuthenticodeSignature` reports `NotSigned` for both
   `SKEER-MIDI-VAULT-Setup-1.1.0.exe` and the bundled app executable. `-Sign` exists and is
   inert by default; it has never executed, because there is no Authenticode certificate
   yet. Its preflight refuses before it destroys anything when the cert cannot be found.
   `signtool verify /pa` is wired to run immediately after each signing step, and
   `SHA256SUMS.txt` is written last so the manifest hashes the signed bytes.
5. **Plug-in keyboard focus and panel layout are not ratified.**
   `EDITOR_WANTS_KEYBOARD_FOCUS` was set TRUE so the filter box can be typed into, which
   means the host's own shortcuts do not fire while the panel has focus — one line to put
   back, at the price of a search box that sometimes ignores typing. The layout is a proposal
   in C++, not an approved design. No suite here can see either: no window is created.
6. **A real host session (step 8) has not happened**: a real OLE drag, the OS overwrite
   prompt, and focus inside a host window all remain unproven.

One more, about the order of work rather than the product: `stamp` compares the bundle's commit
to `HEAD`, so **the release build has to be the last action before publishing**. Editing these
notes after a build — any commit at all — makes the next gate report `stamp FAIL`, correctly:
that bundle no longer matches the tree it is being judged against.

## Read this before sale

`packaging/README.md` covers signing, the install cycle, and what not to ship. The
`docs/limitations.md` honesty rules still apply: classification figures are regression
results on self-authored synthetic fixtures, not real-world accuracy, and the style hint
stays a low-confidence guess.
