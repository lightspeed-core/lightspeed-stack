# pylint: disable=redefined-outer-name, too-many-lines
# pylint: disable=too-many-arguments,too-many-positional-arguments

"""Unit tests for the /conversations REST API endpoints."""

from typing import Any, Optional

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, NotFoundError
from pytest_mock import MockerFixture, MockType
from sqlalchemy.exc import SQLAlchemyError

from app.endpoints.conversations import (
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    simplify_session_data,
)
from configuration import AppConfig
from models.config import Action
from models.database.conversations import UserConversation
from models.responses import (
    ConversationDeleteResponse,
    ConversationResponse,
    ConversationsListResponse,
)
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")
VALID_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
INVALID_CONVERSATION_ID = "invalid-id"


@pytest.fixture
def dummy_request() -> Request:
    """Mock request object for testing.

    Create a mock FastAPI Request configured for tests with full authorization.

    The returned Request has state.authorized_actions set to a set containing
    every member of Action.
    """
    request = Request(
        scope={
            "type": "http",
        }
    )

    request.state.authorized_actions = set(Action)

    return request


def create_mock_conversation(
    mocker: MockerFixture,
    conversation_id: str,
    created_at: str,
    last_message_at: str,
    message_count: int,
    last_used_model: str,
    last_used_provider: str,
    topic_summary: Optional[str] = None,
) -> MockType:
    """Helper function to create a mock conversation object with all required attributes.

    Create a mock conversation object with the attributes used by the
    conversations list and detail tests.

    The returned mock has the following attributes:
    - id: the conversation identifier (string)
    - created_at.isoformat(): returns the provided created_at string
    - last_message_at.isoformat(): returns the provided last_message_at string
    - message_count: number of messages in the conversation
    - last_used_model: model identifier last used in the conversation
    - last_used_provider: provider identifier last used in the conversation
    - topic_summary: optional topic summary (may be None or empty string)

    Parameters:
        mocker (MockerFixture): pytest mocker fixture used to build the mock object.
        conversation_id (str): Conversation identifier to assign to the mock.
        created_at (str): ISO-formatted created-at timestamp to be returned by
        created_at.isoformat().
        last_message_at (str): ISO-formatted last-message timestamp to be
        returned by last_message_at.isoformat().
        message_count (int): Message count to assign to the mock.
        last_used_model (str): Last used model string to assign to the mock.
        last_used_provider (str): Last used provider string to assign to the mock.
        topic_summary (Optional[str]): Optional topic summary to assign to the mock.

    Returns:
        mock_conversation: A mock object configured with the above attributes.
    """
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


