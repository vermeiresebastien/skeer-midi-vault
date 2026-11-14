# SKEER MIDI VAULT — application architecture

Status: implemented in this workspace (version 1.0.0). This document records the
architecture proposal derived from the two existing SKEER-family codebases and
the decisions that were actually shipped.

## 1. What was inspected

### VRAC+ (web + native), `D:\Projects\skeer-audio\vrac-plus`

VRAC+ is the closest precedent for a **local browser application** in the family:

- `src/App.tsx` is a thin shell; instrument state lives in `src/state/useKit.ts`,
  audio lives in `src/audio/`, and visual tokens live in `src/styles.css` plus
  `src/css/`.
- The AudioWorklet renders the audio graph and the React tree never schedules
  individual audio events from render code. That separation is the important
  precedent for MIDI Vault's preview scheduler.
- The web build is a Vite/React/TypeScript static bundle and the native build is
  a JUCE VST3/standalone app. Both are packaged independently of the browser UI.
- The project keeps reusable, deterministic generators (`sampleLibrary.ts`,
  `slicer.ts`) outside React components, and tests them directly.

### REDRUM / Expressive Drum, `D:\Projects\vst-plugins\redrum`

REDRUM is the current SKEER visual reference:

- `Source/UI/Theme.h` defines the exact palette (`#F5F2EB`, `#FCFAF6`,
  `#E7E2D8`, `#292821`, `#716C63`, `#FF6500`, `#00CC66`, `#D9382E`) and the IBM
  Plex Sans / IBM Plex Mono split.
- `Source/UI/FlatLookAndFeel.h`, `Knob.cpp`, `PadGrid.cpp` and
  `SmallComponents.h` show the shared visual grammar: ivory paper, paper-white
  panels, pale-stone secondary surfaces, hairline warm-gray borders, one orange
  primary action and a green activity state.
- The supplied reference pack (`dist/SKEER BRAND ASSETS/`) establishes the
  Studio Clean / Studio Tactile treatments, the appearance panel's control set
  (pad finish, knob finish, panel contrast, border strength, meter color,
  reduced motion) and the approved logo.
- The engine (`Source/Engine/`) is a framework-independent static library with
  tests and a render tool. The editor is the only place that knows about JUCE
  UI. That is exactly the separation MIDI Vault needs between its index/analysis
  engine and any future SKEER host integration.

The reference mockups were used for identity and interaction patterns only. No
audio, presets, samples or proprietary code from VRAC+, REDRUM or any commercial
product is copied into this application. All MIDI fixtures, preview sounds and
analysis rules here are generated for this project.

## 2. Chosen application shape

MIDI Vault is delivered as a **local, offline-first desktop web application**:

```
┌──────────────────────────────────────────────────────────────┐
│ React + TypeScript UI (Vite)                                 │
│  library shell · search · piano roll · Web Audio preview     │
│  Web MIDI output · settings · scan dialogs                   │
└─────────────────────────────┬────────────────────────────────┘
                              │ loopback HTTP + JSON (127.0.0.1)
┌─────────────────────────────▼────────────────────────────────┐
│ Python 3.12 local service (standard library only)            │
│  HTTP API · static bundle host · Range streaming             │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼──────────────┐
│ SkeerMidiVault engine        │  │ SQLite index              │
│  parser · analysis · rules   │  │ WAL · FTS5 · migrations   │
│  classifier · duplicates     │  │ user data + auto cache    │
└───────────────┬──────────────┘  └───────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│ Background scanner                                           │
│  directory traversal thread                                  │
│  bounded process pool for parse + classify                   │
│  pause / resume / cancel / incremental state                 │
└──────────────────────────────────────────────────────────────┘
```

Why not a native JUCE app:

- A MIDI library's hard parts are metadata search, a variable-size table,
  text input, a piano-roll timeline and file-system indexing, not real-time
  audio. Those are much faster to do correctly in the web stack already used by
  VRAC+.
- Browser Web Audio is sufficient for audition previews, and Web MIDI gives
  optional hardware/virtual-port output without a driver.
