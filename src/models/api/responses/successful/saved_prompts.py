"""Successful responses for saved prompts configuration."""

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
