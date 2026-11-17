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
- creates Start Menu and optionally Desktop shortcuts
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

**As measured on 2026-11-17, from the agent shell:** the payload is proven and the registration is
not. Setup installed all 198 files `launch/` holds — nothing missing, nothing extra, including
`_internal\buildinfo\BUILDINFO.json`, `_internal\web\dist\index.html` and both files of the VST3
bundle that carry the version a host lists — and then rolled the tree back because writing the
next thing an installer must write was refused to it: first
`%LOCALAPPDATA%\SKEER MIDI VAULT cycle`, then
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\SKEER AUDIO`, and in a control build of Inno's own
minimal script `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall`. That is the shell's
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

**Still unverified, and only you can verify it:** the Add/Remove Programs entry, the Start Menu and
optional desktop shortcut, the first launch of the installed executable with its tray icon, the
EULA page as Setup shows it, and that the uninstaller leaves the machine as it found it. Run the
first command above from a normal user terminal — Setup and the uninstaller both write the
registry and the user profile, which this agent's shell is not permitted to do on your behalf — and
paste the last line back. `build\work\install-cycle-<utc>\` keeps the Setup logs, the before/after
census and the installed-smoke transcript that go with whatever it reports.

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
row names the cause in the words the stage itself used ("2 unfilled field(s):
`<<<FILL: contact>>> <<<FILL: jurisdiction>>>`"), not just an exit number.

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
state in which these artifacts should be published. Both of the remaining reds are therefore about
work that is not this machine's to finish: filling in the licence, and running the cycle from a
normal user terminal.

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

Two fields are deliberately left unfinished so they cannot ship by accident:

```
Licence and support enquiries: <<<FILL: contact>>>
... governed by the law of <<<FILL: jurisdiction>>>
```

`<<<FILL:` is a placeholder, not a comment: fill both before a customer sees the licence page,
and the release check refuses to certify a build while either token is still in the file. The
version line in §6 is a checked literal — `scripts/check_version_consistency.py` reads it, so a
bump that misses the licence page fails the gate instead of shipping an installer whose licence
names last release.

The installer shows this EULA before installation, and accepting it is what enables Install.
