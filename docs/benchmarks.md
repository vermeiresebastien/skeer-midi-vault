# Scan, search and playback benchmarks

Machine-readable results:

- [`benchmark-results.json`](benchmark-results.json)
- [`playback-stability.json`](playback-stability.json)

## Machine

| Item | Value |
| --- | --- |
| CPU | AMD Ryzen 9 3900X 12-Core (24 logical cores) |
| RAM | 63.9 GB |
| OS | Windows 10 22H2 (build 19045) |
| Python | 3.12.10 |
| Node | 24.19.0 |
| Browser | installed Google Chrome, headless |
| Storage | System temp / NTFS (fast local SSD) |

The same machine is used by the classification evaluation and browser tests. The
project folder can be on a slower drive; benchmark data and the SQLite database
were deliberately placed on the fast local system drive, which is also the default
location for the real database (`%LOCALAPPDATA%`).

## Scan benchmark method

`scripts/benchmark.py --files 1000 --workers 2`:

1. Generates 1,000 deterministic 3-track MIDI files (drums, bass, Rhodes chords;
   four bars each; ~913 bytes per file) in 20 folders under the system temp
   directory.
2. Creates a fresh SQLite database.
3. Runs a full scan with the **process** executor, Balanced intensity, two workers.
4. Runs an incremental rescan without changing any file.
5. Times 120 iterations of four search queries directly through the database API.
6. Samples the whole process tree's resident set every 200 ms during the scan.

## Scan result

| Metric | Value |
| --- | --- |
| Files | 1,000 |
| File bytes | 913,000 (913 B average) |
| Indexed | 1,000 |
| Failed | 0 |
| Full scan wall time | **12.00 s** |
| Full scan throughput | **83.31 files/s** |
| Incremental rescan wall time | **3.92 s** |
| Incremental throughput | **255.15 files/s** (1,000 unchanged) |
| Notes indexed | 100,000 |
| Database size | **19.95 MB** (≈20 KB/file) |
| Process-tree baseline RSS | 28.9 MB |
| Peak process-tree RSS during scan | **88.2 MB** |
| RSS after scan | 34.9 MB |
| FTS5 enabled | yes |

Scan wall time includes process-pool startup and final duplicate grouping.

## Search latency (1,000-file database)

Direct `Database.query_library` calls with a page size of 60, after one warm-up:

| Query | p50 | p95 | Max | Average total matches |
| --- | --- | --- | --- | --- |
| Free text `bass` | 13.74 ms | 18.14 ms | 19.95 ms | 1,000 |
| Sound family `Mixed arrangement` | 13.53 ms | 15.43 ms | 20.09 ms | 1,000 |
| Role + tempo range + confidence | 13.53 ms | 16.56 ms | 18.68 ms | 1,000 |
| Note density + bar range | 13.15 ms | 17.30 ms | 18.63 ms | 1,000 |

These timings exclude HTTP transfer, JSON serialisation into the browser and React
rendering. In the browser E2E run, a search that changed the visible row set
settled in ~38 ms including API and rendering.

## Playback stability while scanning and filtering

`tests/playback-stability.mjs`:

- Auditions `Analog Lead 118.mid` (16.27 s) for 7.6 s.
- Simultaneously starts a background scan of 1,500 copied MIDI files.
- During playback, performs a text search and category filter.
- Samples the audio scheduler's source time against wall time.
- Verifies loop wrap and stop release.

| Metric | Result |
| --- | --- |
| Wall time sampled | 7.607 s |
| Engine source-time advance | 7.521 s |
| Drift ratio | **0.989×** |
| Scan active during playback | **yes** (1,185 files indexed at sample) |
| Search response | **41 ms** |
| Scheduled notes | 60 |
| Late notes | **0** |
| Skipped notes | **0** |
| Still playing after interactions | yes |
| Loop after wrap | 0.731 s, still playing |
| Stop result | 0.000 s, inactive voices 0 |

The browser was muted (no physical output), but the Web Audio graph, scheduler,
transport telemetry, loop and release path all executed. Source-time drift of
about 1% is within the expected sampling/`AudioContext` granularity for a 7.6 s
sample; the key result is zero late/skipped notes while the scan was saturating
workers.

## Slow-drive observation

SQLite WAL commits are a sensitive operation on mechanical/archive drives, not
MIDI parsing itself. On this workstation, scanning the same 120 generated files
with both the source and database on the slower D: data drive took **23.5 s**
before batched commits (2.6 s with both on the system C: SSD). With the batched
commit path (24 files per transaction) the D: scan dropped to **8.0 s** (C: 1.5 s).
The default database location is therefore `%LOCALAPPDATA%` (the application-data
drive), not the project folder. Source MIDI can still live on a slower drive; this
is environment-specific and not part of the fast benchmark above.

## Limitations

- Generated files are small and structurally similar; a real library with large
  multi-track arrangements will parse more slowly per file.
- Memory is sampled at 200 ms, so the true peak may be slightly higher.
- Process executor startup is included, favouring larger libraries' throughput.
- Search numbers are database-layer timings, not full browser wall-clock.
- Playback stability uses a headless muted Chromium on a powerful CPU. It does
  not guarantee identical scheduling on low-power machines or when the browser
  tab is hidden for long periods.
- Scale beyond 1,000 files was not benchmarked; see
  [Known limitations](limitations.md).
