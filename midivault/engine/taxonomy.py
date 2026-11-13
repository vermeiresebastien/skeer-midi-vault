"""Shared category vocabulary and General MIDI family mapping."""
from __future__ import annotations

import re

from .gm import INSTRUMENT_KEYWORDS, ROLE_KEYWORDS

INSTRUMENT_CATEGORIES = [
    "Drums/percussion",
    "Bass",
    "Piano/keys",
    "Guitar/plucked",
    "Strings",
    "Brass/woodwinds",
    "Synth",
    "Mixed arrangement",
    "Unknown",
]

TRACK_INSTRUMENT_CATEGORIES = [c for c in INSTRUMENT_CATEGORIES if c != "Mixed arrangement"]

ROLE_CATEGORIES = [
    "Drum groove",
    "Drum fill",
    "Bassline",
    "Chord progression",
    "Lead/melody",
    "Arpeggio",
    "Pad/sustained harmony",
    "Complete song or multi-part arrangement",
    "Exercise or technical pattern",
    "Unknown",
]

TRACK_ROLE_CATEGORIES = [
    r for r in ROLE_CATEGORIES if r != "Complete song or multi-part arrangement"
]

FEEL_TAGS = ["straight", "swung", "sparse", "dense", "syncopated"]

GENRE_HINT_LABELS = [
    "Hip-hop / lo-fi beat",
    "House / techno",
    "Cinematic / ambient",
    "Jazz-leaning",
    "Rock / band",
    "Classical / acoustic",
    "Funk / groove",
    "Unknown",
]

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def pitch_class_set(pitches) -> set[int]:
    return {int(p) % 12 for p in pitches}


def program_category(program: int | None) -> str | None:
    """Map a GM program to the library's sound-family vocabulary."""
    if program is None:
        return None
    if not 0 <= program <= 127:
        return None
    if program <= 7:
        return "Piano/keys"
    if program <= 15:
        return "Piano/keys"
    if program <= 23:
        return "Piano/keys"
    if program <= 31:
        return "Guitar/plucked"
    if program <= 39:
        return "Bass"
    if program <= 55:
        return "Strings"
    if program <= 79:
        return "Brass/woodwinds"
    if program <= 103:
        return "Synth"
    if program in (104, 105, 106, 107):
        return "Guitar/plucked"
    if program == 108:
        return "Piano/keys"
    if program in (109, 111):
        return "Brass/woodwinds"
    if program == 110:
        return "Strings"
    if 112 <= program <= 119:
        return "Drums/percussion"
    if 120 <= program <= 127:
        return "Synth"
    return None


def _normalise_text(text: str) -> str:
    # Keep word boundaries: "flute" must not match the "lute" keyword.
    lowered = text.casefold().replace("-", " ").replace("_", " ").replace("/", " ")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return f" {re.sub(r' +', ' ', lowered).strip()} "


def _keyword_hits(text: str, keywords: tuple[str, ...] | list[str]) -> int:
    normalised = _normalise_text(text)
    hits = 0
    for keyword in keywords:
        needle = _normalise_text(keyword).strip()
        if not needle:
            continue
        # Permit simple plurals without opening the door to arbitrary substring hits.
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?:s)?(?![a-z0-9])"
        if re.search(pattern, normalised):
            hits += 1
    return hits


def instrument_keyword_categories(text: str) -> dict[str, float]:
    """Return per-family keyword confidence evidence from human text.

    Values are intentionally modest: names are context, never proof. Matching
    uses word boundaries so "flute" cannot imply "lute".
    """
    scores: dict[str, float] = {}
    for category, keywords in INSTRUMENT_KEYWORDS.items():
        hits = _keyword_hits(text, keywords)
        if hits:
            scores[category] = min(0.42, 0.20 + 0.11 * hits)
    return scores


def role_keyword_predictions(text: str) -> dict[str, float]:
    predictions: dict[str, float] = {}
    for role, keywords in ROLE_KEYWORDS.items():
        hits = _keyword_hits(text, keywords)
        if hits:
            predictions[role] = min(0.45, 0.22 + 0.10 * hits)
    return predictions


def tonic_name(pitch_class: int) -> str:
    return _NOTE_NAMES[int(pitch_class) % 12]
