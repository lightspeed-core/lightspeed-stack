"""Model for conversation history cache entry."""

from typing import Optional
from pydantic import BaseModel
from utils.types import ReferencedDocument, ToolCallSummary, ToolResultSummary


class CacheEntry(BaseModel):
    """Model representing a cache entry.

    Attributes:
        query: The query string
        response: The response string
        provider: Provider identification
        model: Model identification
        referenced_documents: List of documents referenced by the response
        tool_calls: List of tool calls made during response generation
        tool_results: List of tool results from tool calls
    """

    query: str
    response: str
    provider: str
    model: str
    started_at: str
    completed_at: str
    referenced_documents: Optional[list[ReferencedDocument]] = None
    tool_calls: Optional[list[ToolCallSummary]] = None
    tool_results: Optional[list[ToolResultSummary]] = None
