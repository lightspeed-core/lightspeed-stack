"""Unit tests for the /conversations REST API endpoints."""

import pytest
from fastapi import HTTPException, status
from llama_stack_client import APIConnectionError, NotFoundError

from app.endpoints.conversations import (
    get_conversation_endpoint_handler,
    delete_conversation_endpoint_handler,
    conversation_id_to_agent_id,
    simplify_session_data,
)
from models.responses import ConversationResponse, ConversationDeleteResponse
from configuration import AppConfig

MOCK_AUTH = ("mock_user_id", "mock_username", "mock_token")
VALID_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
VALID_AGENT_ID = "agent_123"
INVALID_CONVERSATION_ID = "invalid-id"


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


@pytest.fixture(autouse=True)
def setup_conversation_mapping():
    """Set up and clean up the conversation ID to agent ID mapping."""
    # Clear the mapping before each test
    conversation_id_to_agent_id.clear()
    yield
    # Clean up after each test
    conversation_id_to_agent_id.clear()


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

    def test_simplify_session_data_with_model_dump(
        self, mock_session_data, expected_chat_history, mocker
    ):
        """Test simplify_session_data with session data that has model_dump method."""
        # Create a mock object with model_dump method
        mock_session_obj = mocker.Mock()
        mock_session_obj.model_dump.return_value = mock_session_data

        result = simplify_session_data(mock_session_obj)

        assert result == expected_chat_history
        mock_session_obj.model_dump.assert_called_once()

    def test_simplify_session_data_empty_turns(self, mocker):
        """Test simplify_session_data with empty turns."""
        session_data = {
            "session_id": VALID_CONVERSATION_ID,
            "started_at": "2024-01-01T00:00:00Z",
            "turns": [],
        }

        mock_session_obj = mocker.Mock()
        mock_session_obj.model_dump.return_value = session_data

        result = simplify_session_data(mock_session_obj)

        assert not result

    def test_simplify_session_data_filters_unwanted_fields(self, mocker):
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

        mock_session_obj = mocker.Mock()
        mock_session_obj.model_dump.return_value = session_data

        result = simplify_session_data(mock_session_obj)

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

    def test_configuration_not_loaded(self, mocker):
        """Test the endpoint when configuration is not loaded."""
        mocker.patch("app.endpoints.conversations.configuration", None)

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Configuration is not loaded" in exc_info.value.detail["response"]

    def test_invalid_conversation_id_format(self, mocker, setup_configuration):
        """Test the endpoint with an invalid conversation ID format."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_endpoint_handler(INVALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid conversation ID format" in exc_info.value.detail["response"]
        assert INVALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    def test_conversation_not_found_in_mapping(self, mocker, setup_configuration):
        """Test the endpoint when conversation ID is not in the mapping."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "conversation ID not found" in exc_info.value.detail["response"]
        assert VALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    def test_llama_stack_connection_error(self, mocker, setup_configuration):
        """Test the endpoint when LlamaStack connection fails."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.Mock()
        mock_client.agents.session.retrieve.side_effect = APIConnectionError(
            request=None
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        # simulate situation when it is not possible to connect to Llama Stack
        with pytest.raises(HTTPException) as exc_info:
            get_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Unable to connect to Llama Stack" in exc_info.value.detail["response"]

    def test_llama_stack_not_found_error(self, mocker, setup_configuration):
        """Test the endpoint when LlamaStack returns NotFoundError."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder to raise NotFoundError
        mock_client = mocker.Mock()
        mock_client.agents.session.retrieve.side_effect = NotFoundError(
            message="Session not found", response=mocker.Mock(request=None), body=None
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in exc_info.value.detail["response"]
        assert "could not be retrieved" in exc_info.value.detail["cause"]
        assert VALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    def test_session_retrieve_exception(self, mocker, setup_configuration):
        """Test the endpoint when session retrieval raises an exception."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder to raise a general exception
        mock_client = mocker.Mock()
        mock_client.agents.session.retrieve.side_effect = Exception(
            "Failed to get session"
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unknown error" in exc_info.value.detail["response"]
        assert (
            "Unknown error while getting conversation" in exc_info.value.detail["cause"]
        )

    def test_successful_conversation_retrieval(
        self, mocker, setup_configuration, mock_session_data, expected_chat_history
    ):
        """Test successful conversation retrieval with simplified response structure."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock session data with model_dump method
        mock_session_obj = mocker.Mock()
        mock_session_obj.model_dump.return_value = mock_session_data

        # Mock LlamaStackClientHolder
        mock_client = mocker.Mock()
        mock_client.agents.session.retrieve.return_value = mock_session_obj
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = get_conversation_endpoint_handler(
            VALID_CONVERSATION_ID, _auth=MOCK_AUTH
        )

        assert isinstance(response, ConversationResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.chat_history == expected_chat_history
        mock_client.agents.session.retrieve.assert_called_once_with(
            agent_id=VALID_AGENT_ID, session_id=VALID_CONVERSATION_ID
        )


class TestDeleteConversationEndpoint:
    """Test cases for the DELETE /conversations/{conversation_id} endpoint."""

    def test_configuration_not_loaded(self, mocker):
        """Test the endpoint when configuration is not loaded."""
        mocker.patch("app.endpoints.conversations.configuration", None)

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Configuration is not loaded" in exc_info.value.detail["response"]

    def test_invalid_conversation_id_format(self, mocker, setup_configuration):
        """Test the endpoint with an invalid conversation ID format."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint_handler(
                INVALID_CONVERSATION_ID, _auth=MOCK_AUTH
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid conversation ID format" in exc_info.value.detail["response"]
        assert INVALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    def test_conversation_not_found_in_mapping(self, mocker, setup_configuration):
        """Test the endpoint when conversation ID is not in the mapping."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "conversation ID not found" in exc_info.value.detail["response"]
        assert VALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    def test_llama_stack_connection_error(self, mocker, setup_configuration):
        """Test the endpoint when LlamaStack connection fails."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.Mock()
        mock_client.agents.session.delete.side_effect = APIConnectionError(request=None)
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Unable to connect to Llama Stack" in exc_info.value.detail["response"]

    def test_llama_stack_not_found_error(self, mocker, setup_configuration):
        """Test the endpoint when LlamaStack returns NotFoundError."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder to raise NotFoundError
        mock_client = mocker.Mock()
        mock_client.agents.session.delete.side_effect = NotFoundError(
            message="Session not found", response=mocker.Mock(request=None), body=None
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in exc_info.value.detail["response"]
        assert "could not be deleted" in exc_info.value.detail["cause"]
        assert VALID_CONVERSATION_ID in exc_info.value.detail["cause"]

    def test_session_deletion_exception(self, mocker, setup_configuration):
        """Test the endpoint when session deletion raises an exception."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder to raise a general exception
        mock_client = mocker.Mock()
        mock_client.agents.session.delete.side_effect = Exception(
            "Session deletion failed"
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint_handler(VALID_CONVERSATION_ID, _auth=MOCK_AUTH)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unknown error" in exc_info.value.detail["response"]
        assert (
            "Unknown error while deleting conversation"
            in exc_info.value.detail["cause"]
        )

    def test_successful_conversation_deletion(self, mocker, setup_configuration):
        """Test successful conversation deletion."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)

        # Set up conversation mapping
        conversation_id_to_agent_id[VALID_CONVERSATION_ID] = VALID_AGENT_ID

        # Mock LlamaStackClientHolder
        mock_client = mocker.Mock()
        mock_client.agents.session.delete.return_value = None  # Successful deletion
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.LlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = delete_conversation_endpoint_handler(
            VALID_CONVERSATION_ID, _auth=MOCK_AUTH
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert response.response == "Conversation deleted successfully"
        mock_client.agents.session.delete.assert_called_once_with(
            agent_id=VALID_AGENT_ID, session_id=VALID_CONVERSATION_ID
        )
