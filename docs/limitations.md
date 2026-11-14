# Known limitations

This is version 1.0.0. The list is deliberately explicit: the application is
useful, but it is not a DAW, a commercial MIDI catalog and it does not claim
general-purpose classification accuracy.

## Classification and musical analysis

- **Rules, not a learned model.** Instrument, role and style are inferred from
  General MIDI programs, track names, note statistics and filename patterns. The
  included 31-file evaluation is synthetic, controlled and written alongside its
  labels. Do not read its 100% file-level result as real-world accuracy.
- **Genre is a hint.** The style hint (for example "House / techno 22%") has no
  ground truth, no accuracy claim and is intentionally displayed as speculative.
- **Ambiguous music is allowed to be uncertain.** Layered synths, mixed GM
  programs, unnamed tracks, drums with pitched content and tracks that change
  instrument mid-file produce uncertainty or an `Unknown` result. That is a
  feature, not a hidden failure.
- **Format-2 file classification uses the primary sequence.** Individual
  sequences are available separately; a whole-file label is not invented by
  merging independent sequences.
- **Track roles are less reliable than families.** The controlled sample classifies
  13/13 track families but only 11/13 track roles. A cello pad can be read as a
  bassline, and a viola chord bed as an arpeggio.
- **Bars are approximate.** Pickups, mid-file meter changes, tempo changes and
  SMPTE timecode make exact bar numbering impossible without a score. The UI says
  approximate.
- **Key is either embedded or estimated.** The interface distinguishes the two;
  estimated keys can be wrong on modal, atonal or very sparse material.
- **Tempo filtering matches the tempo map's range**, not only the first tempo.
  The displayed BPM is the primary/initial tempo.
- **Time-signature display uses the first meter plus a change count.** The full
  event list is stored, but a full notation view is not provided.

## File and format coverage

- Only Standard MIDI Files with `.mid`/`.midi` are indexed. RIFF/RMID, MIDI 2.0 /
  UMP, `.kar`, trackers, DAW projects and compressed archives are out of scope.
  Archives are never unpacked.
- Files over 64 MB and files exceeding parser safety caps are recorded as failed
  rather than truncated silently.
- Some malformed files are only partially recoverable. They may be indexed with
  warnings and an uncertain classification; the source is never repaired.
- SysEx is skipped. Sustain is interpreted for note lengths but not forwarded over
  Web MIDI.
- Playback sends program changes and notes to Web MIDI; it does not forward
  sustain, pitch bend, modulation, aftertouch or SysEx in this version.
- SMF format 2 playback plays one independent sequence at a time. There is no
  "play all sequences simultaneously" mode.

## Scanning and file systems

- Drive discovery and protected-location rules target **Windows 10/11**. The
  service may run on macOS/Linux, but those platforms are not validated here and
  drive enumeration differs.
- Network, removable and optical sources are treated as optional. Detection of
  mapped UNC paths and email-style cloud-drive labels is **heuristic**. It avoids
  scanning such drives by default, but it cannot prove that every source is
  remote or cloud-backed.
- Cloud-placeholder detection is best effort using Windows attributes and
  reparse-point flags. A provider that materializes files without those flags
  can make the scanner open cloud content. Download-on-access behavior remains a
  provider policy, not something this app can guarantee.
- Inaccessible files/folders become durable failures or traversal issues when the
  OS reports them; a path that hangs inside a third-party file-system driver can
  still delay traversal.
- Excluded paths are prefix/subtree excludes. There is no per-file ignore syntax
  or per-source override of the global skip rules.
- Folders with millions of entries, very deep trees or multi-million-file
  libraries have not been benchmarked. The tested documented result is 1,000
  generated files. The scanner is bounded in memory but large scans take time.
- Duplicate similarity is intentionally conservative. It surfaces likely related
  music; it is not a musicological equivalence proof.
- Source files are never modified, moved, renamed or deleted. Consequently a file
  deleted outside the app remains in the index and is marked missing on the next
  completed scan; it is not removed from your library automatically.

## Preview and playback

- Preview timbres are generated approximations. They are not the original
  instrument sounds, samples, articulations or effects in the source file.
- Web MIDI requires a Chromium-based browser, user permission and an available
  hardware or virtual MIDI port. **No physical MIDI device was available for
  this release**, so device round-trip behavior is implemented but unverified.
- The scheduler runs in the browser tab. Very long hidden-tab sessions can be
  throttled by browser timer policy; scheduled lookahead covers normal
  backgrounding but this is not a real-time DAW audio engine.
