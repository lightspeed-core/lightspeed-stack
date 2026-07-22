"""Catalog models for the ``/shields`` endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CatalogShield(BaseModel):
    """Shield entry in the ``/shields`` catalog response.

    Accepts either catalog field names or ``ShieldConfiguration`` names
    (``shield_id`` / ``provider_shield_id``) via validation aliases.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    identifier: str = Field(validation_alias="shield_id")
    provider_resource_id: str = Field(validation_alias="provider_shield_id")
    provider_id: str
    type: str = "shield"
    params: dict[str, Any] = Field(default_factory=dict)
