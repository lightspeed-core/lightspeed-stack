"""Model for conversation history cache entry."""

from pydantic import BaseModel
from models.responses import ReferencedDocument


class CacheEntry(BaseModel):
    """Model representing a cache entry.

    Attributes:
        query: The query string
        response: The response string
        provider: Provider identification
        model: Model identification
        referenced_documents: List of documents referenced by the response
    """

    query: str
    response: str
    provider: str
    model: str
    started_at: str
    completed_at: str
    referenced_documents: list[ReferencedDocument] | None = None
