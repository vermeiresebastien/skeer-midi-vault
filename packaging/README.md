# Packaging and distribution

The installed application is self-contained. End users do **not** need Python,
Node.js, a terminal, or this repository. The build includes the Python runtime,
the service, the compiled interface and all visual assets.

## Outputs

Built into `launch/`, the one folder everything ships from. `<version>` below is
`__version__` in `midivault/__init__.py`, the only release number the build script reads:

- `SKEER MIDI VAULT/` — the standalone app bundle (`SKEER MIDI VAULT.exe` plus its required
  `_internal/` folder, which also holds `_internal\buildinfo\BUILDINFO.json`, the provenance
  stamp, and `_internal\web\dist`, the interface)
- `SKEER-MIDI-VAULT-Setup-<version>.exe` — Windows installer (the file to send customers)
- `SKEER-MIDI-VAULT-Portable-<version>.zip` — extract-and-run portable build: app bundle and
  the staged `VST3/` folder
- `VST3\SKEER MIDI VAULT.vst3` — staged from the plug-in build, only when one exists and its
  `moduleinfo.json` states the same version as the release
- `SHA256SUMS.txt` — checksums for the two release files, LF line endings so
  `sha256sum -c SHA256SUMS.txt` works unchanged on any platform

The build does not leave an old release beside a new one: it deletes superseded
`Setup`/`Portable` files once every input they depend on exists, then requires exactly two
release files for `<version>` when it writes the manifest.

The installed app:

- installs under `{autopf}\SKEER MIDI VAULT`, which is
  `%LOCALAPPDATA%\Programs\SKEER MIDI VAULT` for the default per-user install and
  `Program Files\SKEER MIDI VAULT` when Setup is run with `/ALLUSERS`
- installs the VST3 bundle into `{app}\VST3` always, and additionally into
  `Program Files\Common Files\VST3` — the folder hosts scan by default — in an all-users
  install. A per-user install never writes to a shared folder, and the Setup log records which
  of the two happened, so a producer who cannot see the plug-in has an explanation to read.
  Nothing in the installer edits a host's plug-in scan paths.
- optionally creates Start Menu and Desktop shortcuts (each is a checkbox; `/MERGETASKS=!startmenuicon,!desktopicon` declines both on the command line)
- starts a loopback-only service, opens the interface in the user's browser and
  runs a tray icon
- stores the library at `%LOCALAPPDATA%\Skeer\MIDI Vault` (never removed by the
  uninstaller)
- supports **Settings → Data & privacy → Quit SKEER MIDI VAULT**
- requires Microsoft Edge or Google Chrome (present on standard Windows 10/11)

## Rebuild

Build tools (only on the build machine):

```powershell
python -m pip install -r packaging\requirements-build.txt
npm --prefix web ci
```

