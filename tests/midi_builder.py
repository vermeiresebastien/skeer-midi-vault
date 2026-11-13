"""Small dependency-free Standard MIDI File builder used by tests and fixtures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


def vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("VLQ cannot encode negative values")
    buffer = value & 0x7F
    value >>= 7
    while value:
        buffer <<= 8
        buffer |= (value & 0x7F) | 0x80
        value >>= 7
    out = bytearray()
    while True:
        out.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(out)


def meta(kind: int, payload: bytes) -> bytes:
    return bytes([0xFF, kind]) + vlq(len(payload)) + payload


@dataclass
class MidiTrack:
    events: list[tuple[int, int, bytes]] = field(default_factory=list)
    _order: int = 0

    def add(self, tick: int, data: bytes) -> "MidiTrack":
        self.events.append((int(tick), self._order, data))
        self._order += 1
        return self

    def tempo(self, tick: int, bpm: float) -> "MidiTrack":
        microseconds = int(round(60_000_000 / bpm))
        return self.add(tick, meta(0x51, microseconds.to_bytes(3, "big")))

    def time_signature(self, tick: int, numerator: int, denominator: int) -> "MidiTrack":
        exponent = 0
        value = denominator
        while value > 1:
            value //= 2
            exponent += 1
        return self.add(tick, meta(0x58, bytes([numerator, exponent, 24, 8])))

    def key_signature(self, tick: int, sharps_flats: int, minor: int = 0) -> "MidiTrack":
        sf = sharps_flats if sharps_flats >= 0 else sharps_flats + 256
        return self.add(tick, meta(0x59, bytes([sf, minor])))

    def track_name(self, name: str, tick: int = 0) -> "MidiTrack":
        return self.add(tick, meta(0x03, name.encode("utf-8")))

    def instrument_name(self, name: str, tick: int = 0) -> "MidiTrack":
        return self.add(tick, meta(0x04, name.encode("utf-8")))

    def text(self, tick: int, kind: int, value: str) -> "MidiTrack":
        return self.add(tick, meta(kind, value.encode("utf-8")))

    def marker(self, tick: int, value: str) -> "MidiTrack":
        return self.text(tick, 0x06, value)

    def program(self, tick: int, program: int, channel: int = 0) -> "MidiTrack":
        return self.add(tick, bytes([0xC0 | channel, program & 0x7F]))

    def bank(self, tick: int, msb: int, lsb: int = 0, channel: int = 0) -> "MidiTrack":
        self.add(tick, bytes([0xB0 | channel, 0, msb & 0x7F]))
        return self.add(tick, bytes([0xB0 | channel, 32, lsb & 0x7F]))

    def cc(self, tick: int, controller: int, value: int, channel: int = 0) -> "MidiTrack":
        return self.add(tick, bytes([0xB0 | channel, controller & 0x7F, value & 0x7F]))

    def sustain(self, tick: int, down: bool, channel: int = 0) -> "MidiTrack":
        return self.cc(tick, 64, 127 if down else 0, channel)

    def note_on(self, tick: int, pitch: int, velocity: int = 96,
                channel: int = 0) -> "MidiTrack":
        return self.add(tick, bytes([0x90 | channel, pitch & 0x7F, velocity & 0x7F]))

    def note_off(self, tick: int, pitch: int, velocity: int = 0,
                 channel: int = 0) -> "MidiTrack":
        return self.add(tick, bytes([0x80 | channel, pitch & 0x7F, velocity & 0x7F]))

    def note(self, tick: int, pitch: int, duration: int, velocity: int = 96,
             channel: int = 0) -> "MidiTrack":
        self.note_on(tick, pitch, velocity, channel)
        return self.note_off(tick + duration, pitch, 0, channel)

    def chord(self, tick: int, pitches: Iterable[int], duration: int,
              velocity: int = 96, channel: int = 0) -> "MidiTrack":
        pitches = list(pitches)
        for pitch in pitches:
            self.note_on(tick, pitch, velocity, channel)
        for pitch in pitches:
            self.note_off(tick + duration, pitch, 0, channel)
        return self

    def sysex(self, tick: int, payload: bytes) -> "MidiTrack":
        return self.add(tick, b"\xF0" + vlq(len(payload)) + payload)

    def raw(self, tick: int, data: bytes) -> "MidiTrack":
        return self.add(tick, data)

    def end(self, tick: int | None = None) -> "MidiTrack":
        last = max((event[0] for event in self.events), default=0)
        return self.add(last if tick is None else tick, meta(0x2F, b""))

    def to_bytes(self, running_status: bool = True, add_end: bool = True) -> bytes:
        events = sorted(self.events, key=lambda event: (event[0], event[1]))
        if add_end and not any(data[:2] == b"\xFF\x2F" for _tick, _order, data in events):
            last = max((event[0] for event in events), default=0)
            events.append((last, self._order + 1, meta(0x2F, b"")))
        out = bytearray()
        previous_tick = 0
        running: int | None = None
        for tick, _order, data in events:
            delta = max(0, tick - previous_tick)
            previous_tick = tick
            out += vlq(delta)
            if len(data) == 1:
                out += data
                running = None
                continue
            status = data[0]
            if running_status and 0x80 <= status <= 0xEF:
                if running == status:
                    out += data[1:]
                    continue
                out += data
                running = status
            else:
                out += data
                if 0x80 <= status <= 0xEF:
                    running = None
        return bytes(out)


def build_smf(tracks: list[MidiTrack], *, midi_format: int = 1, division: int = 480,
              declared_tracks: int | None = None, running_status: bool = True,
              end_tracks: bool = True) -> bytes:
    chunks = bytearray()
    for track in tracks:
        payload = track.to_bytes(running_status=running_status, add_end=end_tracks)
        chunks += b"MTrk" + len(payload).to_bytes(4, "big") + payload
    header = (
        b"MThd"
        + (6).to_bytes(4, "big")
        + int(midi_format).to_bytes(2, "big")
        + int(declared_tracks if declared_tracks is not None else len(tracks)).to_bytes(2, "big")
        + int(division).to_bytes(2, "big")
    )
    return header + bytes(chunks)


# Note helpers -------------------------------------------------------------

MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]


def scale_pitches(root: int, mode: str = "major", octaves: int = 1) -> list[int]:
    scale = MINOR_SCALE if mode == "minor" else MAJOR_SCALE
    return [root + interval + 12 * octave for octave in range(octaves) for interval in scale]


def arp_pitches(root: int, quality: str = "major", octaves: int = 2) -> list[int]:
    intervals = {"major": [0, 4, 7], "minor": [0, 3, 7], "dom7": [0, 4, 7, 10],
                 "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10]}.get(quality, [0, 4, 7])
    return [root + interval + 12 * octave for octave in range(octaves) for interval in intervals]
