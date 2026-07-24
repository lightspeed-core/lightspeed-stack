"""Catalog models for the ``/shields`` endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CatalogShield(BaseModel):
    """Shield entry in the ``/shields`` catalog response.

    Mirrors the LCS-owned ``ShieldConfiguration`` shape (name / type / config).
    """

    name: str = Field(description="Unique, user-facing name of the shield instance")
    type: Literal["question_validity", "redaction"] = Field(
        description="Shield type discriminator",
    )
    config: dict[str, Any] = Field(
        description="Type-specific shield configuration",
    )
