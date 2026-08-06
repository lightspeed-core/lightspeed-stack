"""Metadata models for agent skills shared across the skills endpoint and helpers."""

from pydantic import BaseModel, Field


class SkillMetadata(BaseModel):
    """Metadata describing a single loaded agent skill.

    Attributes:
        name: Unique name of the skill.
        description: Human readable description of what the skill does.
    """

    name: str = Field(..., description="Unique name of the skill")
    description: str = Field(
        ..., description="Human readable description of what the skill does"
    )