Inno Setup 6 is required for the installer and is **not** downloaded by anything here:
install it from <https://jrsoftware.org/isinfo.php> or set `INNO_SETUP_ISCC` to the full path of
`ISCC.exe`. `build_installer.ps1` looks for it in `$INNO_SETUP_ISCC`, the usual install folders,
`build\tools\` and the uninstall registry, and fails its preflight naming whatever is missing
*before* it kills a running instance, deletes an old deliverable or starts a compile.

```powershell
.\packaging\build_installer.ps1                  # interface, app, plug-in staging, installer, ZIP, checksums
.\packaging\build_installer.ps1 -SkipWebBuild    # reuse web/dist as it is
.\packaging\build_installer.ps1 -SkipAppBuild    # recompile the installer only
.\packaging\build_installer.ps1 -SkipPlugin      # deliverable with no VST3 in it
.\packaging\build_installer.ps1 -Sign            # Authenticode; see "Code signing" below
```

The plug-in is a deliverable, so it is checked on the way in rather than trusted:
`plugin\build.ps1` must have produced a bundle whose `moduleinfo.json` version equals
`<version>`, over a binary that is not zero bytes. A 1.1.0 app beside a plug-in still claiming
1.0.0 is two products claiming one release, and the plug-in list in a DAW is where the
contradiction would show.

The Inno script can also be compiled directly:

```powershell
iscc packaging\skeer-midi-vault.iss                  # installer with no plug-in in it
iscc /DPluginStaged=1 packaging\skeer-midi-vault.iss # with the staged VST3
```

`/DPluginStaged` is the only thing that decides whether the installer carries the plug-in, and
it is decided at compile time: with the switch and no `launch\VST3`, Inno aborts on "No files
found" instead of quietly producing an installer that lacks it. `-SkipPlugin` simply does not
pass the switch; `-SkipAppBuild` still stages and installs the plug-in.

`distpath` is a command-line option, not a spec setting: building the standalone
app from the root spec by hand needs `--distpath launch` to keep it in the
unified folder.

Build dependencies live in `packaging/requirements-build.txt`. The runtime
application itself still has zero third-party Python dependencies.

## Test the installed build

```powershell
# packaged executable: health → scan → process-pool workers → quit
python tests\test_packaged_smoke.py
```

For an installed test copy, set `SKEER_PACKAGED_EXE` to the installed executable and
`SKEER_SMOKE_DATA` to a scratch directory. The smoke test verifies:

- the local service starts and answers `/api/health`
- the frozen Python service can index the demo library using process workers
- no `--multiprocessing-fork` worker processes survive app exit
- `/api/app/quit` cleanly exits the tray/service process
- a write without the session token is refused with 403 and does not corrupt the keep-alive
  connection behind it, and a non-JSON body is refused with 415 the same way
- the bundle carries a provenance stamp naming the commit it was built from, the running
  service publishes that same object, and `_internal\web\dist` still hashes to what the stamp
  recorded — the stale-interface case that mtime cannot see

### The install → run → uninstall cycle

`packaging\install_cycle_check.ps1` is the only check that reads what a double-click produces. It
installs the built Setup into its own folder under `%LOCALAPPDATA%\SKEER MIDI VAULT cycle\`,
verifies the installed bytes against `launch/`, runs `tests\test_packaged_smoke.py` against the
**installed** executable, uninstalls, and compares every folder, shortcut, registry entry, the user
library and a census of `C:\Program Files\Common Files\VST3` against the state captured before.
Exit 0 only when all of that passed; 2 when a phase could not be run; 1 when something is wrong.

```powershell
powershell -File packaging\install_cycle_check.ps1              # the full cycle - run this yourself
powershell -File packaging\install_cycle_check.ps1 -KeepInstall # leave it installed to poke at
powershell -File packaging\install_cycle_check.ps1 -FilesOnly -Dir D:\somewhere\empty
```

**As measured on 2026-11-17, from the agent shell, and re-measured on 2026-11-18 against the
rebuilt Setup:** the payload is proven and the registration is
not. Setup installed all 198 files `launch/` holds — nothing missing, nothing extra, including
`_internal\buildinfo\BUILDINFO.json`, `_internal\web\dist\index.html` and both files of the VST3
bundle that carry the version a host lists — and then rolled the tree back because writing the
next thing an installer must write was refused to it: first
`%LOCALAPPDATA%\SKEER MIDI VAULT cycle`, then
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\SKEER AUDIO`, and
`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall` — that last one from Setup's own log,
not only from a control build of Inno's own minimal
script: driving the shipped Setup interactively copied all 199 destinations into a workspace
folder, then raised `IPersistFile::Save failed; code 0x80070005` for the desktop `.lnk` and
`RegCreateKeyEx failed; code 5` for the uninstall key, and `Rolling back changes` emptied the
folder to 0 files with no registry entry left behind. Read `install-cycle-20261117-231426` before
quoting any of that as new: the same two refusals are in the **silent** 2026-11-17 run whose
`/DIR` pointed inside the workspace, which copied the payload, failed the desktop shortcut and
then `Creating new uninstall key`, and rolled back. That the sentence has been here for a day
without being quoted is what the "never reached that key" reading in `docs/limitations.md` came
from, and it is why the check keeps the Setup log path in its `evidence:` line. That is the shell's
child-process policy, not a defect in the artifact: the account's own `powershell` and `reg.exe`
write those places freely, and a stock minimal Inno script fails in exactly the same place, so the
refusal cannot be attributed to this script. Which exit that produces depends on how far Setup got,
and both were measured here on 2026-11-18: with `-FilesOnly -Dir` inside the workspace the copies
finish, only registration is refused, and the check ends `CYCLE INCOMPLETE` (exit 2); with no
`-Dir`, Setup is refused the folder before it copies anything, `files` reports FAIL for that reason
alone, and it ends `CYCLE FAILED` (exit 1). Either headline now carries the refused path and the
`Error 5: Access is denied` beside it, because `release_check.ps1` quotes that line into its
`installed` row and "Setup did not install" on its own reads like a broken installer. That row was
seen carrying it on 2026-11-18: `release_check.ps1 -Stages installed` ended
`NOT READY - 0 passed, 1 failed, 0 skipped, of 1 stages`, its `installed` detail naming
`C:\Users\Sebastien\AppData\Local\SKEER MIDI VAULT cycle` and `Error 5: Access is denied`.

