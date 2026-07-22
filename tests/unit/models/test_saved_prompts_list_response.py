"""Unit tests for saved prompts list response models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from models.api.responses.successful.saved_prompts import (
    SavedPromptResponse,
    SavedPromptsListResponse,
)


def test_saved_prompt_response_serializes_expected_fields() -> None:
    """SavedPromptResponse exposes id/name/content/timestamps and omits user_id."""
    created = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    updated = datetime(2026, 7, 22, 16, 5, 0, tzinfo=UTC)
    item = SavedPromptResponse(
        id="prompt-1",
        name="Deploy to staging",
        content="Help me write a deployment checklist",
        created_at=created,
        updated_at=updated,
    )

    payload = item.model_dump(mode="json")

    assert set(payload.keys()) == {
        "id",
        "name",
        "content",
        "created_at",
        "updated_at",
    }
    assert payload["id"] == "prompt-1"
    assert payload["name"] == "Deploy to staging"
    assert payload["content"] == "Help me write a deployment checklist"
    assert datetime.fromisoformat(payload["created_at"]) == created
    assert datetime.fromisoformat(payload["updated_at"]) == updated
    assert "user_id" not in payload


def test_saved_prompt_response_forbids_extra_fields() -> None:
    """SavedPromptResponse rejects unknown fields such as user_id."""
    created = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        SavedPromptResponse(
            id="prompt-1",
            name="Deploy",
            content="body",
            created_at=created,
            updated_at=created,
            user_id="user-1",  # type: ignore[call-arg]
        )


def test_saved_prompts_list_response_empty_and_populated() -> None:
    """SavedPromptsListResponse wraps prompts list including empty."""
    assert SavedPromptsListResponse(prompts=[]).model_dump() == {"prompts": []}

    created = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    response = SavedPromptsListResponse(
        prompts=[
            SavedPromptResponse(
                id="prompt-1",
                name="one",
                content="c1",
                created_at=created,
                updated_at=created,
            )
        ]
    )
    assert len(response.prompts) == 1
    assert response.prompts[0].name == "one"
