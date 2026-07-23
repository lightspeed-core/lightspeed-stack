"""Request models for saved prompts endpoints."""

from pydantic import BaseModel, Field


class SavedPromptCreateRequest(BaseModel):
    """Request body to create a user-scoped saved prompt.

    Length and emptiness limits are enforced by the endpoint using configured
    saved-prompts limits, not by static field constraints here.

    Attributes:
        name: Display name of the saved prompt.
        content: Prompt body text.
    """

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

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Deploy to staging",
                    "content": "Help me write a deployment checklist…",
                }
            ]
        },
    }
