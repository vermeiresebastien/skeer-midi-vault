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
- installs the VST3 bundle into **one** folder, chosen by the install mode: `{app}\VST3`
  for a per-user install, `Program Files\Common Files\VST3` — the folder hosts scan by
  default — for an all-users one. The two `[Files]` entries carry `Check: not CommonVst3`
  and `Check: CommonVst3`, so neither mode can leave two copies of one class ID standing in
  two folders; through 1.1.1 the all-users mode wrote both, which is what a producer saw as
  the same device listed twice. A per-user install never writes to a shared folder, and the
  Setup log records which of the two happened — the all-users branch prints the shared path
  it used and names the `{app}\VST3` copy it declined, the per-user branch prints the
  `{app}\VST3` path and says the shared folder was not touched — so a producer who cannot
  see the plug-in has an explanation to read.
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
   writes `C:\Program Files\Common Files\VST3` **instead** and leaves `{app}\VST3` empty — as of
   1.1.2 the two placements are mutually exclusive, so an all-users install does not leave a second
   copy behind (through 1.1.1 it did). That switch is honoured, not rejected: the
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
   `7055952` (the destination) and `10fbc15` (the grader). Both arms ran again on 2026-11-22 against the
   Setup this release certifies — `CYCLE OK - 18 phases passed` machine-wide
   (`build\work\install-cycle-20261122-181627`) and `CYCLE OK - 17 phases passed` per-user
   (`…-181612`) — and the `plugin` phase in each arm now checks the destination that mode is allowed to
   write *and* looks in the other one for a second copy, so this section's placement claim is graded on
   the bytes a session will load rather than on 1.1.1's. Either way the plug-in should be listed as
   *SKEER MIDI VAULT* **1.1.2**: that number comes from the staged bundle's `moduleinfo.json`, is
   what a host displays, and the build refuses to ship a bundle whose copy disagrees with the
   release. The same `moduleinfo.json` declares the class under `Sub Categories:
   ["Instrument","Synth"]` on VST 3.7.12 — **and that is the one line of this runbook that changes
   where a session should look**: 1.1.1's copy read `["Fx"]` and the host listed it under Effects, so
   the device is now expected in the **Instruments** drawer. `Class Flags: 2` beside it is
   `Vst::kSimpleModeSupported`, which `IS_SYNTH TRUE` adds; the category list, not that flag, is what
   files the drawer. It declares **three** classes in total — one `Audio Module Class` plus Steinberg's
   `Component Controller Class` and `Plugin Compatibility Class`, all three named
   `SKEER MIDI VAULT` at `1.1.2`, the third with no `Sub Categories` of its own — so a conforming host lists **one** entry, and a second or third
   copy of the name in a scan is a host bug, not a staging mistake. The *which menu* question this
   paragraph used to hand to a session was answered out of the host's own file — for the **1.1.1**
   bytes — and the answer disposes of a hypothesis without settling the new one:
   [plugin/Source/VaultMIDIProcessor.h:86](../plugin/Source/VaultMIDIProcessor.h) returns
   `isMidiEffect() == true`, yet the host filed us `device:vst3:audiofx` — because there is no MIDI-effect
   bucket for it to put us in. Counting the class-id kinds across the `12.3.2` cache gives 1,298 `audiofx`
   and 118 `instr` for VST3 (those 1,416 are the device rows the census counts) plus 184 `audiofx` and 14
   `instr` for the legacy VST2 rows, which are the 198 the census leaves out, and **no** third kind anywhere
   in the file. That is what a plug-in scan DB looks like when a host offers third-party code two drawers, so
   the filing decision really is binary here: a device lands in one drawer or the other, and 1.1.1's
   bytes landed in Effects. What no file on this machine can yet say is where 1.1.2's land — the cached
   row was written for the old bytes and a host rewrites it only when it rescans them. So the first of
   this section's three questions is now two. **1a:** after a rescan, does our device row read `instr`
   with sub-category `Instrument|Synth`? **1b:** will Live put a MIDI-out-only device on a MIDI track
   at all, which has never been tested in either drawer. This runbook claims neither.
   Which bytes you are loading matters for what a session proves: the two JUCE trees build
   different binaries, and only one of them ships. Re-measured 2026-11-22 against the bytes this
   build stages — the earlier figure below was from 2026-11-21 and predates this rebuild,
   which the note at the end of this paragraph has always told the reader to do:
   `launch/VST3/…/Contents/x86_64-win/SKEER MIDI VAULT.vst3` is SHA-256
   `6fcc3f4cb96829f19052dc887ac3386190c643787a6372164d34f3fb94d8505f`, 7,566,336 bytes, and
   byte-identical to the copy under `plugin/build/…` — the 8.0.4 tree — and that copy is what
   `vault-host-test` loaded in the same gate run; the `build/tag-808` bundle is
   `8aaa71651785bb6c…` at 7,694,848 bytes — different size, different SHA-256 — and is
   source-compatibility evidence only. Two of those numbers are worth reading twice. The shipped
   binary is **the same length as 1.1.1's** (`a2f157679dacfd…`, 7,566,336 bytes) and a different
   hash, so a same-length compiled string moved it and no size check could see that — which is why
   the cycle's `plugin` phase works in SHA-256. And the artifact settles the category question
   without waiting for a host: the file contains `Instrument|Synth` once and `1.1.2` once, with no
   `1.1.1` anywhere, so the bytes that ship are the bytes the flags were set in —
   `python -c "b=open(r'launch/VST3/SKEER MIDI VAULT.vst3/Contents/x86_64-win/SKEER MIDI VAULT.vst3','rb').read();print(b.count(b'Instrument|Synth'),b.count(b'1.1.2'),b.count(b'1.1.1'))"`
   prints `1 1 0`. So a DAW session ratifies the 8.0.4 binary; nothing you
   hear in a host speaks for the 8.0.8 build. Recompute the two hashes rather than trusting this
   sentence after any rebuild.

   A second name confusion is live on this machine, and it is not ours. Measured again 2026-11-22 —
   the first census was 2026-11-19 and three of its numbers have since moved, which is itself the
   lesson: `C:\Program Files\Common Files\VST3\SKEER Vault.vst3` is installed, module
   `Contents/x86_64-win/SKEER Vault.vst3` now 6,756,352 bytes stamped 04:04:02 local that morning,
   where 11-19 recorded 5,475,328 at 12:54:42. The sibling project reinstalls itself between
   sessions, so **any figure quoted about that bundle needs a date**. `moduleinfo.json` still says
   `Name = SKEER Vault`, `Vendor = SKEER Audio` and `Version = 1.1.0`. Same brand, different
   product: `git log -S "SKEER Vault" --all` finds that string nowhere in this repo's
   history, so it is not an earlier name of this bundle, and ours is `SKEER MIDI VAULT` at `1.1.2`.
   What 11-19 wrote next is now false on both sides and has been rewritten rather than left: it said
   both bundles declared `Sub Categories: ["Fx"]`, so a host filed the two side by side in an effects
   menu. Read off the folder today, that bundle declares `["Instrument","Instrument","Synth"]` — the
   `Instrument` appears twice, for a reason this repo cannot see because the file belongs to the
   sibling project — and the file is one a strict JSON parser refuses (`json.load` dies at line 12
   with a trailing comma), which is why the census reads these files with a regex. Ours declares
   `["Instrument","Synth"]`. **So the two now share the Instruments drawer and the drawer is no
   longer a discriminator.** What discriminates, in order of reliability: the class-ID tail
   (`536B41754D766C74` is ours — `SkAu`/`Mvlt`; that bundle is `536B6572536B7276` — `Sker`/`Skrv`),
   then the exact name, then the version, which is the weakest of the three because both products
   have shipped `1.1.0`. A session spent on the wrong one proves nothing about these bytes, so check
   the exact name the
   host loaded — and its path, when it shows one — before answering any of the three questions.
   This does not block the `/ALLUSERS` leg: `install_cycle_check.ps1 -AllUsers` requires that the
   new entries in the shared folder sit inside `SKEER MIDI VAULT.vst3`, so a foreign bundle already
   there is neither a refusal nor a false pass. It is not a stranger either: the string comes from
   the sibling repo in this family — `sample-vault/vst/CMakeLists.txt:117` sets
   `PRODUCT_NAME "SKEER Vault"`, and that project's installer deploys exactly that bundle name into
   exactly that shared scan folder (`sample-vault/installer/SKEER_Sample_Vault.iss:23-24`). So it is
   one of your own two products living where the other one's Setup puts it — what placed it there,
   a Setup run or a hand copy, the file alone cannot say, but retiring it is a decision between your
   two plug-ins and not about a third party.

   A running host is reachable from a shell, and that changes who has to answer what. Measured
   2026-11-21 at 21:39Z through this machine's Ableton Live 12 MCP bridge: `plugins` → `VST3` offers
   a vendor folder `SKEER` (BASSGEN, DRUMGEN, DRUMGEN Origin, SliceForge, VRAC+) and one
   `SKEER Audio` holding exactly `SKEER Vault`. It offers a third one too, and the first draft of this
   paragraph got that wrong in a way that mattered: `plugins` → `VST3` lists **three** nodes in this
   family — `SKEER`, `SKEER Audio` and `Skeer Audio` — as separate entries with separate URIs
   (`…VST3:SKEER%20Audio` and `…VST3:Skeer%20Audio`), but the bridge's path lookup case-folds, so
   `Skeer Audio`, `SKEER Audio` and `SKEER AUDIO` all return the contents of the second node and the
   third cannot be addressed by path at all. Since `Skeer Audio` is exactly our `COMPANY_NAME`, that
   unreachable node is where our entry would appear, and "no `SKEER MIDI VAULT` in the browser" was
   therefore never an absence proof: it inspected two of three nodes. The disk census behind that answer: `C:\Program Files\Common
   Files\VST3` holds 56 bundles at its top level and 222 counting the 16 vendor subfolders inside it
   (IK Multimedia 64, Eventide 35, Safari 29, Goodhertz 17, seven folders with 2-6 each and eight with
   one), none of the 222 being ours; `%LOCALAPPDATA%\Programs\Common\VST3` exists and is empty, and the
   only copy of the bundle on the machine was `launch\VST3\`, whose moduleinfo reads `Version 1.1.1`.
   That count is the same folder re-read 2026-11-21 at 21:52Z by a recursive scan, and the 56 in the
   first draft of this paragraph came from a top-level glob — a method flaw, not a smaller number,
   because 166 of those 222 bundles live in subfolders of the root, not in it. A bundle in a
   subfolder is invisible to a top-level glob, and "we are not on this disk" is precisely the finding
   this census is trusted to produce, so identity is now read from the class ID rather than the file
   name: bytes 9-16 of our CID are ASCII `SkAuMvlt`, and exactly one bundle on the machine reports it.
   So question 1 is still unanswered on the shipped bytes, for the reason the paragraph above gives
   rather than a new one — and the browser was never the instrument that could answer it. What can is
   the host's own scan database, and the instrument is now `scripts/host_scan_check.ps1` (read-only),
   which takes the class ID from `plugin/CMakeLists.txt` rather than repeating it. Run 2026-11-21 at
   22:14Z against all four caches on this machine: the newest, `Live 12.3.2`, was **last written at
   22:14 local — sixty minutes before that read, with Live running** — so a scan genuinely did happen
   today, and its 1414 device rows carry zero of our class ID and no row of any kind names
   `SKEER MIDI VAULT`. `Live 12.3.5` (3510 lines, last written 15 Nov 16:49) reads the same, and it was
   the 22:00Z figure; the four needles that first pass counted were substrings of one spelling, so they
   proved one thing rather than four. The control run is what found the spelling: the same script
   pointed at a sibling pair, `-VendorCode Sker -PluginCode Vrac`, finds `SkerVrac` in one device row of
   the very cache where all four needles for us read 0. That row spells the ID `536b-657256726163`, so a
   CID matches only across the host's 8-4-4-4-12 grouping and never as one contiguous run — which is why
   the script counts both spellings and takes the larger, and why a reader written to the contiguous form
   alone reports "not installed" about a plug-in the host has recognised. Two of those 1414 rows carry
   §6's finding into the host's own file: `VRAC+` is cached twice, as `SkerVrac` from vendor `SKEER` and
   as `ErwmVrac` from vendor `Earworm`, and `SliceForge` is cached under `ErwmVrac` — two products, one
   identity, in a list a person reads. So the cache being rewritten is the machine-readable proof that a
   scan happened, and 656 of the 751 rows under `C:\Program Files\Common Files\VST3` point inside vendor
   subfolders (the same 656 of the older cache's 742), so this host scans recursively and a bundle in
   `…\VST3\Skeer Audio\` would be found as readily as one at the top level — worth knowing before the
   1.1.2 placement decision is taken. What a row means is narrower than it looks: the cache records
   scans, not the present disk. In the same read, `%LOCALAPPDATA%\Programs\Common\VST3` is named by 2
   rows of the newest cache and 4 of the older one. Re-measured 2026-11-22 at 03:47 local, that root does
   hold a bundle: `VRAC obsolete\VRAC obsolete (nested 2026-11-02 build)\`, buried inside a plain folder
   instead of named `*.vst3` at the scan root — and its binary is gone, because the row above points at
   `Contents\x86_64-win\VRAC+.vst3`, which no longer exists while `Contents\Resources\moduleinfo.json`
   does. So a row is evidence that a scan once found something, never evidence that it is still there,
   and a row can outlive not only an uninstall but a binary someone moved by hand. The first draft of
   this paragraph asserted the root "holds no bundle at all", which is what counting only top-level
   `*.vst3` names produces; the census that corrected it had to be rerun with the fallback below, because
   a strict-JSON walk also drops bundles whose `moduleinfo.json` JUCE wrote with trailing commas. The
   `Live 12.3.5` cache names `SKEER Vault.vst3` in this same root, and that bundle sits in the *shared*
   folder today — so bundles here have been moved between roots by hand, and each cache remembers where
   the scan found them. Once a scan has happened, a
   host-side parameter read is the three exported controls counted by the host rather than by
   `vault-editor-test`. Rescanning has no method on that bridge (none of its 37 tools
   rescans), so the scan itself stays the owner's. What follows a scan was supposed to need no hand either,
   and that expectation is what the rest of this paragraph now qualifies. Measured
   2026-11-22 at 03:40 local against the running `Ableton Live 12 Suite.exe` (pid 1588): the bridge reads
   the browser, which files third-party bundles under `Plugins/VST3/<Vendor>` and returns each device
   with `is_loadable` and a `query:` URI. *Only* the click that starts a scan needs a hand, this paragraph
   went on to say, because loading ours and counting its exported controls looked drivable through
   `load_instrument_or_effect` and `get_device_parameters`. That was read off the tool descriptions, and the
   second half of it is wrong. Measured 2026-11-22 at 16:45 local on the same running host, against the
   devices already sitting on his one audio track: `get_device_parameters` at (0, 1) names `Snap Heap`,
   `class_name: PluginDevice` — a third-party VST3 the host genuinely has loaded — and returns **one**
   parameter, `Device On`, which is Live's own bypass rather than a control that plug-in wrote; the same call
   at (0, 0) on native `Utility` (`StereoGain`) returns **twelve**, every one of them the device's own. Same
   track, same tool, same minute. `get_track_info` compounds it: a device comes back with a name and a
   `class_name` but never a URI, so a plug-in already on a track cannot be read back as the handle a loader
   wants. One VST3 sample cannot separate "this bridge does not enumerate VST3 parameters" from "this plug-in
   publishes none to its host", and the difference does not change what follows — either way step 8's control
   read is a person looking at the host, not a script. The load leg is a different unknown, not a settled one:
   `load_instrument_or_effect` does take a `uri` (its own example reads
   `query:Synths#Instrument%20Rack:Bass:FileId_5116`), but nothing of ours has ever been loaded here, so no
   measurement says our URI resolves. Three limits on that seam are worth knowing before anyone builds on it.
   `get_session_info` fails on this build with `Python argument types in None.None(Song) did not match
   C++ signature: None(class TPyHandle<class ASong>)`, so session state has to come from `get_track_info`
   or the browser rather than from that tool. And `get_browser_items_at_path` resolves a folder name
   case-insensitively: this browser lists `SKEER`, `SKEER Audio` and `Skeer Audio` as three folders with
   three distinct URIs, and asking for the title-case one hands back the all-caps one. So the folder our
   own bundle will land in — `plugin/CMakeLists.txt` writes the vendor as `Skeer Audio`, and so do
   PulseKit and SKULPT — cannot be listed by path, while the all-caps `SKEER Audio`, which is
   sample-vault's `COMPANY_NAME "SKEER Audio"`, opens and shows one loadable device (`SKEER Vault`,
   `SkerSkrv`, built 2026-11-19). One company, three spellings, one of them unreadable through the seam:
   §6's vendor drift, now visible in a live host's browser rather than only in a cache file.

   The third limit closes the workaround the URI implies. Every device the browser lists carries its own
   `query:` URI, so a URI looks like a way to name `Skeer Audio` without going through the folder list that
   folds it onto its all-caps sibling. `get_browser_items_at_path` refuses one:
   `Unknown or unavailable category: query:plugins#vst3:skeer%20audio`. The echo is the informative part — the
   argument went in title-case and came back lower-cased, which is plausibly where the folding above lives,
   although an error string is a weaker witness than the resolver and the collision is measured independently
   of it. `prefer_candidate` is not what its name suggests: it records a pairwise preference between candidate
   actions, requires telemetry consent, and disambiguates nothing in a browser. What the refusal does hand over
   is the remote script's own method surface, where `load_item` sits beside `preview_item`, `plugins` and
   `user_folders` — so a seam that accepts a URI may exist one level below the tool the bridge exposes.
   Untested, and it stays untested here: the only way to learn whether `load_item` resolves our URI is to put a
   device into a set that is open in front of its owner, which is the owner's call rather than a step in a
   test plan.

   Whether a host has anything to find at all is a machine state, not a property of the release, and
   the runbook above can leave you with the wrong one: `install_cycle_check.ps1 -AllUsers` *uninstalls*
   what it installs, so as measured 2026-11-21 20:48Z this machine holds no copy of ours — neither
   `%LOCALAPPDATA%\Programs\SKEER MIDI VAULT` nor a `SKEER MIDI VAULT.vst3` in the shared scan folder,
   which held only the sibling bundles. That read is superseded at 03:34 local on 2026-11-22: the
   published 1.1.1 Setup, run elevated with `/ALLUSERS`, wrote ours into the shared scan folder — and,
   per the defect recorded in `docs/next-steps-2026-11.md`, a second byte-identical copy into
   `C:\Program Files\SKEER MIDI VAULT\VST3`. What that install left on the machine is now answered by the
   host itself, and the answer supersedes what this paragraph said on 21 November. `Live 12.3.2` scanned at
   `2026-11-22T05:47:07` and wrote a record for us into its own scanner log:

   ```
   VST3: found: SKEER MIDI VAULT
   vendor: Skeer Audio
   device-class-id: device:vst3:audiofx:abcdef01-9182-faeb-536b-41754d766c74?n=SKEER%20MIDI%20VAULT
   version: 1.1.1
   subCategories: Fx
   path: "C:/Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3"
   fp: 737400:6b01e16a
   ```

   The `path:` line is the machine-wide leg's real proof: not that Setup copied bytes somewhere, but that
   the host read a bundle out of `C:\Program Files\Common Files\VST3` and named it. Take the folder from
   the record, never from where the block sits in the file — the log is written by an asynchronous scanner,
   so a record lands under whichever root line happened to print last, and this one prints under a `custom`
   root while naming the global folder. At 16:22:06 Live rewrote `PluginScanDb.txt` (3,531 rows in the
   2026-11-21 read, 3,537 now) and our two rows are in it: module row
   `1940,"C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3",3,1,ok,"737400:6b01e16a"` — the same
   fingerprint the log wrote — and device row
   `3976,1940,…,"SKEER MIDI VAULT","Skeer Audio","1.1.1","VST 3.7.12",1,1,"Fx",1`. Neither row names the
   second copy on disk, inside the app folder, because that path is outside every root this host scans: the
   duplicate's cost is disk, not a second device. What none of this proves is the thing a producer cares
   about — no instance has been loaded on a track, and recognition is the furthest this machine has evidence for.

   The sentence this replaces read the cache's mtime and concluded no scan had happened. Say plainly that
   it was wrong, because the rule behind it is the trap: the two files have different writers.
   `PluginScanner.txt` is appended per pass by the scanner helper; `PluginScanDb.txt` is rewritten by Live
   proper, on its own schedule. The 05:47:07 scan left the DB stamped 22:14:45 the previous day, and a pass
   that changes nothing logs its roots and writes no `found:` line at all — the 16:22:19 and 16:22:48 root
   lines bracket **0** records between them. So neither file's age answers "did it scan", and
   `scripts/host_scan_check.ps1` now reads both and prints the record it found rather than an inference from
   a timestamp. Install first, then scan — and there are three ways to make a bundle visible
   to this host, only two of which need elevation: the per-user Setup (which puts it in `{app}\VST3`, a
   folder a host has to be pointed at by hand), the same Setup elevated with `/ALLUSERS` (the shared
   scan folder), and copying `launch\VST3\SKEER MIDI VAULT.vst3` into
   `%LOCALAPPDATA%\Programs\Common\VST3` — the user-writable root the census further down proves this
   host already reads, which is the shortest route to a session and the easiest to undo. That third one
   is deliberately not done for you here: it leaves a second copy of the bundle on the machine, and
   retiring or duplicating a plug-in folder is a decision about your rig, not a step in a test plan.
   The paragraph this replaces told the reader to choose which Live to launch, "because a scan belongs to a
   version and this machine has four". It has one. The application is
   `C:\ProgramData\Ableton\Live 12 Suite\Program\Ableton Live 12 Suite.exe`, whose `FileVersion` and
   `ProductVersion` both read `12.3.2`, and that image is running now (pid 42900) — `ProgramData`, worth
   naming because `C:\Program Files\Ableton` holds only a `USB Audio Driver` folder, which is how a reader
   concludes Live is not installed. The `Live 12.x` names under `%APPDATA%\Ableton` are version-stamped
   preference folders left by versions this machine no longer runs: `12.0.10`, `12.1`, `12.3`, `12.3.1`,
   `12.3.2` and `12.3.5`, newest file inside each dated 2024-11-17, 2025-10-23, 2026-01-25, 2026-01-26,
   **2026-11-22 16:22:49** and 2026-11-15, and four of the six carry a `PluginScanDb.txt`. So the cache that
   matters is the one the installed app writes, and that is the one holding us — `12.3.2`, rewritten 16:22:06,
   with one device row carrying the dash-grouped class ID and 753 rows out of the shared root. The session
   therefore needs no rescan and no choice of application, which is what that paragraph should have said.
   What the older folders do teach is how to read `host_scan_check.ps1`: it walks every cache it can find, so
   a `0 rows` verdict about a folder last written in January is not evidence about the install, and whoever
   reads the first verdict line off the log gets the wrong answer. One mismatch is recorded rather than
   resolved: `12.3.5` has a November preference folder while the installed executable is a January build of
   `12.3.2`, and nothing measured here explains a newer-version folder than the application present — it is a
   fact about this machine's history, not about the bundle's placement.
   And when you check from a shell whether the host is even up, match the image
   name exactly: it is `Ableton Live 12 Suite.exe`, and a case-insensitive filter on `ableton` also
   returns `ableton-mcp.exe` — on this machine that bridge was running, pid 13980, while Live was not,
   and the only honest signal was the bridge's own reply: `Could not connect to Ableton. Make sure the
   Remote Script is running.` A process sighting is not the DAW.

   Whether the machine-wide folder is one this host reads is answerable without the DAW, and it was
   worth answering. Live keeps a scan cache, `PluginScanDb.txt`, under
   `%APPDATA%\Ableton\Live <version>\Preferences\`, written when it recognises plug-ins. The one
   this machine's `Live 12.3.2` wrote at 15:49 local on 2026-11-21 holds 3,531 rows. **751** of them name
   `C:\Program Files\Common Files\VST3`, at the root or in a vendor subfolder, and **0** name
   `C:\Program Files\VST3` — the folder 1.1.0's `/ALLUSERS` install used. So the destination this
   release changed was not cosmetic on this host: a bundle in the old folder could not have appeared, and
   a bundle of exactly our shape does appear from the new one. The sibling `SKEER Vault.vst3` is listed there
   by full path as `SKEER Audio`, `1.1.0`, `device:vst3:instr`, sub-categories `Instrument|Instrument|Synth`.
   This paragraph first filed that sibling as category `Fx`, and the correction matters more than the typo:
   the sentence was using that agreement with `moduleinfo.json` as evidence, and an agreement recited from
   memory is not evidence in either direction. What the cache does *not* settle is Q1: recognising a bundle is
   not instantiating one on a track.

   What it does give a session is a baseline you can attribute, produced by a command rather than transcribed.
   `scripts/host_scan_check.ps1` walks every cache on the machine; as run 2026-11-21 20:58 local it read
   **four** caches (`12.3`, `12.3.1`, `12.3.2`, `12.3.5`), each of them 0 rows for `SKEER MIDI VAULT` and 0 rows
   for `C:\Program Files\VST3`, and 751 / 742 / 430 / 430 rows for the shared folder, newest first. Pass
   `-BundleName 'SKEER Vault'` and the same counter returns 2 on the two recent caches and flips its
   verdict — that is the control that makes the zeros a measurement and not a dead filter, which is
   worth stating because this script's first version had exactly that defect and its guard caught it
   by going red on a healthy cache.

   Re-taken 2026-11-22, after the machine-wide install and the scan it provoked, the same four caches read
   0 / 0 / **2** / 0 for us: only the cache of the Live that actually ran knows the bundle, which is the honest
   shape of a per-version cache. In that one, the shared-folder count moved 751 → **753** and the delta is
   attributable row by row — a module row and a device row, both naming
   `C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3`, the module row carrying fingerprint
   `737400:6b01e16a`. Total rows moved 3,531 → 3,537; the other four are not ours to explain. So the first row
   naming `SKEER MIDI VAULT` after an install meant the host found it, and nothing else. Read the count with
   the writer in mind: `PluginScanDb.txt` is rewritten by Live proper, not once per scan pass, so a stale one
   proves only what was true at the previous write — the per-pass witness is `PluginScanner.txt`, and the
   script reads both. That second verdict has been seen to work, which is the only way to know it is a
   verdict: copy the `PluginScanDb.txt`/`PluginScanner.txt` pair into a scratch directory, delete our two
   rows from the copied DB alone (3,537 in, 3,535 out, measured 2026-11-22), and point
   `-CacheFile` at the copy — the row-based verdict becomes
   `no row in this cache, but this host recognised the bundle and wrote it down itself`. Against the
   untouched cache it stays on the row-based text. Nothing in that recipe writes to the real preferences
   folder, and the scratch copy of a person's cache should be deleted once the log is kept. The third
   branch — a pair the machine does not carry at all — was checked with a fabricated code
   (`-VendorCode Zzqq -PluginCode Qqzz`): it prints `no bundle with class ID tail '5a7a717151717a7a' is on
   disk under these roots` and exits **0**, because the exit code owns the duplicate question and not the
   installed one. That run also corroborates the denominator above from the other side: the script's own
   counter reads 1,416 device rows in the `12.3.2` cache and 1,407 in `12.3.5`.

   Whoever re-takes these counts needs one warning about separators. The host writes paths mixed — the
   scanner log names our bundle `C:/Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3`, a slash after the
   drive and backslashes after that — so a backslash needle typed as a literal will not match every row, and a
   pattern that loses a backslash level through a shell here-string turns `\vst3` into a vertical tab and
   reports **0** against 753 rows that are plainly in the file. Normalise separators before comparing, then
   case-fold. Learned by getting a zero here on 2026-11-22 and believing the file rather than the pattern.

   That script also censuses, and the census is the part that earned its keep. It prints every distinct
   VST3 root a cache names and whether that folder still exists, not merely the folders the script was
   written to look for — because a needle list can only confirm what its author already suspected. Run at
   21:11 local on 2026-11-21, the two recent caches each name **three** roots and the needles covered one
   of them: `C:\Program Files\Common Files\VST3` (751 rows in `12.3.2`, 742 in `12.3.5`), a `K:\` folder
   holding a mounted backup of some other product's `Program Files` tree (1 row, present on disk), and
   `C:\Users\Sebastien\AppData\Local\Programs\Common\VST3` — 2 rows in `12.3.2` and 4 in `12.3.5`, all
   `ok`, and the `12.3.5` set includes `SKEER Vault.vst3` and `Expressive Drum.vst3` by full path. That
   third root is the per-user VST3 folder: no elevation to write it, no admin to read it, and this host
   has demonstrably enumerated bundles out of it. So "a per-user install has to be pointed at by hand" is
   a fact about where *our* Setup puts the bundle (`{app}\VST3`), not about what this host scans — and the
   machine-wide placement this release fixed has a per-user counterpart that was never the wrong folder,
   just a private one. It is recorded as a numbered step in `docs/next-steps-2026-11.md` rather than
   changed here, because it moves a shipped installer and would need the certification run again.

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
   one migration adds is `files.fingerprint_version` (`midivault/db.py`, `_migrate_schema_1_to_2`), and that name
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
   `plugin/CMakeLists.txt:121` so the filter box can receive keystrokes, which also means the host's
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
