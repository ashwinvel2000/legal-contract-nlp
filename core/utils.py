"""Utility helpers for hashing, timestamps, and snippets."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from core import config


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest for the provided bytes."""
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(tz=config.DEFAULT_TIMEZONE).isoformat()


def find_near_phrase(text: str, idx: int, window: int | None = None) -> Optional[str]:
    """Return a small snippet around ``idx`` within ``text`` for evidence."""
    if idx < 0 or not text:
        return None
    span = window or config.MAX_SNIPPET_CHARS
    start = max(0, idx - span)
    end = min(len(text), idx + span)
    snippet = text[start:end].strip()
    return snippet or None
