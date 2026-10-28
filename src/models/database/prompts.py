"""Persistence models for the versioned prompt catalog."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from models.database.base import Base
from prompts.exceptions import PromptValidationError


class Prompt(Base):  # pylint: disable=too-few-public-methods
    """Prompt identity with a pointer to the default version."""

    __tablename__ = "prompt"

    id: Mapped[str] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(255))

    default_version: Mapped[int] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PromptVersion(Base):  # pylint: disable=too-few-public-methods
    """Immutable version row containing the template text and declared variables."""

    __tablename__ = "prompt_version"

    # Foreign key is not turned on by default for sqlite, but a PromptVersion will always
    # be created after a Prompt is created in the database operation logic. Therefore,
    # a PromptVersion with a nonexistent prompt.id will never be created.
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompt.id"), primary_key=True)

    version: Mapped[int] = mapped_column(primary_key=True)

    template: Mapped[str] = mapped_column(Text())

    variables: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @validates("variables")
    def validate_unique_variables(self, _key: str, value: list[str]) -> list[str]:
        """Ensure no duplicate variable names."""
        if len(value) != len(set(value)):
            raise PromptValidationError("The variables contain duplicate names")

        return value
