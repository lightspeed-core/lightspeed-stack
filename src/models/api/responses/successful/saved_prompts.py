"""Successful responses for saved prompts configuration and listing."""

from datetime import datetime

from pydantic import Field

from models.api.responses.successful.bases import AbstractSuccessfulResponse


class SavedPromptsConfigResponse(AbstractSuccessfulResponse):
    """Saved prompts configuration limits returned to consuming services.

    Attributes:
        max_prompts_per_user: Maximum number of saved prompts allowed per user.
        max_display_name_length: Maximum character length for prompt display name.
        max_content_length: Maximum character length for prompt content body.
    """

    max_prompts_per_user: int = Field(
        ...,
        description="Maximum number of saved prompts allowed per user",
        examples=[50],
    )
    max_display_name_length: int = Field(
        ...,
        description="Maximum character length for prompt display name",
        examples=[255],
    )
    max_content_length: int = Field(
        ...,
        description="Maximum character length for prompt content body",
        examples=[10000],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "max_prompts_per_user": 50,
                    "max_display_name_length": 255,
                    "max_content_length": 10000,
                }
            ]
        },
    }


class SavedPromptResponse(AbstractSuccessfulResponse):
    """Single saved prompt returned to an authenticated user.

    Attributes:
        id: Unique identifier of the saved prompt.
        name: Display name of the saved prompt.
        content: Prompt body text.
        created_at: When the prompt was created.
        updated_at: When the prompt was last updated.
    """

    id: str = Field(
        ...,
        description="Unique identifier of the saved prompt",
        examples=["abc123"],
    )
    name: str = Field(
        ...,
        description="Display name of the saved prompt",
        examples=["Deploy to staging"],
    )
    content: str = Field(
        ...,
        description="Prompt body text",
        examples=["Help me write a deployment checklist…"],
    )
    created_at: datetime = Field(
        ...,
        description="When the prompt was created",
        examples=["2026-07-22T16:00:00+00:00"],
    )
    updated_at: datetime = Field(
        ...,
        description="When the prompt was last updated",
        examples=["2026-07-22T16:00:00+00:00"],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "id": "abc123",
                    "name": "Deploy to staging",
                    "content": "Help me write a deployment checklist…",
                    "created_at": "2026-07-22T16:00:00+00:00",
                    "updated_at": "2026-07-22T16:00:00+00:00",
                }
            ]
        },
    }


class SavedPromptsListResponse(AbstractSuccessfulResponse):
    """List of saved prompts belonging to the authenticated user.

    Attributes:
        prompts: Saved prompts ordered by created_at descending (newest first).
    """

    prompts: list[SavedPromptResponse] = Field(
        ...,
        description="Saved prompts for the authenticated user",
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompts": [
                        {
                            "id": "abc123",
                            "name": "Deploy to staging",
                            "content": "Help me write a deployment checklist…",
                            "created_at": "2026-07-22T16:00:00+00:00",
                            "updated_at": "2026-07-22T16:00:00+00:00",
                        }
                    ]
                },
                {"prompts": []},
            ]
        },
    }
