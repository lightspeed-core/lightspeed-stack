# pylint: disable=redefined-outer-name

"""Unit tests for the /conversations REST API endpoints."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException, status
from pytest_mock import MockerFixture, MockType

from app.endpoints.conversations_v2 import (
    check_conversation_existence,
    check_valid_conversation_id,
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    transform_chat_message,
    update_conversation_endpoint_handler,
)
from configuration import AppConfig
from models.cache_entry import CacheEntry
from models.requests import ConversationUpdateRequest
from models.responses import (
    ConversationData,
    ConversationUpdateResponse,
    ReferencedDocument,
)
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
        docs = [
            ReferencedDocument(doc_title="Test Doc", doc_url="http://example.com")
        ]  # type: ignore
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
def mock_configuration(mocker: MockerFixture) -> MockType:
    """Mock configuration with conversation cache.

    Create a mocked configuration object with a mocked `conversation_cache` attribute.

    Parameters:
        mocker (pytest.MockFixture): The pytest-mock fixture used to create mocks.

    Returns:
        Mock: A mock configuration object whose `conversation_cache` attribute is a mock.
    """
    mock_config = mocker.Mock()
    mock_cache = mocker.Mock()
    mock_config.conversation_cache = mock_cache
    return mock_config


class TestCheckValidConversationId:
    """Test cases for the check_valid_conversation_id function."""

    def test_valid_conversation_id(self, mocker: MockerFixture) -> None:
        """Test with a valid conversation ID."""
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        # Should not raise an exception
        check_valid_conversation_id(VALID_CONVERSATION_ID)

    def test_invalid_conversation_id(self, mocker: MockerFixture) -> None:
        """Test with an invalid conversation ID."""
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            check_valid_conversation_id(INVALID_CONVERSATION_ID)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Invalid conversation ID format" in detail["response"]  # type: ignore


class TestCheckConversationExistence:
    """Test cases for the check_conversation_existence function."""

    def test_conversation_exists(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test when conversation exists."""
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        # Should not raise an exception
        check_conversation_existence("user_id", VALID_CONVERSATION_ID)

    def test_conversation_not_exists(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test when conversation does not exist."""
        mock_configuration.conversation_cache.list.return_value = []
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        with pytest.raises(HTTPException) as exc_info:
            check_conversation_existence("user_id", VALID_CONVERSATION_ID)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    def test_conversation_cache_type_none(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test when conversation_cache_configuration.type is None."""
        mock_cache_config = mocker.Mock()
        mock_cache_config.type = None
        mock_configuration.conversation_cache_configuration = mock_cache_config
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        # Should return early without raising an exception or calling list
        check_conversation_existence("user_id", VALID_CONVERSATION_ID)

        # Verify that conversation_cache.list was not called
        mock_configuration.conversation_cache.list.assert_not_called()


class TestGetConversationsListEndpoint:
    """Test cases for the GET /conversations endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker: MockerFixture) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mock_config._configuration = None  # pylint: disable=protected-access
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations_list_endpoint_handler(
                request=mocker.Mock(),
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_conversation_cache_not_configured(
        self, mocker: MockerFixture
    ) -> None:
        """Test the endpoint when conversation cache is not configured."""
        mock_authorization_resolvers(mocker)
        mock_config = mocker.Mock()
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = None
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations_list_endpoint_handler(
                request=mocker.Mock(),
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation cache not configured" in detail["response"]

    @pytest.mark.asyncio
    async def test_successful_retrieval(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test successful retrieval of conversation list."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        timestamp_str = "2024-01-01T00:00:00Z"
        timestamp_dt = datetime.fromisoformat(
            timestamp_str.replace("Z", "+00:00")
        ).replace(tzinfo=timezone.utc)
        timestamp = timestamp_dt.timestamp()

        mock_configuration.conversation_cache.list.return_value = [
            ConversationData(
                conversation_id=VALID_CONVERSATION_ID,
                topic_summary="summary",
                last_message_timestamp=timestamp,
            )
        ]

        response = await get_conversations_list_endpoint_handler(
            request=mocker.Mock(),
            auth=MOCK_AUTH,
        )

        assert response is not None
        assert len(response.conversations) == 1
        assert response.conversations[0].conversation_id == VALID_CONVERSATION_ID

    @pytest.mark.asyncio
    async def test_successful_retrieval_empty_list(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test successful retrieval of an empty conversation list."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mock_configuration.conversation_cache.list.return_value = []

        response = await get_conversations_list_endpoint_handler(
            request=mocker.Mock(),
            auth=MOCK_AUTH,
        )

        assert response is not None
        assert len(response.conversations) == 0

    @pytest.mark.asyncio
    async def test_with_skip_userid_check(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with skip_userid_check flag.

        Verify the conversations list handler forwards the skip_userid_check
        flag from the auth tuple to the conversation cache.

        Sets up a mocked configuration and auth tuple with the skip flag set to
        True, invokes the handler, and asserts that `conversation_cache.list`
        is called with the user ID and `True`.
        """
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mock_configuration.conversation_cache.list.return_value = []
        mock_auth_with_skip = ("mock_user_id", "mock_username", True, "mock_token")

        await get_conversations_list_endpoint_handler(
            request=mocker.Mock(),
            auth=mock_auth_with_skip,
        )

        mock_configuration.conversation_cache.list.assert_called_once_with(
            "mock_user_id", True
        )

    @pytest.mark.asyncio
    async def test_malformed_auth_object(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with a malformed auth object."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)

        with pytest.raises(IndexError):
            await get_conversations_list_endpoint_handler(
                request=mocker.Mock(),
                auth=(),  # Malformed auth object
            )


class TestGetConversationEndpoint:
    """Test cases for the GET /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker: MockerFixture) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mock_config._configuration = None  # pylint: disable=protected-access
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with an invalid conversation ID format."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=INVALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_conversation_cache_not_configured(
        self, mocker: MockerFixture
    ) -> None:
        """Test the endpoint when conversation cache is not configured.

        Verify the conversation GET endpoint raises an HTTP 500 error when the
        conversation cache is not configured.

        Patches the application configuration so
        `conversation_cache_configuration.type` is None and ensures
        `check_suid` returns True, then calls
        `get_conversation_endpoint_handler` and asserts that it raises an
        `HTTPException` with status code 500 and a response detail containing
        "Conversation cache not configured".
        """
        mock_authorization_resolvers(mocker)
        mock_config = mocker.Mock()
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = None
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation cache not configured" in detail["response"]

    @pytest.mark.asyncio
    async def test_conversation_not_found(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint when conversation does not exist."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_successful_retrieval(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test successful retrieval of a conversation."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mock_configuration.conversation_cache.get.return_value = [
            CacheEntry(
                query="query",
                response="response",
                provider="provider",
                model="model",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
            )
        ]

        response = await get_conversation_endpoint_handler(
            request=mocker.Mock(),
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response is not None
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert len(response.chat_history) == 1
        assert response.chat_history[0]["messages"][0]["content"] == "query"

    @pytest.mark.asyncio
    async def test_with_skip_userid_check(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with skip_userid_check flag."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mock_configuration.conversation_cache.get.return_value = [
            CacheEntry(
                query="query",
                response="response",
                provider="provider",
                model="model",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
            )
        ]
        mock_auth_with_skip = ("mock_user_id", "mock_username", True, "mock_token")

        await get_conversation_endpoint_handler(
            request=mocker.Mock(),
            conversation_id=VALID_CONVERSATION_ID,
            auth=mock_auth_with_skip,
        )

        mock_configuration.conversation_cache.get.assert_called_once_with(
            "mock_user_id", VALID_CONVERSATION_ID, True
        )

    @pytest.mark.asyncio
    async def test_malformed_auth_object(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with a malformed auth object."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)

        with pytest.raises(IndexError):
            await get_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=(),  # Malformed auth object
            )


class TestDeleteConversationEndpoint:
    """Test cases for the DELETE /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker: MockerFixture) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mock_config._configuration = None  # pylint: disable=protected-access
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with an invalid conversation ID format."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=INVALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_conversation_cache_not_configured(
        self, mocker: MockerFixture
    ) -> None:
        """Test the endpoint when conversation cache is not configured."""
        mock_authorization_resolvers(mocker)
        mock_config = mocker.Mock()
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = None
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation cache not configured" in detail["response"]

    @pytest.mark.asyncio
    async def test_conversation_not_found(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint when conversation does not exist."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.delete.return_value = False

        response = await delete_conversation_endpoint_handler(
            request=mocker.Mock(),
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response is not None
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert response.response == "Conversation cannot be deleted"

    @pytest.mark.asyncio
    async def test_successful_deletion(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test successful deletion of a conversation."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mock_configuration.conversation_cache.delete.return_value = True

        response = await delete_conversation_endpoint_handler(
            request=mocker.Mock(),
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response is not None
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert response.response == "Conversation deleted successfully"

    @pytest.mark.asyncio
    async def test_unsuccessful_deletion(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test unsuccessful deletion of a conversation."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mock_configuration.conversation_cache.delete.return_value = False

        response = await delete_conversation_endpoint_handler(
            request=mocker.Mock(),
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response is not None
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert response.response == "Conversation cannot be deleted"

    @pytest.mark.asyncio
    async def test_with_skip_userid_check(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with skip_userid_check flag.

        Verifies that providing an auth tuple with the skip-userid flag set
        causes the conversation delete handler to call the cache delete method
        with the skip flag.

        This test patches configuration and SUID validation, supplies an auth
        tuple where the third element is True, invokes
        delete_conversation_endpoint_handler, and asserts the cache.delete was
        called with (user_id, conversation_id, True).
        """
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mock_auth_with_skip = ("mock_user_id", "mock_username", True, "mock_token")

        await delete_conversation_endpoint_handler(
            request=mocker.Mock(),
            conversation_id=VALID_CONVERSATION_ID,
            auth=mock_auth_with_skip,
        )

        mock_configuration.conversation_cache.delete.assert_called_once_with(
            "mock_user_id", VALID_CONVERSATION_ID, True
        )

    @pytest.mark.asyncio
    async def test_malformed_auth_object(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with a malformed auth object."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)

        with pytest.raises(IndexError):
            await delete_conversation_endpoint_handler(
                request=mocker.Mock(),
                conversation_id=VALID_CONVERSATION_ID,
                auth=(),  # Malformed auth object
            )


class TestUpdateConversationEndpoint:
    """Test cases for the PUT /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker: MockerFixture) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Configuration is not loaded" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
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
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Invalid conversation ID format" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_conversation_cache_not_configured(
        self, mocker: MockerFixture
    ) -> None:
        """Test the endpoint when conversation cache is not configured."""
        mock_authorization_resolvers(mocker)
        mock_config = mocker.Mock()
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = None
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_config)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation cache not configured" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_conversation_not_found(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
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
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_successful_update(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test successful topic summary update."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
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

    @pytest.mark.asyncio
    async def test_with_skip_userid_check(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with skip_userid_check flag."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        mock_configuration.conversation_cache.list.return_value = [
            mocker.Mock(conversation_id=VALID_CONVERSATION_ID)
        ]
        mock_auth_with_skip = ("mock_user_id", "mock_username", True, "mock_token")
        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        await update_conversation_endpoint_handler(
            conversation_id=VALID_CONVERSATION_ID,
            update_request=update_request,
            auth=mock_auth_with_skip,
        )

        mock_configuration.conversation_cache.set_topic_summary.assert_called_once_with(
            "mock_user_id", VALID_CONVERSATION_ID, "New topic summary", True
        )

    @pytest.mark.asyncio
    async def test_malformed_auth_object(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test the endpoint with a malformed auth object."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations_v2.configuration", mock_configuration)
        mocker.patch("app.endpoints.conversations_v2.check_suid", return_value=True)
        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        with pytest.raises(IndexError):
            await update_conversation_endpoint_handler(
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=(),  # Malformed auth object
            )
