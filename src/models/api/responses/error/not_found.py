"""OpenAPI-aligned error response models: HTTP 404 Not Found."""

from typing import ClassVar, Optional

from fastapi import status

from models.api.responses.constants import NOT_FOUND_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse


class NotFoundResponse(AbstractErrorResponse):
    """404 Not Found - Resource does not exist."""

    description: ClassVar[str] = NOT_FOUND_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "conversation",
                    "detail": {
                        "response": "Conversation not found",
                        "cause": (
                            "Conversation with ID "
                            "123e4567-e89b-12d3-a456-426614174000 does not exist"
                        ),
                    },
                },
                {
                    "label": "provider",
                    "detail": {
                        "response": "Provider not found",
                        "cause": "Provider with ID openai does not exist",
                    },
                },
                {
                    "label": "model",
                    "detail": {
                        "response": "Model not found",
                        "cause": "Model with ID gpt-4o-mini does not exist",
                    },
                },
                {
                    "label": "rag",
                    "detail": {
                        "response": "Rag not found",
                        "cause": (
                            "Rag with ID vs_7b52a8cf-0fa3-489c-beab-27e061d102f3 does not exist"
                        ),
                    },
                },
                {
                    "label": "streaming request",
                    "detail": {
                        "response": "Streaming Request not found",
                        "cause": (
                            "Streaming Request with ID "
                            "123e4567-e89b-12d3-a456-426614174000 does not exist"
                        ),
                    },
                },
                {
                    "label": "mcp server",
                    "detail": {
                        "response": "Mcp Server not found",
                        "cause": "Mcp Server with ID test-mcp-server does not exist",
                    },
                },
                {
                    "label": "vector store",
                    "detail": {
                        "response": "Vector Store not found",
                        "cause": "Vector Store with ID vs_abc123 does not exist",
                    },
                },
                {
                    "label": "file",
                    "detail": {
                        "response": "File not found",
                        "cause": "File with ID file_abc123 does not exist",
                    },
                },
                {
                    "label": "prompt",
                    "detail": {
                        "response": "Prompt not found",
                        "cause": (
                            "Prompt with ID "
                            "pmpt_0123456789abcdef0123456789abcdef01234567 does not exist"
                        ),
                    },
                },
            ]
        }
    }

    def __init__(self, *, resource: str, resource_id: Optional[str] = None) -> None:
        """Create a NotFoundResponse for a missing resource and set the HTTP status to 404.

        Args:
            resource: Resource type that was not found (e.g. conversation, model).
            resource_id: Identifier of the missing resource. If None, the resource type
                is not configured (e.g. no model selected).
        """
        response = f"{resource.title()} not found"
        if resource_id is None:
            cause = f"No {resource.title()} is configured"
        else:
            cause = f"{resource.title()} with ID {resource_id} does not exist"
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_404_NOT_FOUND
        )
