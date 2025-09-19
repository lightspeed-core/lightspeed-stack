"""User conversation models."""

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, func

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
