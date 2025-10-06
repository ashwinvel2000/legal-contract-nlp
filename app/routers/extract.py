from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from core import logging as audit_logging
from core import utils
from services import pdf_text, qa_extract

router = APIRouter(prefix="", tags=["extract"])


@router.post("/extract")
async def extract_entities(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    file_hash = utils.sha256_bytes(content)
    timestamp = utils.utc_now_iso()

    pages = pdf_text.extract_pages(content)
    if not pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Digital PDF text not found; scanned PDFs not supported.",
        )

    extraction = qa_extract.extract_fields(pages)

    entities = []
    audit_fields = []

    parties = extraction.get("parties", [])
    for index, party in enumerate(parties[:2]):
        field_name = "party_a" if index == 0 else "party_b"
        entity_payload = {
            "field": field_name,
            "value": party.get("value"),
            "page": party.get("page"),
            "span": party.get("span"),
            "confidence": party.get("confidence"),
        }
        if party.get("evidence"):
            entity_payload["evidence"] = party["evidence"]
        entities.append(entity_payload)
        audit_fields.append({"field": field_name, "confidence": party.get("confidence", 0.0)})

    for field_name in ("effective_date", "agreement_date", "governing_law"):
        field_value = extraction.get(field_name)
        if field_value:
            entity_payload = {
                "field": field_name,
                "value": field_value.get("value"),
                "page": field_value.get("page"),
                "span": field_value.get("span"),
                "confidence": field_value.get("confidence"),
            }
            if field_value.get("evidence"):
                entity_payload["evidence"] = field_value["evidence"]
            entities.append(entity_payload)
            audit_fields.append({"field": field_name, "confidence": field_value.get("confidence", 0.0)})

    audit_logging.append_audit(file_hash, timestamp, audit_fields)

    return {
        "entities": entities,
        "provenance": {"file_sha256": file_hash, "timestamp_utc": timestamp},
    }
