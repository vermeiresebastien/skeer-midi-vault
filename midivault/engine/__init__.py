"""Framework-independent MIDI parsing, analysis and classification."""

from .analytics import analyze
from .classifier import classify
from .smf_parser import MidiParseError, parse_smf
from .versions import CLASSIFIER_VERSION, PARSER_VERSION

__all__ = [
    "MidiParseError",
    "parse_smf",
    "analyze",
    "classify",
    "PARSER_VERSION",
    "CLASSIFIER_VERSION",
]
