"""Tests for conversations.display_history.agentic.models.conversation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from conversations.display_history.agentic.models import (
    AgentTurn,
    Conversation,
    ConversationMetadata,
)
from conversations.display_history.agentic.models.content import TextContentPart
from conversations.display_history.agentic.models.turn_items import MessageTurnItem


class TestConversationEnvelope:
    """Conversation metadata and full envelope."""

    def test_conversation_metadata_required_and_defaults(self) -> None:
        """created_at is required; turn_count defaults to zero; list rows omit chat_history."""
        cid = "c5260aec-4d82-4370-9fdf-05cf908b3f16"
        with pytest.raises(ValidationError):
            ConversationMetadata.model_validate({"conversation_id": cid})

        minimal = ConversationMetadata(
            conversation_id=cid, created_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        )
        assert minimal.created_at == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert minimal.turn_count == 0
        assert "chat_history" not in ConversationMetadata.model_fields
        assert "chat_history" not in minimal.model_dump()

    def test_full_conversation_with_chat_history(self) -> None:
        """Conversation extends metadata with ordered chat_history."""
        turn = AgentTurn(
            id="resp_1",
            status="completed",
            provider="openai",
            model="gpt-4",
            started_at=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 1, 0, 1, 5, tzinfo=UTC),
            context_status="full",
            input=[
                MessageTurnItem(
                    id="in_1",
                    role="user",
                    content=[TextContentPart(text="Hello")],
                )
            ],
            output=[
                MessageTurnItem(
                    id="out_1",
                    role="assistant",
                    content=[TextContentPart(text="Hi there!")],
                )
            ],
        )
        conversation = Conversation(
            conversation_id="c5260aec-4d82-4370-9fdf-05cf908b3f16",
            created_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            chat_history=[turn],
        )
        assert len(conversation.chat_history) == 1
