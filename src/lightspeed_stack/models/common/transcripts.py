"""Pydantic models for persisted query/response transcript entries."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class TranscriptMetadata(BaseModel):
    """Metadata for a transcript entry."""

    provider: Optional[str] = None
    model: str
    query_provider: Optional[str] = None
    query_model: Optional[str] = None
    user_id: str
    conversation_id: str
    timestamp: str


class Transcript(BaseModel):
    """Model representing a transcript entry to be stored."""

    metadata: TranscriptMetadata
    redacted_query: str
    query_is_valid: bool
    llm_response: str
    rag_chunks: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
