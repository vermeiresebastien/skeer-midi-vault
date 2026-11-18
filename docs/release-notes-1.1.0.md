# SKEER MIDI VAULT 1.1.0 — release notes

Built 2026-11-18T14:43:09Z from commit `c520d03eed51`, by the release gate's own `installer`
stage, and the tree was clean when it was stamped (`dirty: false`) — so `stamp` passes on those
bytes and the licence page inside that Setup is the filled one, which is the page a customer then
saw (§6 and §7 read in the wizard, 2026-11-18). The gate still reports NOT READY,
on one stage: see **What still blocks this release**. Numbers below that belong to the earlier
2026-11-17T23:09:47Z build from `766aa311c5d0` say so, and so does every number that belongs to
the 14:43:09Z build — `launch/` holds whatever the most recent build put there, which is what
`SHA256SUMS.txt` is for.

`launch/` is gitignored, so `launch/SHA256SUMS.txt` is the authority for whatever is in that
folder right now, and re-running `sha256sum -c` there beats anything written here. The build is
not byte-reproducible: two clean `766aa311c5d0` builds stamped at 23:05:07Z and 23:09:47Z came out
25,671,546 and 25,669,100 bytes, and on 2026-11-18 the same `c520d03eed51` tree built 25,670,855
bytes by hand and 25,671,112 through the gate four minutes later.

## Standalone distribution

- Windows per-user installer: `launch/SKEER-MIDI-VAULT-Setup-1.1.0.exe` — 25,671,112 bytes,
  `abf5c4a7b4fc02c3290a4798bb0018750268eee5dce13d9c56d0c4e172cee1a6`
- Portable ZIP: `launch/SKEER-MIDI-VAULT-Portable-1.1.0.zip` — 34,693,765 bytes,
  `b08d5bcb2c286c40187ec5536fafb8b14af19c598c51b125fc7894ed1bbb0d7c`
- Checksums: `launch/SHA256SUMS.txt` — 201 bytes, two rows, LF-only terminators, so
  `sha256sum -c SHA256SUMS.txt` run inside `launch/` exits 0; re-verified against exactly the two
  rows above on 2026-11-18.
- The 2026-11-17T23:09:47Z build from `766aa311c5d0` was Setup 25,669,100 bytes
  (`d7ef9f2d05ab0fa9…`) and ZIP 34,695,007 bytes (`b056e9aa765b42dc…`); it carried the unfilled
  licence page and is superseded by the two rows above.

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

## Verification, measured 2026-11-17 and re-run 2026-11-18

