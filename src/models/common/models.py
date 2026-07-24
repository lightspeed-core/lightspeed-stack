"""Backend-agnostic model catalog types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CatalogModel(BaseModel):
    """Normalized model entry used by ``/models`` and internal model resolution.

    Unifies OpenAI-style, Anthropic, and Google ``models.list()`` payloads into
    one catalog shape.
    """

    identifier: str = Field(description="Model identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata excluding core catalog fields",
    )
    api_model_type: str = Field(
        description="API model type (typically mirrors model_type)"
    )
    provider_id: str = Field(description="Provider identifier")
    type: str = Field(default="model", description="Object type, always 'model'")
    provider_resource_id: str = Field(
        default="",
        description="Provider-native resource identifier for the model",
    )
    model_type: str = Field(description="Model type such as 'llm' or 'embedding'")
