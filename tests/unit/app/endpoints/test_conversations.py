# pylint: disable=redefined-outer-name

"""Unit tests for the /conversations REST API endpoints."""

from fastapi import HTTPException, status, Request
import pytest
from llama_stack_client import APIConnectionError, NotFoundError

from app.endpoints.conversations import (
    get_conversation_endpoint_handler,
    delete_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    simplify_session_data,
)
from models.config import Action
from models.responses import (
    ConversationResponse,
    ConversationDeleteResponse,
    ConversationsListResponse,
)
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")
VALID_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
INVALID_CONVERSATION_ID = "invalid-id"


@pytest.fixture
def dummy_request() -> Request:
    """Mock request object for testing."""
    request = Request(
        scope={
            "type": "http",
        }
    )

    request.state.authorized_actions = set(Action)

    return request


def create_mock_conversation(
    mocker,
    conversation_id,
    created_at,
    last_message_at,
    message_count,
    last_used_model,
    last_used_provider,
    topic_summary=None,
):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Helper function to create a mock conversation object with all required attributes."""
    mock_conversation = mocker.Mock()
    mock_conversation.id = conversation_id
    mock_conversation.created_at = mocker.Mock()
    mock_conversation.created_at.isoformat.return_value = created_at
    mock_conversation.last_message_at = mocker.Mock()
    mock_conversation.last_message_at.isoformat.return_value = last_message_at
    mock_conversation.message_count = message_count
    mock_conversation.last_used_model = last_used_model
    mock_conversation.last_used_provider = last_used_provider
    mock_conversation.topic_summary = topic_summary
    return mock_conversation


def mock_database_session(mocker, query_result=None):
    """Helper function to mock get_session with proper context manager support."""
    mock_session = mocker.Mock()
    if query_result is not None:
        # Mock both the filtered and unfiltered query paths
        mock_query = mocker.Mock()
        mock_query.all.return_value = query_result
        mock_query.filter_by.return_value.all.return_value = query_result
        mock_session.query.return_value = mock_query

    # Mock get_session to return a context manager
    mock_session_context = mocker.MagicMock()
    mock_session_context.__enter__.return_value = mock_session
    mock_session_context.__exit__.return_value = None
    mocker.patch(
        "app.endpoints.conversations.get_session", return_value=mock_session_context
    )
    return mock_session


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture():
    """Set up configuration for tests."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "transcripts_enabled": False,
        },
        "mcp_servers": [],
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


@pytest.fixture(name="mock_session_data")
def mock_session_data_fixture():
    """Create mock session data for testing."""
    return {
        "session_id": VALID_CONVERSATION_ID,
        "session_name": "test-session",
        "started_at": "2024-01-01T00:00:00Z",
        "turns": [
            {
                "turn_id": "turn-1",
                "input_messages": [
                    {"content": "Hello", "role": "user", "context": None}
                ],
                "output_message": {
                    "content": "Hi there!",
                    "role": "assistant",
                    "stop_reason": "end_of_turn",
                    "tool_calls": [],
                },
                "started_at": "2024-01-01T00:01:00Z",
                "completed_at": "2024-01-01T00:01:05Z",
                "steps": [],  # Detailed steps that should be filtered out
            },
            {
                "turn_id": "turn-2",
                "input_messages": [
                    {"content": "How are you?", "role": "user", "context": None}
                ],
                "output_message": {
                    "content": "I'm doing well, thanks!",
                    "role": "assistant",
                    "stop_reason": "end_of_turn",
                    "tool_calls": [],
                },
                "started_at": "2024-01-01T00:02:00Z",
                "completed_at": "2024-01-01T00:02:03Z",
                "steps": [],  # Detailed steps that should be filtered out
            },
        ],
    }


@pytest.fixture(name="expected_chat_history")
def expected_chat_history_fixture():
    """Create expected simplified chat history for testing."""
    return [
        {
            "messages": [
                {"content": "Hello", "type": "user"},
                {"content": "Hi there!", "type": "assistant"},
            ],
            "started_at": "2024-01-01T00:01:00Z",
            "completed_at": "2024-01-01T00:01:05Z",
        },
        {
            "messages": [
                {"content": "How are you?", "type": "user"},
                {"content": "I'm doing well, thanks!", "type": "assistant"},
            ],
            "started_at": "2024-01-01T00:02:00Z",
            "completed_at": "2024-01-01T00:02:03Z",
        },
    ]