- No offline audio bounce, stem render, MIDI export of auditioned material or
  sample-exact playback is provided.
- Looping wraps the selected sequence in source time. Tempo changes inside the
  file are honored, while the audition tempo knob scales the entire preview.
- DAW drag uses Chromium's download-URL drag flavor. Some DAWs, browsers or
  security policies may produce a copied file instead of a native drag. A real
  DAW drag-and-drop test is not included in this release; Reveal and Copy/export
  are the guaranteed paths.
- **Preview sounds are approximations, not samples.** Each voice is a small
  oscillator recipe (waveform, filter, envelope, one or two extra partials). It
  stands in for a category so you can tell a bass line from a pad at a glance; it
  is not a piano, and it is not the sound the file was authored with.
- **The category→voice mapping is opinionated.** Ten sounds cover a hundred-plus
  GM programs, so several instruments deliberately share one voice, and a track
  classified `Unknown` inherits the file's category. When you disagree, pick the
  sound yourself.
- **Correcting a file category re-voices the whole file.** It is meant to rescue
  misread loops and one-part files, and it does so by outranking each part's
  automatic label. On a genuinely multi-instrument arrangement that can be too
  blunt: the machine's per-part guess was probably better. Fix the individual
  parts, or use *follow analysis* in the Tracks card. Merely **accepting** an
  automatic prediction never re-voices anything — only a real correction does.
- **Sound picks live in the browser, not the library.** They are stored under the
  file's path in this browser's local storage. They are not in the SQLite index,
  so they are not in a database backup, do not follow the library to another
  machine or browser profile, and are lost when local storage is cleared.
  Renaming or moving a source file orphans its picks.
- **The GM program sent to hardware is a stand-in.** When a Web MIDI output is
  selected, an explicitly chosen sound maps to one GM program number; `Auto`, the
  neutral default and the drum kit leave the file's own program untouched. Your
  hardware's patch for program 24 is not this app's `pluck`, and a kit still
  depends on the receiving device mapping channel 10 to percussion.

## Interface and accessibility

- The canvas piano roll is mouse/touch driven; it is not fully keyboard-navigable
  and it is not a screen-reader substitute for a score. Standard controls,
  dialogs, tables and the transport have labels and keyboard focus states.
- A full assistive-technology audit (NVDA/Narrator/VoiceOver) was not performed.
- English only. No localization or right-to-left layout pass.
- Chrome and Edge are the validated browsers. Safari/Firefox may lack Web MIDI or
  Chromium's file-picker/drag behavior.
- The interface-scale control relies on CSS zoom. At unusual OS/browser zoom
  combinations, text can render slightly differently.

## Data, privacy and deployment

- The service binds to loopback only and has no account system. It has **no
  authentication**, so any process or user that can reach the loopback port on a
  shared machine can query the local index while the app is running. Do not run it
  on a shared untrusted machine if that matters.
- All data is in one SQLite database. Backups are downloaded from the UI; there is
  no in-app restore screen and no cloud sync. To restore, quit the app and replace
  `midivault.sqlite3` with a downloaded backup.
- "Rebuild index" preserves user data but has no progress rollback: if a source is
  offline during the rebuild, its records remain as last indexed/missing
  depending on source availability.
- The standalone installer is a per-user, unsigned Inno Setup package. Windows
  SmartScreen may warn until it is Authenticode-signed by the seller. A certificate,
  auto-update mechanism and enterprise MSI package are not included.
- The installed app runs as a hidden local service with a system-tray icon and
  opens the interface in the **system default browser**. It is not a custom
  Electron/WinUI window. A browser (Edge/Chrome) is therefore required; the tray
  icon needs an interactive Windows desktop session.
- A full install → shortcut → uninstall cycle was not executed inside this build
  sandbox because the sandbox token is denied writes to HKCU and the Start Menu.
  The installer compiled and the portable/packaged builds passed their smoke tests;
  test the Setup once on a normal user desktop before selling.
- No local model is installed or downloaded. The optional local-model integration
  point is an architecture seam for later work.
- Third-party npm packages are used to build/serve the interface
  (React, Vite, font packages, Playwright only for tests). Runtime Python is
  standard-library only; the standalone build bundles the Python runtime.

## Test scope not covered

The test report distinguishes executed coverage from untested paths. Not covered:
physical Web MIDI devices, actual DAW drag targets, real network shares, cloud-only
files from a live provider, inaccessible permissions owned by another account,
100k+ file libraries, macOS/Linux, screen readers, arbitrary commercial MIDI files,
and an interactive installer/uninstaller run on a normal desktop (blocked by the
sandboxed build session).
