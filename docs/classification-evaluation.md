# Classification evaluation

This evaluation uses the generated, hand-labelled fixture library in
`fixtures/demo_library` (labels authored alongside the MIDI by
`scripts/generate_demo_library.py`). It is a controlled regression sample,
not a claim about arbitrary real-world MIDI libraries.

## File-level accuracy

- Sample: **31** files with labels marked as evaluation files.
- Sound family accuracy: **100.0%** (31/31).
- Musical role accuracy: **100.0%** (31/31).
- Files flagged uncertain: **5**.
- Mean automatic confidence: sound family **74.7%**, role **67.8%**.

## Track-level accuracy (multi-track fixture subset)

- Manually labelled tracks: **13**.
- Track sound family accuracy: **100.0%** (13/13).
- Track role accuracy: **84.6%** (11/13).

## Correctly classified

| File | Family | Role | Confidence |
| --- | --- | --- | --- |
| Drums/Deep House Groove 124.mid | Drums/percussion | Drum groove | 70% |
| Drums/Dusty Breakbeat 90.mid | Drums/percussion | Drum groove | 71% |
| Drums/Tom Fill 110.mid | Drums/percussion | Drum fill | 71% |
| Drums/Snare Roll Fill 100.mid | Drums/percussion | Drum fill | 73% |
| Drums/Trap Hat Pattern 140.mid | Drums/percussion | Drum groove | 71% |
| Bass/Funk Bassline F.mid | Bass | Bassline | 63% |
| Bass/Sub Pulse 808.mid | Bass | Bassline | 64% |
| Bass/Walking Upright C.mid | Bass | Bassline | 64% |
| Bass/Missing Program Bass.mid | Bass | Bassline | 63% |
| Keys/Rhodes Chords Cmaj7.mid | Piano/keys | Chord progression | 74% |
| Keys/Piano Arpeggio Am.mid | Piano/keys | Arpeggio | 72% |
| Keys/Warm Piano Chords.mid | Piano/keys | Chord progression | 70% |
| Keys/Sustain Piano.mid | Piano/keys | Pad/sustained harmony | 65% |
| Guitar/Nylon Arpeggio 3-4.mid | Guitar/plucked | Arpeggio | 65% |
| Guitar/Clean Guitar Chords.mid | Guitar/plucked | Chord progression | 74% |
| Orchestral/String Quartet Sketch.mid | Strings | Complete song or multi-part arrangement | 72% |
| Orchestral/Trumpet Melody.mid | Brass/woodwinds | Lead/melody | 72% |
| Orchestral/Flute Exercise 4.mid | Brass/woodwinds | Exercise or technical pattern | 69% |
| Synths/Analog Lead 118.mid | Synth | Lead/melody | 70% |
| Synths/Supersaw Pad C.mid | Synth | Pad/sustained harmony | 68% |
| Synths/Pluck Arp 124.mid | Synth | Arpeggio | 55% |
| Synths/Synth Chords.mid | Synth | Chord progression | 73% |
| Full Arrangements/Midnight Drive 118.mid | Mixed arrangement | Complete song or multi-part arrangement | 78% |
| Full Arrangements/Lo-Fi Study 84.mid | Mixed arrangement | Complete song or multi-part arrangement | 79% |
| Full Arrangements/Odd Meter 7-8.mid | Mixed arrangement | Complete song or multi-part arrangement | 70% |
| Misc/Tempo Map Journey.mid | Synth | Lead/melody | 63% |
| Misc/SMPTE Melody.mid | Brass/woodwinds | Lead/melody | 71% |
| Misc/Overlapping Notes.mid | Brass/woodwinds | Lead/melody | 65% |
| Misc/Meta Only.mid | Unknown | Unknown | 25% |
| Misc/Mystery Sketch.mid | Unknown | Lead/melody | 24% |
| Misc/Misleading Bass Name.mid | Piano/keys | Chord progression | 55% |

## Misclassifications / ambiguous cases

No misclassifications in this sample.

## Uncertain cases

| File | Family | Role | Confidence | Flags |
| --- | --- | --- | --- | --- |
| Orchestral/String Quartet Sketch.mid | Strings | Complete song or multi-part arrangement | 72% | Embedded signature says Bb major; pitch-class profile suggests C major (78%). |
| Synths/Pluck Arp 124.mid | Synth | Arpeggio | 55% | Filename suggests guitar/plucked, while track evidence points to Synth |
| Misc/Meta Only.mid | Unknown | Unknown | 25% | key uncertain |
| Misc/Mystery Sketch.mid | Unknown | Lead/melody | 24% | — |
| Misc/Misleading Bass Name.mid | Piano/keys | Chord progression | 55% | Filename suggests bass, while track evidence points to Piano/keys |

## Track-level mismatches

| File | Track | Expected | Predicted |
| --- | --- | --- | --- |
| Orchestral/String Quartet Sketch.mid | Cello | Strings / Pad/sustained harmony | Strings / Bassline |
| Orchestral/String Quartet Sketch.mid | Viola | Strings / Chord progression | Strings / Arpeggio |

## What is not measured

- Genre: there is no ground truth and the app itself reports it only as a
  low-confidence style hint. No genre accuracy is claimed.
- Real-world commercial MIDI: this sample is synthetically constructed from
  explicit author intent. Real files with misleading track names, layered
  instruments or mixed GM programs will produce more uncertainty.
- Correctness of *accepted* user corrections: corrections are stored
  separately and never evaluated against their original prediction as if
  they were model accuracy.
