"""OpenAPI-aligned error response models: HTTP 409 Conflict."""

from typing import ClassVar

from fastapi import status
from typing_extensions import Self  # noqa: UP035

from models.api.responses.constants import CONFLICT_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class ConflictResponse(AbstractErrorResponse):
    """409 Conflict - Resource already exists."""

    description: ClassVar[str] = CONFLICT_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "mcp server",
                    "detail": {
                        "response": "Mcp Server already exists",
                        "cause": (
                            "Mcp Server with name 'test-mcp-server' is already registered"
                        ),
                    },
                },
                {
                    "label": "mcp tool conflict",
                    "detail": {
                        "response": "Tool conflict",
                        "cause": (
                            "Client MCP tool with server_label 'my-server' "
                            "conflicts with a server-configured MCP tool. "
                            "Rename the client tool to avoid the conflict."
                        ),
                    },
                },
                {
                    "label": "file search conflict",
                    "detail": {
                        "response": "Tool conflict",
                        "cause": (
                            "Client file_search tool conflicts with a "
                            "server-configured file_search tool. "
                            "Remove the client file_search to use the server's configuration."
                        ),
                    },
                },
            ]
        }
    }

    def __init__(self, *, resource: str, resource_id: str) -> None:
        """Create a 409 Conflict response for a duplicate resource.

        Args:
            resource: Type of the resource (e.g. MCP server).
            resource_id: The identifier of the conflicting resource.
        """
        response = f"{resource.title()} already exists"
        cause = f"{resource.title()} with name '{resource_id}' is already registered"
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_409_CONFLICT
        )

    @classmethod
    def mcp_tool(cls, server_label: str) -> Self:
        """Create a ConflictResponse for a client MCP tool conflicting with a server-configured one.

        Args:
            server_label: The server_label field that conflicts.

        Returns:
            A response with a cause describing the MCP tool conflict.
        """
        return cls._from_cause(
            response="Tool conflict",
            cause=(
                f"Client MCP tool with server_label '{server_label}' "
                f"conflicts with a server-configured MCP tool. "
                f"Rename the client tool to avoid the conflict."
            ),
        )

    @classmethod
    def file_search(cls) -> Self:
        """Create a ConflictResponse for a client file_search tool conflicting with a server one.

        Returns:
            A response with a cause describing the file_search tool conflict.
        """
        return cls._from_cause(
            response="Tool conflict",
            cause=(
                "Client file_search tool conflicts with a "
                "server-configured file_search tool. "
                "Remove the client file_search to use the server's configuration."
            ),
        )

    @classmethod
    def _from_cause(cls, *, response: str, cause: str) -> Self:
        """Create a ConflictResponse with explicit response and cause strings.

        Args:
            response: Short summary of the conflict.
            cause: Detailed explanation of the conflict.

        Returns:
            A new ConflictResponse instance.
        """
        instance = cls.__new__(cls)
        AbstractErrorResponse.__init__(
            instance,
            response=response,
            cause=cause,
            status_code=status.HTTP_409_CONFLICT,
        )
        return instance
