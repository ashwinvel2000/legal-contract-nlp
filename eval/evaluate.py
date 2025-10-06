"""Tiny evaluation harness over a handful of golden PDFs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional

from services import pdf_text, qa_extract

_GOLD_PATH = Path(__file__).with_name("golden.jsonl")
_FIELDS = ("party_a", "party_b", "effective_date", "agreement_date")


def _normalize(value: Optional[str]) -> str:
    if not value:
        return ""
    lowered = value.casefold().strip()
    return re.sub(r"[^a-z0-9]", "", lowered)


def _load_golden() -> list[dict[str, object]]:
    if not _GOLD_PATH.exists():
        raise FileNotFoundError(f"Golden file not found: {_GOLD_PATH}")
    records: list[dict[str, object]] = []
    with _GOLD_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def main() -> None:
    gold_records = _load_golden()
    stats: Dict[str, Dict[str, int]] = {
        field: {"correct": 0, "pred": 0, "gold": 0} for field in _FIELDS
    }

    for record in gold_records:
        file_path = Path(record["file"])
        if not file_path.exists():
            print(f"Skipping missing sample: {file_path}")
            continue
        pdf_bytes = file_path.read_bytes()
        pages = pdf_text.extract_pages(pdf_bytes)
        extracted = qa_extract.extract_fields(pages)

        parties = extracted.get("parties", [])
        predictions = {
            "party_a": parties[0]["value"] if len(parties) > 0 else None,
            "party_b": parties[1]["value"] if len(parties) > 1 else None,
            "effective_date": (extracted.get("effective_date") or {}).get("value"),
            "agreement_date": (extracted.get("agreement_date") or {}).get("value"),
        }

        for field in _FIELDS:
            gold_value = record.get(field)
            pred_value = predictions.get(field)
            if gold_value:
                stats[field]["gold"] += 1
            if pred_value:
                stats[field]["pred"] += 1
            if gold_value and pred_value and _normalize(gold_value) == _normalize(pred_value):
                stats[field]["correct"] += 1

    for field in _FIELDS:
        pred = stats[field]["pred"]
        gold = stats[field]["gold"]
        correct = stats[field]["correct"]
        precision = correct / pred if pred else 0.0
        recall = correct / gold if gold else 0.0
        print(
            f"{field}: precision={precision:.2f} recall={recall:.2f} "
            f"(correct={correct}, predicted={pred}, gold={gold})"
        )


if __name__ == "__main__":
    main()