def mock_database_session(
    mocker: MockerFixture, query_result: Optional[list[MockType]] = None
) -> MockType:
    """Helper function to mock get_session with proper context manager support.

    Create and patch a mocked database session and a context-manager-compatible get_session.

    Parameters:
        mocker (pytest.MockerFixture): Fixture used to create and patch mocks.
        query_result (Optional[list]): If provided, configures the
        session.query().all() and session.query().filter_by().all() to return
        this list.

    Returns:
        Mock: The mocked session object that will be yielded by the patched
        get_session context manager.
    """
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
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests.

    Create an AppConfig prepopulated with test-friendly default settings.

    Returns:
        AppConfig: An AppConfig instance initialized from a dictionary
        containing defaults suitable for tests (local service host/port,
        disabled auth and user-data collection, test Llama Stack API key and
        URL, and single worker).
    """
    config_dict: dict[str, Any] = {
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
def mock_session_data_fixture() -> dict[str, Any]:
    """Create mock session data for testing.

    Provide a representative mock session data payload used by tests to
    simulate a conversation session.

    The returned dictionary contains:
    - session_id: conversation identifier.
    - session_name: human-readable session name.
    - started_at: ISO 8601 timestamp when the session started.
    - turns: list of turn objects; each turn includes:
        - turn_id: identifier for the turn.
        - input_messages: list of input message objects with `content`, `role`,
          and optional `context`.
        - output_message: assistant response object with `content`, `role`, and
          auxiliary fields (e.g., `stop_reason`, `tool_calls`) that tests
          expect to be filtered by simplification logic.
        - started_at / completed_at: ISO 8601 timestamps for the turn.
        - steps: detailed internal steps included to verify they are removed by simplification.

    Returns:
        dict: A mock session data structure matching the shape produced by the
        Llama Stack client for use in unit tests.
    """
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
def expected_chat_history_fixture() -> list[dict[str, Any]]:
    """Create expected simplified chat history for testing.

    Expected simplified chat history used by tests.

    Returns:
        list[dict[str, Any]]: A list of conversation turns. Each turn contains:
            - messages: list of message dicts with `content` (str) and `type`
              (`"user"` or `"assistant"`)
            - started_at: ISO 8601 UTC timestamp string for the turn start
            - completed_at: ISO 8601 UTC timestamp string for the turn end
    """
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


@pytest.fixture(name="mock_conversation")
def mock_conversation_fixture() -> UserConversation:
    """Create a mock UserConversation object for testing.

    Returns:
        mock_conv (UserConversation): A UserConversation initialized with
        VALID_CONVERSATION_ID, user_id set to "another_user", message_count 2,
        last_used_model "mock-model", last_used_provider "mock-provider", and
        topic_summary "Mock topic".
    """
    mock_conv = UserConversation()
    mock_conv.id = VALID_CONVERSATION_ID
    mock_conv.user_id = "another_user"  # Different from test auth
    mock_conv.message_count = 2
    mock_conv.last_used_model = "mock-model"
    mock_conv.last_used_provider = "mock-provider"
    mock_conv.topic_summary = "Mock topic"
    return mock_conv


class TestSimplifySessionData:
    """Test cases for the simplify_session_data function."""

    @pytest.mark.asyncio
    async def test_simplify_session_data_with_model_dump(
        self,
        mock_session_data: dict[str, Any],
        expected_chat_history: list[dict[str, Any]],
    ) -> None:
        """Test simplify_session_data with session data."""
        result = simplify_session_data(mock_session_data)

        assert result == expected_chat_history

    @pytest.mark.asyncio
    async def test_simplify_session_data_empty_turns(self) -> None:
        """Test simplify_session_data with empty turns."""
        session_data = {
            "session_id": VALID_CONVERSATION_ID,
            "started_at": "2024-01-01T00:00:00Z",
            "turns": [],
        }

        result = simplify_session_data(session_data)

        assert not result

    @pytest.mark.asyncio
    async def test_simplify_session_data_filters_unwanted_fields(self) -> None:
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
    async def test_configuration_not_loaded(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mocker.patch("app.endpoints.conversations.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Configuration is not loaded" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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

        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Invalid conversation ID format" in detail["response"]  # type: ignore
        assert INVALID_CONVERSATION_ID in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_llama_stack_connection_error(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint when LlamaStack connection fails."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

        # Mock AsyncLlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.side_effect = APIConnectionError(
            request=None  # type: ignore
        )
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

        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore

    @pytest.mark.asyncio
    async def test_llama_stack_not_found_error(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint when LlamaStack returns NotFoundError.

        Verify the GET /conversations/{conversation_id} handler raises an HTTP
        404 when the Llama Stack client reports the session as not found.

        Asserts that the raised HTTPException contains a response message
        indicating the conversation was not found and a cause that includes
        "does not exist" and the conversation ID.
        """
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

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

        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore
        assert "does not exist" in detail["cause"]  # type: ignore
        assert VALID_CONVERSATION_ID in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_session_retrieve_exception(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint when session retrieval raises an APIConnectionError."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

        # Mock AsyncLlamaStackClientHolder to raise APIConnectionError
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.side_effect = APIConnectionError(
            request=mocker.Mock()
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore

    @pytest.mark.asyncio
    async def test_get_conversation_forbidden(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test forbidden access when user lacks permission to read conversation."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value=set(Action.GET_CONVERSATION),
        )  # Reduce user's permissions to access only their conversations

        mock_row = mocker.Mock()
        mock_row.user_id = "different_user_id"

        # Mock the SQLAlchemy-like session
        mock_session = mocker.MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_row
        )

        mock_session.__enter__.return_value = mock_session
        mock_session.__exit__.return_value = None

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        expected = (
            f"User {MOCK_AUTH[0]} does not have permission "
            f"to read conversation with ID {VALID_CONVERSATION_ID}"
        )
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert expected in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_get_others_conversations_allowed_for_authorized_user(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        mock_conversation: MockType,
        dummy_request: Request,
        mock_session_data: dict[str, Any],
    ) -> None:  # pylint: disable=too-many-arguments, too-many-positional-arguments
        """Test allowed access to another user's conversation for authorized user."""
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value={Action.GET_CONVERSATION, Action.READ_OTHERS_CONVERSATIONS},
        )  # Allow user to access other users' conversations
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.return_value = mocker.Mock(
            data=[mock_session_data]
        )

        mock_session_retrieve_result = mocker.Mock()
        mock_session_retrieve_result.model_dump.return_value = mock_session_data
        mock_client.agents.session.retrieve.return_value = mock_session_retrieve_result

        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client
        response = await get_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response.conversation_id == VALID_CONVERSATION_ID
        assert hasattr(response, "chat_history")

    @pytest.mark.asyncio
    async def test_successful_conversation_retrieval(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        mock_session_data: dict[str, Any],
        expected_chat_history: list[dict[str, Any]],
        dummy_request: Request,
    ) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """Test successful conversation retrieval with simplified response structure."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

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

    @pytest.mark.asyncio
    async def test_retrieve_conversation_returns_none(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when retrieve_conversation returns None."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation", return_value=None
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_no_sessions_found_in_get_conversation(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test when no sessions are found for the conversation."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder with empty sessions list
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.return_value = mocker.Mock(data=[])
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
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_in_get_conversation(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test when SQLAlchemyError is raised during conversation retrieval."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder - SQLAlchemyError should come from session.retrieve
        mock_client = mocker.AsyncMock()
        mock_session_list_response = mocker.Mock()
        mock_session_list_response.data = [{"session_id": VALID_CONVERSATION_ID}]
        mock_client.agents.session.list.return_value = mock_session_list_response
        mock_client.agents.session.retrieve.side_effect = SQLAlchemyError(
            "Database error"
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

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Database" in detail["response"]  # type: ignore


class TestDeleteConversationEndpoint:
    """Test cases for the DELETE /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mocker.patch("app.endpoints.conversations.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Configuration is not loaded" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_format(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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

        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Invalid conversation ID format" in detail["response"]  # type: ignore
        assert INVALID_CONVERSATION_ID in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_llama_stack_connection_error(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint when LlamaStack connection fails."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

        # Mock AsyncLlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.delete.side_effect = APIConnectionError(
            request=None  # type: ignore
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

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore

    @pytest.mark.asyncio
    async def test_llama_stack_not_found_error(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint when LlamaStack returns NotFoundError."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

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
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore
        assert "does not exist" in detail["cause"]  # type: ignore
        assert VALID_CONVERSATION_ID in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_session_deletion_exception(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint when session deletion raises an exception."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

        # Mock AsyncLlamaStackClientHolder to raise a general exception
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.delete.side_effect = APIConnectionError(
            request=None  # type: ignore
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
        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Unable to connect to Llama Stack" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_delete_conversation_forbidden(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test forbidden deletion when user lacks permission to delete conversation."""
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value=set(Action.DELETE_CONVERSATION),
        )  # Reduce user's permissions to delete only their conversations

        mock_row = mocker.Mock()
        mock_row.user_id = "different_user_id"

        # Mock the SQLAlchemy-like session
        mock_session = mocker.MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_row
        )

        mock_session.__enter__.return_value = mock_session
        mock_session.__exit__.return_value = None

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        expected = (
            f"User {MOCK_AUTH[0]} does not have permission "
            f"to delete conversation with ID {VALID_CONVERSATION_ID}"
        )
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert expected in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_delete_others_conversations_allowed_for_authorized_user(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        mock_conversation: MockType,
        dummy_request: Request,
    ) -> None:
        """Test allowed deletion of another user's conversation for authorized user."""
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value={
                Action.DELETE_OTHERS_CONVERSATIONS,
                Action.DELETE_CONVERSATION,
            },
        )  # Allow user to detele other users' conversations

        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.return_value.data = [
            {"session_id": VALID_CONVERSATION_ID}
        ]
        mock_client.agents.session.delete.return_value = None
        mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder.get_client",
            return_value=mock_client,
        )

        mocker.patch(
            "app.endpoints.conversations.delete_conversation", return_value=None
        )
        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert response.success is True
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert "deleted successfully" in response.response

    @pytest.mark.asyncio
    async def test_successful_conversation_deletion(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test successful conversation deletion."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch("app.endpoints.conversations.retrieve_conversation")

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

    @pytest.mark.asyncio
    async def test_retrieve_conversation_returns_none_in_delete(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when retrieve_conversation returns None in delete endpoint."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation", return_value=None
        )

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_no_sessions_found_in_delete(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test when no sessions are found in delete endpoint (early return)."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder with empty sessions list
        mock_client = mocker.AsyncMock()
        mock_client.agents.session.list.return_value = mocker.Mock(data=[])
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True  # Operation completed successfully
        assert "cannot be deleted" in response.response  # But nothing was deleted

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_in_delete(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test when SQLAlchemyError is raised during conversation deletion."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)
        mocker.patch("app.endpoints.conversations.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder - SQLAlchemyError should come from delete_conversation
        mock_client = mocker.AsyncMock()
        mock_session_list_response = mocker.Mock()
        mock_session_list_response.data = [{"session_id": VALID_CONVERSATION_ID}]
        mock_client.agents.session.list.return_value = mock_session_list_response
        mock_client.agents.session.delete.return_value = None
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        # Mock delete_conversation to raise SQLAlchemyError
        mocker.patch(
            "app.endpoints.conversations.delete_conversation",
            side_effect=SQLAlchemyError("Database error"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Database" in detail["response"]  # type: ignore


# Generated entirely by AI, no human review, so read with that in mind.
class TestGetConversationsListEndpoint:
    """Test cases for the GET /conversations endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mocker.patch("app.endpoints.conversations.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations_list_endpoint_handler(
                auth=MOCK_AUTH, request=dummy_request
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Configuration is not loaded" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_successful_conversations_list_retrieval(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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
    async def test_database_exception(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when database query raises an exception."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session to raise exception
        mock_session = mock_database_session(mocker)
        mock_session.query.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await get_conversations_list_endpoint_handler(
                auth=MOCK_AUTH, request=dummy_request
            )

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_in_list(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when database query raises SQLAlchemyError."""
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.conversations.configuration", setup_configuration)

        # Mock database session to raise SQLAlchemyError when all() is called
        # Since dummy_request has all actions, it will use query directly (not filter_by)
        mock_session = mocker.Mock()
        mock_query = mocker.Mock()
        # Configure all() to raise SQLAlchemyError
        mock_query.all = mocker.Mock(
            side_effect=SQLAlchemyError("Database connection error")
        )
        mock_session.query.return_value = mock_query

        # Mock get_session to return a context manager
        mock_session_context = mocker.MagicMock()
        mock_session_context.__enter__.return_value = mock_session
        mock_session_context.__exit__.return_value = None
        mocker.patch(
            "app.endpoints.conversations.get_session", return_value=mock_session_context
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations_list_endpoint_handler(
                auth=MOCK_AUTH, request=dummy_request
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Database" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_conversations_list_with_none_topic_summary(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
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
