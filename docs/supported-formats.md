# Supported formats and parser behavior

SKEER MIDI VAULT indexes **Standard MIDI Files** (`.mid`, `.midi`, extension
case-insensitive) up to **64 MB**. The parser is a custom implementation in
`midivault/engine/smf_parser.py`; it does not depend on a third-party MIDI
library.

## File formats

| Feature | Supported behavior |
| --- | --- |
| SMF format 0 | One multi-channel track, split into logical tracks by channel for the UI |
| SMF format 1 | Multiple simultaneous track chunks; tracks are grouped into logical tracks and played together |
| SMF format 2 | Independent sequences are **not** merged. Each sequence has its own tracks, tempo map, duration and preview; the interface exposes sequence tabs |
| Running status | Supported, including running status after meta/sysex events where applicable |
| Variable-length values | Supported with a hard error for values over the MIDI 4-byte limit |
| PPQN divisions | Supported |
| SMPTE divisions | Supported; note times are converted to seconds. SMPTE drop-frame forms are accepted |
| Unknown chunks | Skipped with a warning rather than aborting the file |
| Extra/declared track mismatch | Recovered where possible and recorded as warnings |

## Events read

- Note on/off; note-on velocity 0 is treated as note-off.
- Program change and channel number; program changes mid-track are reflected in
  the track's noted program count.
- Set tempo (µs per quarter note) and full tempo maps; multiple tempos are kept,
  with a primary/initial tempo and minimum/maximum range.
- Time signature, key signature, SMPTE offset, sequence number.
- Track name, instrument name, text, lyrics, markers, cue points and copyright
  (searchable; shown as embedded text where relevant).
- Sustain pedal CC64: notes are extended while the pedal is down, with a final
  release when the pedal lifts.
- All-notes-off / all-sound-off produce deterministic note closure.
- SysEx is consumed safely and is not interpreted.
- Channel prefix and general-purpose meta events are tolerated/skipped.

## Note handling

- Overlapping notes on the same pitch/channel are paired and trimmed so that a
  later note-on closes the previous instance instead of producing unplayable
  overlaps.
- Notes without a matching note-off receive an **assumed** duration; the file is
  marked with a warning. This is surfaced rather than silently hidden.
- Unmatched note-offs are warnings.
- Notes still open at end-of-track are closed at end of track with an assumption.
- Safety caps protect the scanner from malicious or pathological files:
  1,024 tracks, 2,000,000 events per track, 500,000 notes per track and 500 text
  events. Hitting a cap records a warning.

## Metadata and estimates

Every field that the UI shows as a musical value has a source category:

| Source | Meaning |
| --- | --- |
| `embedded` | Read from a MIDI event or track name in the file |
| `calculated` / `estimated` | Derived from the notes (key profile, density, bar estimate, etc.) |
| `assumed` | A safe default used because the file lacks the data (for example 4/4, 120 BPM) |
| `filename` | Found in the file or folder name; never presented as embedded metadata |
| `user` | Accepted/corrected by you; kept separately from automatic predictions |
| `auto` | Automatic classifier result |

Bars are an approximation when tempo/meter changes, pickups, or SMPTE timing make
bar numbering ambiguous. The UI labels the value as approximate.

## Playback coverage

- Notes are converted to absolute seconds using the parsed tempo map; the
  audition tempo control scales the whole preview rather than rewriting the file.
- Format-2 playback is one sequence at a time.
- Drum tracks use the preview synth's drum mapping; pitched tracks use generated
  preview timbres. These are audition sounds, not the original instruments.
- Web MIDI output sends note on/off on the track's original channel and program
  number. Sustain and SysEx are not forwarded in version 1.

## Not supported

- RIFF/RMID files that wrap SMF data. Renaming an `.rmi` to `.mid` does not make it
  a Standard MIDI File.
- MIDI 2.0 / Universal MIDI Packet files.
- MOD, XM, IT, S3M tracker formats, Ableton project files, DAW project bundles.
- `.kar` karaoke files (not indexed).
- Compressed archives (`.zip`, `.rar`, `.7z`, etc.) are never opened or unpacked.
- Embedded audio or sample extraction.
- Files larger than 64 MB, or files whose event counts exceed the safety caps.
- Lyrics display/editing, notation view, recording, and editing source files.

## Corrupt-file policy

A malformed file is never allowed to stop a scan. It becomes a `failed` row with
an error message and is visible through **Scan issues and failed files**. Partially
valid files that can still be read are indexed with warnings; the classification
may be marked uncertain. The scanner never repairs or rewrites the source.
