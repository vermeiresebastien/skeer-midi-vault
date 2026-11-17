# SKEER MIDI VAULT — agent instructions

Local-first MIDI library and audition tool: a Python 3.12 stdlib HTTP service
(loopback only) plus a React 19 + TypeScript/Vite interface, indexed in SQLite.
Version 1.1.0.

## Deliverables: `launch/` is the one place to build and run from

Every build exports all deliverables into `launch/` at the repo root. Never make
the user hunt through `dist/` or `dist-installer/` for what to run.

```powershell
.\packaging\build_installer.ps1     # rebuilds web/dist, app bundle, installer, zip, checksums -> launch/
```

`launch/` holds:

- `SKEER MIDI VAULT/` — the standalone app. `SKEER MIDI VAULT.exe` only runs with
  its sibling `_internal/` (Python runtime + `web/dist`) beside it: **onedir, not
  onefile.** Do not switch to `--onefile`; each multiprocessing scan worker would
  re-extract ~50 MB to `%TEMP%`.
- `SKEER-MIDI-VAULT-Setup-1.1.0.exe`, `SKEER-MIDI-VAULT-Portable-1.1.0.zip`,
  `SHA256SUMS.txt`
- `VST3/SKEER MIDI VAULT.vst3` — the staged plug-in bundle the installer and the
  ZIP both carry. `build_installer.ps1` refuses to ship it if its
  `moduleinfo.json` disagrees with the release, and passes `/DPluginStaged` to Inno
  only when it really staged one; `-SkipPlugin` makes an installer with no plug-in
  rather than an ISCC error about a missing `Source`.

Rules:

- `launch/` is **fully gitignored** — nothing inside it is ever tracked.
- The bundle is **removed before being rewritten** so a stale file cannot survive
  a build ([packaging/build_installer.ps1:160](packaging/build_installer.ps1)), and
  the staged plug-in bundle is removed the same way at line 210.
- Verify `launch/` holds freshly timestamped binaries before reporting a build done.
- The Setup is **per-user by default**: `{autopf}` is `%LOCALAPPDATA%\Programs` and
  the plug-in goes to `{app}\VST3`, which a host has to be pointed at by hand. Only
  Setup run with `/ALLUSERS` in admin mode also writes
  `C:\Program Files\Common Files\VST3`, where every host looks by default.
  `[Code] function CommonVst3` logs which of the two happened, so the Setup log —
  not the README — says where the bundle landed.
- An Inno `[Code]` section comment must be `//` or `{ }`. A `;` there is not a
  comment, it is a syntax error (`'BEGIN' expected`), because the section is handed
  to the script compiler instead of being read as an ini-style list. Measured on
  Inno Setup 6.7.4.
- `distpath` is a CLI option, not a spec setting: building from the root
  `SKEER MIDI VAULT.spec` by hand needs `--distpath launch`.
- `dist/` and `dist-installer/` are the superseded locations, kept ignored only so
  pre-existing copies stay out of `git status`.
- [tests/test_packaged_smoke.py:22](tests/test_packaged_smoke.py) launches
  `launch\SKEER MIDI VAULT\SKEER MIDI VAULT.exe` by default; `SKEER_PACKAGED_EXE`
  overrides it.

## Commands

```powershell
python -m midivault.server --open       # run from source; serves web/dist on 127.0.0.1:8737
.\start.ps1                             # builds web/dist if stale, then launches
npm --prefix web ci                     # frontend deps only; the Python app has ZERO runtime deps
npm --prefix web run dev                # Vite :5173, proxies /api -> :8737
npm --prefix web run build              # tsc --noEmit && vite build — this is also the only typecheck
python -m unittest discover -s tests    # 104 tests, ~22s; framework is unittest, NOT pytest
powershell -File plugin/build.ps1       # VST3 + 6 headless suites (locator, index, midi source, emit, editor, host)
powershell -File plugin/build.ps1 -BuildDir build/tag-808 -Juce D:/Projects/skeer-audio/pulsekit/build/_deps/juce-src   # 8.0.8 tree
python scripts/evaluate_classification.py
node tests/e2e-web.mjs                  # needs playwright-core (in web/node_modules) + CHROME_PATH
node tests/autoplay-deck.mjs            # drives the real UI: autoplay deck, bounded run, durable selection
node tests/playback-stability.mjs       # drift/telemetry under a concurrent 1500-file scan
node tests/midi-output-guard.mjs        # fake requestMIDIAccess: refused send, disconnect, unload release
node tests/space-activation.mjs         # Space reaches the focused control, not the transport
node tests/deck-broken-row.mjs          # the deck walks past a row whose details/preview are empty
node tests/scan-settings.mjs            # Settings → Scanning re-hash guard: PATCH, reload, re-arm
powershell -File scripts/release_check.ps1              # the release gate; exit 0 READY / 1 NOT READY / 2 INCOMPLETE
powershell -File scripts/release_check.ps1 -Fast        # gate, suite, licence, checksums only
python scripts/check_release_gate.py    # falsifies that gate and the build script: 33 cases on a copied tree
powershell -File packaging/install_cycle_check.ps1      # Setup → run installed exe → uninstall, compared to before
```

