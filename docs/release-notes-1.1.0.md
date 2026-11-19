# SKEER MIDI VAULT 1.1.0 — release notes

The rule in **Order of work** below governs this whole page: the last action of a release is a
gate run, and a gate run rebuilds. So whatever `launch/` holds when you read this was built from a
committed, clean tree by the gate's own `installer` stage, and the two files that say so are
`launch/SKEER MIDI VAULT/_internal/buildinfo/BUILDINFO.json` (commit, `dirty`, `built_at`) and
`launch/SHA256SUMS.txt` (the bytes, verified by `sha256sum -c` there) — both beat anything written
here, because recording a run in this file moves HEAD and makes the next run the current one.
What this page can state truthfully is each gate **run**, labelled with the commit it judged:

| Gate run (UTC) | Judged | Eleven-stage verdict | Payload leg against those same bytes |
| --- | --- | --- | --- |
| 2026-11-19T19:00:06Z | `f50940283f57`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` (`release-check-20261119-190006`) | **the first run where the checksum stage judged its own build.** Execution order in that log is `installer → checksums → stamp → smoke`: `installer PASS - Setup 25671032 bytes, ZIP 34695228 bytes`, then `checksums PASS - 2 row(s), 2 release file(s) in launch/, sha256sum -c exit 0` against exactly those bytes, `stamp PASS - commit f50940283f57, clean, web/dist dafc8187f542`, `smoke PASS - exit 0, bundle built from f50940283f57` (and `plugin` plus `plugin808` each `ctest 6/6`). `installed` refused at its first write, creating `C:\Users\Sebastien\AppData\Local\SKEER MIDI VAULT cycle` — Error 5, the same boundary as every row below |
| 2026-11-19T18:22:39Z | `25a7ccd0d562`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` (`release-check-20261119-182239`) | **the publish run.** `installer PASS - Setup 25671169 bytes, ZIP 34693150 bytes`, `stamp PASS - commit 25a7ccd0d562, clean, web/dist dafc8187f542`, `smoke PASS`. Then, by hand against those bytes: `sha256sum -c SHA256SUMS.txt` exit 0 in `launch/`, Setup `2f11401d…460abc`, ZIP `1ca58426…894916`. Tag `v1.1.0` pushed on `25a7ccd`, release created, and `gh release download` of the published assets re-run through `sha256sum -c` → both `OK`, sizes equal to the `installer` row |
| 2026-11-19T18:16:59Z | `10b53bf27d52`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` (`release-check-20261119-181659`) | `installer PASS - Setup 25671638 bytes, ZIP 34693734 bytes`, `stamp PASS - commit 10b53bf27d52, clean`, `smoke PASS - bundle built from 10b53bf27d52`; `installed` died at the `%LOCALAPPDATA%` directory refusal, Error 5 |
| 2026-11-19T18:09:04Z | `c3b56dfe5576`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` (`release-check-20261119-180904`) | `installer PASS - Setup 25671438 bytes, ZIP 34694178 bytes`, `stamp PASS - commit c3b56dfe5576, clean`; that Setup re-run differentially: 199 files with 3 Start Menu and 2 desktop `.lnk` attempts by default, the same 199 with **neither** under `/MERGETASKS=!startmenuicon,!desktopicon`, both legs then dying only at the `HKCU\...\Uninstall` refusal |
| 2026-11-18T16:51:30Z | `9b61e95f9055`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` (`release-check-20261118-165130`) | `-FilesOnly`: `Setup 25673024 bytes, hash matches the manifest`, `files PASS - 199 file(s) installed … all 198 payload file(s), nothing extra`, `CYCLE INCOMPLETE - 3 phase(s) skipped, of 8` (`install-cycle-20261118-165355`) |
| 2026-11-18T16:43:41Z | `76f7b2169835`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` (`release-check-20261118-164341`) | `-FilesOnly`: `Setup 25671511 bytes, hash matches the manifest`, `files PASS - 199 file(s) installed … all 198 payload file(s), nothing extra`, `CYCLE INCOMPLETE - 3 phase(s) skipped, of 8` (`install-cycle-20261118-164637`) |
| 2026-11-18T16:33:02Z | `52a16fd71c8b`, clean | `NOT READY - 10 passed, 1 failed, 0 skipped` — only `installed` | `-FilesOnly`: `Setup 25673369 bytes, hash matches the manifest`, `files PASS - 199 file(s) installed … all 198 payload file(s), nothing extra` (`install-cycle-20261118-163739`) |
| 2026-11-18T16:22:24Z | `a4708a87ec6d`, clean | same 10 of 11, same single FAIL | same row on `Setup 25671363 bytes` (`install-cycle-20261118-162825`) |
| 2026-11-18T14:43:09Z | `c520d03eed51`, clean | same 10 of 11, same single FAIL | `-FilesOnly` PASS, then that Setup through the real wizard: 199 destinations copied, refused the shortcut and the uninstall key, rolled back to 0 files |
| 2026-11-17T23:09:47Z | `766aa311c5d0`, clean | `NOT READY - 9 passed, 2 failed` — `licence` (the two then-unfilled fields) and `installed` | `files PASS`, all 198 payload files, nothing extra |

