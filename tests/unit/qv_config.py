"""Shared helpers for constructing resolved QuestionValidityConfig in tests."""

from constants import (
    DEFAULT_INVALID_QUESTION_RESPONSE,
    DEFAULT_MODEL_PROMPT,
)
from models.config import QuestionValidityConfig


def make_qv_config(**kwargs: object) -> QuestionValidityConfig:
    """Build a QuestionValidityConfig with startup-resolved text fields filled.

    Production code fills omitted prompt/refusal fields in Configuration load.
    Unit tests that construct configs directly should use this helper so
    ``QuestionValidity`` construction succeeds.
    """
    defaults: dict[str, object] = {
        "model_id": "test",
        "model_prompt": DEFAULT_MODEL_PROMPT,
        "invalid_question_response": DEFAULT_INVALID_QUESTION_RESPONSE,
    }
    defaults.update(kwargs)
    return QuestionValidityConfig(**defaults)  # type: ignore[arg-type]
