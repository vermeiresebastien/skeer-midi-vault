# SKEER MIDI VAULT — agent instructions

Local-first MIDI library and audition tool: a Python 3.12 stdlib HTTP service
(loopback only) plus a React 19 + TypeScript/Vite interface, indexed in SQLite.
Version 1.0.0.

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
- `SKEER-MIDI-VAULT-Setup-1.0.0.exe`, `SKEER-MIDI-VAULT-Portable-1.0.0.zip`,
  `SHA256SUMS.txt`

Rules:

- `launch/` is **fully gitignored** — nothing inside it is ever tracked.
- The bundle is **removed before being rewritten** so a stale file cannot survive
  a build ([packaging/build_installer.ps1:31](packaging/build_installer.ps1)).
- Verify `launch/` holds freshly timestamped binaries before reporting a build done.
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
python -m unittest discover -s tests    # 55 tests, ~12s; framework is unittest, NOT pytest
python scripts/evaluate_classification.py
node tests/e2e-web.mjs                  # needs playwright-core (in web/node_modules) + CHROME_PATH
```

There is **no lint command** — no ruff/black/mypy config, no ESLint config. Do not
invent one unprompted. Tests isolate in `tempfile` directories; they never touch
`%LOCALAPPDATA%`.

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
  in [midivault/engine/versions.py](midivault/engine/versions.py) when parse output
  semantics or classification rules change.
- **Loopback-only:** [midivault/server.py:50](midivault/server.py) refuses to bind
  outside `127.0.0.1`/`localhost`/`::1`; CORS echoes only loopback origins
  ([midivault/api.py:97](midivault/api.py)). No telemetry, accounts or cloud calls.
- **Honesty in labels:** accuracy claims are regression results on self-authored
  synthetic fixtures, never claims about real-world MIDI. Genre stays a low-confidence
  hint. See [docs/limitations.md](docs/limitations.md).

## Version bumps need all five

`midivault/__init__.py` · `packaging/skeer-midi-vault.iss` (`AppVersion`,
`VersionInfoVersion`) · `build/version_info.txt` · `desktop.py` (`VERSION`) ·
`web/package.json` (`version`).

`midivault/__init__.py` is the only one the interface can see: `/api/bootstrap`
publishes it as `app.version`, which Settings → About and
`window.__SKEER_MIDIVAULT_DEBUG__.version` both read. Never hardcode a version
string in `web/src/`.

## Docs drift — verified against the tree

- `web/package.json` `screenshots` points at a missing `tests/screenshots.mjs`;
  capture lives inside `tests/e2e-web.mjs`.
- `npm --prefix web test` runs `vitest`, which is not a dependency and matches no
  files — there are no frontend unit tests.

Check a documented path against the real tree before acting on it.