Two things the same afternoon settled about running Setup by hand from a restricted shell, because
a hand-run Setup is told neither. `-Dir` must arrive with its backslashes intact: a POSIX
shell eats the
ones in an unquoted `D:\…`, Inno then treats `D:Projects…` as *relative to the repo*, and the
`files` row reports 199 destinations "outside the requested directory" for that reason alone —
quote the argument, and the mangled folder is cleaned up by the rollback rather than left behind.
And the wizard will not open at all until the child's `TMP`/`TEMP` point inside the workspace:
Setup's first act is to create `is-XXXX.tmp` under `%TEMP%`, which is refused here, and the
`/TMPDIR` switch does not help because this Setup rejects it on the command line (exit 1, no log
written). `install_cycle_check.ps1` has done that redirection all along, at
[install_cycle_check.ps1:198](install_cycle_check.ps1) — it is only a hand-run Setup that has to
be told. With the environment redirected, the licence page renders and the rest of the wizard is
reachable — it opens on *License Agreement* with **I do not accept the agreement** selected, which
leaves **Next** disabled, so nothing installs unless someone chooses otherwise.

One reading trap, because the two clocks in the evidence differ: the `install-cycle-<utc>` and
`release-check-<utc>` folder names and the bundle's `built_at` are UTC, while every line Setup
writes is local — Setup declares its own offset on the first line of its log,
`Log opened. (Time zone: UTC+01:00)` here. So the run in `install-cycle-20261117-235354` opens with
a `2026-11-18 00:53` line: the same second, an hour later on paper. The dates above are local.

The refusal follows the **executable**, not the folder, and that was pinned down on 2026-11-18.
`Get-Acl` reports `Allow FullControl` for this user on `%LOCALAPPDATA%` and on the Start Menu's
`Programs`, and a `powershell` child of this same shell creates folders and writes files in all of
them. Setup, launched the same way from the same parent, is refused even opening a file there: with
`%LOCALAPPDATA%\SKEER MIDI VAULT cycle\1.1.0` and `Programs\SKEER AUDIO` pre-created by the shell so
that Setup had no directory left to make, it copied 0 files and died with `CreateFile failed; code 5.
Access is denied.` So do not spend another run on `-Dir` or on pre-made folders — nothing outside the
workspace is writable by this artifact from here, and the cycle can only finish in a terminal outside
the sandbox. (Both probe folders were removed afterwards, and the three things worth re-checking —
the Add/Remove Programs entries, the running SKEER processes and the `SKEER*` folders in
`%LOCALAPPDATA%` — read the same after the attempt as before it.)

Two mechanics that were worth finding out rather than guessing at, both now handled by the script:
`Start-Process` routes through `ShellExecute`, whose attachment manager raised a modal
"Open File - Security Warning" that no headless run can answer, so Setup is launched with
`CreateProcess` instead; and SetupLdr cannot create its extraction directory in this `%TEMP%`, so
the child is given a `TMP`/`TEMP` inside the evidence folder.

