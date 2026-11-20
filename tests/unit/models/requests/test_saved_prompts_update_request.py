"""Unit tests for the saved prompt update request model."""

import pytest
from pydantic import ValidationError

from models.api.requests.saved_prompts import SavedPromptUpdateRequest


def test_valid_body_parses() -> None:
    """A complete update body parses with all fields."""
    request = SavedPromptUpdateRequest(
        name="Deploy to staging",
        content="Help me write a deployment checklist",
        position=2,
    )

    assert request.name == "Deploy to staging"
    assert request.content == "Help me write a deployment checklist"
    assert request.position == 2


@pytest.mark.parametrize("missing_field", ["name", "content", "position"])
def test_missing_field_rejected(missing_field: str) -> None:
    """Full-replace semantics: every field is required."""
    body = {
        "name": "Deploy to staging",
        "content": "Help me write a deployment checklist",
        "position": 1,
    }
    del body[missing_field]

    with pytest.raises(ValidationError):
        SavedPromptUpdateRequest(**body)


@pytest.mark.parametrize("position", [0, -1])
def test_non_positive_position_rejected(position: int) -> None:
    """Positions below 1 are rejected by the request model."""
    with pytest.raises(ValidationError):
        SavedPromptUpdateRequest(
            name="Deploy to staging",
            content="Help me write a deployment checklist",
            position=position,
        )


def test_unknown_field_rejected() -> None:
    """Unknown fields such as user_id are rejected."""
    with pytest.raises(ValidationError):
        SavedPromptUpdateRequest(
            name="Deploy to staging",
            content="Help me write a deployment checklist",
            position=1,
            user_id="user-1",  # type: ignore[call-arg]
        )
