"""Shared helpers for application exception unit tests."""

from fastapi import Request

from conversations.display_history.errors import ConversationHistoryError

CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
USER_ID = "mock_user_id"
RESPONSE_ID = "resp_abc123"


class UnmappedConversationHistoryError(ConversationHistoryError):
    """Test-only domain error with no HTTP mapping."""

    def __init__(self, message: str = "secret-internal-detail") -> None:
        """Initialize with a message used to verify sanitization in handler tests."""
        super().__init__(message)


def http_request(method: str = "GET") -> Request:
    """Build a minimal HTTP request with the given method."""
    return Request(scope={"type": "http", "method": method})