**Closed on 2026-11-21, in a terminal this shell cannot reach.** Those four items ran against the
shipping Setup — `SKEER-MIDI-VAULT-Setup-1.1.0.exe`, 25670588 bytes, `preflight` reporting `hash
matches the manifest`, the `855516d5bbee` build — from an elevated prompt, twice:
`install-cycle-20261121-153747` with both shortcut tasks declined and
`install-cycle-20261121-153801` with `-WithShortcuts`. Both ended `CYCLE OK - 17 phases passed`.
Add/Remove Programs gained the entry and went back to `0 entry(ies)`; the second run found both
`.lnk` files at the paths `[Icons]` declares and found neither after the uninstall; the installed
`SKEER MIDI VAULT.exe` hashed the same as the one in `launch/` and passed
`tests\test_packaged_smoke.py` *from a Setup-registered folder*, which had never happened — the
only earlier pass was against a hand-copied tree; the user library at
`%LOCALAPPDATA%\Skeer\MIDI Vault` came through untouched; and the census of
`C:\Program Files\Common Files\VST3` read 1317 entries before and the same 1317 after, in both
runs. Two things that did **not** settle there have since settled, both on 1.1.1 bytes: the
1.1.1 Setup got its own run from `release_check.ps1`'s `installed` stage
(`install-cycle-20261121-185610`, `CYCLE OK - 17 phases passed`, shared folder unchanged at 1317),
and the `/ALLUSERS` leg both of those per-user runs left open was executed from an elevated prompt
and graded green — `shared-folder PASS`, 2 files placed under `C:\Program Files\Common Files\VST3`,
every one inside our own bundle, and the uninstall returning the folder to the census it started
from. Item 1 below carries the detail, including the first attempt that went red on the grader
rather than on the installer.

One item that used to open that list is no longer in it: the licence page has been seen the way a
buyer sees it. On 2026-11-18 the wizard opened on *License Agreement* with §6 and §7 filled —
`Licence and support enquiries: sebastienvermeire@gmail.com`, the Belgium jurisdiction clause, no
`<<<FILL:` token anywhere — with *I do not accept the agreement* selected and **Next** disabled, and
the run was ended with Cancel, leaving 0 files installed and nothing registered. What that page
shows is `packaging/EULA.txt` verbatim, because
`skeer-midi-vault.iss:45` sets `LicenseFile={#SourceRoot}\packaging\EULA.txt` — which is why the
gate's `licence` stage and the falsifier's EULA case cover the same bytes the buyer reads.

### A host session — the three questions only a DAW can answer

