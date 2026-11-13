"""Versions that invalidate cached parsing/classification work.

Bump ``PARSER_VERSION`` when the parser output schema or timing semantics
changes. Bump ``CLASSIFIER_VERSION`` when the rules or their features change.
User corrections and collections live outside this cache and survive both.
"""

PARSER_VERSION = 1
CLASSIFIER_VERSION = 1
CLASSIFIER_METHOD = "SKEER transparent rules"
CLASSIFIER_RULESET = "rules-1"
SCHEMA_VERSION = 1

SUPPORTED_EXTENSIONS = {".mid", ".midi"}
MAX_FILE_BYTES = 64 * 1024 * 1024