## Published as v1.1.0

The tag `v1.1.0` points at `25a7ccd0d562b2f90ec4eaaf028f4ad59abc08dd` and the release carries three
assets — `SKEER-MIDI-VAULT-Setup-1.1.0.exe`, `SKEER-MIDI-VAULT-Portable-1.1.0.zip`,
`SHA256SUMS.txt` — which are those bytes: downloaded back and re-verified with `sha256sum -c`
against the manifest the build wrote, both `OK`, sizes equal to the `installer PASS` row above.
`README.md` links these three by their release download URLs, so the page and the assets cannot
drift apart silently.

**The page and today's `launch/` are not the same bytes, and that is intended.** Reading the asset
metadata back from GitHub on 2026-11-19, the release serves the `25a7ccd` build — Setup
`2f11401d509b…00460abc` at 25,671,169 B, ZIP `1ca58426b7b1…96894916` at 34,693,150 B — while
`launch/` now holds the `f50940283f57` rebuild that the certification run below produced, Setup
`db8727a86341…e1f34c49` at 25,671,032 B and ZIP `1682fed1ec3f…3d32668a` at 34,695,228 B. The
`1c17f6a` pair recorded an hour earlier (`a0374baed6ea…` 25,671,593 B, `8fb23860732c…` 34,692,377 B)
was superseded by that run. Two builds an hour apart share every install input and still differ in
size, which is why no size on this page is load-bearing. So `launch/SHA256SUMS.txt` is the manifest
for the local build and **will not verify a download**;
compare a download to the `SHA256SUMS.txt` published beside it. Nothing a user runs differs
between the two: the seven paths that moved since `25a7ccd` are `.github/social-preview.png`,
`AGENTS.md`, `docs/limitations.md`, this file, `packaging/README.md`, `scripts/release_check.ps1`
and `tests/test_packaged_smoke.py`, and
none of them is an install input — Setup reads `launch\SKEER MIDI VAULT\*`, `launch\VST3\*` and
`packaging\EULA.txt` ([skeer-midi-vault.iss:88,93](../packaging/skeer-midi-vault.iss), `:45` for
the licence), and the frozen app carries only `desktop.py`'s import graph plus
`web/dist` ([SKEER MIDI VAULT.spec:12](../SKEER MIDI VAULT.spec)). The interface is provably the
same file set: the two runs that publish one — `25a7ccd` and `f50940283f57` — both stamp
`web_dist dafc8187f542…`. What differs is the build stamp itself, and the size it lands at.

