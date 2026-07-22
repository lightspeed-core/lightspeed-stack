"""User saved prompt models."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from lightspeed_stack.models.database.base import Base


class SavedPrompt(Base):  # pylint: disable=too-few-public-methods
    """Model for storing a user's saved (frequently used) prompts."""

    __tablename__ = "saved_prompt"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_saved_prompt_user_name"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)

    user_id: Mapped[str] = mapped_column(index=True)

    name: Mapped[str] = mapped_column(String(255))

    content: Mapped[str] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        onupdate=func.now(),  # pylint: disable=not-callable
    )