| Check | Result |
| --- | --- |
| Python suite (`python -m unittest discover -s tests`) | **104 tests, OK** in 19.9 s |
| Version gate | **8 files, 11 values, one version 1.1.0** |
| Release-gate falsifier | **FALSIFIER OK**, 31 of 33 cases executed — re-run 2026-11-18 on both states of `packaging/EULA.txt` (placeholders present, then filled), and case F still reddens `licence` either way |
| Plug-in, JUCE 8.0.4 tree (`plugin/build.ps1`) | exit 0, **ctest 6/6** |
| Plug-in, JUCE 8.0.8 tree (`-BuildDir build/tag-808`) | exit 0, **ctest 6/6** |
| Packaged smoke (`python tests/test_packaged_smoke.py`) | exit 0, health reports **1.1.0**, 36 files indexed / 1 failed / 0 issues, `keep-alive` 403→200 and 415→200, **no orphan `--multiprocessing-fork` workers** |
| Checksums | `sha256sum -c SHA256SUMS.txt` exit 0, 0 CR bytes in the manifest |
| Installer payload | real Setup installed **all 198 payload files** (199 log destinations, the extra being Inno's own uninstaller), **nothing missing and nothing extra**; proven red by adding one file to `launch/` and restored. Re-run against the `766aa311c5d0` Setup: `CYCLE INCOMPLETE`, `files` PASS, 3 phases skipped. **Re-run again on 2026-11-18 against the rebuilt `c520d03eed51` Setup** — `-FilesOnly -Dir` inside the workspace: `CYCLE INCOMPLETE - 3 phase(s) skipped, of 8`, `files PASS - 199 file(s) installed … all 198 payload file(s), nothing extra, and Setup could not finish registering`; and the same Setup driven in GUI mode copied all 199 destinations into a workspace folder before the identical refusal rolled it back to 0 files |
| Release gate, all eleven stages | **2026-11-18, against the rebuilt `c520d03eed51` deliverables: `NOT READY - 10 passed, 1 failed, 0 skipped, of 11 stages` (exit 1)** — every stage green except `installed`, which is the folder refusal in item 2. `licence PASS - no placeholders, licence page states 1.1.0`, `stamp PASS - commit c520d03eed51, clean, web/dist dafc8187f542`, `smoke PASS - exit 0, bundle built from c520d03eed51`, `installer` rebuilt Setup 25,671,112 B and ZIP 34,693,765 B, `checksums` 2 rows OK. The previous full run (2026-11-17, against the `766aa311c5d0` bytes) was `NOT READY - 9 passed, 2 failed`; its `licence` red was the two fields that are now filled. |

That earlier caveat is now discharged: the 2026-11-18 rebuild **has** been through the payload leg,
twice — once through `-FilesOnly` and once through the real wizard. What still has not run anywhere
is everything Setup must do *outside* the install folder (Start Menu, `HKCU\...\Uninstall`, the
first launch of the registered executable, the uninstall comparison), because the refusal follows
the Setup executable rather than the path, in silent and interactive mode alike.

The `WinError 10038` traceback the smoke run prints at shutdown is the known interpreter teardown
race in the HTTP thread, documented in `AGENTS.md` and deliberately not silenced. Where it sits in
a redirected log is not when it happened: in every gate log read here it is written at lines 8-14,
*above* the script's own `exit 0` and `PASS packaged smoke test` lines, because the frozen child's
stderr is unbuffered while the parent's stdout flushes at exit. What the file does carry is that
the run reports `orphan workers []`, prints PASS, and the stage exits 0.

## What still blocks this release

1. **The licence is filled, shipped and now seen — and still not reviewed by counsel.** Both
   answers are in the page — `sebastienvermeire@gmail.com` at `packaging/EULA.txt:42`, `Belgium`
   at `:45`, the address read from `git config user.email` and the country from this machine's geo
   (`HKCU\Control Panel\International\Geo` → `Name BE`). Nothing was invented, including no legal
   name, because a personal name with an accent in it could not be verified from here. The gate's
   `licence` stage exits 0 on it, and the Setup in `launch/` was compiled after the fill — ISCC
   logged `Reading file (LicenseFile)` in the run that produced these bytes — so a `<<<FILL:`
   token cannot reach a buyer from this build. On 2026-11-18 that page was also **read as a
   customer reads it**: the wizard opened on *License Agreement*, §6 rendered
   `Licence and support enquiries: sebastienvermeire@gmail.com` and §7
   `This agreement is governed by the law of Belgium, and any dispute arising out of it is subject
   to the exclusive jurisdiction of the courts of that place`, wrapping intact and no token
   anywhere; the radio defaults to *I do not accept the agreement*, which keeps **Next** disabled,
   and the run was ended with Cancel — `0` files installed, no registry entry, no shortcut. What
   the `licence` stage still does not prove, and what remains open, is that the drafting has
   **not been reviewed by counsel**. The question a personal seller should settle before the first
   sale — whether selling software for money makes you a *trader*, with the 14-day withdrawal
   right and refund path that follow, neither of which this EULA mentions — is written out in
   `packaging/README.md`.
2. **The full install → run → uninstall cycle has not completed anywhere, and this shell cannot
   complete it.** The payload copy is proven on these exact bytes (row above), but the host's
   policy refuses **Setup**
   every write outside the workspace: first at creating its target under `%LOCALAPPDATA%` and
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\SKEER AUDIO` (`Error 5: Access is denied`),
   and — with both folders pre-created by the shell so that Setup had no directory left to make —
   at `CreateFile failed; code 5`, still with 0 files copied. It follows the executable, not the
   path: the ACLs on those folders are FullControl for this user and a `powershell` child of the
   same shell writes there freely, while the identical Setup copies all 198 files into a workspace
   path. Measured again 2026-11-18 in **interactive** mode, where the wizard copied all 199
   destinations into a workspace folder first and then raised those refusals as its own
   message boxes — and they are not new: the silent 2026-11-17 run in
   `build\work\install-cycle-20261117-231426` carries both, from the same Setup, after it had
   copied the payload. `IPersistFile::Save failed; code 0x80070005` is for
   `C:\Users\Sebastien\Desktop\SKEER MIDI VAULT.lnk`, the Start Menu refusal being the separate
   `unable to create the directory "…Start Menu\Programs\SKEER AUDIO". Error 5` line, and
   `Error creating registry key: HKEY_CURRENT_USER\...\Uninstall\{B7E2D5A8-…}_is1 / RegCreateKeyEx
   failed; code 5` for the uninstall entry — before `Rolling back changes` emptied the folder
   again. It could not even extract first: Setup is refused its `is-XXXX.tmp` under `%TEMP%`
   unless the child's `TMP`/`TEMP` are redirected into the workspace, which the check already does
   and a hand-run Setup is not told. So no `-Dir`, and no
   pre-made folder, gets the cycle finished from here. Run
   `powershell -File packaging\install_cycle_check.ps1` from a normal user terminal once — the
   three sibling SKEER installs already registered on this machine are proof the same installer
   family registers and uninstalls correctly here — and the `installed` stage can go PASS.
   The nearest this shell can reach is the executable running from a *relocated* copy of the
   payload rather than a registered location: `python tests/test_packaged_smoke.py` under
   `SKEER_PACKAGED_EXE` PASSed against a hand-copied tree with `built from c520d03eed51 clean`,
   `session protected: True`, `keep-alive` 403→200 and 415→200 and `orphan workers []`.
3. **The `/ALLUSERS` leg is untested**: `IsAdmin=False` for this shell (measured 2026-11-18), so
   `CommonVst3` and the `Common Files\VST3` copy have never run — and the bundle is not in
   `Common Files\VST3` now (`Test-Path` false), which is also why no host on this machine can see
   it yet. That leg needs an elevated terminal and a consent prompt only the owner can answer:
   `Setup.exe /ALLUSERS`, after which the Setup log line `VST3: installing into …` — not the
   README — says where the bundle landed.
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