class TestSimplifySessionData:
    """Test cases for the simplify_session_data function."""

    @pytest.mark.asyncio
    async def test_simplify_session_data_with_model_dump(
        self, mock_session_data, expected_chat_history
    ):
        """Test simplify_session_data with session data."""
        result = simplify_session_data(mock_session_data)

        assert result == expected_chat_history

    @pytest.mark.asyncio
    async def test_simplify_session_data_empty_turns(self):
        """Test simplify_session_data with empty turns."""
        session_data = {
            "session_id": VALID_CONVERSATION_ID,
            "started_at": "2024-01-01T00:00:00Z",
            "turns": [],
        }

        result = simplify_session_data(session_data)

        assert not result

    @pytest.mark.asyncio
    async def test_simplify_session_data_filters_unwanted_fields(self):
        """Test that simplify_session_data properly filters out unwanted fields."""
        session_data = {
            "session_id": VALID_CONVERSATION_ID,
            "turns": [
                {
                    "turn_id": "turn-1",
                    "input_messages": [
                        {
                            "content": "Test message",
                            "role": "user",
                            "context": {"some": "context"},  # Should be filtered out
                            "metadata": {"extra": "data"},  # Should be filtered out
                        }
                    ],
                    "output_message": {
                        "content": "Test response",
                        "role": "assistant",
                        "stop_reason": "end_of_turn",  # Should be filtered out
                        "tool_calls": ["tool1", "tool2"],  # Should be filtered out
                    },
                    "started_at": "2024-01-01T00:01:00Z",
                    "completed_at": "2024-01-01T00:01:05Z",
                    "steps": ["step1", "step2"],  # Should be filtered out
                }
            ],
        }

        result = simplify_session_data(session_data)

        expected = [
            {
                "messages": [
                    {"content": "Test message", "type": "user"},
                    {"content": "Test response", "type": "assistant"},
                ],
                "started_at": "2024-01-01T00:01:00Z",
                "completed_at": "2024-01-01T00:01:05Z",
            }
        ]

        assert result == expected


