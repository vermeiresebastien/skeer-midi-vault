"""Plain data structures shared by the parser, analytics and classifier."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Note:
    start_tick: int
    end_tick: int
    start_beat: float
    end_beat: float
    start_seconds: float
    duration_seconds: float
    pitch: int
    velocity: int
    channel: int
    program: int | None = None
    assumed_duration: bool = False
    sustained: bool = False

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds

    def preview_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "b": round(self.start_beat, 6),
            "d": round(max(0.0, self.end_beat - self.start_beat), 6),
            "t": round(self.start_seconds, 6),
            "l": round(self.duration_seconds, 6),
            "p": self.pitch,
            "v": self.velocity,
        }
        if self.assumed_duration:
            d["a"] = 1
        if self.sustained:
            d["s"] = 1
        return d


@dataclass(slots=True)
class TempoEvent:
    tick: int
    beat: float
    seconds: float
    bpm: float
    microseconds: int
    embedded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "beat": round(self.beat, 6),
            "seconds": round(self.seconds, 6),
            "bpm": round(self.bpm, 4),
            "microseconds": self.microseconds,
            "embedded": self.embedded,
        }


@dataclass(slots=True)
class TimeSignatureEvent:
    tick: int
    beat: float
    numerator: int
    denominator: int
    clocks_per_click: int = 24
    notated_32nds: int = 8
    embedded: bool = True

    @property
    def label(self) -> str:
        return f"{self.numerator}/{self.denominator}"

    @property
    def beats_per_bar(self) -> float:
        return float(self.numerator) * 4.0 / float(self.denominator)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "beat": round(self.beat, 6),
            "numerator": self.numerator,
            "denominator": self.denominator,
            "label": self.label,
            "clocks_per_click": self.clocks_per_click,
            "notated_32nds": self.notated_32nds,
            "embedded": self.embedded,
        }


@dataclass(slots=True)
class KeySignatureEvent:
    tick: int
    beat: float
    sharps_flats: int
    minor: int
    label: str | None
    embedded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "beat": round(self.beat, 6),
            "sharps_flats": self.sharps_flats,
            "minor": self.minor,
            "label": self.label,
            "embedded": self.embedded,
        }


@dataclass(slots=True)
class TextEvent:
    tick: int
    beat: float
    text: str
    kind: str
    track_index: int = 0
    sequence_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "beat": round(self.beat, 6),
            "text": self.text,
            "kind": self.kind,
            "track_index": self.track_index,
            "sequence_index": self.sequence_index,
        }


@dataclass(slots=True)
class TrackData:
    sequence_index: int
    track_index: int
    chunk_index: int
    channel: int
    name: str | None
    instrument_name: str | None
    notes: list[Note] = field(default_factory=list)
    programs: list[int] = field(default_factory=list)
    program_events: list[dict[str, Any]] = field(default_factory=list)
    bank_msb: int | None = None
    bank_lsb: int | None = None
    controller_counts: dict[int, int] = field(default_factory=dict)
    controller_values: dict[int, int] = field(default_factory=dict)
    sustain_events: int = 0
    texts: list[TextEvent] = field(default_factory=list)
    assumed_durations: int = 0
    sustained_notes: int = 0
    orphan_note_offs: int = 0

    @property
    def program(self) -> int | None:
        return self.programs[0] if self.programs else None

    @property
    def pitch_min(self) -> int | None:
        return min((n.pitch for n in self.notes), default=None)

    @property
    def pitch_max(self) -> int | None:
        return max((n.pitch for n in self.notes), default=None)

    def preview_dict(self) -> dict[str, Any]:
        return {
            "sequence_index": self.sequence_index,
            "track_index": self.track_index,
            "chunk_index": self.chunk_index,
            "channel": self.channel,
            "name": self.name,
            "instrument_name": self.instrument_name,
            "program": self.program,
            "programs": sorted(set(self.programs)),
            "bank_msb": self.bank_msb,
            "bank_lsb": self.bank_lsb,
            "controller_counts": {str(k): v for k, v in sorted(self.controller_counts.items())},
            "controller_values": {str(k): v for k, v in sorted(self.controller_values.items())},
            "sustain_events": self.sustain_events,
            "assumed_durations": self.assumed_durations,
            "sustained_notes": self.sustained_notes,
            "notes": [n.preview_dict() for n in self.notes],
        }


@dataclass(slots=True)
class SequenceData:
    index: int
    name: str | None
    tracks: list[TrackData]
    tempos: list[TempoEvent]
    time_signatures: list[TimeSignatureEvent]
    key_signatures: list[KeySignatureEvent]
    texts: list[TextEvent]
    duration_seconds: float
    duration_beats: float
    end_tick: int
    timing_type: str
    ticks_per_quarter: int | None
    bars: float | None
    warnings: list[str] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        return sum(len(t.notes) for t in self.tracks)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    def preview_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "duration_seconds": round(self.duration_seconds, 6),
            "duration_beats": round(self.duration_beats, 6),
            "timing_type": self.timing_type,
            "ticks_per_quarter": self.ticks_per_quarter,
            "bars": None if self.bars is None else round(self.bars, 4),
            "tempos": [t.to_dict() for t in self.tempos],
            "time_signatures": [t.to_dict() for t in self.time_signatures],
            "key_signatures": [k.to_dict() for k in self.key_signatures],
            "texts": [t.to_dict() for t in self.texts[:200]],
            "warnings": list(self.warnings),
            "tracks": [t.preview_dict() for t in self.tracks],
        }


@dataclass(slots=True)
class ParseResult:
    format: int
    declared_track_count: int
    actual_track_count: int
    division: int
    timing_type: str
    ticks_per_quarter: int | None
    smpte_fps: float | None
    ticks_per_frame: int | None
    sequences: list[SequenceData]
    warnings: list[str] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        return sum(s.note_count for s in self.sequences)

    @property
    def duration_seconds(self) -> float:
        return max((s.duration_seconds for s in self.sequences), default=0.0)

    @property
    def duration_beats(self) -> float:
        return max((s.duration_beats for s in self.sequences), default=0.0)

    @property
    def is_format_2(self) -> bool:
        return self.format == 2

    def preview_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "declared_track_count": self.declared_track_count,
            "actual_track_count": self.actual_track_count,
            "division": self.division,
            "timing_type": self.timing_type,
            "ticks_per_quarter": self.ticks_per_quarter,
            "smpte_fps": self.smpte_fps,
            "ticks_per_frame": self.ticks_per_frame,
            "duration_seconds": round(self.duration_seconds, 6),
            "duration_beats": round(self.duration_beats, 6),
            "note_count": self.note_count,
            "warnings": list(self.warnings),
            "sequences": [s.preview_dict() for s in self.sequences],
        }
