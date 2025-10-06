"""Fallback heuristics to identify contracting parties via NER."""
from __future__ import annotations

import re
from typing import Dict, List

from core import config, model

_WINDOW_AFTER_BETWEEN = 240
_DEFAULT_WINDOW = 800
_ACCEPTED_LABELS = {"ORG", "MISC", "PER"}


def _segment_text(text: str) -> List[tuple[int, str]]:
    lowered = text.lower()
    segments: List[tuple[int, str]] = []
    for keyword in config.PARTY_KEYWORDS:
        for match in re.finditer(re.escape(keyword), lowered):
            start = max(0, match.start())
            end = min(len(text), match.end() + _WINDOW_AFTER_BETWEEN)
            segments.append((start, text[start:end]))
    if not segments:
        segments.append((0, text[: min(len(text), _DEFAULT_WINDOW)]))
    return segments


def _boost_score(name: str, base: float) -> float:
    lowered = name.lower()
    for token in config.ORG_BOOST_TOKENS:
        if token in lowered:
            return min(base + 0.15, 1.0)
    return base


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_parties(text: str) -> List[Dict[str, object]]:
    """Return up to two likely party names from contract text."""
    ner = model.get_ner()
    candidates: dict[str, Dict[str, object]] = {}
    for offset, segment in _segment_text(text):
        if not segment.strip():
            continue
        try:
            results = ner(segment)
        except Exception:
            continue
        for entity in results:
            label = entity.get("entity_group") or entity.get("entity")
            if label not in _ACCEPTED_LABELS:
                continue
            value = segment[entity["start"] : entity["end"]].strip()
            if not value:
                continue
            norm = _normalize(value)
            if not norm:
                continue
            if value.lower() in config.ROLE_STOPWORDS:
                continue
            start = offset + int(entity["start"])
            end = offset + int(entity["end"])
            confidence = float(entity.get("score", 0.0))
            confidence = _boost_score(value, confidence)
            record = {
                "value": value,
                "span": [start, end],
                "confidence": confidence,
            }
            stored = candidates.get(norm)
            if stored is None or record["confidence"] > stored["confidence"]:
                candidates[norm] = record
    ordered = sorted(candidates.values(), key=lambda item: (-item["confidence"], item["span"][0]))
    return ordered[:2]
