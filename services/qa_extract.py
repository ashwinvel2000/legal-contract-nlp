from __future__ import annotations

import re
from typing import Dict, List, Optional

from core import config, model, utils
from services import ner_fallback

_ROLE_KEYWORDS = {word.lower() for word in config.ROLE_STOPWORDS}
_PARTY_EXCLUSIONS = {word.lower() for word in config.PARTY_EXCLUSION_TERMS}
_ORG_KEY_HINTS = {token.lower() for token in config.ORG_BOOST_TOKENS}
_MIN_PARTY_CONFIDENCE = 0.15
_MAX_PARTY_CONFIDENCE = 0.99
_MIN_ORG_LEN = 4

_QA_QUESTIONS = {
    "parties": "Who are the parties to the contract?",
    "party_a": "Who is the first party to the contract?",
    "party_b": "Who is the second party to the contract?",
    "party_shipper": "Who is the Shipper in the contract?",
    "party_transporter": "Who is the Transporter in the contract?",
    "agreement_date": "What is the agreement date?",
    "effective_date": "What is the effective date?",
    "governing_law": "What law governs the agreement?",
}


def _locate_span(context: str, answer: str) -> Optional[List[int]]:
    if not answer:
        return None
    direct = context.find(answer)
    if direct != -1:
        return [direct, direct + len(answer)]
    lowered = context.lower()
    lowered_answer = answer.lower()
    approx = lowered.find(lowered_answer)
    if approx != -1:
        return [approx, approx + len(answer)]
    return None


def _build_evidence(text: str, span: Optional[List[int]]) -> Optional[str]:
    if span is None:
        return None
    return utils.find_near_phrase(text, span[0])


def _dedupe_entities(entities: List[Dict[str, object]]) -> List[Dict[str, object]]:
    seen: dict[str, Dict[str, object]] = {}
    for entity in entities:
        value = (entity.get("value") or "").strip()
        if not value:
            continue
        norm = re.sub(r"[^a-z0-9]", "", value.lower())
        if not norm:
            continue
        stored = seen.get(norm)
        if stored is None or float(entity.get("confidence", 0.0)) > float(stored.get("confidence", 0.0)):
            seen[norm] = entity
    return sorted(seen.values(), key=lambda item: (-float(item.get("confidence", 0.0)), item.get("page", 0)))


