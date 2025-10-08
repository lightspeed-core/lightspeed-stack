"""Model for conversation history cache entry."""

from pydantic import BaseModel, Field
from typing import List
from models.responses import ReferencedDocument

class AdditionalKwargs(BaseModel):
    """A structured model for the 'additional_kwargs' dictionary."""
    referenced_documents: List[ReferencedDocument] = Field(default_factory=list)


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
    additional_kwargs: AdditionalKwargs | None = None
