"""Tests for conversations.display_history.agentic.models.conversation."""

import pytest
from pydantic import ValidationError

from conversations.display_history.agentic.models import (
    AgentTurn,
    Conversation,
    ConversationMetadata,
)
from tests.unit.conversations.display_history.agentic.models.helpers import (
    assistant_message,
    user_message,
)


class TestConversationEnvelope:
    """Conversation metadata and full envelope."""

    def test_conversation_metadata_required_and_defaults(self) -> None:
        """created_at is required; turn_count defaults to zero; list rows omit chat_history."""
        cid = "c5260aec-4d82-4370-9fdf-05cf908b3f16"
        with pytest.raises(ValidationError):
            ConversationMetadata.model_validate({"conversation_id": cid})

        minimal = ConversationMetadata(
            conversation_id=cid, created_at="2024-01-01T00:00:00Z"
        )
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
            started_at="2024-01-01T00:01:00Z",
            completed_at="2024-01-01T00:01:05Z",
            context_status="full",
            input=[user_message("in_1", "Hello")],
            output=[assistant_message("out_1", "Hi there!")],
        )
        conversation = Conversation(
            conversation_id="c5260aec-4d82-4370-9fdf-05cf908b3f16",
            created_at="2024-01-01T00:00:00Z",
            chat_history=[turn],
        )
        assert len(conversation.chat_history) == 1