def _collect_parties_from_answer(
    page: Dict[str, object],
    answer: str,
    score: float,
    extra_answers: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    text = str(page["text"])
    page_number = int(page["page"])
    span = _locate_span(text, answer)
    snippet_start = (span[0] if span else text.find(answer))
    if snippet_start == -1:
        snippet_start = 0
    window_start = max(0, snippet_start - 200)
    window_end = min(len(text), (span[1] if span else snippet_start + len(answer)) + 200)
    snippet = text[window_start:window_end]
    ner = model.get_ner()
    candidates: List[Dict[str, object]] = []
    try:
        ner_results = ner(snippet)
    except Exception:
        ner_results = []
    for entity in ner_results:
        if (entity.get("entity_group") or entity.get("entity")) not in {"ORG", "MISC", "PER"}:
            continue
        value = snippet[entity["start"] : entity["end"]].strip()
        if not value:
            continue
        lowered_value = value.lower()
        if lowered_value in _ROLE_KEYWORDS:
            continue
        if any(term in lowered_value for term in _PARTY_EXCLUSIONS):
            continue
        start = window_start + int(entity["start"])
        end = window_start + int(entity["end"])
        confidence = float(entity.get("score", 0.0))
        hints = {token for token in _ORG_KEY_HINTS if token in lowered_value}
        adjusted_conf = confidence if confidence > 0 else score
        if hints:
            adjusted_conf = max(adjusted_conf, confidence + 0.1)
        candidates.append(
            {
                "value": value,
                "page": page_number,
                "span": [start, end],
                "confidence": min(max(adjusted_conf, _MIN_PARTY_CONFIDENCE), _MAX_PARTY_CONFIDENCE),
                "evidence": _build_evidence(text, [start, end]),
            }
        )
    if not candidates and answer:
        span = _locate_span(text, answer)
        candidates.append(
            {
                "value": answer.strip(),
                "page": page_number,
                "span": span,
                "confidence": score,
                "evidence": _build_evidence(text, span),
            }
        )
    role_pattern = re.compile(
        r"([A-Z][A-Za-z&.,'\-]*(?:\s+[A-Z0-9][A-Za-z&.,'\-]*){1,5})\s*\((?:the\s+)?(transporter|shipper|seller|buyer|licensor|licensee|borrower|lender)\)",
        re.IGNORECASE,
    )
    for match in role_pattern.finditer(snippet):
        value = match.group(1).strip()
        lowered_value = value.lower()
        if lowered_value in _ROLE_KEYWORDS:
            continue
        if any(term in lowered_value for term in _PARTY_EXCLUSIONS):
            continue
        value = value.removeprefix("and ").removeprefix("& ")
        value = value.strip()
        if not value:
            continue
        value = re.sub(r"^(?:and|&|and\s*&|&\s*and)\s+", "", value, flags=re.IGNORECASE)
        value = value.strip()
        if not value:
            continue
        lowered_value = value.lower()
        if lowered_value in _ROLE_KEYWORDS:
            continue
        if any(term in lowered_value for term in _PARTY_EXCLUSIONS):
            continue
        start = window_start + match.start(1)
        end = window_start + match.end(1)
        candidates.append(
            {
                "value": value,
                "page": page_number,
                "span": [start, end],
                "confidence": max(score, 0.4),
                "evidence": _build_evidence(text, [start, end]),
            }
        )
    if extra_answers:
        for alt in extra_answers:
            alt = (alt or "").strip()
            if not alt:
                continue
            alt_span = _locate_span(text, alt)
            if not alt_span:
                continue
            alt_value = text[alt_span[0] : alt_span[1]].strip()
            if alt_value.lower() in _ROLE_KEYWORDS:
                continue
            candidates.append(
                {
                    "value": alt_value,
                    "page": page_number,
                    "span": alt_span,
                    "confidence": max(score - 0.05, _MIN_PARTY_CONFIDENCE),
                    "evidence": _build_evidence(text, alt_span),
                }
            )
    return candidates


def _fallback_parties(pages: List[Dict[str, object]]) -> List[Dict[str, object]]:
    fallback: List[Dict[str, object]] = []
    for page in pages:
        text = str(page["text"])
        page_number = int(page["page"])
        for candidate in ner_fallback.find_parties(text):
            span = candidate.get("span")
            fallback.append(
                {
                    "value": candidate.get("value"),
                    "page": page_number,
                    "span": span if span else None,
                    "confidence": float(candidate.get("confidence", 0.35)),
                    "evidence": _build_evidence(text, span if span else None),
                }
            )
    return fallback


def _keyword_search_date(
    pages: List[Dict[str, object]], keywords: tuple[str, ...]
) -> Optional[Dict[str, object]]:
    for page in pages:
        text = str(page["text"])
        lowered = text.lower()
        page_number = int(page["page"])
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword), lowered):
                window_start = match.end()
                window_end = min(len(text), window_start + 160)
                window = text[window_start:window_end]
                date_match = config.DATE_PATTERN.search(window)
                if date_match:
                    start = window_start + date_match.start()
                    end = window_start + date_match.end()
                    value = window[date_match.start() : date_match.end()].strip()
                    return {
                        "value": value,
                        "page": page_number,
                        "span": [start, end],
                        "confidence": 0.4,
                        "evidence": _build_evidence(text, [start, end]),
                    }
    for page in pages:
        text = str(page["text"])
        page_number = int(page["page"])
        match = config.DATE_PATTERN.search(text)
        if match:
            start, end = match.start(), match.end()
            return {
                "value": match.group(0).strip(),
                "page": page_number,
                "span": [start, end],
                "confidence": 0.3,
                "evidence": _build_evidence(text, [start, end]),
            }
    return None


def _find_contextual_date(
    pages: List[Dict[str, object]], cues: tuple[str, ...], exclude_span: Optional[List[int]] = None
) -> Optional[Dict[str, object]]:
    lowered_cues = tuple(cue.lower() for cue in cues)
    for page in pages:
        text = str(page["text"])
        lowered = text.lower()
        for match in config.DATE_PATTERN.finditer(text):
            start, end = match.start(), match.end()
            span = [start, end]
            if exclude_span and span == exclude_span:
                continue
            window = lowered[max(0, start - 60) : start]
            if any(cue in window for cue in lowered_cues):
                value = match.group(0).strip()
                return {
                    "value": value,
                    "page": int(page["page"]),
                    "span": span,
                    "confidence": 0.45,
                    "evidence": _build_evidence(text, span),
                }
    return None


