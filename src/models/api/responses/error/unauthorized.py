"""OpenAPI-aligned error response models: HTTP 401 Unauthorized."""

from typing import ClassVar

from fastapi import status

from models.api.responses.constants import UNAUTHORIZED_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class UnauthorizedResponse(AbstractErrorResponse):
    """401 Unauthorized - Missing or invalid credentials."""

    description: ClassVar[str] = UNAUTHORIZED_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "missing header",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "No Authorization header found",
                    },
                },
                {
                    "label": "missing token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "No token found in Authorization header",
                    },
                },
                {
                    "label": "expired token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Token has expired",
                    },
                },
                {
                    "label": "invalid signature",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Invalid token signature",
                    },
                },
                {
                    "label": "invalid key",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Token signed by unknown key",
                    },
                },
                {
                    "label": "missing claim",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Token missing claim: user_id",
                    },
                },
                {
                    "label": "invalid k8s token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Invalid or expired Kubernetes token",
                    },
                },
                {
                    "label": "invalid jwk token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Authentication key server returned invalid data",
                    },
                },
                {
                    "label": "mcp oauth",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": (
                            "MCP server at https://mcp.example.com/v1 requires OAuth"
                        ),
                    },
                },
            ]
        }
    }

    def __init__(self, *, cause: str) -> None:
        """Create an UnauthorizedResponse for missing or invalid client credentials.

        Uses a standardized response message and the given cause; HTTP status is 401.

        Args:
            cause: Human-readable explanation (e.g. missing token, expired token).
        """
        response_msg = "Missing or invalid credentials provided by client"
        super().__init__(
            response=response_msg, cause=cause, status_code=status.HTTP_401_UNAUTHORIZED
        )