Everything the plug-in does is proven headless. `plugin/build.ps1` builds the bundle and runs six
suites against it — `vault-locator-test`, `vault-index-test`, `vault-midi-test`, `vault-emit-test`,
`vault-editor-test` (the panel's widget tree, pumped without a window) and `vault-host-test`, which
loads the bundle the way a host does and emits through that wrapper — on the 8.0.4 and the 8.0.8 JUCE
alike. Three things are left, and none of them can be settled from a shell:

1. **Does a host find it?** A per-user install puts the bundle in
   `%LOCALAPPDATA%\Programs\SKEER MIDI VAULT\VST3`, which no host scans by default. Setup's own log
   says which folder it used — `VST3: installing into …` or `VST3: installed only in …` — and the
   choices are to point the host at that folder or re-run Setup elevated with `/ALLUSERS`, which
   also writes `C:\Program Files\Common Files\VST3`. That switch is honoured, not rejected: the
   script sets `PrivilegesRequired=lowest` with `PrivilegesRequiredOverridesAllowed=commandline`
   (`packaging/skeer-midi-vault.iss:35-36`), which is what lets a command-line install choose
   all-users mode. One command grades that leg instead of asking you to read a log: `packaging\install_cycle_check.ps1 -AllUsers`,
   from an elevated prompt — it refuses in preflight when the terminal is not admin, so it cannot
   half-install, and it requires both the `VST3: installing into` line and a shared folder whose
   only new entries are inside `SKEER MIDI VAULT.vst3`. That command has now run: 2026-11-21, 18:56Z,
   against the 1.1.1 Setup the certification built, and it ended `CYCLE OK - 18 phases passed` with
   `shared-folder PASS - 2 file(s) placed under C:\Program Files\Common Files\VST3, every one inside
   our own bundle, and nothing else in that folder moved` and `uninstall PASS - shared VST3 folder
   still unchanged`. The attempt 16 minutes earlier graded that row **FAIL**, and the fault was the
   grader's: it matched diff entries against `^SKEER MIDI VAULT\.vst3`, but the helper emits
   `added: <path>`, so no entry could ever classify as ours — while Setup's own log had listed both
   files created under `Common Files\VST3` and both deleted on uninstall. Fix-forward commits
   `7055952` (the destination) and `10fbc15` (the grader). Either way the plug-in should be listed as
   *SKEER MIDI VAULT* **1.1.1**: that number comes from the staged bundle's `moduleinfo.json`, is
   what a host displays, and the build refuses to ship a bundle whose copy disagrees with the
   release. The same `moduleinfo.json` declares the class under `Sub Categories: ["Fx"]` on
   VST 3.7.12. It declares **three** classes in total — one `Audio Module Class` plus Steinberg's
   `Component Controller Class` and `Plugin Compatibility Class`, all three named
   `SKEER MIDI VAULT` at `1.1.1` — so a conforming host lists **one** entry, and a second or third
   copy of the name in a scan is a host bug, not a staging mistake. What is not settled from a
   shell is *which menu* that entry appears in: `Sub Categories` says `Fx`, while
   [plugin/Source/VaultMIDIProcessor.h:86](../plugin/Source/VaultMIDIProcessor.h) returns
   `isMidiEffect() == true`, and a host that reads the MIDI-effect flag files the plug-in with the
   MIDI effects and restricts it to MIDI tracks. Ask the host which it did, and record the answer —
   this runbook does not claim it.
   Which bytes you are loading matters for what a session proves: the two JUCE trees build
   different binaries, and only one of them ships. Re-measured 2026-11-21 against the bytes the
   1.1.1 release ships — the earlier figure below was from 2026-11-18 and predates this rebuild,
   which the note at the end of this paragraph has always told the reader to do:
   `launch/VST3/…/Contents/x86_64-win/SKEER MIDI VAULT.vst3` is SHA-256
   `a2f157679dacfd7ae202db7e8d246cc4a85a5e727eb62c4c7a8fd4bd6e9c9bf9`, 7,566,336 bytes, and
   byte-identical to the copy under `plugin/build/…` — the 8.0.4 tree — and that copy is what
   `vault-host-test` loaded in the same gate run; the `build/tag-808` bundle is
   `6b898e83dabcb631…` at 7,694,848 bytes — different size, different SHA-256 — and is
   source-compatibility evidence only. So a DAW session ratifies the 8.0.4 binary; nothing you
   hear in a host speaks for the 8.0.8 build. Recompute the two hashes rather than trusting this
   sentence after any rebuild.

   A second name confusion is live on this machine, and it is not ours. Census 2026-11-19:
   `C:\Program Files\Common Files\VST3\SKEER Vault.vst3` is installed — module
   `Contents/x86_64-win/SKEER Vault.vst3`, 5,475,328 bytes, stamped 12:54:42 that day, with
   `moduleinfo.json` saying `Name = SKEER Vault` and `Version = 1.1.0`. Same brand, same version,
   different product: `git log -S "SKEER Vault" --all` finds that string nowhere in this repo's
   history, so it is not an earlier name of this bundle, and ours is `SKEER MIDI VAULT` at
   7,566,336 bytes. Both declare `Sub Categories: ["Fx"]`, so a host that scans the shared folder
   files the two side by side in the same menu as same-version effects — and a session spent on the
   wrong one proves nothing about these bytes. Check the exact name the
   host loaded (and its path, when it shows one) before answering any of the three questions.
   This does not block the `/ALLUSERS` leg: `install_cycle_check.ps1 -AllUsers` requires that the
   new entries in the shared folder sit inside `SKEER MIDI VAULT.vst3`, so a foreign bundle already
   there is neither a refusal nor a false pass. It is not a stranger either: the string comes from
   the sibling repo in this family — `sample-vault/vst/CMakeLists.txt:117` sets
   `PRODUCT_NAME "SKEER Vault"`, and that project's installer deploys exactly that bundle name into
   exactly that shared scan folder (`sample-vault/installer/SKEER_Sample_Vault.iss:23-24`). So it is
   one of your own two products living where the other one's Setup puts it — what placed it there,
   a Setup run or a hand copy, the file alone cannot say, but retiring it is a decision between your
   two plug-ins and not about a third party.

   What that session will be operating on, measured on this machine 2026-11-19 so nobody has to
   guess it mid-take:
   `%LOCALAPPDATA%\Skeer\MIDI Vault\midivault.sqlite3` is 449,347,584 bytes with
   `PRAGMA user_version = 1` — read from the header bytes at offset 60, so nothing was opened and
   no `-shm`/`-wal` was created by the reading. The sidecars that are already there are a 32,768-byte
   `-shm` and a **0-byte** `-wal`: a write-ahead log with no frames has nothing to replay, which is
   why the plug-in's read-only open is safe beside them (and why the absence of a checkpoint is not
   evidence of an unclean shutdown). This is not a defect to fix before the session, and the
   session does not have to come after an app run: `supportedSchemaVersion` is 2
   (`plugin/Source/VaultIndexReader.h:15`) so a schema-1 index is accepted, the only column the
   one migration adds is `files.fingerprint_version` (`midivault/db.py:1782-1799`), and that name
   does not appear anywhere under `plugin/Source/` — every column the plug-in selects or filters on
   was already in the schema-1 `files` table. Migrate first or connect first; the plug-in reads the
   same rows either way. The locator's four roots match what the service writes
   (`plugin/Source/VaultIndexLocator.cpp:81-85`, `%LOCALAPPDATA%` + `Skeer\MIDI Vault` at `:32-43`
   and `:77`), so **Connect** should list this library without you pointing at the file.
