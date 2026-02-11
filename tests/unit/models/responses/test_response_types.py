"""Unit tests for response-related type models defined in models/responses.py."""

import pytest
from pydantic import ValidationError

from models.responses import ConversationData, ConversationDetails, ProviderHealthStatus


class TestConversationDetails:
    """Test cases for ConversationDetails type."""

    def test_constructor(self) -> None:
        """Test ConversationDetails with all fields."""
        details = ConversationDetails(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            created_at="2024-01-01T00:00:00Z",
            last_message_at="2024-01-01T00:05:00Z",
            message_count=5,
            last_used_model="gpt-4",
            last_used_provider="openai",
            topic_summary="Test topic",
        )
        assert details.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert details.created_at == "2024-01-01T00:00:00Z"
        assert details.last_message_at == "2024-01-01T00:05:00Z"
        assert details.message_count == 5
        assert details.last_used_model == "gpt-4"
        assert details.last_used_provider == "openai"
        assert details.topic_summary == "Test topic"

    def test_missing_required_fields(self) -> None:
        """Test ConversationDetails raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ConversationDetails()  # type: ignore[call-arg]


class TestConversationData:
    """Test cases for ConversationData type."""

    def test_constructor(self) -> None:
        """Test ConversationData with all fields."""
        data = ConversationData(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            topic_summary="Test topic",
            last_message_timestamp=1704067200.0,
        )
        assert data.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert data.topic_summary == "Test topic"
        assert data.last_message_timestamp == 1704067200.0

    def test_topic_summary_none(self) -> None:
        """Test ConversationData with None topic_summary."""
        data = ConversationData(
            conversation_id="conv-123",
            topic_summary=None,
            last_message_timestamp=1704067200.0,
        )
        assert data.topic_summary is None

    def test_missing_required_fields(self) -> None:
        """Test ConversationData raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ConversationData()  # type: ignore[call-arg]


class TestProviderHealthStatus:
    """Test cases for ProviderHealthStatus type."""

    def test_constructor(self) -> None:
        """Test ProviderHealthStatus with all fields."""
        status_obj = ProviderHealthStatus(
            provider_id="provider1",
            status="healthy",
            message="All systems operational",
        )
        assert status_obj.provider_id == "provider1"
        assert status_obj.status == "healthy"
        assert status_obj.message == "All systems operational"

    def test_missing_required_fields(self) -> None:
        """Test ProviderHealthStatus raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ProviderHealthStatus()  # type: ignore[call-arg]
