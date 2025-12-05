"""Context objects for internal operations."""

from dataclasses import dataclass
from typing import Any

from llama_stack_client import AsyncLlamaStackClient

from models.requests import QueryRequest
from models.responses import RAGChunk, ReferencedDocument


@dataclass
class ResponseGeneratorContext:  # pylint: disable=too-many-instance-attributes
    """
    Context object for response generator creation.

    This class groups all the parameters needed to create a response generator
    for streaming query endpoints, reducing function parameter count from 10 to 1.

    Attributes:
        conversation_id: The conversation identifier
        user_id: The user identifier
        skip_userid_check: Whether to skip user ID validation
        model_id: The model identifier
        provider_id: The provider identifier
        llama_stack_model_id: The full llama stack model ID
        query_request: The query request object
        started_at: Timestamp when the request started (ISO 8601 format)
        client: The Llama Stack client for API interactions
        metadata_map: Dictionary for storing metadata from tool responses
    """

    # Conversation & User context
    conversation_id: str
    user_id: str
    skip_userid_check: bool

    # Model & Provider info
    model_id: str
    provider_id: str
    llama_stack_model_id: str

    # Request & Timing
    query_request: QueryRequest
    started_at: str

    # Dependencies & State
    client: AsyncLlamaStackClient
    metadata_map: dict[str, dict[str, Any]]
    vector_io_rag_chunks: list[RAGChunk] | None = None
    vector_io_referenced_docs: list[ReferencedDocument] | None = None
