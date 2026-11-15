"""Versions that invalidate cached parsing/classification work.

Bump ``PARSER_VERSION`` when the parser output schema or timing semantics
changes. Bump ``CLASSIFIER_VERSION`` when the rules or their features change.
Bump ``FINGERPRINT_VERSION`` when the similarity fingerprint gains, drops or
re-scales a component — vectors from different generations are not comparable,
so they must never be cosine-scores against each other. User corrections and
collections live outside this cache and survive all three.

Bump ``SCHEMA_VERSION`` when the SQLite layout changes, and add the matching
``ALTER`` to ``MIGRATIONS`` in ``midivault/db.py`` with the key being the
version it migrates *from*. An index newer than this build is refused rather
than silently downgraded.
"""

PARSER_VERSION = 2
CLASSIFIER_VERSION = 1
CLASSIFIER_METHOD = "SKEER transparent rules"
CLASSIFIER_RULESET = "rules-1"
SCHEMA_VERSION = 2

# Generation of the fingerprint vectors written from here on. Fingerprint rows
# written before fingerprinting was versioned carry LEGACY_FINGERPRINT_VERSION
# and are excluded from similarity until they are re-indexed.
FINGERPRINT_VERSION = 1
LEGACY_FINGERPRINT_VERSION = 0

SUPPORTED_EXTENSIONS = {".mid", ".midi"}
MAX_FILE_BYTES = 64 * 1024 * 1024