`scripts/release_check.ps1` is the one command whose exit code means "ship it": it
owns eleven stages (`gate, suite, web, plugin, plugin808, installer, stamp, smoke,
checksums, licence, installed`), writes one log per stage under
`build\work\release-check-<utc>\`, and never reports READY on a stage it skipped.
`scripts/check_release_gate.py` is its falsifier — it copies the real files into
`build\work\release-gate-falsifier\`, stubs the child commands, and requires each
defect to redden the stage that names it, with a green control case that reaches
READY. Run it after touching either script: a gate nobody has seen go red is not
known to be a gate. `packaging\install_cycle_check.ps1` is destructive by design and
refuses before touching anything if the app is running or already registered; read
[packaging/README.md](packaging/README.md) for what it proves and what a restricted
shell cannot let it finish.

`tests/midi-output-guard.mjs`, `space-activation.mjs`, `deck-broken-row.mjs` and
`scan-settings.mjs` need no service: `tests/app-harness.mjs` serves the real
`web/dist` with every `/api` call answered from fixtures, so the React app under
test is the shipped one while the user's index stays untouched. The same four were
each re-run against a detached `git worktree` at HEAD — point `SKEER_ENGINE_TS` at
the pre-fix `engine.ts`, or `SKEER_DIST` at a pre-fix build, and the checks fail
there. Keep that property: a fix landing without its check failing on HEAD is not
verified.

`plugin/build.ps1` is the plug-in lane and the only command that needs a compiler: it
configures, builds and runs six C++ suites — `vault-locator-test` (where the index
is), `vault-index-test` (reading it without writing to it), `vault-midi-test` (the
source bytes), `vault-emit-test` (a clip on the host's clock), `vault-editor-test` (the
panel a producer touches) and `vault-host-test` (loading the bundle the way a DAW does,
and emitting through that wrapper) — then `ctest`. It writes into
`plugin/build/` and installs nothing. The default JUCE is skulpt's local checkout at
8.0.4 while `plugin/CMakeLists.txt` asks FetchContent for 8.0.8, so run both lines
above and require both green: the modules differed between those tags once already
(`MidiMessageSequence::size` became `getNumEvents`). The second tree needs its own
build directory — reconfiguring one tree with the other's JUCE fails inside
`juceaide` — which is what `-BuildDir build/tag-808` is for.

The plug-in has a real editor (`plugin/Source/VaultEditor.cpp`): one column with a
filter box, the library list, the three exported controls always visible, and a status
strip that says which file is playing and which one the project asked for. `createEditor()`
returns it and `hasEditor()` is true. Two things about it are rules, not details: the
index is touched **only** after an explicit Connect click — building the panel opens
nothing — and every query opens its own read-only connection and closes it before
returning, so no handle on the user's library outlives a click and none can be standing
in the way of a host-driven state restore. SQLite is never queried from `processBlock`,
and a clip becomes playing only through `VaultMIDIProcessor::loadFile()`.

Three more are rules the last review round wrote down, and a change that breaks any of
them should be argued with that review, not silently rewritten: a query that **fails**
keeps the index path and says "not read this time" — only an explicit Disconnect forgets
it, so the strip must never collapse "could not read" into "not connected"; the replace
prompt on "Save clip as..." is the **OS's** (`saveChooserFlags()` sets
`warnAboutOverwriting`), so no in-house `AlertWindow` is stacked on top of it — JUCE's
non-native alert numbers its first button **1**, and a confirm box here is a gate nobody
can drive headless; and a 0-byte source is refused before anything is written, because
`File::replaceWithData` turns a zero-length write into a delete. `handleChosenTarget()` is
the dialog-free seam the chooser's callback and the suite both call; do not move the
refusals back into `saveClipAs()`, where nothing can reach them.
`vault-editor-test` drives that widget tree headless — no window, no peer, no desktop,
no stolen focus — which means it has to pump a message loop for the filter box, because
`juce::TextEditor` posts its change notification rather than calling it inline.

There is **no lint command** — no ruff/black/mypy config, no ESLint config. Do not
invent one unprompted. Tests isolate in `tempfile` directories; they never touch
`%LOCALAPPDATA%`. Every harness that writes must authenticate: the three
service-backed browser harnesses share `tests/api-client.mjs`, and
`tests/test_packaged_smoke.py` fetches
the token the same way in Python — both call `GET /api/session` and echo
`X-SKEER-Token` on every write, so a harness that posts without it gets 403, the
same as a foreign page. `test_packaged_smoke.py` is a standalone script, not a
`unittest` module: it collects zero tests, so `python -m unittest discover -s tests`
never runs it. Two commands do: `scripts/release_check.ps1` runs it against
`launch\SKEER MIDI VAULT\`, and `packaging\install_cycle_check.ps1` runs it again
against the **installed** executable through `SKEER_PACKAGED_EXE`, because the
bundle beside `launch/` is not the artifact a user ends up running. Its shutdown
prints an `OSError: [WinError 10038]` traceback from the frozen HTTP thread — a
known race between the quit path and the socket close, printed on an otherwise
passing run; do not "fix" it by deleting the print. SQLite suites open their temp dir with
`ignore_cleanup_errors=True`: Windows can hold a just-closed WAL file for a beat
and fail `tearDown` on a run where every assertion passed — ~1 suite in 6 before
that, and the flake is in the harness, not the code.

## Non-negotiables

- **Engine purity:** `midivault/engine/` must not import `db`, `api`, `scanner` or
  know about SQLite. It takes bytes, returns dataclasses, so future SKEER tools can
  reuse it. Grep-verified today; keep it that way.
- **Never write to a source MIDI file.** No rename, move, delete, edit or archive
  extraction anywhere in the product.
- **User data survives reprocessing.** Manual corrections, favorites, tags, notes
  and collections live in their own tables and must not be overwritten by a rescan,
  classifier bump or index rebuild.
- **Cache invalidation is versioned:** bump `PARSER_VERSION` / `CLASSIFIER_VERSION`
  / `FINGERPRINT_VERSION` in [midivault/engine/versions.py](midivault/engine/versions.py)
  when parse output semantics, classification rules, or the similarity vector change.
  A fingerprint from another generation is skipped by similarity, never compared.
- **Schema changes migrate:** bump `SCHEMA_VERSION` and add the step to `MIGRATIONS`
  in [midivault/db.py](midivault/db.py) (keyed by the version it comes *from*).
  Opening an index runs the version-gated steps, backs the old index up first, and
  refuses a newer index rather than downgrading it — see `tests/test_schema_migration.py`.
  Anything that needs the finished column set goes in `POST_SCHEMA_SQL`, not `SCHEMA_SQL`.
- **Loopback-only:** `midivault/server.py` refuses to bind outside
  `127.0.0.1`/`localhost`/`::1`; CORS echoes only loopback origins. On top of that,
  every request is rejected unless its `Host` names loopback (`_host_is_allowed`,
  which is what defeats DNS rebinding), writes need the session token
  (`X-SKEER-Token`, issued by `GET /api/session`, enforced when a launcher passes
  `session_token`), and a JSON body must actually be `application/json`. Do not
  loosen these in `api.py` — `tests/test_http_boundary.py` simulates the attacks.
  No telemetry, accounts or cloud calls.
- **Honesty in labels:** accuracy claims are regression results on self-authored
  synthetic fixtures, never claims about real-world MIDI. Genre stays a low-confidence
  hint. See [docs/limitations.md](docs/limitations.md).

## Version bumps: seven files with a literal, one with an absence

`midivault/__init__.py` · `packaging/skeer-midi-vault.iss` (`AppVersion`,
`VersionInfoVersion`) · `build/version_info.txt` (`filevers`, `prodvers`,
`FileVersion`, `ProductVersion`) · `desktop.py` (`VERSION`) ·
`web/package.json` (`version`) · `plugin/CMakeLists.txt` (`project(... VERSION)`) ·
`packaging/EULA.txt` (the "This version is X.Y.Z." line the licence page shows) —
eleven values in all, plus `packaging/build_installer.ps1` probed for the *absence* of
one. Measured 2026-11-17 at 1.1.0: the checker prints `8 files, 11 values, one version
1.1.0.`

`midivault/__init__.py` is the only one the interface can see: `/api/bootstrap`
publishes it as `app.version`, which Settings → About and
`window.__SKEER_MIDIVAULT_DEBUG__.version` both read. Never hardcode a version
string in `web/src/`.

The plug-in literal is load-bearing, not a build artifact: CMake writes
`plugin/CMakeLists.txt`'s `project(... VERSION)` into the built bundle's
`moduleinfo.json` and into the binary, and that is the number a host lists the
plug-in by. A 1.0.1 app beside a plug-in still saying 1.0.0 is two products
claiming one release. `packaging/build_installer.ps1` reads the version from
`midivault/__init__.py` and is itself probed for *not* carrying a literal, because a
second home for the number is how a partial bump produced a ZIP named for the old
version, an installer named for the new one, and an empty `SHA256SUMS.txt` with exit
code 0.

`python scripts/check_version_consistency.py` prints the file:line, literal and value
for every one of those, and exits non-zero on any disagreement;
`tests/test_version_consistency.py` runs it, so `python -m unittest discover -s tests`
fails on a half-done bump. That test also runs the checker against a bumped copy in a
temp directory and requires it to fail, because a gate nobody has seen go red is not
known to be a gate. The script's own output -- not this list -- is the authority on
which literals are probed.

## Docs drift — verified against the tree

- `web/package.json` `screenshots` points at a missing `tests/screenshots.mjs`;
  capture lives inside `tests/e2e-web.mjs`.
- `npm --prefix web test` runs `vitest`, which *is* a declared and installed
  devDependency (`^5.0.5`) — measured 2026-11-17 it exits 1 with `No test files
  found`, because no `src/**/*.test.ts` spec exists. There are no frontend unit
  tests; frontend verification is the browser harnesses under `tests/`.

Check a documented path against the real tree before acting on it.