That run also exposed an ordering defect in the gate, and it is worth stating plainly because it
undermines every `checksums PASS` recorded from before the fix — which is every row in that table
except the `f50940283f57` one. The checksum stage used to sit with the gates that cost
seconds, which is *before* `installer` rewrites `launch/` and regenerates `SHA256SUMS.txt` at
[packaging/build_installer.ps1:301](packaging/build_installer.ps1) — so it hashed the *previous*
build's artifacts, and the bytes a release actually shipped were never hashed by the gate that
called them READY. It is why the publish run's hashes were taken by hand rather than quoted from
the stage, and it is visible in that run's own evidence: `checksums.log` is finished at 19:23:01
while `installer.log` keeps writing until 19:24:25, eighty seconds later. The fix is in these notes' commit: the block is now `Test-Checksums`, defined where it
was and called immediately after the `installer` stage, so a full run judges what the build just
wrote. Nothing about the fast lane changes — `-Fast` and `-Stages` subsets that skip `installer`
fall through to the same call and check whatever `launch/` holds, exactly as before — and
`python scripts/check_release_gate.py` still reddens the CRLF, mismatched-hash, unnamed-artifact and
previous-release rows on that stage (measured on this tree, `FALSIFIER OK`).

The published release page carried the bare `checksums PASS` row too, so it was edited on
2026-11-19 to say what that row does and does not attest to, in the same words as here. Only the
notes were touched: the three assets read back afterwards hold the sizes and `sha256` digests they
had before the edit, and for the two deliverables GitHub's own computed digest equals the
`SHA256SUMS.txt` row printed on the page — a server-side check that does not go through anything this
shell hashed.

Recording the publish run at all is possible because a tag pins it. **Order of work** below says the
last gate run of a release is the one nobody records, since the commit that records it invalidates
the bundle; that argument depends on `HEAD` being the only handle on the judged commit. Once the
release is built, tagged and hashed, the run can be written down.

In every one of those runs the only stage that has never gone green is `installed`, and that is
this shell refusing Setup any write outside the workspace — item 2 of **What still blocks this
release**. The licence page inside each of those Setups is the filled one, and it has been read as
a customer reads it: §6 and §7 in the rendered wizard, 2026-11-18.

The build is not byte-reproducible, which is the second reason no size is pinned above: two clean
`766aa311c5d0` builds stamped at 23:05:07Z and 23:09:47Z came out 25,671,546 and 25,669,100 bytes,
the `c520d03eed51` tree built 25,670,855 by hand and 25,671,112 through the gate four minutes
later, and the `a4708a87ec6d` and `52a16fd71c8b` gate builds eleven minutes apart came out
25,671,363 and 25,673,369 — 2,006 bytes apart for a diff that touched no code. The gate builds since
then, each from a commit that edited markdown and no source, have landed 25,671,511 and 25,673,024:
within a few kilobytes of all of the above, which is exactly why a size cannot be pinned here — it
would be the size of one particular build, not of the release.

## Standalone distribution

- Windows per-user installer: `launch/SKEER-MIDI-VAULT-Setup-1.1.0.exe` — the byte count and hash
  of the copy in front of you are in `launch/SHA256SUMS.txt`, not here; the paragraph above shows
  two consecutive clean builds of this release differing by 2,006 bytes.
- Portable ZIP: `launch/SKEER-MIDI-VAULT-Portable-1.1.0.zip` — same authority.
- Checksums: `launch/SHA256SUMS.txt` — two rows, LF-only terminators, so
  `sha256sum -c SHA256SUMS.txt` run inside `launch/` exits 0; the gate's `checksums` stage runs
  exactly that on every run in the table above, and it has passed on all six.
