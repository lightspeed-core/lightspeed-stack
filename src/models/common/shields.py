"""Catalog models for the ``/shields`` endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CatalogShield(BaseModel):
    """Shield entry in the ``/shields`` catalog response.

    Attributes:
        name: Unique, user-facing name identifying this shield instance.
        provider_id: Shield provider / type discriminator.
        type: Catalog entry type; always shield.
        config: Type-specific shield configuration.
    """

    name: str = Field(description="Unique, user-facing name of the shield instance")
    provider_id: Literal["question_validity", "redaction"] = Field(
        description="Shield provider / type discriminator",
    )
    type: Literal["shield"] = Field(
        default="shield",
        description="Catalog entry type; always shield",
    )
    config: dict[str, Any] = Field(
        description="Type-specific shield configuration",
    )
