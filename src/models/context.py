"""Context objects for internal operations."""

from dataclasses import dataclass, field
from llama_stack_client import AsyncLlamaStackClient

from models.requests import QueryRequest


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
        query_request: The query request object
        started_at: Timestamp when the request started (ISO 8601 format)
        client: The Llama Stack client for API interactions
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.
    """

    # Conversation & User context
    conversation_id: str
    user_id: str
    skip_userid_check: bool

    # Model info
    model_id: str

    # Request & Timing
    query_request: QueryRequest
    started_at: str

    # Dependencies & State
    client: AsyncLlamaStackClient

    # RAG index identification
    vector_store_ids: list[str] = field(default_factory=list)
    rag_id_mapping: dict[str, str] = field(default_factory=dict)
