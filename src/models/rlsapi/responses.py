"""Models for rlsapi v1 REST API responses."""

from typing import Optional
from pydantic import Field

from models.config import ConfigurationBase
from models.responses import (
    AbstractSuccessfulResponse,
    RAGChunk,
    ReferencedDocument,
    ToolCallSummary,
    ToolResultSummary,
)


class RlsapiV1InferData(ConfigurationBase):
    """Response data for rlsapi v1 /infer endpoint.

    Attributes:
        text: The generated response text.
        request_id: Unique identifier for the request.
        tool_calls: MCP tool calls made during inference (verbose mode only).
        tool_results: Results from MCP tool calls (verbose mode only).
        rag_chunks: RAG chunks retrieved from documentation (verbose mode only).
        referenced_documents: Source documents referenced (verbose mode only).
        input_tokens: Number of input tokens consumed (verbose mode only).
        output_tokens: Number of output tokens generated (verbose mode only).
    """

    text: str = Field(
        ...,
        description="Generated response text",
        examples=["To list files in Linux, use the `ls` command."],
    )
    request_id: Optional[str] = Field(
        None,
        description="Unique request identifier",
        examples=["01JDKR8N7QW9ZMXVGK3PB5TQWZ"],
    )

    # Extended metadata fields (only populated when include_metadata=true)
    tool_calls: Optional[list[ToolCallSummary]] = Field(
        None,
        description="Tool calls made during inference (requires include_metadata=true)",
    )
    tool_results: Optional[list[ToolResultSummary]] = Field(
        None,
        description="Results from tool calls (requires include_metadata=true)",
    )
    rag_chunks: Optional[list[RAGChunk]] = Field(
        None,
        description="Retrieved RAG documentation chunks (requires include_metadata=true)",
    )
    referenced_documents: Optional[list[ReferencedDocument]] = Field(
        None,
        description="Source documents referenced in answer (requires include_metadata=true)",
    )
    input_tokens: Optional[int] = Field(
        None,
        description="Number of input tokens consumed (requires include_metadata=true)",
    )
    output_tokens: Optional[int] = Field(
        None,
        description="Number of output tokens generated (requires include_metadata=true)",
    )


class RlsapiV1InferResponse(AbstractSuccessfulResponse):
    """RHEL Lightspeed rlsapi v1 /infer response.

    Attributes:
        data: Response data containing text and request_id.
    """

    data: RlsapiV1InferData = Field(
        ...,
        description="Response data containing text and request_id",
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "data": {
                        "text": "To list files in Linux, use the `ls` command.",
                        "request_id": "01JDKR8N7QW9ZMXVGK3PB5TQWZ",
                    }
                }
            ]
        },
    }
