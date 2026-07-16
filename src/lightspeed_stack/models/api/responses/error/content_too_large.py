"""OpenAPI-aligned error response models: HTTP 413 Payload Too Large."""

from typing import ClassVar, Optional, Self

from fastapi import status

from models.api.responses.constants import (
    FILE_UPLOAD_EXCEEDS_SIZE_LIMIT_DESCRIPTION,
    PROMPT_TOO_LONG_DESCRIPTION,
)
from models.api.responses.error.bases import AbstractErrorResponse


class PromptTooLongResponse(AbstractErrorResponse):
    """413 Payload Too Large - Prompt is too long."""

    description: ClassVar[str] = PROMPT_TOO_LONG_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "context window exceeded",
                    "detail": {
                        "response": "Context window exceeded",
                        "cause": (
                            "The input exceeds the context window size "
                            "of model 'gpt-4o-mini'."
                        ),
                    },
                },
                {
                    "label": "prompt too long",
                    "detail": {
                        "response": "Prompt is too long",
                        "cause": "The prompt exceeds the maximum allowed length.",
                    },
                },
            ]
        }
    }

    def __init__(
        self,
        *,
        response: str = "Prompt is too long",
        model: Optional[str] = None,
    ) -> None:
        """Initialize a PromptTooLongResponse.

        Args:
            response: Short summary of the error. Defaults to "Prompt is too long".
            model: The model identifier for which the prompt is too long.
        """
        if model:
            cause = f"The input exceeds the context window size of model '{model}'."
        else:
            cause = "The prompt exceeds the maximum allowed length."

        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )


class FileTooLargeResponse(AbstractErrorResponse):
    """413 Content Too Large - File upload exceeds size limit."""

    description: ClassVar[str] = FILE_UPLOAD_EXCEEDS_SIZE_LIMIT_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "file upload",
                    "detail": {
                        "response": "File too large",
                        "cause": (
                            "File size 150000000 bytes exceeds maximum "
                            "allowed size of 104857600 bytes (100 MB)"
                        ),
                    },
                },
                {
                    "label": "backend rejection",
                    "detail": {
                        "response": "Invalid file upload",
                        "cause": "File upload rejected: File size exceeds limit",
                    },
                },
            ]
        }
    }

    @classmethod
    def exceeds_local_limit(
        cls,
        *,
        file_size: int,
        max_size: int,
        response: str = "File too large",
    ) -> Self:
        """Build a 413 when measured bytes exceed the configured upload maximum.

        Args:
            file_size: Measured size of the upload in bytes.
            max_size: Configured maximum allowed size in bytes.
            response: Short summary shown to the client.

        Returns:
            A response whose cause includes both sizes and the maximum size in MB (floored).
        """
        cause = (
            f"File size {file_size} bytes exceeds maximum allowed "
            f"size of {max_size} bytes ({max_size // (1024 * 1024)} MB)"
        )
        return cls(response=response, cause=cause)

    @classmethod
    def from_backend_rejection(
        cls,
        *,
        message: str,
        response: str = "Invalid file upload",
    ) -> Self:
        """Build a 413 when Llama Stack rejects the upload after we sent it.

        Args:
            message: Error text from the backend.
            response: Short summary shown to the client.

        Returns:
            A response whose cause prefixes the message with a fixed label.
        """
        cause = f"File upload rejected: {message}"
        return cls(response=response, cause=cause)

    def __init__(self, *, response: str, cause: str) -> None:
        """Create a 413 Content Too Large error with explicit summary and cause.

        Args:
            response: Short summary of the error.
            cause: Detailed explanation for operators and clients.
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
