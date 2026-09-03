"""Successful responses for stored prompt templates."""

from typing import ClassVar, Optional

from pydantic import Field

from models.api.responses.successful.bases import (
    AbstractDeleteResponse,
    AbstractSuccessfulResponse,
)


class PromptResourceResponse(AbstractSuccessfulResponse):
    """A stored prompt template as returned by Llama Stack.

    Attributes:
        prompt_id: Prompt identifier from Llama Stack.
        version: Version number for this prompt.
        is_default: Whether this version is the default.
        prompt: Prompt text with placeholders.
        variables: Variable names used in the template.
    """

    prompt_id: str = Field(..., description="Prompt identifier from Llama Stack")
    version: int = Field(..., description="Version number for this prompt")
    is_default: Optional[bool] = Field(
        None, description="Whether this version is the default"
    )
    prompt: Optional[str] = Field(None, description="Prompt text with placeholders")
    variables: Optional[list[str]] = Field(
        None, description="Variable names used in the template"
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                    "version": 1,
                    "is_default": True,
                    "prompt": "Summarize: {{text}}",
                    "variables": ["text"],
                }
            ]
        },
    }


class PromptsListResponse(AbstractSuccessfulResponse):
    """List of stored prompt templates returned by Llama Stack.

    Attributes:
        data: Prompt entries as returned by the Llama Stack list API.
    """

    data: list[PromptResourceResponse] = Field(
        default_factory=list,
        description="Prompt entries (as returned by Llama Stack list)",
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                            "version": 1,
                            "is_default": True,
                            "prompt": "Summarize: {{text}}",
                            "variables": ["text"],
                        }
                    ],
                }
            ]
        },
    }


class PromptDeleteResponse(AbstractDeleteResponse):
    """Result of deleting a stored prompt (always HTTP 200, like conversations v2).

    Attributes:
        prompt_id: Prompt identifier that was passed to delete.
        deleted: Whether the prompt was deleted successfully
        response: Human readable response
    """

    resource_name: ClassVar[str] = "Prompt"
    prompt_id: str = Field(
        ...,
        description="Prompt identifier that was passed to delete.",
        examples=["pmpt_0123456789abcdef0123456789abcdef01234567"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "deleted",
                    "value": {
                        "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                        "deleted": True,
                        "response": "Prompt deleted successfully",
                    },
                },
                {
                    "label": "not found",
                    "value": {
                        "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                        "deleted": False,
                        "response": "Prompt not found",
                    },
                },
            ]
        }
    }
