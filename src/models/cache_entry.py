"""Model for conversation history cache entry."""

from pydantic import BaseModel, Field
from typing import List
from models.responses import ReferencedDocument


class CacheEntry(BaseModel):
    """Model representing a cache entry.

    Attributes:
        query: The query string
        response: The response string
        provider: Provider identification
        model: Model identification
        additional_kwargs: additional property to store data like referenced documents
    """

    query: str
    response: str
    provider: str
    model: str
    started_at: str
    completed_at: str
    referenced_documents: List[ReferencedDocument] | None = None
