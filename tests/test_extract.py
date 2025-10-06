from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from core import config, utils


class _DummyQA:
    def __call__(self, *args, **kwargs):  # pragma: no cover - simple stub
        return {"answer": "", "score": 0.0}


class _DummyNER:
    def __call__(self, *args, **kwargs):  # pragma: no cover - simple stub
        return []


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    from core import model

    model.clear_caches()
    dummy_qa = _DummyQA()
    dummy_ner = _DummyNER()
    monkeypatch.setattr("core.model.get_qa", lambda: dummy_qa)
    monkeypatch.setattr("core.model.get_ner", lambda: dummy_ner)
    from app.main import app

    with TestClient(app) as client:
        yield client


def test_sha256_bytes() -> None:
    digest = utils.sha256_bytes(b"legal")
    assert digest == "a708df92c9e46229e8f1cd50d8b7d172bda33fc24c8d96d7e9dabf6eba73baa2"


def test_date_pattern_matches_sample() -> None:
    assert config.DATE_PATTERN.search("3 October 2025")
    assert config.DATE_PATTERN.search("October 3, 2025")
    assert config.DATE_PATTERN.search("2024-06-01")


def test_find_near_phrase() -> None:
    text = "The Agreement is made effective as of October 3, 2025 between the parties."
    idx = text.index("October")
    snippet = utils.find_near_phrase(text, idx, window=10)
    assert "October" in snippet
    expected = text[max(0, idx - 10) : min(len(text), idx + 10)].strip()
    assert snippet == expected


def test_health_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_page(test_client: TestClient) -> None:
    response = test_client.get("/")
    assert response.status_code == 200
    assert "Contract Extraction Demo" in response.text
    assert "Upload a digitally generated contract PDF" in response.text


def test_demo_guide_page(test_client: TestClient) -> None:
    response = test_client.get("/demo-guide")
    assert response.status_code == 200
    assert "Interview walk-through" in response.text


def test_extract_endpoint(monkeypatch: pytest.MonkeyPatch, test_client: TestClient) -> None:
    monkeypatch.setattr(
        "services.pdf_text.extract_pages",
        lambda _: [{"page": 1, "text": "Sample contract between Alpha Corp and Beta LLC effective 2024-06-01."}],
    )
    monkeypatch.setattr(
        "services.qa_extract.extract_fields",
        lambda pages: {
            "parties": [
                {"value": "Alpha Corp", "page": 1, "span": [23, 33], "confidence": 0.9},
                {"value": "Beta LLC", "page": 1, "span": [38, 46], "confidence": 0.85},
            ],
            "effective_date": {
                "value": "2024-06-01",
                "page": 1,
                "span": [58, 68],
                "confidence": 0.8,
            },
            "agreement_date": None,
        },
    )

    response = test_client.post(
        "/extract",
        files={"file": ("sample.pdf", b"fake", "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert "entities" in body and "provenance" in body
    assert any(entity["field"] == "party_a" for entity in body["entities"])
    assert body["provenance"]["file_sha256"]

    audit_path = Path(config.AUDIT_LOG_PATH)
    assert audit_path.exists()
    assert os.path.getsize(audit_path) > 0
