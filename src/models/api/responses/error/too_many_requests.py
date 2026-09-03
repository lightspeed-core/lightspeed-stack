"""OpenAPI-aligned error response models: HTTP 429 Too Many Requests."""

from typing import ClassVar

from fastapi import status
from typing_extensions import Self  # noqa: UP035

from models.api.responses.constants import QUOTA_EXCEEDED_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse
from quota.quota_exceed_error import QuotaExceedError


class QuotaExceededResponse(AbstractErrorResponse):
    """429 Too Many Requests - Quota limit exceeded."""

    description: ClassVar[str] = QUOTA_EXCEEDED_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "model",
                    "detail": {
                        "response": "The model quota has been exceeded",
                        "cause": "The token quota for model gpt-4-turbo has been exceeded.",
                    },
                },
                {
                    "label": "user none",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "User 123 has no available tokens",
                    },
                },
                {
                    "label": "cluster none",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Cluster has no available tokens",
                    },
                },
                {
                    "label": "subject none",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Unknown subject 999 has no available tokens",
                    },
                },
                {
                    "label": "user insufficient",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "User 123 has 5 tokens, but 10 tokens are needed",
                    },
                },
                {
                    "label": "cluster insufficient",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Cluster has 500 tokens, but 900 tokens are needed",
                    },
                },
                {
                    "label": "subject insufficient",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed",
                    },
                },
            ]
        }
    }

    @classmethod
    def model(cls, model_name: str) -> Self:
        """Create a QuotaExceededResponse for a specific model.

        Args:
            model_name: The model identifier whose token quota was exceeded.

        Returns:
            Response with a standard message and a cause that includes the model name.
        """
        response = "The model quota has been exceeded"
        cause = f"The token quota for model {model_name} has been exceeded."
        return cls(response=response, cause=cause)

    @classmethod
    def from_exception(cls, exc: QuotaExceedError) -> Self:
        """Construct a QuotaExceededResponse representing the provided QuotaExceedError.

        Args:
            exc: The exception whose string form is used as the cause.

        Returns:
            Response with a standard quota-exceeded message and the exception text as cause.
        """
        response = "The quota has been exceeded"
        cause = str(exc)
        return cls(response=response, cause=cause)

    def __init__(self, *, response: str, cause: str) -> None:
        """Create a QuotaExceededResponse with a public message and an explanatory cause.

        Sets the HTTP status code to 429 (Too Many Requests).

        Args:
            response: Public-facing error message describing the quota condition.
            cause: Detailed cause stored in the error detail.
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
