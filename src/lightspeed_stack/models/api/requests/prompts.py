"""Request models for prompt template endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class PromptCreateRequest(BaseModel):
    """Request body to create a stored prompt template in Llama Stack.

    Attributes:
        prompt: Prompt text with variable placeholders.
        variables: Variable names allowed in the template.
    """

    prompt: str = Field(
        ...,
        description="Prompt text with variable placeholders",
        examples=["Summarize: {{text}}"],
        min_length=1,
    )
    variables: Optional[list[str]] = Field(
        None,
        description="Variable names allowed in the template",
        examples=[["text"]],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "Summarize: {{text}}",
                    "variables": ["text"],
                }
            ]
        },
    }


class PromptUpdateRequest(BaseModel):
    """Request body to update a stored prompt (creates a new version).

    Attributes:
        prompt: Updated prompt text.
        version: Current version being updated.
        set_as_default: Whether the new version becomes the default.
        variables: Updated allowed variable names.
    """

    prompt: str = Field(
        ...,
        description="Updated prompt text",
        examples=["Summarize in bullet points: {{text}}"],
        min_length=1,
    )
    version: int = Field(
        ...,
        description="Current version being updated",
        examples=[1],
        gt=0,
    )
    set_as_default: Optional[bool] = Field(
        None,
        description="Whether the new version becomes the default",
        examples=[True],
    )
    variables: Optional[list[str]] = Field(
        None,
        description="Updated allowed variable names",
        examples=[["text"]],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "Summarize in bullet points: {{text}}",
                    "version": 1,
                    "set_as_default": True,
                    "variables": ["text"],
                }
            ]
        },
    }
