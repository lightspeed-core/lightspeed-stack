"""Shared helpers for agentic display-history model unit tests."""

from conversations.display_history.agentic.models.content import text_message_content
from conversations.display_history.agentic.models.turn_items import MessageTurnItem


def user_message(item_id: str, text: str) -> MessageTurnItem:
    """Build a user message turn item."""
    return MessageTurnItem(
        id=item_id,
        role="user",
        content=text_message_content(text),
    )


def assistant_message(item_id: str, text: str) -> MessageTurnItem:
    """Build an assistant message turn item."""
    return MessageTurnItem(
        id=item_id,
        role="assistant",
        content=text_message_content(text),
    )
