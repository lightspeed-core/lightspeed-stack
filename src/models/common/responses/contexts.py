"""Context objects for the responses endpoint pipeline and streaming query generators."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks
from llama_stack_client import AsyncLlamaStackClient
from pydantic import BaseModel, ConfigDict, Field

from models.api.requests import QueryRequest
from models.common.moderation import ShieldModerationResult
from models.common.turn_summary import RAGContext


# TODO: LCORE-2121: Use AuthTuple everywhere (type refactoring needed) pylint: disable=W0511
class ResponsesContext(BaseModel):
    """Shared request-scoped context for the /responses endpoint pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: AsyncLlamaStackClient = Field(description="The Llama Stack client")
    auth: tuple[str, str, bool, str] = Field(
        description="Authentication tuple (user_id, username, skip_userid_check, token)",
    )
    input_text: str = Field(description="Extracted user input text for the turn")
    started_at: datetime = Field(description="UTC timestamp when the request started")
    moderation_result: ShieldModerationResult = Field(
        description="Shield moderation outcome",
    )
    inline_rag_context: RAGContext = Field(
        description="Inline RAG context for the turn"
    )
    filter_server_tools: bool = Field(
        default=False,
        description="Whether to filter server-deployed MCP tool events from output",
    )
    background_tasks: Optional[BackgroundTasks] = Field(
        default=None,
        description="Background tasks for telemetry, if enabled",
    )
    rh_identity_context: tuple[str, str] = Field(
        default=("", ""),
        description="RH identity (org_id, system_id) for Splunk events",
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="User-Agent string from request headers",
    )
    endpoint_path: str = Field(
        ...,
        description="API endpoint path used for metric labeling",
    )
    generate_topic_summary: bool = Field(
        default=False,
        description="Whether to generate a topic summary for new conversations",
    )


@dataclass
class ResponseGeneratorContext:  # pylint: disable=too-many-instance-attributes
    """
    Context object for response generator creation.

    This class groups all the parameters needed to create a response generator
    for streaming query endpoints, reducing function parameter count from 10 to 1.

    Attributes:
        conversation_id: The conversation identifier
        request_id: Unique identifier for the streaming request
        user_id: The user identifier
        skip_userid_check: Whether to skip user ID validation
        model_id: The model identifier
        query_request: The query request object
        started_at: Timestamp when the request started (ISO 8601 format)
        client: The Llama Stack client for API interactions
        moderation_result: The moderation result
        inline_rag_context: Inline RAG context
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.
    """

    # Conversation & User context
    conversation_id: str
    request_id: str
    user_id: str
    skip_userid_check: bool

    # Model info
    model_id: str

    # Request & Timing
    query_request: QueryRequest
    started_at: str

    # Dependencies & State
    client: AsyncLlamaStackClient
    moderation_result: ShieldModerationResult

    # RAG index identification
    inline_rag_context: RAGContext
    vector_store_ids: list[str] = field(default_factory=list)
    rag_id_mapping: dict[str, str] = field(default_factory=dict)
