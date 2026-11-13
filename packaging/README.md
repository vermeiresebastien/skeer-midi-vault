# Packaging and distribution

The installed application is self-contained. End users do **not** need Python,
Node.js, a terminal, or this repository. The build includes the Python runtime,
the service, the compiled interface and all visual assets.

## Outputs

Built into `dist-installer/`:

- `SKEER-MIDI-VAULT-Setup-1.0.0.exe` — per-user Windows installer (recommended
  file to send to customers)
- `SKEER-MIDI-VAULT-Portable-1.0.0.zip` — extract-and-run portable build
- `SHA256SUMS.txt` — checksums for release publishing

The installed app:

- installs under `%LOCALAPPDATA%\Programs\SKEER MIDI VAULT`
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

Inno Setup 6 is required for the installer. Install it from
<https://jrsoftware.org/isinfo.php> or set `INNO_SETUP_ISCC` to `ISCC.exe`.

```powershell
# rebuild the interface, application and installer; regenerate checksums
.\packaging\build_installer.ps1
```

The Inno script can also be compiled directly:

```powershell
iscc packaging\skeer-midi-vault.iss
```

Build dependencies live in `packaging/requirements-build.txt`. The runtime
application itself still has zero third-party Python dependencies.

## Test the installed build

```powershell
# packaged executable: health → scan → process-pool workers → quit
python tests\test_packaged_smoke.py
```

For an installed test copy, point the test at the installed executable and use a
temporary data directory. The smoke test verifies:

- the local service starts and answers `/api/health`
- the frozen Python service can index the demo library using process workers
- no `--multiprocessing-fork` worker processes survive app exit
- `/api/app/quit` cleanly exits the tray/service process

### Installer verification note

The packaged application (`dist/SKEER MIDI VAULT/`) and the portable ZIP are
fully exercised by `tests/test_packaged_smoke.py`. The Inno setup EXE compiles
successfully, but a complete interactive install → shortcut → uninstall cycle was
not run inside this sandboxed build session: the setup process token is denied
writes to `HKCU` and the user Start Menu, and Inno's own minimal test installer
fails the same way in that environment. Before sending the Setup file to
customers, run it once on a normal user desktop to confirm shortcut creation,
first launch, the tray icon and the uninstaller.

## Code signing and SmartScreen

The installer is currently **unsigned**. Windows SmartScreen may warn recipients
until the file builds reputation, and the Windows version information/icon are
set but not cryptographically signed.

For commercial distribution, sign both the application executable and the
installer with an Authenticode code-signing certificate. The exact certificate
and timestamping vendor are the seller's choice; a typical command shape is:

```powershell
signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 /a "dist\SKEER MIDI VAULT\SKEER MIDI VAULT.exe"
signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 /a "dist-installer\SKEER-MIDI-VAULT-Setup-1.0.0.exe"
```

Re-run the installer build after signing the executable if you sign before
Inno compiles, because the signed executable bytes are included in the payload.
Signing is not performed by the included build script.

## What not to ship

Do not ship the `build/`, `dist-debug/`, `tests/`, `.git/` or source tree to
customers. Ship only the setup executable or portable ZIP from `dist-installer/`.

## Versioning

When changing the application version, update:

- `midivault/__init__.py`
- `packaging/skeer-midi-vault.iss` (`AppVersion` and `VersionInfoVersion`)
- `build/version_info.txt`
- `desktop.py` (`VERSION`, for the runtime file/log)

The application version is also shown in **Settings → About**.

## Legal

`packaging/EULA.txt` is a supplied template. Review it with counsel and replace
publisher/contact/governing-law details before selling. The installer shows this
EULA before installation.
