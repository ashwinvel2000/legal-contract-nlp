"""Audit logging helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from core import config


def append_audit(file_hash: str, timestamp: str, fields: Iterable[Mapping[str, float]]) -> None:
    """Append a structured audit record; excludes raw document content."""
    record = {
        "file_sha256": file_hash,
        "timestamp_utc": timestamp,
        "fields": [
            {"field": entry.get("field"), "confidence": float(entry.get("confidence", 0.0))}
            for entry in fields
        ],
    }
    path = Path(config.AUDIT_LOG_PATH)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True))
        handle.write("\n")
