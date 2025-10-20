# pylint: disable=redefined-outer-name

"""Unit tests for the /conversations REST API endpoints."""

from unittest.mock import Mock
import pytest
from pytest_mock import MockerFixture
from fastapi import HTTPException, status

from app.endpoints.conversations_v2 import (
    transform_chat_message,
    update_conversation_endpoint_handler,
    check_valid_conversation_id,
    check_conversation_existence,
)
from models.cache_entry import CacheEntry
from models.requests import ConversationUpdateRequest
from models.responses import ConversationUpdateResponse, ReferencedDocument
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")
VALID_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
INVALID_CONVERSATION_ID = "invalid-id"


def test_transform_message() -> None:
    """Test the transform_chat_message transformation function."""
    entry = CacheEntry(
        query="query",
        response="response",
        provider="provider",
        model="model",
        started_at="2024-01-01T00:00:00Z",
        completed_at="2024-01-01T00:00:05Z",
    )
    transformed = transform_chat_message(entry)
    assert transformed is not None

    assert "provider" in transformed
    assert transformed["provider"] == "provider"

    assert "model" in transformed
    assert transformed["model"] == "model"

    assert "started_at" in transformed
    assert transformed["started_at"] == "2024-01-01T00:00:00Z"

    assert "completed_at" in transformed
    assert transformed["completed_at"] == "2024-01-01T00:00:05Z"

    assert "messages" in transformed
    assert len(transformed["messages"]) == 2

    message1 = transformed["messages"][0]
    assert message1["type"] == "user"
    assert message1["content"] == "query"

    message2 = transformed["messages"][1]
    assert message2["type"] == "assistant"
    assert message2["content"] == "response"


class TestTransformChatMessage:
    """Test cases for the transform_chat_message utility function."""

    def test_transform_message_without_documents(self) -> None:
        """Test the transformation when no referenced_documents are present."""
        entry = CacheEntry(
            query="query",
            response="response",
            provider="provider",
            model="model",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            # referenced_documents is None by default
        )
        transformed = transform_chat_message(entry)

        assistant_message = transformed["messages"][1]

        # Assert that the key is NOT present when the list is None
        assert "referenced_documents" not in assistant_message

    def test_transform_message_with_referenced_documents(self) -> None:
        """Test the transformation when referenced_documents are present."""
        docs = [ReferencedDocument(doc_title="Test Doc", doc_url="http://example.com")]
        entry = CacheEntry(
            query="query",
            response="response",
            provider="provider",
            model="model",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            referenced_documents=docs,
        )

        transformed = transform_chat_message(entry)
        assistant_message = transformed["messages"][1]

        assert "referenced_documents" in assistant_message
        ref_docs = assistant_message["referenced_documents"]
        assert len(ref_docs) == 1
        assert ref_docs[0]["doc_title"] == "Test Doc"
        assert str(ref_docs[0]["doc_url"]) == "http://example.com/"

    def test_transform_message_with_empty_referenced_documents(self) -> None:
        """Test the transformation when referenced_documents is an empty list."""
        entry = CacheEntry(
            query="query",
            response="response",
            provider="provider",
            model="model",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            referenced_documents=[],  # Explicitly empty
        )

        transformed = transform_chat_message(entry)
        assistant_message = transformed["messages"][1]

        assert "referenced_documents" in assistant_message
        assert assistant_message["referenced_documents"] == []


@pytest.fixture
def mock_configuration():
    """Mock configuration with conversation cache."""
    mock_config = Mock()
    mock_cache = Mock()
    mock_config.conversation_cache = mock_cache
    return mock_config


class TestCheckValidConversationId:
    """Test cases for the check_valid_conversation_id function."""

    def test_valid_conversation_id(self, mocker: MockerFixture):
        """Test with a valid conversation ID."""
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        # Should not raise an exception
        check_valid_conversation_id(VALID_CONVERSATION_ID)

    def test_invalid_conversation_id(self, mocker: MockerFixture):
        """Test with an invalid conversation ID."""
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            check_valid_conversation_id(INVALID_CONVERSATION_ID)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid conversation ID format" in exc_info.value.detail["response"]


class TestCheckConversationExistence:
    """Test cases for the check_conversation_existence function."""

    def test_conversation_exists(self, mocker, mock_configuration):
        """Test when conversation exists."""
        mock_configuration.conversation_cache.list.return_value = [
            Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        # Should not raise an exception
        check_conversation_existence("user_id", VALID_CONVERSATION_ID)

    def test_conversation_not_exists(self, mocker, mock_configuration):
        """Test when conversation does not exist."""
        mock_configuration.conversation_cache.list.return_value = []
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        with pytest.raises(HTTPException) as exc_info:
            check_conversation_existence("user_id", VALID_CONVERSATION_ID)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in exc_info.value.detail["response"]


class TestUpdateConversationEndpoint:
    """Test cases for the PUT /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker: MockerFixture):
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", None)

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, mock_configuration
    ):
        """Test the endpoint with an invalid conversation ID format."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=False)

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                conversation_id=INVALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid conversation ID format" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_conversation_cache_not_configured(self, mocker: MockerFixture):
        """Test the endpoint when conversation cache is not configured."""
        mock_authorization_resolvers(mocker)
        mock_config = Mock()
        mock_config.conversation_cache = None
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert (
            "Conversation cache is not configured" in exc_info.value.detail["response"]
        )

    @pytest.mark.asyncio
    async def test_conversation_not_found(
        self, mocker: MockerFixture, mock_configuration
    ):
        """Test the endpoint when conversation does not exist."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = []

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_successful_update(self, mocker: MockerFixture, mock_configuration):
        """Test successful topic summary update."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            Mock(conversation_id=VALID_CONVERSATION_ID)
        ]

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        response = await update_conversation_endpoint_handler(
            conversation_id=VALID_CONVERSATION_ID,
            update_request=update_request,
            auth=MOCK_AUTH,
        )

        assert isinstance(response, ConversationUpdateResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert response.message == "Topic summary updated successfully"

        # Verify that set_topic_summary was called
        mock_configuration.conversation_cache.set_topic_summary.assert_called_once_with(
            "mock_user_id", VALID_CONVERSATION_ID, "New topic summary", False
        )