2. **Does the panel behave by hand?** The filter box takes typing, the library list scrolls, the
   three exported controls stay visible, and nothing touches the index until **Connect** is clicked.
   Then confirm the two promises the code makes about failure: a query that *fails* keeps the index
   path and says "not read this time" — only **Disconnect** forgets it and **Rescan** retries — and
   the status strip names both the file that is playing and the file the project asked for.
3. **Keyboard focus is your decision, not a test.** `EDITOR_WANTS_KEYBOARD_FOCUS` is TRUE at
   `plugin/CMakeLists.txt:106` so the filter box can receive keystrokes, which also means the host's
   own shortcuts do not fire while the panel has focus — and the host gets its keys back as soon as
   focus leaves. Say which behaviour you want shipped: the other answer is that same line set FALSE,
   which is a CMake change and therefore a rebuilt bundle, and no suite can prefer either because
   none of them creates a window.

While a host is open, exercise the two paths that end on a real filesystem: drag a clip out into the
arrange page, and **Save clip as…** onto a file that already exists — the *operating system's* own
overwrite prompt should appear, and cancelling it must leave that file untouched. Afterwards check a
library folder: the product never renames, moves, edits or deletes a source MIDI file, and that rule
is worth confirming against your own recordings rather than the suites.

Write what you find into the **DAW drag target verification** and **Installer verification** bullets
of `docs/completed-partial-missing.md`, and the row-18 / step-8 status of
`docs/next-steps-2026-11.md`.

## Code signing and SmartScreen

The deliverable is unsigned by default. `-Sign` is the only path that signs, it is inert unless
asked for, and its preflight demands `signtool` and a certificate before the build touches
anything:

```powershell
$env:SKEER_SIGN_PFX = 'C:\path\to\cert.pfx'                 # or SKEER_SIGN_THUMBPRINT for a store cert
$env:SKEER_SIGN_PASSWORD = '...'                            # only if the .pfx is protected
$env:SKEER_SIGN_TS_URL = 'http://timestamp.digicert.com'    # optional; it has a default
.\packaging\build_installer.ps1 -Sign
```