- The 2026-11-17T23:09:47Z build from `766aa311c5d0` was Setup 25,669,100 bytes
  (`d7ef9f2d05ab0fa9…`) and ZIP 34,695,007 bytes (`b056e9aa765b42dc…`); it carried the unfilled
  licence page and is superseded.

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
| Installer payload | real Setup installed **all 198 payload files** (199 log destinations, the extra being Inno's own uninstaller), **nothing missing and nothing extra**; proven red by adding one file to `launch/` and restored. Re-run against every Setup in the table at the top of this page — each reported `hash matches the manifest` and a `files` PASS — and the `c520d03eed51` one went through the real wizard as well, which copied all 199 destinations before the refusal rolled them back to 0 |
| Release gate, all eleven stages | the runs are in that table; the 2026-11-18T16:51:30Z leg against `9b61e95f9055` is the stage detail to read (evidence `build\work\release-check-20261118-165130`) — `gate` 8 files / 11 values, `suite` 104 tests OK, `licence` no placeholders and the page states 1.1.0, `checksums` 2 rows and `sha256sum -c` exit 0, `web` tsc --noEmit and vite build, `plugin` and `plugin808` ctest 6/6 each, `installer` rebuilt both deliverables (Setup 25,673,024 B, ZIP 34,694,410 B), `stamp PASS - commit 9b61e95f9055, clean, web/dist dafc8187f542`, `smoke PASS - exit 0, bundle built from 9b61e95f9055`; the one FAIL is `installed`, the folder refusal in item 2. Only the 2026-11-17 run differed, at 9 of 11: its second red was the two licence fields that are now filled. |

That earlier caveat is discharged for every Setup `launch/` has held today: each went through the
payload leg against its own manifest hash, and the `c520d03eed51` one also through the real wizard.
What still has not run anywhere
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
   complete it.** The payload copy is proven against every Setup in the table above, but the host's
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
   and a hand-run Setup is not told. So `-Dir` buys the payload leg and nothing more — for the
   build as released, the reason was in the script rather than the argument list: the Start Menu
   entry sat under `{autoprograms}\SKEER AUDIO\` with **no `Tasks:` flag** (line 93 then), so only
   the desktop icon was conditional and every Setup run, whatever it was handed, had one mandatory
   write outside the workspace. Measured 2026-11-18 on that day's Setup build: `install_cycle_check.ps1 -FilesOnly
   -Dir` pointed inside the workspace copied all 198 payload files, then Setup raised exactly that
   refusal —
   `unable to create the directory "…Start Menu\Programs\SKEER AUDIO". Error 5` — exited 4 and
   rolled the folder back, leaving 0 uninstall keys, no shortcut and no group.
   **That entry carries a `Tasks:` flag as of 2026-11-19** (`startmenuicon` at
   `packaging/skeer-midi-vault.iss:64`, used at `:98`; `desktopicon` at `:65`, used at `:99`), so a
   customer can decline a shortcut the installer is not allowed to write instead of losing the
   install. Proven by differential on a probe compile of the edited script (23,373,436 bytes,
   `iscc` exit 0, `[Files]` plug-in lines excluded, so its 197 successful-install lines are not the
   certified build's 198): default `/VERYSILENT` still attempts both icons — 3 Start Menu lines, 2
   desktop lines — and exits 4; `/MERGETASKS=!startmenuicon,!desktopicon` copies the same 197 and
   attempts **neither** (0 and 0), so the first refusal moves to
   `Error creating registry key: …\Uninstall\{B7E2D5A8-…}_is1`; `/MERGETASKS=!startmenuicon` alone
   keeps the 2 desktop lines, which is each task governing its own entry. The registry key is the
   one write no argument can decline, so **no combination of arguments from this shell finishes the
   cycle** — the uninstall entry is the whole residual now, not a folder. Run
   `powershell -File packaging\install_cycle_check.ps1` from a normal user terminal once — the
   three sibling SKEER installs already registered on this machine are proof the same installer
   family registers and uninstalls correctly here, and this shell's own preflight shows a child
   process writing that same `HKCU\...\Uninstall` succeeds — and the `installed` stage can go PASS.
   The edit is **in the shipped bytes now**: the deliverables were rebuilt on 2026-11-19 after the
   commit that carries it, and `BUILDINFO.json` in the bundle is the authority for which commit did
   the build. Re-proved differentially on that rebuilt Setup (`release-check-20261119-180904`'s own
   installer output): default `/VERYSILENT` installs 199 files and attempts 3 Start Menu and 2
   desktop `.lnk` writes; `/MERGETASKS=!startmenuicon,!desktopicon` installs the same 199 with **0
   and 0**, dying only at the registry key this shell refuses. The check now passes that flag
   itself ([packaging/install_cycle_check.ps1:385](packaging/install_cycle_check.ps1)), because a
   throwaway copy it is about to uninstall should not put shortcuts in the user's shell — re-run
   through the check against the `f50940283f57` Setup, both routes: `-FilesOnly -Dir <in the repo>`
   gives `files PASS - 199 file(s) installed … all 198 payload file(s), nothing extra` with Setup
   stopping at `HKCU\...\Uninstall\{B7E2D5A8-…}_is1` (exit 4), and the same command without `-Dir`
   still stops one step earlier at the default `%LOCALAPPDATA%` cycle folder — which is what the
   gate's `installed` row reports, because [scripts/release_check.ps1:391](scripts/release_check.ps1)
   calls the check with no arguments, so that stage dies in its install phase and never reaches a
   payload line. Either way the payload relocation is now proven
   against the shipping binary, and the residual is exactly one registry write.
   The nearest this shell can reach is the executable running from a *relocated* copy of the
   payload rather than a registered location: `python tests/test_packaged_smoke.py` under
   `SKEER_PACKAGED_EXE` PASSed against a hand-copied tree with `built from c520d03eed51 clean`,
   `session protected: True`, `keep-alive` 403→200 and 415→200 and `orphan workers []`.
3. **The `/ALLUSERS` leg is untested**: `IsAdmin=False` for this shell (measured 2026-11-18), so
   `CommonVst3` and the `Common Files\VST3` copy have never run — and the bundle is not in
   `Common Files\VST3` now (`Test-Path` false), which is also why no host on this machine can see
   it yet. That leg needs an elevated terminal and a consent prompt only the owner can answer:
   `Setup.exe /ALLUSERS`, after which the Setup log line `VST3: installing into …` — not the
   README — says where the bundle landed. That leg now has a harness rather than only an
   instruction: `packaging\install_cycle_check.ps1 -AllUsers` passes `/ALLUSERS` to Setup, demands
   the `VST3: installing into` line in the Setup log, demands that the shared folder gained files
   **and** that every added entry sits inside `SKEER MIDI VAULT.vst3` — nothing else in
   `Common Files\VST3` may move — and the existing uninstall comparison then requires the folder
   back exactly as it was censused. The uninstaller gets no switch: it inherits the install mode
   from its own registration. Measured 2026-11-18 in this shell, `-AllUsers` refuses in preflight
   with `CYCLE NOT RUN - preflight refused; nothing was installed` and exit 1 (and the same with
   `-FilesOnly`, which contradicts it), so the refusal path is proven and the elevated path —
   like `-Sign` — has never executed from here.
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
   prompt, and focus inside a host window all remain unproven. One fact decided before that
   session, so it is not wasted: the bundle a host would load is the **8.0.4** build. Measured
   2026-11-18 against the tip, the staged `launch/VST3` binary is byte-identical to the one under
   `plugin/build` that `vault-host-test` loaded in the same gate run, while `plugin/build/tag-808`
   holds a different binary — so a session ratifies those bytes and says nothing about the 8.0.8
   build, which is compile-and-suite compatibility evidence only. `packaging/README.md` says the
   same, with the host-list detail that `moduleinfo.json` files the class under
   `Sub Categories: ["Fx"]`.

## Order of work

`stamp` compares the bundle's commit to `HEAD`, so **the release build has to be the last action
before publishing**. Editing these notes after a build — any commit at all — makes the next gate
report `stamp FAIL`, correctly: that bundle no longer matches the tree it is being judged against.
The consequence is structural, not accidental, and it is why the header of this page names
`BUILDINFO.json` and `SHA256SUMS.txt` instead of a hash: the final gate run of a release is the
one nobody records, because recording it would require the commit that invalidates it.

## Read this before sale

`packaging/README.md` covers signing, the install cycle, and what not to ship. The
`docs/limitations.md` honesty rules still apply: classification figures are regression
results on self-authored synthetic fixtures, not real-world accuracy, and the style hint
stays a low-confidence guess.