class TestGetConversationEndpoint:
    """Test cases for the GET /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker, dummy_request):
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", None)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Configuration is not loaded" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint with an invalid conversation ID format."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                conversation_id=INVALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
                request=dummy_request,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid conversation ID format" in exc_info.value.detail["response"]
        assert INVALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    @pytest.mark.asyncio
    async def test_llama_stack_connection_error(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint when LlamaStack connection fails."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.side_effect = APIConnectionError(request=None)
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        # simulate situation when it is not possible to connect to Llama Stack
        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Unable to connect to Llama Stack" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_llama_stack_not_found_error(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint when LlamaStack returns NotFoundError."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder to raise NotFoundError
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.side_effect = NotFoundError(
            message="Session not found", response=mocker.Mock(request=None), body=None
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in exc_info.value.detail["response"]
        assert "could not be retrieved" in exc_info.value.detail["cause"]
        assert VALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    @pytest.mark.asyncio
    async def test_session_retrieve_exception(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint when session retrieval raises an exception."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder to raise a general exception
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.side_effect = Exception("Failed to get session")
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unknown error" in exc_info.value.detail["response"]
        assert (
            "Unknown error while getting conversation" in exc_info.value.detail["cause"]
        )

    @pytest.mark.asyncio
    async def test_successful_conversation_retrieval(
        self,
        mocker,
        setup_configuration,
        mock_session_data,
        expected_chat_history,
        dummy_request,
    ):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """Test successful conversation retrieval with simplified response structure."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.return_value = mocker.Mock(
            data=[mock_session_data]
        )

        # Mock session.retrieve to return an object with model_dump() method
        mock_session_retrieve_result = mocker.Mock()
        mock_session_retrieve_result.model_dump.return_value = mock_session_data
        mock_client.agents.session.retrieve.return_value = mock_session_retrieve_result

        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await get_conversation_endpoint_handler(
            request=dummy_request, conversation_id=VALID_CONVERSATION_ID, auth=MOCK_AUTH
        )

        assert isinstance(response, ConversationResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.chat_history == expected_chat_history
        mock_client.agents.session.list.assert_called_once_with(
            agent_id=VALID_CONVERSATION_ID
        )


class TestDeleteConversationEndpoint:
    """Test cases for the DELETE /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker, dummy_request):
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", None)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Configuration is not loaded" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint with an invalid conversation ID format."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=INVALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid conversation ID format" in exc_info.value.detail["response"]
        assert INVALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    @pytest.mark.asyncio
    async def test_llama_stack_connection_error(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint when LlamaStack connection fails."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.delete.side_effect = APIConnectionError(request=None)
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Unable to connect to Llama Stack" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_llama_stack_not_found_error(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint when LlamaStack returns NotFoundError."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder to raise NotFoundError
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.delete.side_effect = NotFoundError(
            message="Session not found", response=mocker.Mock(request=None), body=None
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in exc_info.value.detail["response"]
        assert "could not be deleted" in exc_info.value.detail["cause"]
        assert VALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    @pytest.mark.asyncio
    async def test_session_deletion_exception(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test the endpoint when session deletion raises an exception."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock AsyncLlamaStackClientHolder to raise a general exception
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.delete.side_effect = Exception(
            "Session deletion failed"
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unknown error" in exc_info.value.detail["response"]
        assert (
            "Unknown error while deleting conversation"
            in exc_info.value.detail["cause"]
        )

    @pytest.mark.asyncio
    async def test_successful_conversation_deletion(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test successful conversation deletion."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.validate_conversation_ownership")

        # Mock the delete_conversation function
        mocker.patch("app.endpoints.conversations.delete_conversation")

        # Mock AsyncLlamaStackClientHolder
        mock_client = mocker.AsyncMock()
        # Ensure the endpoint sees an existing session so it proceeds to delete
        mock_client.agents.session.list.return_value = mocker.Mock(
            data=[{"session_id": VALID_CONVERSATION_ID}]
        )
        mock_client.agents.session.delete.return_value = None  # Successful deletion
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await delete_conversation_endpoint_handler(
            request=dummy_request, conversation_id=VALID_CONVERSATION_ID, auth=MOCK_AUTH
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert response.response == "Conversation deleted successfully"
        mock_client.agents.session.delete.assert_called_once_with(
            agent_id=VALID_CONVERSATION_ID, session_id=VALID_CONVERSATION_ID
        )


# Generated entirely by AI, no human review, so read with that in mind.
class TestGetConversationsListEndpoint:
    """Test cases for the GET /conversations endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(self, mocker, dummy_request):
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", None)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations_list_endpoint_handler(
                auth=MOCK_AUTH, request=dummy_request
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Configuration is not loaded" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_successful_conversations_list_retrieval(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test successful retrieval of conversations list."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session and query results
        mock_conversations = [
            create_mock_conversation(
                mocker,
                "123e4567-e89b-12d3-a456-426614174000",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                5,
                "gemini/gemini-2.0-flash",
                "gemini",
                "OpenStack deployment strategies",
            ),
            create_mock_conversation(
                mocker,
                "456e7890-e12b-34d5-a678-901234567890",
                "2024-01-01T01:00:00Z",
                "2024-01-01T01:02:00Z",
                2,
                "gemini/gemini-2.5-flash",
                "gemini",
                "Kubernetes troubleshooting",
            ),
        ]
        mock_database_session(mocker, mock_conversations)

        response = await get_conversations_list_endpoint_handler(
            auth=MOCK_AUTH, request=dummy_request
        )

        assert isinstance(response, ConversationsListResponse)
        assert len(response.conversations) == 2

        # Test first conversation
        conv1 = response.conversations[0]
        assert conv1.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert conv1.created_at == "2024-01-01T00:00:00Z"
        assert conv1.last_message_at == "2024-01-01T00:05:00Z"
        assert conv1.message_count == 5
        assert conv1.last_used_model == "gemini/gemini-2.0-flash"
        assert conv1.last_used_provider == "gemini"
        assert conv1.topic_summary == "OpenStack deployment strategies"

        # Test second conversation
        conv2 = response.conversations[1]
        assert conv2.conversation_id == "456e7890-e12b-34d5-a678-901234567890"
        assert conv2.created_at == "2024-01-01T01:00:00Z"
        assert conv2.last_message_at == "2024-01-01T01:02:00Z"
        assert conv2.message_count == 2
        assert conv2.last_used_model == "gemini/gemini-2.5-flash"
        assert conv2.last_used_provider == "gemini"
        assert conv2.topic_summary == "Kubernetes troubleshooting"

    @pytest.mark.asyncio
    async def test_empty_conversations_list(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test when user has no conversations."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session with no results
        mock_database_session(mocker, [])

        response = await get_conversations_list_endpoint_handler(
            auth=MOCK_AUTH, request=dummy_request
        )

        assert isinstance(response, ConversationsListResponse)
        assert len(response.conversations) == 0
        assert response.conversations == []

    @pytest.mark.asyncio
    async def test_database_exception(self, mocker, setup_configuration, dummy_request):
        """Test when database query raises an exception."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session to raise exception
        mock_session = mock_database_session(mocker)
        mock_session.query.side_effect = Exception("Database error")

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations_list_endpoint_handler(
                auth=MOCK_AUTH, request=dummy_request
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unknown error" in exc_info.value.detail["response"]

    @pytest.mark.asyncio
    async def test_conversations_list_with_none_topic_summary(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test conversations list when topic_summary is None."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session with conversation having None topic_summary
        mock_conversations = [
            create_mock_conversation(
                mocker,
                "123e4567-e89b-12d3-a456-426614174000",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                5,
                "gemini/gemini-2.0-flash",
                "gemini",
                None,  # topic_summary is None
            ),
        ]
        mock_database_session(mocker, mock_conversations)

        response = await get_conversations_list_endpoint_handler(
            auth=MOCK_AUTH, request=dummy_request
        )

        assert isinstance(response, ConversationsListResponse)
        assert len(response.conversations) == 1

        conv = response.conversations[0]
        assert conv.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert conv.topic_summary is None

    @pytest.mark.asyncio
    async def test_conversations_list_with_mixed_topic_summaries(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test conversations list with mixed topic_summary values (some None, some not)."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session with mixed topic_summary values
        mock_conversations = [
            create_mock_conversation(
                mocker,
                "123e4567-e89b-12d3-a456-426614174000",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                5,
                "gemini/gemini-2.0-flash",
                "gemini",
                "OpenStack deployment strategies",  # Has topic_summary
            ),
            create_mock_conversation(
                mocker,
                "456e7890-e12b-34d5-a678-901234567890",
                "2024-01-01T01:00:00Z",
                "2024-01-01T01:02:00Z",
                2,
                "gemini/gemini-2.5-flash",
                "gemini",
                None,  # No topic_summary
            ),
            create_mock_conversation(
                mocker,
                "789e0123-e45b-67d8-a901-234567890123",
                "2024-01-01T02:00:00Z",
                "2024-01-01T02:03:00Z",
                3,
                "openai/gpt-4",
                "openai",
                "Machine learning model training",  # Has topic_summary
            ),
        ]
        mock_database_session(mocker, mock_conversations)

        response = await get_conversations_list_endpoint_handler(
            auth=MOCK_AUTH, request=dummy_request
        )

        assert isinstance(response, ConversationsListResponse)
        assert len(response.conversations) == 3

        # Test first conversation (with topic_summary)
        conv1 = response.conversations[0]
        assert conv1.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert conv1.topic_summary == "OpenStack deployment strategies"

        # Test second conversation (without topic_summary)
        conv2 = response.conversations[1]
        assert conv2.conversation_id == "456e7890-e12b-34d5-a678-901234567890"
        assert conv2.topic_summary is None

        # Test third conversation (with topic_summary)
        conv3 = response.conversations[2]
        assert conv3.conversation_id == "789e0123-e45b-67d8-a901-234567890123"
        assert conv3.topic_summary == "Machine learning model training"

    @pytest.mark.asyncio
    async def test_conversations_list_with_empty_topic_summary(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test conversations list when topic_summary is an empty string."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session with conversation having empty topic_summary
        mock_conversations = [
            create_mock_conversation(
                mocker,
                "123e4567-e89b-12d3-a456-426614174000",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                5,
                "gemini/gemini-2.0-flash",
                "gemini",
                "",  # Empty topic_summary
            ),
        ]
        mock_database_session(mocker, mock_conversations)

        response = await get_conversations_list_endpoint_handler(
            auth=MOCK_AUTH, request=dummy_request
        )

        assert isinstance(response, ConversationsListResponse)
        assert len(response.conversations) == 1

        conv = response.conversations[0]
        assert conv.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert conv.topic_summary == ""

    @pytest.mark.asyncio
    async def test_conversations_list_topic_summary_field_presence(
        self, mocker, setup_configuration, dummy_request
    ):
        """Test that topic_summary field is always present in ConversationDetails objects."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session with conversations
        mock_conversations = [
            create_mock_conversation(
                mocker,
                "123e4567-e89b-12d3-a456-426614174000",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                5,
                "gemini/gemini-2.0-flash",
                "gemini",
                "Test topic summary",
            ),
        ]
        mock_database_session(mocker, mock_conversations)

        response = await get_conversations_list_endpoint_handler(
            auth=MOCK_AUTH, request=dummy_request
        )

        assert isinstance(response, ConversationsListResponse)
        assert len(response.conversations) == 1

        conv = response.conversations[0]

        # Verify that topic_summary field exists and is accessible
        assert hasattr(conv, "topic_summary")
        assert conv.topic_summary == "Test topic summary"

        # Verify that the field is properly serialized (if needed for API responses)
        conv_dict = conv.model_dump()
        assert "topic_summary" in conv_dict
        assert conv_dict["topic_summary"] == "Test topic summary"
