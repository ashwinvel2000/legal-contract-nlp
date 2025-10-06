"""PDF text extraction for digital files."""
from __future__ import annotations

import io
import re
from typing import Dict, List

import pdfplumber

_CONTROL_CHAR_PATTERN = re.compile(r"[\u0000-\u001f\u007f]")


def _sanitize_text(text: str) -> str:
    cleaned = _CONTROL_CHAR_PATTERN.sub("", text)
    return cleaned.strip()


def extract_pages(pdf_bytes: bytes) -> List[Dict[str, object]]:
    """Extract textual content from each page of a digital PDF."""
    pages: List[Dict[str, object]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            text = _sanitize_text(raw_text)
            if text:
                pages.append({"page": page_number, "text": text})
    return pages
