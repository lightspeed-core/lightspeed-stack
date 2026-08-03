"""Request models for catalog-related endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class ModelFilter(BaseModel):
    """Model representing a query parameter to select models by its type.

    Attributes:
        model_type: Required model type, such as 'llm', 'embeddings' etc.
    """

    model_config = {"extra": "forbid"}
    model_type: Optional[str] = Field(
        None,
        description="Optional filter to return only models matching this type",
        examples=["llm", "embeddings"],
    )
