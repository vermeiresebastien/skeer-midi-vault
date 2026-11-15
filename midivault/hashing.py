"""File digests used for duplicate identity and change detection.

Both definitions live here so the digest the incremental scan compares against
can never drift from the digest the pipeline stores.
"""
from __future__ import annotations

import hashlib

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str | None:
    """The same value ``sha256_bytes`` gives for the file's whole content.

    Returns None when the file cannot be read, which callers must treat as
    "unknown", never as "unchanged".
    """
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                block = handle.read(_CHUNK)
                if not block:
                    break
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()