Order is enforced by the script, because getting it wrong produces an artifact that looks signed
and is not: the app executable is signed **before** Inno compiles, since its bytes are the
payload; the Setup executable is signed **after** Inno produces it; `SHA256SUMS.txt` is written
**last**, so the manifest hashes signed bytes. Every signature is checked with
`signtool verify /pa` immediately and a failure stops the build.

The certificate and timestamping vendor are the seller's choice. Without a signature, Windows
SmartScreen may warn recipients until the file builds reputation; the version information and
icon are set either way, and signing is what makes them attributable to a publisher.

## Before shipping: `scripts\release_check.ps1`

One command, one exit code, eleven stages. It is the only thing in this repository whose status
line means "ship it", so it is the last thing run before a file leaves.

```powershell
powershell -File scripts\release_check.ps1            # gate, suite, web, plugin, plugin808,
                                                     # installer, stamp, smoke, checksums,
                                                     # licence, installed
powershell -File scripts\release_check.ps1 -Fast     # gate, suite, licence, checksums
powershell -File scripts\release_check.ps1 -Stages stamp,smoke
```

Exit 0 prints `READY`, exit 1 prints `NOT READY`, and exit 2 prints `INCOMPLETE` — a stage that
could not run is never allowed to count as a pass, which is the difference between a gate and a
cheerleader. Each stage writes its own log under `build\work\release-check-<utc>\`, and the summary
row names the cause in the words the stage itself used, not just an exit number: on the run that
filled this licence, the `licence` row changed from "2 unfilled field(s):
`<<<FILL: contact>>> <<<FILL: jurisdiction>>>`" to "no placeholders, licence page states 1.1.0".

`python scripts\check_release_gate.py` is its falsifier. It copies the ten files a release touches into
`build\work\release-gate-falsifier\`, fabricates a `launch/` with a correct manifest, stubs the
child commands, and then requires 33 outcomes (31 of which execute on this machine: the two `web`
cases are mutually exclusive by design, and the no-second-JUCE-tree case can only fire where that
tree is absent): a control build that reaches READY, and one planted
defect per gate rule — a bumped literal, a CRLF manifest, a wrong hash, a missing row, a stale
1.0.0 row, an unfilled licence field, a licence page naming the wrong version, a plug-in suite that
prints a green-looking ctest line while exiting non-zero, a bundle whose stamp names no commit, an
installer that produced nothing, and so on. Run it after editing either script; the gate's own
redesign is the most likely thing here to silently stop checking something.

As measured on 2026-11-17 against the built 1.1.0 deliverables, `-Fast` reports `NOT READY` with
three passes and exactly one failure — the two unfilled `EULA.txt` fields above. Nothing else in
that set is red. The full eleven-stage set, run on 2026-11-17 against a clean build of the release
commit, reports `NOT READY - 9 passed, 2 failed, 0 skipped, of 11 stages`: `licence` FAIL on those
same two fields, and `installed` FAIL because Setup cannot make a folder in this shell. `stamp` is
**not** one of the failures — it passes on a bundle built from a committed tree, which is the only
state in which these artifacts should be published. Run again on 2026-11-18 against the
deliverables rebuilt after the licence fill — commit `c520d03eed51`, `stamp PASS - clean` — and a
third time that evening at 16:22:24Z against the deliverables the gate rebuilt from
`a4708a87ec6d`, the set
reports `NOT READY - 10 passed, 1 failed, 0 skipped, of 11 stages`: every stage green except
`installed`, which is still Setup being refused a folder by this shell. One red is left and it is
not this machine's to finish.

## What not to ship

Do not ship the `build/`, `dist/`, `dist-installer/`, `dist-debug/`, `tests/`,
`.git/` or source tree to customers. Ship only the setup executable or portable
ZIP from `launch/`.

## Versioning — one release number, and the gate that holds it there

`midivault/__init__.py` is the reference. Every other place that states the version is compared
to it by `scripts/check_version_consistency.py`, which reads eleven literals across eight
files:

| file | literals |
| --- | --- |
| `midivault/__init__.py` | `__version__` — the reference |
| `packaging/skeer-midi-vault.iss` | `AppVersion`, `VersionInfoVersion` |
| `build/version_info.txt` | `filevers`, `prodvers`, `FileVersion`, `ProductVersion` |
| `desktop.py` | `VERSION` |
| `web/package.json` | `version` |
| `plugin/CMakeLists.txt` | `project(... VERSION)` |
| `packaging/EULA.txt` | the version on the licence page |
| `packaging/build_installer.ps1` | forbidden: a `$Version` literal of its own |

```powershell
python scripts\check_version_consistency.py
```

Exit 0 means all eleven agree and the build script still derives its version from the reference.
Values are compared as numbers, so `1.1.0`, `1.1.0.0` and `1, 1, 0, 0` are one version and only
a real difference is a failure.

`build/version_info.txt` gets four probes because Windows reads the fixed file info (`filevers`,
`prodvers`) and the string table (`FileVersion`, `ProductVersion`) separately: one probe cannot
see the other three, and a bump that reaches only two of them yields an installer whose product
version disagrees with the binary it installs.

`tests/test_version_consistency.py` runs the checker inside
`python -m unittest discover -s tests`, keeps its own list of the literals the gate must read,
and proves the gate can fail: it copies the probe targets into a temporary directory, moves one
literal, reformats another out of the checker's reach, and plants a `$Version` in a copy of the
build script. A gate nobody has seen go red is not known to be a gate.

The build script runs the same two version checks in its preflight, so a half-done bump stops
before anything is deleted.

**Settings → About** shows `app.version` from `/api/bootstrap`, i.e. whatever
`midivault/__init__.py` says, so it needs no edit of its own.

## Legal

`packaging/EULA.txt` has **not been reviewed by counsel**. It is drafting that reached a state a
build can ship, and nobody should read it as legal advice or as clearance to sell.

Both fields were filled on 2026-11-18, from the machine rather than out of thin air:

```
Licence and support enquiries: sebastienvermeire@gmail.com
    ^ from `git config user.email`, read 2026-11-18
