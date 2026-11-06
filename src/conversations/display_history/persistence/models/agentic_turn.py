"""Agentic turn content stored for display history."""

from typing import Any, Optional

from sqlalchemy import JSON, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.database.base import Base


class UserAgenticTurn(Base):  # pylint: disable=too-few-public-methods
    """Display data for one agent turn, linked to the parent user turn.

    Stores summary fields plus JSON for input items, output items, and citations.
    Application startup does not create this table until v3 persistence is enabled.
    """

    __tablename__ = "user_agentic_turn"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "turn_number"],
            ["user_turn.conversation_id", "user_turn.turn_number"],
            ondelete="CASCADE",
        ),
    )

    conversation_id: Mapped[str] = mapped_column(primary_key=True)
    turn_number: Mapped[int] = mapped_column(primary_key=True)

    status: Mapped[str] = mapped_column(default="completed", nullable=False)
    agent: Mapped[Optional[str]] = mapped_column(default=None, nullable=True)
    context_status: Mapped[str] = mapped_column(default="full", nullable=False)

    input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)

    referenced_documents: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    input_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    output_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