- The engine is a standalone Python package. It is deliberately not part of the
  HTTP layer, so a future SKEER native host, CLI or local model can import the
  same parser/classifier. The API is a replaceable adapter.

Why not Electron/Tauri:

- The existing SKEER family already ships a local web edition pattern.
- A plain Python service is small, auditable and does not need native packaging
  for this first version. `start.bat`/`start.ps1` are the complete install step.
- SQLite gives durable single-file backup and recovery for free.

## 3. Repository layout

```
midivault/
  engine/
    __init__.py
    smf_parser.py        SMF 0/1/2 parser, running status, tempo/SMPTE, sustain
    analytics.py         note statistics, grid, polyphony, key estimation
    classifier.py        instrument/role/style rules, confidence, evidence
    duplicates.py        exact + similarity grouping
    model.py             immutable dataclasses shared by parser/classifier
    versions.py          PARSER_VERSION / CLASSIFIER_VERSION / RULESET
  db.py                  schema, migrations, FTS5, all SQL
  scanner.py             scan controller and background workers
  pipeline.py            worker-side parse → analyse → classify, cache payload
  api.py                 loopback JSON/HTTP routes, MIDI streaming
  server.py              entry point, static bundle host
  platform.py            drives, protected folders, reparse/cloud flags
web/
  src/                   React UI
  src/audio/             preview synth, lookahead scheduler, MIDI output
  public/brand/          approved SKEER artwork and cropped derivatives
desktop.py               standalone launcher: server + browser + tray + single instance
packaging/               PyInstaller/Inno build script, installer script, EULA
scripts/                 demo library generator, evaluation, benchmark, brand assets
tests/                   Python unit + integration + fixture + browser tests
docs/                    architecture, test report, limits, screenshots
launch/                  standalone bundle / Setup.exe / portable ZIP / checksums
```

The engine has no import from `db`, `scanner`, `api` or `web`. It receives bytes
and returns plain dataclasses/dicts. The UI has no knowledge of file-system
paths beyond the paths the API exposes. That boundary is enforced by tests.

## 4. Storage model

SQLite in WAL mode, one writer at a time, short transactions:

| Table | Purpose |
| --- | --- |
| `sources` | drives/folders, optional flags, availability, last seen |
| `excludes` | user-excluded subtrees |
| `scan_runs`, `scan_issues` | durable scan history and failures |
| `directories` | folder browsing and counts |
| `files` | path, size, mtime, hash, parser/classifier versions, scan state, auto + effective labels, musical summary |
| `tracks` | per-sequence/channel logical tracks, auto + effective labels |
| `file_corrections`, `track_corrections` | user accepted/corrected labels |
| `predictions` | immutable audit of auto predictions by classifier version |
| `collections`, `collection_files` | custom collections |
| `tags`, `file_tags` | user tags |
| `favorites` | represented by `files.favorite` (simple and filterable) |
| `duplicate_groups`, `duplicate_members` | exact and similar groups |
| `files_fts` | FTS5 search over names, paths, track names, tags, notes, text |
| `settings` | scanner/service preferences |
| `meta` | schema and engine versions |

Source files are never written. The default database lives at
`%LOCALAPPDATA%\Skeer\MIDI Vault\midivault.sqlite3` (override with `--data-dir` or
`SKEER_MIDIVAULT_DATA`), deliberately on the user application-data drive because
SQLite WAL writes are frequent during a scan. `user_*` corrections, collections,
tags, favorites and notes are independent of the parser cache, so a version bump,
rescan or index rebuild does not erase them. The database can be backed up with
SQLite's online backup API while the app is open.

## 5. Scanning and analysis pipeline

1. The scanner validates explicitly enabled sources and resolves exclusions.
2. A traversal thread walks directories with `os.scandir`, does not follow
   symbolic links or reparse points, skips protected locations and skips cloud
   placeholders via Windows file attributes. It never opens an archive.
3. Every discovered `.mid`/`.midi` file is compared against the existing index
   using size, mtime, parser version and classifier version. Unchanged files are
   skipped in incremental mode.
