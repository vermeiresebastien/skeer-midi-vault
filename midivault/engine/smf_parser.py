"""A defensive Standard MIDI File parser.

Supported: Standard MIDI Files format 0, 1 and 2, running status, tempo maps,
metrical and SMPTE time divisions, sustain pedal, overlapping notes, program and
bank changes, controller summaries, names/text/metas, and key/time signatures.

Format 2 track chunks are kept as independent sequences. They are never merged
onto a shared timeline. Unknown chunks are skipped; malformed tracks are
reported as warnings when other tracks remain readable. Times are derived from
the embedded tempo map; when none exists 120 BPM is used *and marked assumed*.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Any

from .gm import program_name
from .model import (
    KeySignatureEvent,
    Note,
    ParseResult,
    SequenceData,
    TempoEvent,
    TextEvent,
    TimeSignatureEvent,
    TrackData,
)
from .versions import MAX_FILE_BYTES, PARSER_VERSION

_MAX_TRACKS = 1024
_MAX_EVENTS_PER_TRACK = 2_000_000
_MAX_NOTES_PER_TRACK = 500_000
_MAX_TEXT_EVENTS = 500

META_TEXT_KINDS = {
    0x01: "text",
    0x02: "copyright",
    0x03: "track_name",
    0x04: "instrument_name",
    0x05: "lyric",
    0x06: "marker",
    0x07: "cue",
    0x08: "program_name",
    0x09: "device_name",
}

_MAJOR_KEYS = {
    -7: "Cb", -6: "Gb", -5: "Db", -4: "Ab", -3: "Eb", -2: "Bb", -1: "F",
    0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#",
}
_MINOR_KEYS = {
    -7: "Ab", -6: "Eb", -5: "Bb", -4: "F", -3: "C", -2: "G", -1: "D",
    0: "A", 1: "E", 2: "B", 3: "F#", 4: "C#", 5: "G#", 6: "D#", 7: "A#",
}


class MidiParseError(ValueError):
    """Raised when a file is not a usable Standard MIDI File."""

    def __init__(self, message: str, code: str = "invalid_midi"):
        super().__init__(message)
        self.code = code


def _read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for i in range(8):
        if offset >= len(data):
            raise MidiParseError("Unexpected end of data while reading a variable-length value", "truncated_vlq")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            if i > 3:
                raise MidiParseError("Variable-length value exceeds the MIDI 4-byte limit", "bad_vlq")
            return value, offset
    raise MidiParseError("Variable-length value is unreasonably long", "bad_vlq")


def _decode_text(payload: bytes) -> str:
    if not payload:
        return ""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = payload.decode("cp1252")
        except UnicodeDecodeError:
            text = payload.decode("latin-1", errors="replace")
    text = "".join(ch if ch >= " " or ch in "\t\n\r" else " " for ch in text)
    return text.strip()[:500]


def _signed_byte(value: int) -> int:
    return value - 256 if value >= 128 else value


def _key_label(sharps_flats: int, minor: int) -> str | None:
    if not 0 <= minor <= 1 or not -7 <= sharps_flats <= 7:
        return None
    root = (_MINOR_KEYS if minor else _MAJOR_KEYS)[sharps_flats]
    return f"{root} {'minor' if minor else 'major'}"


@dataclass(slots=True)
class _OpenNote:
    start_tick: int
    velocity: int
    program: int | None


@dataclass
class _ChannelState:
    channel: int
    open_notes: dict[int, list[_OpenNote]] = field(default_factory=dict)
    waiting_pedal: list[tuple[_OpenNote, int, int]] = field(default_factory=list)
    sustain: bool = False
    current_program: int | None = None
    bank_msb: int | None = None
    bank_lsb: int | None = None
    programs: list[int] = field(default_factory=list)
    program_events: list[dict[str, Any]] = field(default_factory=list)
    controller_counts: dict[int, int] = field(default_factory=dict)
    controller_values: dict[int, int] = field(default_factory=dict)
    sustain_events: int = 0
    closed_notes: list[Note] = field(default_factory=list)
    assumed_durations: int = 0
    sustained_notes: int = 0
    orphan_note_offs: int = 0


@dataclass
class _RawTrack:
    chunk_index: int
    name: str | None = None
    instrument_name: str | None = None
    end_tick: int = 0
    channels: dict[int, _ChannelState] = field(default_factory=dict)
    tempos: list[tuple[int, int, int, float]] = field(default_factory=list)
    time_signatures: list[tuple[int, int, int, int, int, int]] = field(default_factory=list)
    key_signatures: list[tuple[int, int, int, int]] = field(default_factory=list)
    texts: list[TextEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    event_count: int = 0
    saw_end_of_track: bool = False


class _TrackEvent:
    __slots__ = ("kind", "tick", "channel", "data1", "data2", "payload", "order")

    def __init__(self, kind: str, tick: int, order: int, payload: Any = None,
                 channel: int | None = None, data1: int | None = None,
                 data2: int | None = None):
        self.kind = kind
        self.tick = tick
        self.order = order
        self.channel = channel
        self.data1 = data1
        self.data2 = data2
        self.payload = payload


def _close_pedal_notes(state: _ChannelState, end_tick: int, fallback_ticks: int) -> None:
    del fallback_ticks
    for open_note, _off_tick, _pitch in state.waiting_pedal:
        _add_note(state, open_note, _pitch, max(open_note.start_tick + 1, end_tick),
                  sustained=True, assumed=False)
    state.waiting_pedal.clear()


def _add_note(state: _ChannelState, open_note: _OpenNote, pitch: int, end_tick: int,
              *, sustained: bool, assumed: bool) -> None:
    state.closed_notes.append(
        Note(
            start_tick=open_note.start_tick,
            end_tick=max(open_note.start_tick + 1, end_tick),
            start_beat=0.0,
            end_beat=0.0,
            start_seconds=0.0,
            duration_seconds=0.0,
            pitch=max(0, min(127, int(pitch))),
            velocity=open_note.velocity,
            channel=state.channel,
            program=open_note.program,
            assumed_duration=assumed,
            sustained=sustained,
        )
    )
    if assumed:
        state.assumed_durations += 1
    if sustained:
        state.sustained_notes += 1


def _close_all_notes(state: _ChannelState, end_tick: int, fallback_ticks: int,
                     *, drums: bool) -> None:
    for pitch, notes in list(state.open_notes.items()):
        for open_note in notes:
            assumed = True
            cap = fallback_ticks
            candidate = min(end_tick, open_note.start_tick + cap)
            _add_note(state, open_note, pitch, candidate, sustained=False, assumed=assumed)
        notes.clear()
    if state.waiting_pedal:
        for open_note, _off_tick, pitch in state.waiting_pedal:
            cap = fallback_ticks
            candidate = min(end_tick, open_note.start_tick + cap)
            _add_note(state, open_note, pitch, candidate, sustained=True, assumed=True)
        state.waiting_pedal.clear()
    state.sustain = False


def _parse_track(data: bytes, chunk_index: int, ticks_per_quarter: int | None,
                 ticks_per_second: float | None) -> _RawTrack:
    raw = _RawTrack(chunk_index=chunk_index)
    offset = 0
    abs_tick = 0
    last_event_tick = 0
    running_status: int | None = None
    order = 0
    event_cap_hit = False
    note_cap_hit = False

    if ticks_per_quarter:
        melodic_fallback = max(1, int(ticks_per_quarter * 4))
        drum_fallback = max(1, int(ticks_per_quarter / 4))
    else:
        tps = ticks_per_second or 500.0
        melodic_fallback = max(1, int(tps))
        drum_fallback = max(1, int(tps * 0.05))

    while offset < len(data):
        if raw.event_count >= _MAX_EVENTS_PER_TRACK:
            raw.warnings.append("Event safety cap reached; remaining track data ignored")
            event_cap_hit = True
            break
        event_start = offset
        try:
            delta, offset = _read_vlq(data, offset)
        except MidiParseError as exc:
            raw.warnings.append(str(exc))
            offset = len(data)
            break
        abs_tick += delta
        last_event_tick = max(last_event_tick, abs_tick)
        if offset >= len(data):
            raw.warnings.append("Track ended after a delta time without an event")
            break
        status_byte = data[offset]
        if status_byte & 0x80:
            status = status_byte
            offset += 1
            if status < 0xF0:
                running_status = status
            else:
                running_status = None
        else:
            if running_status is None:
                raw.warnings.append(f"Data byte 0x{status_byte:02X} without a running status at byte {event_start}")
                offset = len(data)
                break
            status = running_status

        if status == 0xFF:
            running_status = None
            try:
                if offset >= len(data):
                    raise MidiParseError("Meta event missing a type byte", "truncated_meta")
                meta_type = data[offset]
                offset += 1
                length, offset = _read_vlq(data, offset)
                if offset + length > len(data):
                    raw.warnings.append("Truncated meta event payload")
                    length = max(0, len(data) - offset)
                payload = data[offset:offset + length]
                offset += length
                _handle_meta(raw, meta_type, payload, abs_tick, chunk_index, order)
                if meta_type == 0x2F:
                    raw.saw_end_of_track = True
                    raw.end_tick = max(last_event_tick, abs_tick)
                    if offset < len(data):
                        raw.warnings.append("Data after End of Track ignored")
                    break
            except MidiParseError as exc:
                raw.warnings.append(str(exc))
                break
            order += 1
            raw.event_count += 1
            continue

        if status in (0xF0, 0xF7):
            running_status = None
            try:
                length, offset = _read_vlq(data, offset)
            except MidiParseError as exc:
                raw.warnings.append(str(exc))
                break
            if offset + length > len(data):
                raw.warnings.append("Truncated system-exclusive event")
                offset = len(data)
                break
            offset += length
            order += 1
            raw.event_count += 1
            continue

        if status >= 0xF0:
            raw.warnings.append(f"Unsupported status 0x{status:02X}; track stopped")
            break

        channel = status & 0x0F
        kind = status & 0xF0
        data_len = 1 if kind in (0xC0, 0xD0) else 2
        if offset + data_len > len(data):
            raw.warnings.append("Truncated channel event")
            break
        data1 = data[offset]
        data2 = data[offset + 1] if data_len == 2 else 0
        if data1 & 0x80 or (data_len == 2 and data2 & 0x80):
            raw.warnings.append(f"Invalid data byte in channel event at byte {event_start}")
            break
        offset += data_len
        order += 1
        raw.event_count += 1

        state = raw.channels.setdefault(channel, _ChannelState(channel=channel))
        if kind == 0x90 and data2 > 0:
            if sum(len(v) for v in state.open_notes.values()) >= _MAX_NOTES_PER_TRACK:
                if not note_cap_hit:
                    raw.warnings.append("Note safety cap reached; further notes ignored")
                    note_cap_hit = True
                continue
            state.open_notes.setdefault(data1, []).append(
                _OpenNote(start_tick=abs_tick, velocity=data2, program=state.current_program)
            )
        elif kind == 0x80 or (kind == 0x90 and data2 == 0):
            queue = state.open_notes.get(data1)
            if not queue:
                state.orphan_note_offs += 1
            else:
                open_note = queue.pop(0)
                if not queue:
                    state.open_notes.pop(data1, None)
                if state.sustain:
                    state.waiting_pedal.append((open_note, abs_tick, data1))
                else:
                    _add_note(state, open_note, data1, abs_tick, sustained=False, assumed=False)
        elif kind == 0xB0:
            controller = data1
            value = data2
            state.controller_counts[controller] = state.controller_counts.get(controller, 0) + 1
            state.controller_values[controller] = value
            if controller == 0:
                state.bank_msb = value
            elif controller == 32:
                state.bank_lsb = value
            elif controller == 64:
                new_sustain = value >= 64
                state.sustain_events += 1
                if new_sustain and not state.sustain:
                    state.sustain = True
                elif not new_sustain and state.sustain:
                    _close_pedal_notes(state, abs_tick,
                                      melodic_fallback if channel != 9 else drum_fallback)
                    state.sustain = False
            elif controller == 120:
                _close_all_notes(state, abs_tick,
                                 melodic_fallback if channel != 9 else drum_fallback,
                                 drums=channel == 9)
            elif controller == 123:
                _close_all_notes(state, abs_tick,
                                 melodic_fallback if channel != 9 else drum_fallback,
                                 drums=channel == 9)
            # Other controllers are summarised, not interpreted musically.
        elif kind == 0xC0:
            state.current_program = data1
            state.programs.append(data1)
            state.program_events.append({
                "tick": abs_tick,
                "program": data1,
                "bank_msb": state.bank_msb,
                "bank_lsb": state.bank_lsb,
            })
        # 0xA0 poly pressure, 0xD0 channel pressure and 0xE0 pitch bend are
        # intentionally accepted and ignored for index statistics.

    if not raw.saw_end_of_track:
        raw.warnings.append("Missing End of Track meta event")
    if event_cap_hit:
        raw.warnings.append("Track parsed only up to the event safety cap")

    end_tick = max(last_event_tick, raw.end_tick)
    for channel, state in raw.channels.items():
        _close_all_notes(
            state, max(end_tick, state.closed_notes[-1].end_tick if state.closed_notes else end_tick),
            melodic_fallback if channel != 9 else drum_fallback,
            drums=channel == 9,
        )
    return raw


def _handle_meta(raw: _RawTrack, meta_type: int, payload: bytes, tick: int,
                 chunk_index: int, order: int) -> None:
    if meta_type in META_TEXT_KINDS:
        text = _decode_text(payload)
        if text:
            kind = META_TEXT_KINDS[meta_type]
            if kind == "track_name" and not raw.name:
                raw.name = text
            elif kind == "instrument_name" and not raw.instrument_name:
                raw.instrument_name = text
            if len(raw.texts) < _MAX_TEXT_EVENTS:
                raw.texts.append(TextEvent(
                    tick=tick, beat=0.0, text=text, kind=kind,
                    track_index=chunk_index, sequence_index=0,
                ))
        return
    if meta_type == 0x51:
        if len(payload) < 3:
            raw.warnings.append("Truncated tempo meta event")
            return
        microseconds = int.from_bytes(payload[:3], "big")
        if microseconds <= 0:
            raw.warnings.append("Ignored invalid zero tempo")
            return
        if microseconds < 1000:
            raw.warnings.append("Unusually fast tempo accepted from file")
        raw.tempos.append((tick, order, microseconds, 60_000_000.0 / microseconds))
        return
    if meta_type == 0x58:
        if len(payload) < 4:
            raw.warnings.append("Truncated time-signature meta event")
            return
        numerator = payload[0]
        exponent = payload[1]
        clocks = payload[2] if len(payload) > 2 else 24
        thirty_seconds = payload[3] if len(payload) > 3 else 8
        if numerator <= 0:
            raw.warnings.append("Ignored invalid zero-numerator time signature")
            return
        if exponent > 8:
            raw.warnings.append(f"Unusual time-signature denominator exponent {exponent} accepted")
        denominator = 2 ** min(exponent, 16)
        raw.time_signatures.append((tick, order, numerator, denominator, clocks, thirty_seconds))
        return
    if meta_type == 0x59:
        if len(payload) < 2:
            raw.warnings.append("Truncated key-signature meta event")
            return
        sharps_flats = _signed_byte(payload[0])
        minor = payload[1]
        if not -7 <= sharps_flats <= 7 or minor not in (0, 1):
            raw.warnings.append("Key signature outside the Standard MIDI File range")
        raw.key_signatures.append((tick, order, sharps_flats, minor))
        return
    # Sequence number, SMPTE offset, sequencer-specific, copyright and other
    # meta events do not change library timing or labels.
    del chunk_index


def _unique_by_tick(events: list[tuple]) -> list[tuple[int, tuple]]:
    """Sort by (tick, order), keep the last event at each tick.

    Event tuples are ``(tick, order, *payload)``; the payload shape differs per
    meta event type.
    """
    by_tick: dict[int, tuple] = {}
    for event in sorted(events, key=lambda item: (item[0], item[1])):
        tick = event[0]
        by_tick[tick] = tuple(event[2:])
    return sorted(by_tick.items())


def _build_tempo_map(raw_events: list[tuple[int, int, int, float]], tick_rate: int | None,
                     ticks_per_second: float | None) -> tuple[list[TempoEvent], bool]:
    unique = _unique_by_tick(raw_events)
    entries: list[TempoEvent] = []
    embedded = bool(unique)
    last_tick = 0
    last_seconds = 0.0
    current_bpm = 120.0
    current_us = 500_000
    first = True
    if unique and unique[0][0] == 0:
        tick, (microseconds, bpm) = unique[0]
        current_bpm = bpm
        current_us = microseconds
        entries.append(TempoEvent(0, 0.0, 0.0, bpm, microseconds, embedded=True))
        unique = unique[1:]
    else:
        entries.append(TempoEvent(0, 0.0, 0.0, 120.0, 500_000, embedded=False))
    for tick, (microseconds, bpm) in unique:
        if tick < last_tick:
            tick = last_tick
        if tick == last_tick:
            # A later event at the same tick wins.
            if entries and entries[-1].tick == tick:
                entries[-1] = TempoEvent(tick, tick / tick_rate if tick_rate else 0.0,
                                         last_seconds, bpm, microseconds, embedded=True)
            current_bpm = bpm
            current_us = microseconds
            continue
        if tick_rate:
            last_seconds += (tick - last_tick) / tick_rate * (60.0 / current_bpm)
        else:
            tps = ticks_per_second or 500.0
            last_seconds += (tick - last_tick) / tps
        last_tick = tick
        entries.append(TempoEvent(
            tick=tick,
            beat=tick / tick_rate if tick_rate else last_seconds * current_bpm / 60.0,
            seconds=last_seconds,
            bpm=bpm,
            microseconds=microseconds,
            embedded=True,
        ))
        current_bpm = bpm
        current_us = microseconds
        first = False
    del first, current_us
    return entries, embedded


def _seconds_at_tick(tempos: list[TempoEvent], tick: int, tick_rate: int | None,
                     ticks_per_second: float | None) -> float:
    if tick <= 0:
        return 0.0
    if not tempos:
        return 0.0
    if tick_rate is None:
        return tick / (ticks_per_second or 500.0)
    ticks = [t.tick for t in tempos]
    idx = bisect.bisect_right(ticks, tick) - 1
    idx = max(0, idx)
    entry = tempos[idx]
    return entry.seconds + (tick - entry.tick) / tick_rate * 60.0 / entry.bpm


def _beat_at_tick(tick: int, tick_rate: int | None, tempos: list[TempoEvent],
                  ticks_per_second: float | None) -> float:
    if tick_rate:
        return tick / tick_rate
    seconds = _seconds_at_tick(tempos, tick, None, ticks_per_second)
    bpm = tempos[0].bpm if tempos else 120.0
    return seconds * bpm / 60.0


def _build_time_signatures(raw: list[tuple[int, int, int, int, int, int]],
                           tick_rate: int | None, tempos: list[TempoEvent],
                           ticks_per_second: float | None) -> list[TimeSignatureEvent]:
    unique = _unique_by_tick(raw)
    events: list[TimeSignatureEvent] = []
    if not unique or unique[0][0] != 0:
        events.append(TimeSignatureEvent(0, 0.0, 4, 4, embedded=False))
    for tick, data in unique:
        numerator, denominator, clocks, thirty_seconds = data
        events.append(TimeSignatureEvent(
            tick=tick,
            beat=_beat_at_tick(tick, tick_rate, tempos, ticks_per_second),
            numerator=int(numerator),
            denominator=int(denominator),
            clocks_per_click=int(clocks),
            notated_32nds=int(thirty_seconds),
            embedded=True,
        ))
    return events


def _build_key_signatures(raw: list[tuple[int, int, int, int]],
                          tick_rate: int | None, tempos: list[TempoEvent],
                          ticks_per_second: float | None) -> list[KeySignatureEvent]:
    unique = _unique_by_tick(raw)
    events: list[KeySignatureEvent] = []
    for tick, data in unique:
        sharps_flats, minor = data
        events.append(KeySignatureEvent(
            tick=tick,
            beat=_beat_at_tick(tick, tick_rate, tempos, ticks_per_second),
            sharps_flats=int(sharps_flats),
            minor=int(minor),
            label=_key_label(int(sharps_flats), int(minor)),
        ))
    return events


def _bars_for_sequence(events: list[TimeSignatureEvent], end_tick: int,
                       tick_rate: int) -> float:
    if tick_rate <= 0:
        return 0.0
    end_beat = end_tick / tick_rate
    useful = [e for e in events if e.tick / tick_rate <= end_beat]
    if not useful:
        return end_beat / 4.0
    bars = 0.0
    cursor_beat = 0.0
    current = useful[0]
    for event in useful[1:]:
        event_beat = event.tick / tick_rate
        if event_beat > cursor_beat:
            bars += (event_beat - cursor_beat) / max(current.beats_per_bar, 0.001)
            cursor_beat = event_beat
        current = event
    if end_beat > cursor_beat:
        bars += (end_beat - cursor_beat) / max(current.beats_per_bar, 0.001)
    return bars


def _convert_notes(state: _ChannelState, track: TrackData,
                   tick_rate: int | None, tempos: list[TempoEvent],
                   ticks_per_second: float | None) -> None:
    for note in state.closed_notes:
        note.start_beat = _beat_at_tick(note.start_tick, tick_rate, tempos, ticks_per_second)
        note.end_beat = _beat_at_tick(note.end_tick, tick_rate, tempos, ticks_per_second)
        note.start_seconds = _seconds_at_tick(tempos, note.start_tick, tick_rate, ticks_per_second)
        note.duration_seconds = max(
            0.0001,
            _seconds_at_tick(tempos, note.end_tick, tick_rate, ticks_per_second) - note.start_seconds,
        )
        track.notes.append(note)
    track.notes.sort(key=lambda n: (n.start_tick, n.pitch, -n.velocity))
    track.notes = track.notes[:_MAX_NOTES_PER_TRACK]
    track.assumed_durations = sum(1 for n in track.notes if n.assumed_duration)
    track.sustained_notes = sum(1 for n in track.notes if n.sustained)


def _make_logical_tracks(raw: _RawTrack, sequence_index: int,
                         tick_rate: int | None, tempos: list[TempoEvent],
                         ticks_per_second: float | None,
                         text_events: list[TextEvent]) -> list[TrackData]:
    channels_with_notes = [
        (channel, state) for channel, state in sorted(raw.channels.items())
        if state.closed_notes
    ]
    multiple = len(channels_with_notes) > 1
    tracks: list[TrackData] = []
    for logical_index, (channel, state) in enumerate(channels_with_notes):
        name = raw.name
        if name and multiple:
            name = f"{name} · Ch {channel + 1}"
        track = TrackData(
            sequence_index=sequence_index,
            track_index=logical_index,
            chunk_index=raw.chunk_index,
            channel=channel,
            name=name,
            instrument_name=raw.instrument_name,
            programs=sorted(set(state.programs)),
            program_events=state.program_events,
            bank_msb=state.bank_msb,
            bank_lsb=state.bank_lsb,
            controller_counts=dict(state.controller_counts),
            controller_values=dict(state.controller_values),
            sustain_events=state.sustain_events,
            texts=[t for t in raw.texts if t.kind in ("text", "marker", "lyric")
                   or t.kind == "track_name"],
            orphan_note_offs=state.orphan_note_offs,
        )
        _convert_notes(state, track, tick_rate, tempos, ticks_per_second)
        track.assumed_durations = state.assumed_durations
        track.sustained_notes = state.sustained_notes
        track.orphan_note_offs = state.orphan_note_offs
        tracks.append(track)
        text_events.extend(track.texts)
    return tracks


def _dedupe_texts(texts: list[TextEvent]) -> list[TextEvent]:
    seen: set[tuple[str, str, int]] = set()
    result: list[TextEvent] = []
    for text in sorted(texts, key=lambda t: (t.sequence_index, t.tick, t.text)):
        key = (text.kind, text.text.casefold(), text.track_index)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= _MAX_TEXT_EVENTS:
            break
    return result


def _parse_header(data: bytes) -> tuple[int, int, int]:
    if len(data) < 14:
        raise MidiParseError("File is too small to be a Standard MIDI File", "truncated_header")
    if data[:4] == b"RIFF":
        raise MidiParseError("RIFF/RMID containers are not supported; use a .mid Standard MIDI File", "rif_midi")
    if data[:4] != b"MThd":
        raise MidiParseError("Missing MThd header; not a Standard MIDI File", "missing_header")
    header_length = int.from_bytes(data[4:8], "big")
    if header_length < 6 or 8 + header_length > len(data):
        raise MidiParseError("Invalid or truncated MThd header length", "bad_header_length")
    midi_format = int.from_bytes(data[8:10], "big")
    declared_tracks = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    if midi_format not in (0, 1, 2):
        raise MidiParseError(f"Unsupported MIDI format {midi_format}", "unsupported_format")
    if division == 0:
        raise MidiParseError("Invalid zero time division", "bad_division")
    return midi_format, declared_tracks, division


def parse_smf(data: bytes) -> ParseResult:
    if not data:
        raise MidiParseError("Empty file", "empty")
    if len(data) > MAX_FILE_BYTES:
        raise MidiParseError(
            f"File is larger than the {MAX_FILE_BYTES // (1024 * 1024)} MB safety limit",
            "file_too_large",
        )
    midi_format, declared_tracks, division = _parse_header(data)
    if declared_tracks > _MAX_TRACKS:
        raise MidiParseError("MIDI header declares too many tracks", "too_many_tracks")
    if declared_tracks == 0:
        raise MidiParseError("MIDI header declares zero tracks", "zero_tracks")

    if division & 0x8000:
        timing_type = "smpte"
        fps_byte = (division >> 8) & 0xFF
        fps = 256 - fps_byte
        ticks_per_frame = division & 0xFF
        if ticks_per_frame == 0:
            raise MidiParseError("Invalid SMPTE division with zero ticks per frame", "bad_division")
        if fps not in (24, 25, 29, 30):
            raise MidiParseError(f"Unsupported SMPTE frame rate {fps}", "bad_smpte")
        smpte_fps = 29.97 if fps == 29 else float(fps)
        ticks_per_quarter = None
        ticks_per_second = smpte_fps * ticks_per_frame
    else:
        timing_type = "metrical"
        ticks_per_quarter = division & 0x7FFF
        if ticks_per_quarter <= 0:
            raise MidiParseError("Invalid ticks-per-quarter value", "bad_division")
        smpte_fps = None
        ticks_per_frame = None
        ticks_per_second = None

    header_length = int.from_bytes(data[4:8], "big")
    offset = 8 + header_length
    chunks: list[bytes] = []
    file_warnings: list[str] = []
    chunk_ids: list[str] = []
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_length = int.from_bytes(data[offset + 4:offset + 8], "big")
        offset += 8
        available = len(data) - offset
        if chunk_length > available:
            file_warnings.append(
                f"Chunk {chunk_id.decode('latin-1', 'replace')} is shorter than declared; parsed available data"
            )
            chunk_length = available
        payload = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_id == b"MTrk":
            chunks.append(payload)
            chunk_ids.append("MTrk")
        else:
            file_warnings.append(
                f"Skipped unknown chunk {chunk_id.decode('latin-1', 'replace')}"
            )
            chunk_ids.append(chunk_id.decode("latin-1", "replace"))
        if len(chunks) > _MAX_TRACKS:
            raise MidiParseError("Too many track chunks", "too_many_tracks")
    if offset < len(data):
        file_warnings.append("Trailing bytes after the last complete chunk were ignored")
    if not chunks:
        raise MidiParseError("No MTrk chunks found", "no_tracks")
    if midi_format == 0 and len(chunks) > 1:
        file_warnings.append(
            f"Format 0 declares one track but contains {len(chunks)} chunks; chunks share one timeline"
        )
    if declared_tracks != len(chunks):
        file_warnings.append(
            f"Header declares {declared_tracks} track(s); {len(chunks)} MTrk chunk(s) found"
        )

    raws: list[_RawTrack] = []
    parse_warnings: list[str] = []
    for chunk_index, chunk in enumerate(chunks):
        try:
            raw = _parse_track(chunk, chunk_index, ticks_per_quarter, ticks_per_second)
            raws.append(raw)
            for warning in raw.warnings:
                parse_warnings.append(f"Track chunk {chunk_index + 1}: {warning}")
        except Exception as exc:  # Defensive: a bad chunk must not abort valid ones.
            parse_warnings.append(f"Track chunk {chunk_index + 1} could not be parsed: {exc}")

    if not raws:
        raise MidiParseError(
            "None of the track chunks could be parsed: " + "; ".join(parse_warnings[:4]),
            "all_tracks_failed",
        )

    sequences: list[SequenceData] = []
    if midi_format == 2:
        raw_groups = [[raw] for raw in raws]
    else:
        raw_groups = [raws]

    for sequence_index, group in enumerate(raw_groups):
        all_tempos: list[tuple[int, int, int, float]] = []
        all_time_sigs: list[tuple[int, int, int, int, int, int]] = []
        all_key_sigs: list[tuple[int, int, int, int]] = []
        all_texts: list[TextEvent] = []
        for raw in group:
            all_tempos.extend(raw.tempos)
            all_time_sigs.extend(raw.time_signatures)
            all_key_sigs.extend(raw.key_signatures)
            all_texts.extend(raw.texts)
        tempos, tempo_embedded = _build_tempo_map(all_tempos, ticks_per_quarter, ticks_per_second)
        time_signatures = _build_time_signatures(all_time_sigs, ticks_per_quarter, tempos, ticks_per_second)
        key_signatures = _build_key_signatures(all_key_sigs, ticks_per_quarter, tempos, ticks_per_second)
        tracks: list[TrackData] = []
        track_texts: list[TextEvent] = []
        for raw in group:
            tracks.extend(_make_logical_tracks(
                raw, sequence_index, ticks_per_quarter, tempos, ticks_per_second, track_texts
            ))
        # A logical track index must be unique within the sequence. A format-1
        # file can have multiple chunks, each with channel tracks, so a simple
        # per-chunk index would collide.
        for unique_track_index, track in enumerate(tracks):
            track.track_index = unique_track_index
        for text in all_texts:
            text.sequence_index = sequence_index
        for text in track_texts:
            text.sequence_index = sequence_index
        all_texts.extend(track_texts)
        deduped_texts = _dedupe_texts(all_texts)

        end_tick = max((raw.end_tick for raw in group), default=0)
        end_tick = max([end_tick] + [n.end_tick for t in tracks for n in t.notes] +
                       [tick for tick, _o, _u, _b in all_tempos] +
                       [tick for tick, _o, _n, _d, _c, _t in all_time_sigs])
        duration_seconds = _seconds_at_tick(tempos, end_tick, ticks_per_quarter, ticks_per_second)
        duration_beats = _beat_at_tick(end_tick, ticks_per_quarter, tempos, ticks_per_second)
        bars = None
        if timing_type == "metrical" and ticks_per_quarter:
            bars = _bars_for_sequence(time_signatures, end_tick, ticks_per_quarter)

        sequence_name = None
        if midi_format == 2:
            candidate = next((raw.name for raw in group if raw.name), None)
            sequence_name = candidate or f"Sequence {sequence_index + 1}"

        warnings = list(parse_warnings)
        for raw in group:
            for warning in raw.warnings:
                entry = f"Track chunk {raw.chunk_index + 1}: {warning}"
                if entry not in warnings:
                    warnings.append(entry)
        for track in tracks:
            if track.orphan_note_offs:
                warnings.append(
                    f"Track {track.track_index + 1}: ignored {track.orphan_note_offs} unmatched note-off event(s)"
                )
            if track.assumed_durations:
                warnings.append(
                    f"Track {track.track_index + 1}: assumed the end of {track.assumed_durations} note(s) without a note-off"
                )
        seq = SequenceData(
            index=sequence_index,
            name=sequence_name,
            tracks=tracks,
            tempos=tempos,
            time_signatures=time_signatures,
            key_signatures=key_signatures,
            texts=deduped_texts,
            duration_seconds=duration_seconds,
            duration_beats=duration_beats,
            end_tick=end_tick,
            timing_type=timing_type,
            ticks_per_quarter=ticks_per_quarter,
            bars=bars,
            warnings=warnings,
        )
        sequences.append(seq)
        # File-level warning inventory so a details view can show all parser
        # observations without having to inspect every sequence separately.
        file_warnings.extend(seq.warnings)
        del tempo_embedded

    if timing_type == "smpte":
        file_warnings.append("SMPTE time division: tempo events do not drive timing")
    if midi_format == 2 and len(sequences) > 1:
        file_warnings.append(
            f"Format 2: {len(sequences)} independent sequences are indexed separately; "
            "they are never mixed onto one timeline"
        )
    file_warnings.extend(parse_warnings)
    # Deduplicate while preserving order.
    seen_warnings: set[str] = set()
    unique_warnings = []
    for warning in file_warnings:
        if warning not in seen_warnings:
            seen_warnings.add(warning)
            unique_warnings.append(warning)

    return ParseResult(
        format=midi_format,
        declared_track_count=declared_tracks,
        actual_track_count=len(chunks),
        division=division,
        timing_type=timing_type,
        ticks_per_quarter=ticks_per_quarter,
        smpte_fps=smpte_fps,
        ticks_per_frame=ticks_per_frame,
        sequences=sequences,
        warnings=unique_warnings,
    )


def parser_metadata() -> dict[str, Any]:
    return {
        "parser_version": PARSER_VERSION,
        "formats": [0, 1, 2],
        "timing": ["metrical", "smpte"],
        "max_file_bytes": MAX_FILE_BYTES,
        "max_tracks": _MAX_TRACKS,
        "max_notes_per_track": _MAX_NOTES_PER_TRACK,
        "program_count": 128,
        "program_name": program_name(0),
        "dummy_float": math.nan if False else 0.0,
    }
