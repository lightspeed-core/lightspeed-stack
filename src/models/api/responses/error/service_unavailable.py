"""OpenAPI-aligned error response models: HTTP 503 Service Unavailable."""

from typing import ClassVar

from fastapi import status

from models.api.responses.constants import SERVICE_UNAVAILABLE_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class ServiceUnavailableResponse(AbstractErrorResponse):
    """503 Backend Unavailable."""

    description: ClassVar[str] = SERVICE_UNAVAILABLE_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "llama stack",
                    "detail": {
                        "response": "Unable to connect to Llama Stack",
                        "cause": "Connection error while trying to reach backend service.",
                    },
                },
                {
                    "label": "kubernetes api",
                    "detail": {
                        "response": "Unable to connect to Kubernetes API",
                        "cause": (
                            "Failed to connect to Kubernetes API: "
                            "Service Unavailable (status 503)"
                        ),
                    },
                },
            ]
        }
    }

    def __init__(self, *, backend_name: str, cause: str) -> None:
        """Construct a response indicating the specified backend cannot be reached.

        Args:
            backend_name: Name of the backend service that could not be contacted.
            cause: Detailed explanation of why the service is unavailable.
        """
        response = f"Unable to connect to {backend_name}"
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
