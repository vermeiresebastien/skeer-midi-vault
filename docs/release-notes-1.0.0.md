# SKEER MIDI VAULT 1.0.0 — release notes

## Standalone distribution

- Windows per-user installer: `launch/SKEER-MIDI-VAULT-Setup-1.0.0.exe`
- Portable ZIP: `launch/SKEER-MIDI-VAULT-Portable-1.0.0.zip`
- SHA-256 release checksums: `launch/SHA256SUMS.txt`

The installed application includes the Python runtime and interface. Customers do
not need Python, Node.js, a terminal or admin rights. It opens the library in the
default browser and runs a tray service; **Settings → Data & privacy → Quit
SKEER MIDI VAULT** stops it.

## Fixed: white screen / crash during piano-roll interaction

- Replaced the full-screen SVG `feTurbulence` + `mix-blend-mode` paper texture
  with a static pre-rasterized PNG grain tile. The old filter forced a viewport-sized
  compositor raster/blend on every repaint and could crash Chromium's renderer
  during continuous drags.
- The piano-roll canvas now paints only the static notes/grid. The playhead is a
  lightweight DOM overlay, so dragging/seek updates no longer repaint the complete
  canvas on every frame.
- Click/drag seeking and the seek slider now pause the audio graph for the
  duration of the gesture and resume once on release, instead of restarting the
  scheduler on every pointermove.
- Tempo-knob drags are debounced and flushed on release instead of restarting the
  audio graph dozens of times per second.
- Added finite-number guards for sequence durations, note timing, pitch, velocity,
  seek targets and tempo values.
- Added canvas draw guards, context-loss recovery and a branded React error
  boundary. An unexpected render failure now shows a recoverable diagnostic screen
  with reload/copy-diagnostics actions rather than a blank white page.
- Added pointer-cancel/lost-capture handling so a drag interrupted by leaving the
  window cannot leave the app in a stuck seeking state.

Regression coverage: all 36 demo files were selected and dragged (paused and while
playing) in a stress probe, and the standard browser suite now includes a dedicated
piano-roll/seek/tempo drag check.

## Reliability and packaging

- App quit now waits for an active scan and its process pool to shut down, then
  exits the process. Packaged smoke testing asserts zero orphan
  `--multiprocessing-fork` workers.
- Added a desktop launcher with a single-instance mutex, tray icon, browser
  auto-open, per-user runtime file and an explicit quit endpoint.
- Added PyInstaller/Inno build pipeline, application icon and version metadata,
  EULA template and signing/distribution notes.

## Verification

- Python unit/integration: **51/51**
- Browser end-to-end: **16/16** (includes drag/scrub regression)
- Packaged standalone smoke: **passed** (health, frozen process-worker scan,
  clean quit, no orphan workers)
- Playback while scanning/filtering: **0 late, 0 skipped** scheduled notes
- Portable ZIP: extracted and smoke-tested

The installer is **unsigned**. Sign it with an Authenticode certificate before
public sale to reduce SmartScreen warnings. A full interactive install/uninstall
cycle could not be executed inside this sandboxed build session; test the Setup on
a normal desktop once before distribution. Details:
[`packaging/README.md`](../packaging/README.md).
