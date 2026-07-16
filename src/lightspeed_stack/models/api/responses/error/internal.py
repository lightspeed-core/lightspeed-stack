"""OpenAPI-aligned error response models: HTTP 500 Internal Server Error."""

from typing import ClassVar

from fastapi import status
from typing_extensions import Self  # noqa: UP035

from models.api.responses.constants import INTERNAL_SERVER_ERROR_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class InternalServerErrorResponse(AbstractErrorResponse):
    """500 Internal Server Error."""

    description: ClassVar[str] = INTERNAL_SERVER_ERROR_DESCRIPTION

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "internal",
                    "detail": {
                        "response": "Internal server error",
                        "cause": "An unexpected error occurred while processing the request.",
                    },
                },
                {
                    "label": "configuration",
                    "detail": {
                        "response": "Configuration is not loaded",
                        "cause": "Lightspeed Stack configuration has not been initialized.",
                    },
                },
                {
                    "label": "feedback storage",
                    "detail": {
                        "response": "Failed to store feedback",
                        "cause": "Failed to store feedback at directory: /path/example",
                    },
                },
                {
                    "label": "query",
                    "detail": {
                        "response": "Error while processing query",
                        "cause": "Failed to call backend API",
                    },
                },
                {
                    "label": "conversation cache",
                    "detail": {
                        "response": "Conversation cache not configured",
                        "cause": "Conversation cache is not configured or unavailable.",
                    },
                },
                {
                    "label": "database",
                    "detail": {
                        "response": "Database query failed",
                        "cause": "Failed to query the database",
                    },
                },
                {
                    "label": "cluster version not found",
                    "detail": {
                        "response": "Internal server error",
                        "cause": "ClusterVersion 'version' resource not found in OpenShift cluster",
                    },
                },
                {
                    "label": "cluster version permission denied",
                    "detail": {
                        "response": "Internal server error",
                        "cause": "Insufficient permissions to read ClusterVersion resource",
                    },
                },
                {
                    "label": "invalid cluster version",
                    "detail": {
                        "response": "Internal server error",
                        "cause": "Missing or invalid 'clusterID' in ClusterVersion",
                    },
                },
                {
                    "label": "mcp server registration",
                    "detail": {
                        "response": "Failed to register MCP server",
                        "cause": (
                            "Could not register the MCP server with the remote service."
                        ),
                    },
                },
            ]
        }
    }

    @classmethod
    def generic(cls) -> Self:
        """
        Create an InternalServerErrorResponse representing a generic internal server error.

        Returns:
            InternalServerErrorResponse instance with the standard response message
            "Internal server error" and a cause explaining an unexpected processing error.
        """
        return cls(
            response="Internal server error",
            cause="An unexpected error occurred while processing the request.",
        )

    @classmethod
    def configuration_not_loaded(cls) -> Self:
        """
        Create an InternalServerErrorResponse indicating the service config was not initialized.

        Returns:
            InternalServerErrorResponse with response "Configuration is not loaded" and
            cause "Lightspeed Stack configuration has not been initialized."
        """
        return cls(
            response="Configuration is not loaded",
            cause="Lightspeed Stack configuration has not been initialized.",
        )

    @classmethod
    def feedback_path_invalid(cls, path: str) -> Self:
        """
        Create an InternalServerErrorResponse describing a failure to store feedback.

        Args:
            path: Filesystem directory where feedback storage was attempted.

        Returns:
            Error response with response message "Failed to store feedback" and a cause
            indicating the failed directory.
        """
        return cls(
            response="Failed to store feedback",
            cause=f"Failed to store feedback at directory: {path}",
        )

    @classmethod
    def query_failed(cls, cause: str) -> Self:
        """
        Create an InternalServerErrorResponse representing a failed query.

        Args:
            cause: The error cause message.

        Returns:
            Error response with response "Error while processing query" and the provided
            cause.
        """
        return cls(
            response="Error while processing query",
            cause=cause,
        )

    @classmethod
    def cache_unavailable(cls) -> Self:
        """
        Create an InternalServerErrorResponse indicating the conversation cache is unavailable.

        Returns:
            Error response with a message that the conversation cache is not configured and
            a corresponding cause.
        """
        return cls(
            response="Conversation cache not configured",
            cause="Conversation cache is not configured or unavailable.",
        )

    @classmethod
    def database_error(cls) -> Self:
        """
        Create an InternalServerErrorResponse representing a database query failure.

        Returns:
            Instance with response "Database query failed" and cause "Failed to query the
            database".
        """
        return cls(
            response="Database query failed",
            cause="Failed to query the database",
        )

    @classmethod
    def mcp_server_registration_failed(cls) -> Self:
        """
        Create an InternalServerErrorResponse representing a failed MCP server registration.

        Returns:
            Error response with response "Failed to register MCP server" and cause
            "Could not register the MCP server with the remote service."
        """
        return cls(
            response="Failed to register MCP server",
            cause=("Could not register the MCP server with the remote service."),
        )

    def __init__(self, *, response: str, cause: str) -> None:
        """Initialize the error response for internal server errors and set the HTTP status code.

        Args:
            response: Public-facing error message.
            cause: Internal explanation of the error cause.
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
