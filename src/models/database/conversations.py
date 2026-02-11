"""User conversation models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database.base import Base


class UserConversation(Base):  # pylint: disable=too-few-public-methods
    """Model for storing user conversation metadata."""

    __tablename__ = "user_conversation"

    # The conversation ID
    id: Mapped[str] = mapped_column(primary_key=True)

    # The user ID associated with the conversation
    user_id: Mapped[str] = mapped_column(index=True)

    # The last provider/model used in the conversation
    last_used_model: Mapped[str] = mapped_column()
    last_used_provider: Mapped[str] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
    )

    # The number of user messages in the conversation
    message_count: Mapped[int] = mapped_column(default=0)

    topic_summary: Mapped[str] = mapped_column(default="")


class UserTurn(Base):  # pylint: disable=too-few-public-methods
    """Model for storing turn-level metadata."""

    __tablename__ = "user_turn"

    # Foreign key to user_conversation (part of composite primary key)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("user_conversation.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Turn number (1-indexed, first turn is 1) for ordering within a conversation
    # Part of composite primary key with conversation_id
    turn_number: Mapped[int] = mapped_column(primary_key=True)

    # Timestamps for the turn
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(nullable=False)

    model: Mapped[str] = mapped_column(nullable=False)
