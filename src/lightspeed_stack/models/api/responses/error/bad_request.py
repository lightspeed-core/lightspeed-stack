"""OpenAPI-aligned error response models: HTTP 400 Bad Request."""

from typing import ClassVar

from fastapi import status

from models.api.responses.constants import BAD_REQUEST_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class BadRequestResponse(AbstractErrorResponse):
    """400 Bad Request. Invalid resource identifier."""

    description: ClassVar[str] = BAD_REQUEST_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "conversation_id",
                    "detail": {
                        "response": "Invalid conversation ID format",
                        "cause": (
                            "The conversation ID "
                            "123e4567-e89b-12d3-a456-426614174000 has invalid format."
                        ),
                    },
                },
                {
                    "label": "prompt_id",
                    "detail": {
                        "response": "Invalid prompt ID format",
                        "cause": "The prompt ID pmpt_1234567890abcdef has invalid format.",
                    },
                },
            ]
        }
    }

    def __init__(self, *, resource: str, resource_id: str) -> None:
        """
        Create a 400 Bad Request response for an invalid resource ID format.

        Args:
            resource: Type of the resource (for message), e.g. conversation or provider.
            resource_id: The invalid resource identifier used in the error message.
        """
        response = f"Invalid {resource} ID format"
        cause = f"The {resource} ID {resource_id} has invalid format."
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_400_BAD_REQUEST
        )
