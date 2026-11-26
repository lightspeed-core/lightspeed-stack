"""Unit tests for the /v3/conversations REST API endpoints."""

from datetime import UTC, datetime

import pytest
from fastapi import Request
from pytest_mock import MockerFixture

from app.endpoints.conversations_v3 import (
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    update_conversation_endpoint_handler,
)
from conversations.display_history.agentic.models.conversation import (
    Conversation,
    ConversationMetadata,
)
from conversations.display_history.errors import InvalidConversationIdError
from models.api.requests import ConversationUpdateRequest
from models.config import Action
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")
VALID_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
INVALID_CONVERSATION_ID = "invalid-id"


@pytest.fixture(name="dummy_request")
def dummy_request_fixture() -> Request:
    """Mock request object for testing.

    The returned Request has state.authorized_actions set to every Action.
    """
    request = Request(scope={"type": "http"})
    request.state.authorized_actions = set(Action)
    return request


@pytest.fixture(name="configure_v3")
def configure_v3_fixture(mocker: MockerFixture) -> None:
    """Authorize the request and skip configuration loading."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.conversations_v3.check_configuration_loaded")


def sample_metadata() -> ConversationMetadata:
    """Conversation metadata used by list endpoint tests."""
    return ConversationMetadata(
        conversation_id=VALID_CONVERSATION_ID,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        topic_summary="summary",
    )


def sample_conversation() -> Conversation:
    """Conversation used by get endpoint tests."""
    return Conversation(
        conversation_id=VALID_CONVERSATION_ID,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        topic_summary="summary",
        chat_history=[],
    )


@pytest.mark.usefixtures("configure_v3")
class TestGetConversationsListEndpoint:
    """Test cases for the GET /v3/conversations endpoint."""

    @pytest.mark.asyncio
    async def test_successful_retrieval(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test successful retrieval of the conversation list."""
        mocker.patch(
            "app.endpoints.conversations_v3.list_conversations",
            return_value=[sample_metadata()],
        )

        response = await get_conversations_list_endpoint_handler(
            request=dummy_request,
            auth=MOCK_AUTH,
        )

        assert len(response.conversations) == 1
        assert response.conversations[0].conversation_id == VALID_CONVERSATION_ID

    @pytest.mark.asyncio
    async def test_successful_retrieval_empty_list(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test successful retrieval of an empty conversation list."""
        mocker.patch(
            "app.endpoints.conversations_v3.list_conversations",
            return_value=[],
        )

        response = await get_conversations_list_endpoint_handler(
            request=dummy_request,
            auth=MOCK_AUTH,
        )

        assert response.conversations == []


@pytest.mark.usefixtures("configure_v3")
class TestGetConversationEndpoint:
    """Test cases for the GET /v3/conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_successful_retrieval(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test successful retrieval of a conversation."""
        mocker.patch(
            "app.endpoints.conversations_v3.get_conversation",
            return_value=sample_conversation(),
        )

        response = await get_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.chat_history == []

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint with an invalid conversation ID format."""
        get_mock = mocker.patch("app.endpoints.conversations_v3.get_conversation")

        with pytest.raises(InvalidConversationIdError):
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=INVALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        get_mock.assert_not_called()


@pytest.mark.usefixtures("configure_v3")
class TestDeleteConversationEndpoint:
    """Test cases for the DELETE /v3/conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_successful_deletion(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test successful deletion of a conversation."""
        mocker.patch(
            "app.endpoints.conversations_v3.delete_conversation",
            return_value=True,
        )

        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response.deleted is True
        assert response.conversation_id == VALID_CONVERSATION_ID

    @pytest.mark.asyncio
    async def test_conversation_not_deleted(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test deletion when the conversation is already missing."""
        mocker.patch(
            "app.endpoints.conversations_v3.delete_conversation",
            return_value=False,
        )

        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response.deleted is False

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint with an invalid conversation ID format."""
        delete_mock = mocker.patch("app.endpoints.conversations_v3.delete_conversation")

        with pytest.raises(InvalidConversationIdError):
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=INVALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        delete_mock.assert_not_called()


@pytest.mark.usefixtures("configure_v3")
class TestUpdateConversationEndpoint:
    """Test cases for the PUT /v3/conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_successful_update(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test successful update of a conversation topic summary."""
        mocker.patch(
            "app.endpoints.conversations_v3.update_conversation_topic",
            return_value=True,
        )

        response = await update_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            update_request=ConversationUpdateRequest(topic_summary="new topic"),
            auth=MOCK_AUTH,
        )

        assert response.success is True
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.model_dump()["message"] == "Topic summary updated successfully"

    @pytest.mark.asyncio
    async def test_conversation_not_updated(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test update when the conversation row disappears before the update."""
        mocker.patch(
            "app.endpoints.conversations_v3.update_conversation_topic",
            return_value=False,
        )

        response = await update_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            update_request=ConversationUpdateRequest(topic_summary="new topic"),
            auth=MOCK_AUTH,
        )

        assert response.success is False
        assert response.model_dump()["message"] == "Topic summary was not updated"

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint with an invalid conversation ID format."""
        update_mock = mocker.patch(
            "app.endpoints.conversations_v3.update_conversation_topic"
        )

        with pytest.raises(InvalidConversationIdError):
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=INVALID_CONVERSATION_ID,
                update_request=ConversationUpdateRequest(topic_summary="new topic"),
                auth=MOCK_AUTH,
            )

        update_mock.assert_not_called()