def _extract_simple_field(field: str, pages: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    qa = model.get_qa()
    question = _QA_QUESTIONS[field]
    best: Optional[Dict[str, object]] = None
    for page in pages:
        text = str(page["text"])
        if not text.strip():
            continue
        try:
            answer = qa(question=question, context=text)
        except Exception:
            continue
        score = float(answer.get("score", 0.0))
        if score < config.QA_SCORE_THRESHOLD:
            continue
        value = (answer.get("answer") or "").strip()
        if not value:
            continue
        span = _locate_span(text, value)
        record = {
            "value": value,
            "page": int(page["page"]),
            "span": span,
            "confidence": score,
            "evidence": _build_evidence(text, span),
        }
        if best is None or score > best["confidence"]:
            best = record
    return best


def _extract_date_field(
    field: str,
    pages: List[Dict[str, object]],
    keywords: tuple[str, ...],
) -> Optional[Dict[str, object]]:
    qa = model.get_qa()
    best: Optional[Dict[str, object]] = None
    question = _QA_QUESTIONS[field]
    for page in pages:
        text = str(page["text"])
        if not text.strip():
            continue
        try:
            answer = qa(question=question, context=text)
        except Exception:
            continue
        score = float(answer.get("score", 0.0))
        value = (answer.get("answer") or "").strip()
        if not value:
            continue
        span = _locate_span(text, value)
        if not config.DATE_PATTERN.search(value):
            continue
        record = {
            "value": value,
            "page": int(page["page"]),
            "span": span,
            "confidence": score,
            "evidence": _build_evidence(text, span),
        }
        if best is None or score > best["confidence"]:
            best = record
    if best and best["confidence"] >= config.QA_SCORE_THRESHOLD:
        return best
    fallback = _keyword_search_date(pages, keywords)
    if fallback:
        if not best or fallback["confidence"] >= best["confidence"]:
            return fallback
    return best


def extract_fields(pages: List[Dict[str, object]]) -> Dict[str, object]:
    parties_candidates: List[Dict[str, object]] = []
    qa = model.get_qa()
    for page in pages:
        text = str(page["text"])
        if not text.strip():
            continue
        try:
            answer = qa(question=_QA_QUESTIONS["parties"], context=text)
        except Exception:
            continue
        score = float(answer.get("score", 0.0))
        if score < config.QA_SCORE_THRESHOLD:
            continue
        value = (answer.get("answer") or "").strip()
        if not value:
            continue
        extra_answers: List[str] = []
        try:
            alt_answers = qa(
                question=_QA_QUESTIONS["parties"],
                context=text,
                top_k=4,
            )
            if isinstance(alt_answers, list):
                extra_answers = [item.get("answer", "") for item in alt_answers if item.get("answer")]
        except Exception:
            extra_answers = []
        parties_candidates.extend(
            _collect_parties_from_answer(page, value, score, extra_answers=extra_answers)
        )
    if len(parties_candidates) < 2:
        # Ask additional targeted questions on pages where QA scored highest.
        ranked_pages = sorted(
            [
                (
                    idx,
                    page,
                    qa(
                        question=_QA_QUESTIONS["parties"],
                        context=str(page["text"]),
                    ).get("score", 0.0),
                )
                for idx, page in enumerate(pages)
                if str(page.get("text", "")).strip()
            ],
            key=lambda item: item[2],
            reverse=True,
        )
        targeted_questions = [
            _QA_QUESTIONS["party_a"],
            _QA_QUESTIONS["party_b"],
            _QA_QUESTIONS["party_shipper"],
            _QA_QUESTIONS["party_transporter"],
        ]
        for _, page, _ in ranked_pages[:1]:
            page_text = str(page["text"])
            if not page_text.strip():
                continue
            for question in targeted_questions:
                try:
                    targeted_answer = qa(question=question, context=page_text)
                except Exception:
                    continue
                t_score = float(targeted_answer.get("score", 0.0))
                if t_score < _MIN_PARTY_CONFIDENCE:
                    continue
                value = (targeted_answer.get("answer") or "").strip()
                if not value:
                    continue
                parties_candidates.extend(
                    _collect_parties_from_answer(page, value, t_score)
                )
    if len(parties_candidates) < 2:
        parties_candidates.extend(_fallback_parties(pages))
    filtered_candidates = []
    for candidate in parties_candidates:
        value = (candidate.get("value") or "").strip()
        if not value:
            continue
        stripped = re.sub(r"[^A-Za-z0-9&]", "", value)
        if len(stripped) < _MIN_ORG_LEN:
            continue
        lowered = value.lower()
        if lowered in _ROLE_KEYWORDS:
            continue
        if any(term in lowered for term in _PARTY_EXCLUSIONS):
            continue
        digits = sum(ch.isdigit() for ch in stripped)
        if digits and digits >= len(stripped) / 2:
            continue
        word_count = len(re.findall(r"[A-Za-z][A-Za-z&.'-]*", value))
        if word_count < 2:
            continue
        filtered_candidates.append(candidate)
    parties = _dedupe_entities(filtered_candidates)[:2]

    effective_date = _extract_date_field(
        "effective_date", pages, config.EFFECTIVE_DATE_KEYWORDS
    )
    agreement_date = _extract_date_field(
        "agreement_date", pages, config.AGREEMENT_DATE_KEYWORDS
    )
    if (
        effective_date
        and agreement_date
        and effective_date.get("value")
        and agreement_date.get("value")
        and agreement_date["value"] == effective_date["value"]
    ):
        contextual = _find_contextual_date(
            pages,
            config.AGREEMENT_DATE_CUES,
            exclude_span=effective_date.get("span"),
        )
        if contextual:
            agreement_date = contextual
    elif not agreement_date:
        contextual = _find_contextual_date(
            pages,
            config.AGREEMENT_DATE_CUES,
            exclude_span=effective_date.get("span") if effective_date else None,
        )
        if contextual:
            agreement_date = contextual

    governing_law = _extract_simple_field("governing_law", pages)

    return {
        "parties": parties,
        "effective_date": effective_date,
        "agreement_date": agreement_date,
        "governing_law": governing_law,
    }


__all__ = ["extract_fields", "_locate_span"]
