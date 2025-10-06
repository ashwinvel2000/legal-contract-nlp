"""Model loader utilities for QA and NER pipelines."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from transformers import pipeline

from core import config


@lru_cache(maxsize=1)
def get_qa() -> Any:
    """Return the question-answering pipeline instance."""
    return pipeline("question-answering", model=config.QA_MODEL_NAME)


@lru_cache(maxsize=1)
def get_ner() -> Any:
    """Return the token-classification pipeline instance."""
    return pipeline(
        "token-classification",
        model=config.NER_MODEL_NAME,
        aggregation_strategy="simple",
    )


def clear_caches() -> None:
    """Reset cached pipelines; primarily useful for tests."""
    get_qa.cache_clear()
    get_ner.cache_clear()
