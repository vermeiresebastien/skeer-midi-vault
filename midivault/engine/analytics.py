"""Calculated musical statistics.

Everything here is derived from the parsed event stream. Raw embedded values
(tempo/time-signature/key-signature events, track names, text) are kept
distinctly labelled in the output so the interface can say "embedded" versus
"estimated" instead of presenting an inference as file metadata.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from .gm import note_name, program_name
from .model import Note, ParseResult, SequenceData, TrackData
from .taxonomy import program_category, tonic_name

# Krumhansl-Kessler key profiles.
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

_CHORD_TEMPLATES = [
    (0, 4, 7), (0, 3, 7), (0, 3, 6), (0, 4, 7, 10), (0, 3, 7, 10),
    (0, 4, 7, 11), (0, 3, 7, 11), (0, 5, 7), (0, 2, 7),
]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_mean(values: list[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def _safe_median(values: list[float], default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    denom_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    denom_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if denom_a == 0 or denom_b == 0:
        return 0.0
    return numerator / (denom_a * denom_b)


def estimate_key(notes: list[Note], beats_per_quarter: float = 1.0) -> dict[str, Any]:
    """Estimate a tonal centre from duration-weighted pitch classes.

    The result is an *estimate*. It includes the best correlation and a second
    hypothesis so weak evidence can be surfaced instead of hidden.
    """
    tonal_notes = [n for n in notes if n.channel != 9]
    if len(tonal_notes) < 8:
        return {
            "estimated": None, "confidence": 0.0, "uncertain": True,
            "correlation": 0.0, "evidence": "Too few tonal notes for key estimation",
            "runner_up": None,
        }
    histogram = [0.0] * 12
    total_weight = 0.0
    use_seconds = beats_per_quarter is None or beats_per_quarter <= 0
    for note in tonal_notes:
        weight = (
            min(4.0, max(0.1, note.duration_seconds * 2.0))
            if use_seconds
            else min(4.0, max(0.1, note.end_beat - note.start_beat))
        )
        histogram[note.pitch % 12] += weight
        total_weight += weight
    if total_weight <= 0:
        result = estimate_key([], beats_per_quarter)
        return result
    hypotheses: list[tuple[float, str, int, str]] = []
    for tonic in range(12):
        major_rot = [_MAJOR_PROFILE[(pc - tonic) % 12] for pc in range(12)]
        minor_rot = [_MINOR_PROFILE[(pc - tonic) % 12] for pc in range(12)]
        hypotheses.append((_pearson(histogram, major_rot), tonic_name(tonic), tonic, "major"))
        hypotheses.append((_pearson(histogram, minor_rot), tonic_name(tonic), tonic, "minor"))
    hypotheses.sort(key=lambda item: item[0], reverse=True)
    best_corr, tonic, _pc, mode = hypotheses[0]
    second_corr, second_tonic, _pc2, second_mode = hypotheses[1]
    if best_corr < 0.30:
        return {
            "estimated": None, "confidence": 0.0, "uncertain": True,
            "correlation": round(best_corr, 4),
            "runner_up": f"{second_tonic} {second_mode}",
            "evidence": "Pitch-class profile is too weak to estimate a key",
        }
    fit = _clamp((best_corr - 0.25) / 0.6)
    margin = max(0.0, best_corr - second_corr)
    evidence_volume = _clamp(len(tonal_notes) / 20.0)
    confidence = _clamp(
        (0.18 + 0.67 * fit + min(0.13, margin * 0.6))
        * (0.60 + 0.40 * evidence_volume),
        0.10,
        0.9,
    )
    if len(tonal_notes) < 12:
        confidence = min(confidence, 0.55)
    return {
        "estimated": f"{tonic} {mode}",
        "confidence": round(confidence, 3),
        "uncertain": confidence < 0.5 or margin < 0.02,
        "correlation": round(best_corr, 4),
        "runner_up": f"{second_tonic} {second_mode}",
        "evidence": (
            f"Pitch-class profile correlation {best_corr:.2f}; "
            f"next hypothesis {second_tonic} {second_mode} ({second_corr:.2f})"
        ),
    }


def _group_onsets(notes: list[Note], tolerance: float = 0.045) -> list[list[Note]]:
    if not notes:
        return []
    ordered = sorted(notes, key=lambda n: (n.start_seconds, n.pitch))
    groups: list[list[Note]] = [[ordered[0]]]
    for note in ordered[1:]:
        if abs(note.start_seconds - groups[-1][0].start_seconds) <= tolerance:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def _polyphony(notes: list[Note]) -> tuple[int, float]:
    if not notes:
        return 0, 0.0
    events: list[tuple[float, int]] = []
    for note in notes:
        events.append((note.start_seconds, 1))
        events.append((note.end_seconds, -1))
    events.sort(key=lambda item: (item[0], item[1]))  # note-offs before note-ons
    active = 0
    maximum = 0
    last_time = events[0][0]
    area = 0.0
    for time, delta in events:
        if active > 0:
            area += active * max(0.0, time - last_time)
        last_time = time
        active += delta
        maximum = max(maximum, active)
    start = min(note.start_seconds for note in notes)
    end = max(note.end_seconds for note in notes)
    span = max(1e-6, end - start)
    return maximum, area / span


def _sequence_events(seq: SequenceData) -> dict[str, Any]:
    tempo_events = [t for t in seq.tempos if t.embedded]
    return {
        "tempo_events": [
            {"tick": t.tick, "bpm": round(t.bpm, 4), "beat": round(t.beat, 4),
             "seconds": round(t.seconds, 4)}
            for t in seq.tempos
        ],
        "tempo_change_count": max(0, len(tempo_events) - (1 if tempo_events and tempo_events[0].tick == 0 else 0)),
        "tempo_min_bpm": round(min((t.bpm for t in seq.tempos), default=120.0), 4),
        "tempo_max_bpm": round(max((t.bpm for t in seq.tempos), default=120.0), 4),
        "tempo_assumed": not tempo_events,
    }


def _primary_sequence(parse: ParseResult) -> tuple[int, SequenceData | None]:
    if not parse.sequences:
        return 0, None
    best_index = max(
        range(len(parse.sequences)),
        key=lambda index: (parse.sequences[index].note_count, -index),
    )
    return best_index, parse.sequences[best_index]


def _bar_beats(seq: SequenceData | None) -> float:
    if seq and seq.time_signatures:
        return max(0.25, seq.time_signatures[0].beats_per_bar)
    return 4.0


def _timing_units(seq: SequenceData | None) -> tuple[str, float]:
    """Return the analysis unit and the number of those units per bar."""
    if seq and seq.timing_type == "smpte":
        bpm = seq.tempos[0].bpm if seq.tempos else 120.0
        return "second", max(0.25, _bar_beats(seq) * 60.0 / bpm)
    return "beat", _bar_beats(seq)


def _note_positions(notes: list[Note], timing_type: str, initial_bpm: float,
                    bar_beats: float) -> list[float]:
    if timing_type == "smpte":
        # Use a musical coordinate (120 BPM equivalent) only for rhythm pattern
        # features; duration and tempo remain in seconds in the public summary.
        units_per_second = 2.0
        bar_seconds = bar_beats * 60.0 / max(initial_bpm, 1.0)
        return [((n.start_seconds * units_per_second) % max(0.25, bar_beats)) for n in notes]
    del bar_beats
    return [n.start_beat % 4.0 for n in notes]


def _best_chord_coverage(pitch_class_counts: Counter[int]) -> tuple[float, str | None]:
    total = sum(pitch_class_counts.values())
    if not total:
        return 0.0, None
    best = (0.0, None)
    for root in range(12):
        for template in _CHORD_TEMPLATES:
            tones = {(root + interval) % 12 for interval in template}
            covered = sum(count for pc, count in pitch_class_counts.items() if pc in tones)
            if covered / total > best[0]:
                quality = "major" if template in ((0, 4, 7), (0, 4, 7, 10), (0, 4, 7, 11)) else "minor"
                best = (covered / total, f"{tonic_name(root)} {quality}")
    return best


def _grid_rhythm(notes: list[Note], timing_type: str, bar_beats: float) -> dict[str, float]:
    if not notes:
        return {
            "grid_occupancy": 0.0, "offbeat_ratio": 0.0, "syncopation_ratio": 0.0,
            "swing_ratio": 0.0, "regularity": 0.0, "pattern_repeat": 0.0,
        }
    fractions = []
    bar_positions = []
    for note in notes:
        if timing_type == "smpte":
            # Use seconds converted to a 120 BPM-equivalent beat for shape only.
            unit = note.start_seconds * 2.0
        else:
            unit = note.start_beat
        fractions.append(unit % 1.0)
        bar_positions.append(int(round((unit % max(0.25, bar_beats)) * 4)) % 16)
    count = len(fractions)
    quarter = sum(1 for f in fractions if min(abs(f), abs(f - 1.0)) < 0.09)
    eighth = sum(1 for f in fractions if abs(f - 0.5) < 0.09)
    # Triplet-swing positions sit near 1/3 and 2/3 of a beat. The tolerance
    # must be tighter than the distance to regular 16th-note positions (0.25
    # and 0.75) or every 16th-note pattern would be misread as swung.
    swung_eighth = sum(
        1 for f in fractions
        if abs(f - 0.667) < 0.055 or abs(f - 0.333) < 0.055
    )
    weak_sixteenth = sum(
        1 for f in fractions
        if abs(f - 0.25) < 0.055 or abs(f - 0.75) < 0.055
    )
    offbeat = eighth + swung_eighth + weak_sixteenth
    swing_base = eighth + swung_eighth
    swing_ratio = swung_eighth / swing_base if swing_base else 0.0
    syncopation = (weak_sixteenth + eighth * 0.45 + swung_eighth * 0.55) / max(1, count)
    # Pattern repetition across bars, normalised to 16 steps per bar.
    repeat = 0.0
    if len(bar_positions) >= 6:
        per_bar = max(1, int(round(len(notes) / max(1.0, notes[-1].start_seconds + 0.001))))
        del per_bar
        bar_step = int(max(1, round(bar_beats * 4)))
        bars: list[set[int]] = []
        for note, pos in zip(notes, bar_positions):
            bar = int((note.start_seconds if timing_type == "smpte" else note.start_beat) // max(0.25, bar_beats))
            # `bar` can jump past the end when a clip rests for a whole bar, so
            # grow to fill the gap instead of appending a single set per note.
            while len(bars) <= bar:
                bars.append(set())
            bars[bar].add(pos)
        if len(bars) >= 2:
            first = bars[0]
            sims = []
            for other in bars[1:]:
                sims.append(len(first & other) / max(1, len(first | other)))
            repeat = sum(sims) / len(sims)
        del bar_step
    # Inter-onset interval regularity.
    ordered = sorted(notes, key=lambda n: n.start_seconds)
    intervals = [b.start_seconds - a.start_seconds for a, b in zip(ordered, ordered[1:])
                 if b.start_seconds > a.start_seconds + 1e-4]
    regularity = 0.0
    if intervals:
        buckets = Counter(round(value, 2) for value in intervals)
        regularity = buckets.most_common(1)[0][1] / len(intervals)
    return {
        "grid_occupancy": round(len([p for p in bar_positions if True]) / max(1, len(bar_positions)), 4),
        "quarter_note_ratio": round(quarter / max(1, count), 4),
        "eighth_note_ratio": round(eighth / max(1, count), 4),
        "offbeat_ratio": round(offbeat / max(1, count), 4),
        "syncopation_ratio": round(_clamp(syncopation, 0.0, 1.0), 4),
        "swing_ratio": round(swing_ratio, 4),
        "regularity": round(regularity, 4),
        "pattern_repeat": round(repeat, 4),
    }


def analyze_track(track: TrackData, seq: SequenceData | None, bar_beats: float) -> dict[str, Any]:
    timing_type = seq.timing_type if seq else "metrical"
    notes = track.notes
    note_count = len(notes)
    starts = [n.start_beat if timing_type == "metrical" else n.start_seconds for n in notes]
    ends = [n.end_beat if timing_type == "metrical" else
            n.start_seconds + n.duration_seconds for n in notes]
    span_units = (max(ends) - min(starts)) if notes else 0.0
    if span_units <= 0:
        span_units = 1.0
    unit = "beat" if timing_type == "metrical" else "second"
    densities = [n.duration_seconds for n in notes]
    if timing_type == "metrical":
        note_durations = [max(0.01, n.end_beat - n.start_beat) for n in notes]
    else:
        note_durations = [max(0.001, n.duration_seconds) for n in notes]
    groups = _group_onsets(notes)
    notes_in_groups = sum(len(g) for g in groups)
    multi_group_notes = sum(len(g) for g in groups if len(g) > 1)
    mono_ratio = 1.0 - (multi_group_notes / notes_in_groups) if notes_in_groups else 0.0
    max_poly, mean_poly = _polyphony(notes)
    pitches = [n.pitch for n in notes]
    velocities = [n.velocity for n in notes]
    pitch_classes = Counter(n.pitch % 12 for n in notes)
    pc_weighted: Counter[int] = Counter()
    for note in notes:
        pc_weighted[note.pitch % 12] += max(0.1, (note.end_beat - note.start_beat)
                                             if timing_type == "metrical" else note.duration_seconds)
    chord_coverage, chord_hypothesis = _best_chord_coverage(pc_weighted)
    rhythm = _grid_rhythm(notes, timing_type, bar_beats)
    low_register_ratio = sum(1 for p in pitches if p < 48) / note_count if notes else 0.0
    high_register_ratio = sum(1 for p in pitches if p >= 72) / note_count if notes else 0.0
    # Melodic interval statistics use a start-then-pitch order. For chord tracks
    # these are less meaningful and the classifier weights them down.
    ordered = sorted(notes, key=lambda n: (n.start_seconds, n.pitch))
    intervals = [ordered[i + 1].pitch - ordered[i].pitch for i in range(len(ordered) - 1)]
    directed = [i for i in intervals if i != 0]
    stepwise = sum(1 for interval in directed if 0 < abs(interval) <= 2)
    leaps = sum(1 for interval in directed if abs(interval) >= 12)
    changes = sum(1 for a, b in zip(directed, directed[1:]) if (a > 0) != (b > 0))
    longest_run = 0
    current_run = 0
    previous_direction = 0
    for interval in directed:
        direction = 1 if interval > 0 else -1
        if abs(interval) <= 2 and direction == previous_direction:
            current_run += 1
        elif abs(interval) <= 2:
            current_run = 1
        else:
            current_run = 0
        longest_run = max(longest_run, current_run)
        previous_direction = direction
    distinct_pitch_classes = len(pitch_classes)
    dense_onset = _clamp((note_count / span_units) / 4.0)
    arpeggio_score = (
        0.30 * mono_ratio
        + 0.20 * rhythm["regularity"]
        + 0.22 * chord_coverage
        + 0.13 * dense_onset
        + 0.15 * _clamp((6 - distinct_pitch_classes) / 4.0)
    )
    scale_score = (
        0.34 * (stepwise / max(1, len(directed)))
        + 0.22 * (longest_run / max(1, len(directed)))
        + 0.16 * mono_ratio
        + 0.14 * rhythm["regularity"]
        + 0.14 * _clamp(1.0 - (distinct_pitch_classes / 12.0))
    )
    program_cats = sorted({
        category for program in track.programs
        if (category := program_category(program)) is not None
    })
    controller_summary = {str(code): count for code, count in sorted(track.controller_counts.items())}
    name = track.name or ""
    instrument_name = track.instrument_name or ""
    return {
        "sequence_index": track.sequence_index,
        "track_index": track.track_index,
        "chunk_index": track.chunk_index,
        "channel": track.channel,
        "channel_display": track.channel + 1,
        "drum_channel": track.channel == 9,
        "name": track.name,
        "instrument_name": track.instrument_name,
        "programs": track.programs,
        "program_names": [program_name(p) for p in track.programs if program_name(p)],
        "program_categories": program_cats,
        "bank": {"msb": track.bank_msb, "lsb": track.bank_lsb},
        "note_count": note_count,
        "pitch_min": min(pitches) if pitches else None,
        "pitch_max": max(pitches) if pitches else None,
        "pitch_min_name": note_name(min(pitches)) if pitches else None,
        "pitch_max_name": note_name(max(pitches)) if pitches else None,
        "pitch_median": _safe_median([float(p) for p in pitches]) if pitches else None,
        "pitch_mean": round(_safe_mean([float(p) for p in pitches]), 2) if pitches else None,
        "pitch_range": (max(pitches) - min(pitches)) if pitches else 0,
        "distinct_pitches": len(set(pitches)),
        "distinct_pitch_classes": distinct_pitch_classes,
        "pitch_classes": [pitch_classes.get(i, 0) for i in range(12)],
        "velocity_min": min(velocities) if velocities else None,
        "velocity_max": max(velocities) if velocities else None,
        "velocity_mean": round(_safe_mean([float(v) for v in velocities]), 2) if velocities else None,
        "velocity_std": round(statistics.pstdev(velocities), 2) if len(velocities) > 1 else 0.0,
        "duration_units": round(span_units, 4),
        "bar_span": round(span_units / max(0.25, bar_beats), 4),
        "unit": unit,
        "note_density": round(note_count / span_units, 4),
        "avg_note_duration": round(_safe_mean(note_durations), 4),
        "median_note_duration": round(_safe_median(note_durations), 4),
        "short_note_ratio": round(sum(1 for d in note_durations if d <= (0.25 if unit == "beat" else 0.15)) / max(1, note_count), 4),
        "long_note_ratio": round(sum(1 for d in note_durations if d >= (1.0 if unit == "beat" else 0.5)) / max(1, note_count), 4),
        "monophonic_ratio": round(mono_ratio, 4),
        "simultaneous_onset_ratio": round((notes_in_groups - len(groups)) / max(1, notes_in_groups), 4),
        "avg_group_size": round(notes_in_groups / max(1, len(groups)), 4),
        "max_group_size": max((len(g) for g in groups), default=0),
        "chord_group_count": sum(1 for g in groups if len(g) > 1),
        "polyphony_max": max_poly,
        "polyphony_mean": round(mean_poly, 4),
        "pitch_class_entropy": round(_entropy(list(pitch_classes.values())), 4),
        "low_register_ratio": round(low_register_ratio, 4),
        "high_register_ratio": round(high_register_ratio, 4),
        "stepwise_ratio": round(stepwise / max(1, len(directed)), 4),
        "large_leap_ratio": round(leaps / max(1, len(directed)), 4),
        "direction_changes": changes,
        "longest_stepwise_run": longest_run,
        "chord_tone_coverage": round(chord_coverage, 4),
        "chord_hypothesis": chord_hypothesis,
        "arpeggio_score": round(arpeggio_score, 4),
        "scale_score": round(scale_score, 4),
        "regularity": rhythm["regularity"],
        "pattern_repeat": rhythm["pattern_repeat"],
        "syncopation_ratio": rhythm["syncopation_ratio"],
        "offbeat_ratio": rhythm["offbeat_ratio"],
        "swing_ratio": rhythm["swing_ratio"],
        "eighth_note_ratio": rhythm["eighth_note_ratio"],
        "quarter_note_ratio": rhythm["quarter_note_ratio"],
        "grid_occupancy": rhythm["grid_occupancy"],
        "sustain_events": track.sustain_events,
        "sustained_notes": track.sustained_notes,
        "assumed_durations": track.assumed_durations,
        "orphan_note_offs": track.orphan_note_offs,
        "controller_summary": controller_summary,
        "source_text": f"{name} {instrument_name}".strip(),
        "embedded_texts": [text.text for text in track.texts if text.text][:20],
        "short_note_threshold": 0.25 if unit == "beat" else 0.15,
        "long_note_threshold": 1.0 if unit == "beat" else 0.5,
        "is_percussion_program": any(p is not None and 112 <= p <= 119 for p in track.programs),
        "program_categories": program_cats,
    }


def _entropy(values: list[int]) -> float:
    total = sum(values)
    if total <= 0:
        return 0.0
    value = 0.0
    for count in values:
        if count > 0:
            p = count / total
            value -= p * math.log2(p)
    return value / math.log2(12) if value else 0.0


def _sequence_summary(seq: SequenceData) -> dict[str, Any]:
    key_info = estimate_key(
        [note for track in seq.tracks for note in track.notes],
        None if seq.timing_type == "smpte" else (seq.ticks_per_quarter or 1),
    )
    tempo_events = [t for t in seq.tempos if t.embedded]
    tempo_assumed = not tempo_events
    ts_embedded = any(ts.embedded for ts in seq.time_signatures)
    initial_ts = seq.time_signatures[0] if seq.time_signatures else None
    initial_tempo = seq.tempos[0] if seq.tempos else None
    return {
        "index": seq.index,
        "name": seq.name,
        "duration_seconds": round(seq.duration_seconds, 4),
        "duration_beats": round(seq.duration_beats, 4),
        "bars": None if seq.bars is None else round(seq.bars, 2),
        "timing_type": seq.timing_type,
        "note_count": seq.note_count,
        "track_count": seq.track_count,
        "tempo": {
            "initial_bpm": round(initial_tempo.bpm, 3) if initial_tempo else 120.0,
            "source": "embedded" if tempo_events else "assumed",
            "assumed": tempo_assumed,
            "min_bpm": round(min((t.bpm for t in seq.tempos), default=120.0), 3),
            "max_bpm": round(max((t.bpm for t in seq.tempos), default=120.0), 3),
            "change_count": max(0, len(tempo_events) - (1 if tempo_events and tempo_events[0].tick == 0 else 0)),
            "events": _sequence_events(seq)["tempo_events"],
        },
        "time_signature": {
            "initial": initial_ts.label if initial_ts else "4/4",
            "source": "embedded" if ts_embedded else "assumed",
            "assumed": not ts_embedded,
            "change_count": max(0, len(seq.time_signatures) - 1),
            "events": [ts.to_dict() for ts in seq.time_signatures],
        },
        "key": {
            "embedded": seq.key_signatures[0].label if seq.key_signatures else None,
            "embedded_events": [k.to_dict() for k in seq.key_signatures],
            **key_info,
            "source": "embedded" if seq.key_signatures else (
                "estimated" if key_info["estimated"] else "none"
            ),
        },
        "warnings": list(seq.warnings),
        "text": [t.text for t in seq.texts][:200],
    }


def _text_inventory(parse: ParseResult) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for seq in parse.sequences:
        for text in seq.texts:
            key = (text.kind, text.text.casefold())
            if key in seen or not text.text.strip():
                continue
            seen.add(key)
            output.append({
                "kind": text.kind,
                "text": text.text,
                "tick": text.tick,
                "sequence": seq.index,
            })
            if len(output) >= 240:
                return output
    return output


def _pick_tempo_and_meter(seq: SequenceData | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if seq is None:
        return (
            {"initial_bpm": 120.0, "source": "assumed", "change_count": 0,
             "min_bpm": 120.0, "max_bpm": 120.0, "events": [], "assumed": True},
            {"initial": "4/4", "source": "assumed", "change_count": 0,
             "events": [], "assumed": True},
        )
    tempo_events = [t for t in seq.tempos if t.embedded]
    ts_embedded = any(ts.embedded for ts in seq.time_signatures)
    initial_ts = seq.time_signatures[0] if seq.time_signatures else None
    initial_tempo = seq.tempos[0] if seq.tempos else None
    return (
        {
            "initial_bpm": round(initial_tempo.bpm, 3) if initial_tempo else 120.0,
            "source": "embedded" if tempo_events else "assumed",
            "assumed": not tempo_events,
            "min_bpm": round(min((t.bpm for t in seq.tempos), default=120.0), 3),
            "max_bpm": round(max((t.bpm for t in seq.tempos), default=120.0), 3),
            "change_count": max(0, len(tempo_events) - (1 if tempo_events and tempo_events[0].tick == 0 else 0)),
            "events": _sequence_events(seq)["tempo_events"],
        },
        {
            "initial": initial_ts.label if initial_ts else "4/4",
            "source": "embedded" if ts_embedded else "assumed",
            "assumed": not ts_embedded,
            "change_count": max(0, len(seq.time_signatures) - 1),
            "events": [ts.to_dict() for ts in seq.time_signatures],
        },
    )


def analyze(parse: ParseResult, filename: str = "", relative_folder: str = "") -> dict[str, Any]:
    """Return file- and track-level calculated analysis.

    For format 2, the file-level *musical* summary is taken from the primary
    sequence (the one with most notes). Independent sequences remain separate;
    file-wide inventory counts, text and durations are not summed into a fake
    timeline.
    """
    primary_index, primary = _primary_sequence(parse)
    bar_beats = _bar_beats(primary)
    tempo, time_signature = _pick_tempo_and_meter(primary)
    tracks_analysis: list[dict[str, Any]] = []
    all_notes: list[Note] = []
    primary_notes: list[Note] = []
    for seq in parse.sequences:
        for track in seq.tracks:
            track_analysis = analyze_track(track, seq, _bar_beats(seq))
            tracks_analysis.append(track_analysis)
            all_notes.extend(track.notes)
            if seq.index == primary_index:
                primary_notes.extend(track.notes)
    key_info = estimate_key(primary_notes, primary.ticks_per_quarter if primary else None)
    key_embedded_events = primary.key_signatures if primary else []
    embedded_key = key_embedded_events[0].label if key_embedded_events else None
    key_source = "embedded" if embedded_key else ("estimated" if key_info["estimated"] else "none")
    key_payload = {
        "label": embedded_key or key_info["estimated"],
        "embedded": embedded_key,
        "estimated": key_info["estimated"],
        "source": key_source,
        "confidence": 1.0 if embedded_key else key_info["confidence"],
        "uncertain": False if embedded_key else key_info["uncertain"],
        "correlation": key_info["correlation"],
        "runner_up": key_info.get("runner_up"),
        "events": [k.to_dict() for k in key_embedded_events],
        "evidence": "Embedded key signature" if embedded_key else key_info["evidence"],
        "conflict": None,
    }
    if (embedded_key and key_info["estimated"] and key_info["estimated"] != embedded_key
            and key_info["confidence"] >= 0.68 and len(primary_notes) >= 16):
        key_payload["conflict"] = (
            f"Embedded signature says {embedded_key}; pitch-class profile suggests "
            f"{key_info['estimated']} ({key_info['confidence'] * 100:.0f}%)."
        )
    pitch_values = [note.pitch for note in all_notes]
    velocity_values = [note.velocity for note in all_notes]
    durations_seconds = [note.duration_seconds for note in all_notes]
    tracks_with_notes = [track for track in tracks_analysis if track["note_count"] > 0]
    programs = sorted({p for track in tracks_with_notes for p in track["programs"]})
    categories = sorted({c for track in tracks_with_notes for c in track["program_categories"]})
    embedded_text = _text_inventory(parse)
    total_note_count = len(all_notes)
    primary_span = primary.duration_beats if primary else 0.0
    duration_seconds = primary.duration_seconds if primary else parse.duration_seconds
    density = len(primary_notes) / primary_span if primary_span > 0 else 0.0
    poly_max = max((track["polyphony_max"] for track in tracks_with_notes), default=0)
    poly_mean = _safe_mean([track["polyphony_mean"] for track in tracks_with_notes])
    bars = primary.bars if primary else None
    sequence_summaries = [_sequence_summary(seq) for seq in parse.sequences]
    computed = {
        "key_estimated": key_info["estimated"],
        "key_confidence": key_info["confidence"],
        "assumed_tempo": tempo["assumed"],
        "assumed_time_signature": time_signature["assumed"],
        "assumed_durations": sum(track.assumed_durations for seq in parse.sequences for track in seq.tracks),
        "smphte_timing": parse.timing_type == "smpte",
    }
    file_payload = {
        "format": parse.format,
        "format_2": parse.format == 2,
        "sequence_count": len(parse.sequences),
        "primary_sequence_index": primary_index,
        "timing_type": parse.timing_type,
        "ticks_per_quarter": parse.ticks_per_quarter,
        "smpte_fps": parse.smpte_fps,
        "ticks_per_frame": parse.ticks_per_frame,
        "duration_seconds": round(duration_seconds, 4),
        "duration_beats": round(primary_span, 4),
        "bars": None if bars is None else round(bars, 2),
        "note_count": total_note_count,
        "primary_note_count": len(primary_notes),
        "track_count": len(tracks_with_notes),
        "sequence_count_with_notes": sum(
            1 for seq in parse.sequences if seq.note_count > 0
        ),
        "channel_count": len({track["channel"] for track in tracks_with_notes}),
        "programs": programs,
        "program_names": [program_name(p) for p in programs if program_name(p)],
        "program_categories": categories,
        "tempo": tempo,
        "time_signature": time_signature,
        "key": key_payload,
        "pitch_min": min(pitch_values) if pitch_values else None,
        "pitch_max": max(pitch_values) if pitch_values else None,
        "pitch_min_name": note_name(min(pitch_values)) if pitch_values else None,
        "pitch_max_name": note_name(max(pitch_values)) if pitch_values else None,
        "velocity_min": min(velocity_values) if velocity_values else None,
        "velocity_max": max(velocity_values) if velocity_values else None,
        "velocity_mean": round(_safe_mean([float(v) for v in velocity_values]), 2) if velocity_values else None,
        "avg_note_duration_seconds": round(_safe_mean(durations_seconds), 4) if durations_seconds else 0.0,
        "note_density": round(density, 4),
        "polyphony_max": poly_max,
        "polyphony_mean": round(poly_mean, 3),
        "controllers": _controller_inventory(parse),
        "embedded_text": embedded_text,
        "assumed_durations": computed["assumed_durations"],
        "warnings": list(parse.warnings),
        "computed": computed,
        "unique_track_names": sorted({t["name"] for t in tracks_with_notes if t["name"]}),
        "unique_program_names": sorted({name for t in tracks_with_notes for name in t["program_names"]}),
        "file_size": None,
        "filename": filename,
        "folder": relative_folder,
    }
    if parse.format == 2 and len(parse.sequences) > 1:
        file_payload["warnings"].append(
            "Format 2 file: file-level musical summary describes the primary sequence only; "
            "independent sequences are listed separately."
        )
    return {
        "file": file_payload,
        "tracks": tracks_analysis,
        "sequences": sequence_summaries,
        "primary_sequence_index": primary_index,
    }


def _controller_inventory(parse: ParseResult) -> dict[str, Any]:
    counts: Counter[int] = Counter()
    values: dict[int, int] = {}
    tracks_with_sustain = 0
    for seq in parse.sequences:
        for track in seq.tracks:
            counts.update(track.controller_counts)
            for key, value in track.controller_values.items():
                values[key] = value
            if track.sustain_events:
                tracks_with_sustain += 1
    cc_names = {
        0: "Bank select MSB", 1: "Modulation", 7: "Volume", 10: "Pan",
        11: "Expression", 32: "Bank select LSB", 64: "Sustain", 91: "Reverb",
        93: "Chorus", 120: "All sound off", 121: "Reset controllers",
        123: "All notes off",
    }
    return {
        "counts": {str(code): count for code, count in sorted(counts.items())},
        "values": {str(code): value for code, value in sorted(values.items())},
        "named": [
            {"code": code, "name": cc_names.get(code, f"CC {code}"), "count": count}
            for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12]
        ],
        "tracks_with_sustain": tracks_with_sustain,
    }
