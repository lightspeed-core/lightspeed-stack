"""User saved prompt models."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database.base import Base


class SavedPrompt(Base):  # pylint: disable=too-few-public-methods
    """Model for storing a user's saved (frequently used) prompts.

    The ``position`` column holds the per-user ordering (1-based, no gaps
    after normalization). It is nullable at the database level because
    ``ALTER TABLE ADD COLUMN`` cannot add a NOT NULL constraint without a
    default on existing deployments, and SQLite cannot add constraints to
    existing tables at all; application code always assigns it and the
    startup migration backfills every existing row (see
    ``app/schema_migrations.py``).
    """

    __tablename__ = "saved_prompt"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_saved_prompt_user_name"),
        UniqueConstraint(
            "user_id", "position", name="uq_saved_prompt_user_position"
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)

    user_id: Mapped[str] = mapped_column(index=True)

    name: Mapped[str] = mapped_column(String(255))

    content: Mapped[str] = mapped_column(Text())

    position: Mapped[int] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        onupdate=func.now(),  # pylint: disable=not-callable
    )
