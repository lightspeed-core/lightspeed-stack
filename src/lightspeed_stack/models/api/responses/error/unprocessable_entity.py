"""OpenAPI-aligned error response models: HTTP 422 Unprocessable Entity."""

from typing import ClassVar

from fastapi import status

from models.api.responses.constants import UNPROCESSABLE_CONTENT_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class UnprocessableEntityResponse(AbstractErrorResponse):
    """422 Unprocessable Entity - Request validation failed."""

    description: ClassVar[str] = UNPROCESSABLE_CONTENT_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "invalid format",
                    "detail": {
                        "response": "Invalid request format",
                        "cause": "Invalid request format. The request body could not be parsed.",
                    },
                },
                {
                    "label": "missing attributes",
                    "detail": {
                        "response": "Missing required attributes",
                        "cause": "Missing required attributes: ['query', 'model', 'provider']",
                    },
                },
                {
                    "label": "invalid value",
                    "detail": {
                        "response": "Invalid attribute value",
                        "cause": "Invalid attachment type: must be one of ['text/plain', "
                        "'application/json', 'application/yaml', 'application/xml']",
                    },
                },
            ]
        }
    }

    def __init__(self, *, response: str, cause: str) -> None:
        """Create a 422 Unprocessable Entity error response.

        Args:
            response: Human-readable message describing what was unprocessable.
            cause: Specific cause or diagnostic information explaining the error.
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