4. Changed/new files are hashed and handed to a bounded process pool. Worker
   processes parse, analyse and classify without touching SQLite or the UI.
5. The coordinator writes committed results in small batches (up to 24 completed
   files or about 650 ms of work), using one SQLite transaction per batch and
   per-item savepoints. This keeps slow/mechanical drives from paying one fsync
   per file. Failures become durable `failed` rows with an error message and
   never stop the scan.
6. At finalisation, exact duplicates (content hash) and practical similarity
   groups are recomputed and scan counters are recorded. The final duplicate pass
   can take longer than parsing on a large synthetic corpus; progress remains
   visible in the scan footer.

Pause stops new work at a safe checkpoint; in-flight items are allowed to finish
(in-flight work is never half-written). Cancel stops new work and shuts the pool
down. Rows are only committed after a complete parse, so an interrupted scan
leaves earlier results intact and simply resumes on the next incremental scan.
Unavailable sources are remembered as unavailable; indexed entries are not
deleted. On application quit the desktop launcher cancels an active scan and waits
for the worker pool to shut down before the process exits, preventing orphaned
multiprocessing workers.

## 6. Classification contract

Two primary dimensions are stored per file and per logical track:

- sound family: Drums/percussion, Bass, Piano/keys, Guitar/plucked, Strings,
  Brass/woodwinds, Synth, Mixed arrangement, Unknown;
- musical role: Drum groove, Drum fill, Bassline, Chord progression,
  Lead/melody, Arpeggio, Pad/sustained harmony, Complete song/multi-part
  arrangement, Exercise/technical pattern, Unknown.

Each prediction records:

```
predicted_category
confidence             0..1, calibrated with support and conflict caps
evidence[]             {source, label, weight, kind: embedded|calculated|filename|conflict}
alternatives[]
method + ruleset version
user_state              null | accepted | corrected
```

Automatic predictions live in `files`/`tracks`/`predictions`. Effective labels
are denormalised for fast search and only replaced by rescans when the user has
not touched that dimension. User corrections persist separately and can be
reverted to the latest automatic prediction. Feel tags (straight/swung/sparse/
dense/syncopated) are optional observed tags; genre is a clearly labelled,
low-confidence style hint (never a hard category).

## 7. Preview boundary

- Parsed notes are cached in SQLite as compact JSON, so opening a file does not
  re-read or re-parse disk.
- The scheduler is a pure TypeScript lookahead scheduler with an injectable
  clock. It owns note-on/off timing and can drive either Web Audio or Web MIDI.
- Rendering (piano roll, playhead, meters) is downstream of the scheduler and
  never determines note timing.
- Stop, file switch, track change and output-device change call an explicit
  all-notes-off path. Preview timbres are labelled as audition sounds, not a
  reproduction of the file's original instruments.

## 8. Identity implementation

The React design system uses the exact SKEER tokens from `Theme.h`. Studio Clean
and Studio Tactile are two token sets over the same components. Appearance
options write CSS custom properties on the app root; they do not fork component
code. The approved logo is used from
`web/public/brand/skeer-wordmark.png` (cropped from the supplied ivory artwork).
No unapproved restyling of the mark is performed.

## 9. Verification plan

- Parser unit tests: formats 0/1/2, tempo maps, SMPTE division, running status,
  sustain, overlapping notes, malformed chunks, missing end-of-track.
- Scanner integration: exclusions, protected paths, junction loop, corrupt file,
  interrupted scan, unavailable drive, incremental rescan.
- Classification evaluation on a hand-labelled fixture set, instrument and role
  reported separately.
- UI browser tests: initial empty state, scan flow, search/filter, edit and
  persistence, playback, piano-roll drag/scrubbing, format-2 sequences, export,
  both skins and appearance controls.
- A separate playback stability probe runs transport and scheduler telemetry while
  a scan and search/filter work are active.
- Packaged-build smoke test: frozen app health, process-worker scan, clean quit and
  no orphan worker processes.
- Benchmarks on documented hardware and generated library.
- Screenshots of both skins and the appearance/scan dialogs.