This agreement is governed by the law of Belgium
    ^ from `HKCU\Control Panel\International\Geo` → `Name BE`, read the same day
```

They are ordinary text now, not tokens. The guard that kept them from shipping unfinished is the
`licence` stage of `scripts/release_check.ps1`, which fails any page still carrying a `<<<FILL:`
marker, and `scripts/check_release_gate.py` plants one in a shadow copy to prove that stage still
reddens — the falsifier no longer depends on the real page being unfinished. To change an answer,
edit `packaging/EULA.txt:42` or `:45` and rebuild, because Inno compiles the file into the Setup
(`skeer-midi-vault.iss:45`): the installer stamped 2026-11-17 carried both tokens and was replaced
on 2026-11-18 by one compiled after the fill, and that is the artifact the sizes and digests in
`docs/release-notes-1.1.0.md` now name. Nothing in `build_installer.ps1` checks or strips a token,
so the gate is the only guard, and any later change to these two lines is just text until a build
carries it. The version line in §6 is still a checked
literal — `scripts/check_version_consistency.py` reads it, so a bump that misses the licence page
fails the gate instead of shipping an installer whose licence names last release.

Know what the first field costs, because it is a one-way step: that address is compiled into
every Setup and portable ZIP, so anyone who receives the product holds a personal email as the
name of the party granting the licence. The repository being private is irrelevant to that — the
artifacts are not.

Said out loud because it shapes both fields: **the seller is one person, not a company** —
decided 2026-11-18. `SKEER AUDIO` is a trading name with no legal entity behind it, so the
licence identifies its counterparty only through the contact line. That makes `contact` carry
more than an address: it is the place where a buyer can see who is granting the licence, and
`jurisdiction` is the law of the country that person lives in, because there is no registered
office to point at — which is why the two lines above hold an address and a country rather than a
company name and a registered seat. The consequence worth knowing before the first sale, and the
reason this section opens with a counsel warning: whether an individual selling software for money
is a *trader* for consumer-protection purposes is a question this file cannot answer, and it
decides duties the EULA does not currently mention at all — a 14-day withdrawal right and
refund path among them. A company would have had those by default; a personal seller should
ask counsel whether they apply before assuming they do not.

The installer shows this EULA before installation, and accepting it is what enables Install.
