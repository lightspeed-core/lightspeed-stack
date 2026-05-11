"""Unit tests for the ConversationSummary model."""

import pytest

from models.compaction import ConversationSummary


def _valid_kwargs() -> dict:
    """Return a kwargs dict with valid values for every required field."""
    return {
        "summary_text": "Summary of the conversation.",
        "summarized_through_turn": 8,
        "token_count": 42,
        "created_at": "2026-05-11T00:00:00Z",
        "model_used": "openai/gpt-4o-mini",
    }


def test_constructor_with_valid_values() -> None:
    """All required fields populated; instance round-trips through Pydantic."""
    summary = ConversationSummary(**_valid_kwargs())
    assert summary.summary_text == "Summary of the conversation."
    assert summary.summarized_through_turn == 8
    assert summary.token_count == 42
    assert summary.created_at == "2026-05-11T00:00:00Z"
    assert summary.model_used == "openai/gpt-4o-mini"


def test_summarized_through_turn_accepts_zero() -> None:
    """A zero turn count is allowed (NonNegativeInt) — represents an empty
    conversation entry point even though compaction itself does not produce
    one in this state."""
    kwargs = _valid_kwargs()
    kwargs["summarized_through_turn"] = 0
    summary = ConversationSummary(**kwargs)
    assert summary.summarized_through_turn == 0


def test_summarized_through_turn_rejects_negative() -> None:
    """Negative turn counts are rejected."""
    kwargs = _valid_kwargs()
    kwargs["summarized_through_turn"] = -1
    with pytest.raises(ValueError):
        ConversationSummary(**kwargs)


def test_token_count_rejects_zero() -> None:
    """Token count of zero is rejected (PositiveInt); a summary with no
    tokens would not be a meaningful record."""
    kwargs = _valid_kwargs()
    kwargs["token_count"] = 0
    with pytest.raises(ValueError):
        ConversationSummary(**kwargs)


def test_token_count_rejects_negative() -> None:
    """Negative token count is rejected."""
    kwargs = _valid_kwargs()
    kwargs["token_count"] = -1
    with pytest.raises(ValueError):
        ConversationSummary(**kwargs)


def test_required_fields_are_required() -> None:
    """Omitting any required field raises a Pydantic validation error."""
    for field in (
        "summary_text",
        "summarized_through_turn",
        "token_count",
        "created_at",
        "model_used",
    ):
        kwargs = _valid_kwargs()
        del kwargs[field]
        with pytest.raises(ValueError):
            ConversationSummary(**kwargs)
