"""Successful response models for synchronous query and streaming query documentation."""

from typing import Any, Optional

from pydantic import Field
from pydantic_core import SchemaError

from constants import MEDIA_TYPE_EVENT_STREAM
from models.api.responses.constants import SUCCESSFUL_RESPONSE_DESCRIPTION
from models.api.responses.successful.bases import AbstractSuccessfulResponse
from models.common.turn_summary import (
    RAGChunk,
    ReferencedDocument,
    ToolCallSummary,
    ToolResultSummary,
)


class QueryResponse(AbstractSuccessfulResponse):
    """Model representing LLM response to a query.

    Attributes:
        conversation_id: The optional conversation ID (UUID).
        response: The response.
        rag_chunks: Deprecated. List of RAG chunks used to generate the response.
            This information is now available in tool_results under file_search_call type.
        referenced_documents: The URLs and titles for the documents used to generate the response.
        tool_calls: List of tool calls made during response generation.
        tool_results: List of tool results.
        truncated: Whether conversation history was truncated.
        input_tokens: Number of tokens sent to LLM.
        output_tokens: Number of tokens received from LLM.
        available_quotas: Quota available as measured by all configured quota limiters.
    """

    conversation_id: Optional[str] = Field(
        None,
        description="The optional conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    response: str = Field(
        description="Response from LLM",
        examples=[
            "Kubernetes is an open-source container orchestration system for automating ..."
        ],
    )

    rag_chunks: list[RAGChunk] = Field(
        default_factory=list,
        description="Deprecated: List of RAG chunks used to generate the response.",
    )

    referenced_documents: list[ReferencedDocument] = Field(
        default_factory=list,
        description="List of documents referenced in generating the response",
        examples=[
            [
                {
                    "doc_url": "https://docs.openshift.com/"
                    "container-platform/4.15/operators/olm/index.html",
                    "doc_title": "Operator Lifecycle Manager (OLM)",
                }
            ]
        ],
    )

    truncated: bool = Field(
        False,
        description="Deprecated: whether conversation history was truncated",
        examples=[False, True],
    )

    input_tokens: int = Field(
        0,
        description="Number of tokens sent to LLM",
        examples=[150, 250, 500],
    )

    output_tokens: int = Field(
        0,
        description="Number of tokens received from LLM",
        examples=[50, 100, 200],
    )

    available_quotas: dict[str, int] = Field(
        default_factory=dict,
        description="Quota available as measured by all configured quota limiters",
        examples=[{"daily": 1000, "monthly": 50000}],
    )

    tool_calls: list[ToolCallSummary] = Field(
        default_factory=list,
        description="List of tool calls made during response generation",
    )

    tool_results: list[ToolResultSummary] = Field(
        default_factory=list,
        description="List of tool results",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "response": "Operator Lifecycle Manager (OLM) helps users install...",
                    "referenced_documents": [
                        {
                            "doc_url": "https://docs.openshift.com/container-platform/4.15/"
                            "operators/understanding/olm/olm-understanding-olm.html",
                            "doc_title": "Operator Lifecycle Manager concepts and resources",
                        },
                    ],
                    "truncated": False,
                    "input_tokens": 123,
                    "output_tokens": 456,
                    "available_quotas": {
                        "UserQuotaLimiter": 998911,
                        "ClusterQuotaLimiter": 998911,
                    },
                    "tool_calls": [
                        {"name": "tool1", "args": {}, "id": "1", "type": "tool_call"}
                    ],
                    "tool_results": [
                        {
                            "id": "1",
                            "status": "success",
                            "content": "bla",
                            "type": "tool_result",
                            "round": 1,
                        }
                    ],
                }
            ]
        }
    }


class StreamingQueryResponse(AbstractSuccessfulResponse):
    """Documentation-only model for streaming query responses using Server-Sent Events (SSE)."""

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """Generate FastAPI response dict for SSE streaming with examples.

        Note: This is used for OpenAPI documentation only. The actual endpoint
        returns a StreamingResponse object, not this Pydantic model.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples")
        if not model_examples:
            raise SchemaError(f"Examples not found in {cls.__name__}")
        example_value = model_examples[0]
        content = {
            MEDIA_TYPE_EVENT_STREAM: {
                "schema": {"type": "string"},
                "example": example_value,
            }
        }

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "content": content,
            # Note: No "model" key since we're not actually serializing this model
        }

    model_config = {
        "json_schema_extra": {
            "examples": [
                (
                    'data: {"event": "start", "data": {'
                    '"conversation_id": "123e4567-e89b-12d3-a456-426614174000", '
                    '"request_id": "123e4567-e89b-12d3-a456-426614174001"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 0, "token": "No Violation"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 1, "token": ""}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 2, "token": "Hello"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 3, "token": "!"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 4, "token": " How"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 5, "token": " can"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 6, "token": " I"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 7, "token": " assist"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 8, "token": " you"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 9, "token": " today"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 10, "token": "?"}}\n\n'
                    'data: {"event": "turn_complete", "data": {'
                    '"token": "Hello! How can I assist you today?"}}\n\n'
                    'data: {"event": "end", "data": {'
                    '"referenced_documents": [], '
                    '"truncated": null, "input_tokens": 11, "output_tokens": 19}, '
                    '"available_quotas": {}}\n\n'
                ),
            ]
        }
    }


class StreamingInterruptResponse(AbstractSuccessfulResponse):
    """Model representing a response to a streaming interrupt request.

    Attributes:
        request_id: The streaming request ID targeted by the interrupt call.
        interrupted: Whether an in-progress stream was interrupted.
        message: Human-readable interruption status message.
    """

    request_id: str = Field(
        description="The streaming request ID targeted by the interrupt call",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

    interrupted: bool = Field(
        description="Whether an in-progress stream was interrupted",
        examples=[True],
    )

    message: str = Field(
        description="Human-readable interruption status message",
        examples=["Streaming request interrupted"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "request_id": "123e4567-e89b-12d3-a456-426614174000",
                    "interrupted": True,
                    "message": "Streaming request interrupted",
                }
            ]
        }
    }
