"""Application configuration constants for the legal MVP service."""
from __future__ import annotations

from datetime import timezone
import re
from typing import Final

QA_MODEL_NAME: Final[str] = "akdeniz27/roberta-base-cuad"
NER_MODEL_NAME: Final[str] = "dslim/bert-base-NER"
QA_SCORE_THRESHOLD: Final[float] = 0.25
MAX_SNIPPET_CHARS: Final[int] = 80
AUDIT_LOG_PATH: Final[str] = "audit.log"
DEFAULT_TIMEZONE = timezone.utc

DATE_REGEX: Final[str] = (
    r"\b(?:"
    r"\d{1,2}[\-/]?[A-Za-z]{3,9}[\-/]?\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")\b"
)
DATE_PATTERN: Final[re.Pattern[str]] = re.compile(DATE_REGEX)

EFFECTIVE_DATE_KEYWORDS: Final[tuple[str, ...]] = (
    "effective date",
    "date of this agreement",
    "effective as of",
)
AGREEMENT_DATE_KEYWORDS: Final[tuple[str, ...]] = (
    "agreement date",
    "dated as of",
    "agreement dated",
)
PARTY_KEYWORDS: Final[tuple[str, ...]] = (
    "between",
    "by and between",
    "among",
)
ORG_BOOST_TOKENS: Final[tuple[str, ...]] = (
    "inc",
    "inc.",
    "corp",
    "corp.",
    "corporation",
    "llc",
    "ltd",
    "limited",
    "company",
)

ROLE_STOPWORDS: Final[tuple[str, ...]] = (
    "transporter",
    "shipper",
    "seller",
    "buyer",
    "licensor",
    "licensee",
    "lender",
    "borrower",
)

AGREEMENT_DATE_CUES: Final[tuple[str, ...]] = (
    "agreement dated",
    "service agreement dated",
    "agreement date",
)

PARTY_EXCLUSION_TERMS: Final[tuple[str, ...]] = (
    "agreement",
    "contract",
    "appendix",
    "term",
    "article",
    "section",
    "schedule",
    "exhibit",
)
