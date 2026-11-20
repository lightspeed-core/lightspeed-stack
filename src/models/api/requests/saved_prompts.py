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


class SavedPromptUpdateRequest(BaseModel):
    """Request body to update a user-scoped saved prompt in place.

    Full-replace semantics: the caller sends the complete prompt object and
    every field is required; omitting a field is a validation error rather
    than "leave unchanged". Length limits are enforced by the endpoint using
    configured saved-prompts limits, not by static field constraints here.

    Attributes:
        name: Display name of the saved prompt.
        content: Prompt body text.
        position: Target position in the user's list (1-based); values above
            the number of prompts the user holds move the prompt to the end.

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
    position: int = Field(
        ...,
        ge=1,
        description="Target position in the user's list (1-based)",
        examples=[1],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Deploy to staging",
                    "content": "Help me write a deployment checklist…",
                    "position": 1,
                }
            ]
        },
    }
