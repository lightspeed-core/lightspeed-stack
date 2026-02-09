# pylint: disable=redefined-outer-name, too-many-lines
# pylint: disable=too-many-arguments,too-many-positional-arguments

"""Unit tests for the /conversations REST API endpoints."""

from datetime import UTC, datetime
from typing import Any, Optional

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, APIStatusError, NotFoundError
from pytest_mock import MockerFixture, MockType
from sqlalchemy.exc import SQLAlchemyError

from app.endpoints.conversations_v1 import (
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    update_conversation_endpoint_handler,
)
from utils.conversations import build_conversation_turns_from_items
from configuration import AppConfig
from models.config import Action
from models.database.conversations import UserConversation, UserTurn
from models.requests import ConversationUpdateRequest
from models.responses import (
    ConversationDeleteResponse,
    ConversationResponse,
    ConversationsListResponse,
    ConversationUpdateResponse,
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


def create_mock_db_turn(
    mocker: MockerFixture,
    turn_number: int,
    started_at: str = "2024-01-01T00:01:00Z",
    completed_at: str = "2024-01-01T00:01:05Z",
    provider: str = "google",
    model: str = "gemini-2.0-flash-exp",
) -> MockType:
    """Create a mock UserTurn database object.

    Args:
        mocker: Mocker fixture
        turn_number: Turn number (1-indexed)
        started_at: ISO 8601 timestamp string
        completed_at: ISO 8601 timestamp string
        provider: Provider identifier
        model: Model identifier

    Returns:
        Mock UserTurn database object with required attributes
    """
    mock_turn = mocker.Mock(spec=UserTurn)
    mock_turn.turn_number = turn_number
    # Convert ISO strings to datetime objects (Python 3.12+ supports "Z" directly)
    mock_turn.started_at = datetime.fromisoformat(started_at)
    mock_turn.completed_at = datetime.fromisoformat(completed_at)
    mock_turn.provider = provider
    mock_turn.model = model
    return mock_turn


def _setup_user_turn_query(
    mock_query: MockType, db_turns: Optional[list[MockType]]
) -> None:
    """Configure mock query for UserTurn model.

    Args:
        mock_query: The mock query object to configure.
        db_turns: List of UserTurn objects to return, or None for empty list.
    """
    turns_to_return = db_turns if db_turns is not None else []
    mock_query.filter_by.return_value.order_by.return_value.all.return_value = (
        turns_to_return
    )


def _setup_user_conversation_query(
    mock_query: MockType, query_result: Optional[list[MockType]]
) -> None:
    """Configure mock query for UserConversation model.

    Args:
        mock_query: The mock query object to configure.
        query_result: List of UserConversation objects to return, or None for None.
    """
    if query_result is not None:
        mock_query.all.return_value = query_result
        mock_query.filter_by.return_value.all.return_value = query_result
        mock_query.filter_by.return_value.first.return_value = (
            query_result[0] if query_result else None
        )
    else:
        mock_query.filter_by.return_value.first.return_value = None


def _patch_get_session_functions(
    mocker: MockerFixture, mock_session_context: MockType
) -> None:
    """Patch all get_session functions used by the endpoint handlers.

    Args:
        mocker: Mocker fixture for creating patches.
        mock_session_context: The context manager mock to return from get_session.
    """
    mocker.patch(
        "app.endpoints.conversations_v1.get_session", return_value=mock_session_context
    )
    mocker.patch("app.database.get_session", return_value=mock_session_context)
    mocker.patch("utils.endpoints.get_session", return_value=mock_session_context)
    mocker.patch("utils.endpoints.can_access_conversation", return_value=True)


def mock_database_session(
    mocker: MockerFixture,
    query_result: Optional[list[MockType]] = None,
    db_turns: Optional[list[MockType]] = None,
) -> MockType:
    """Helper function to mock get_session with proper context manager support.

    Create and patch a mocked database session and a context-manager-compatible get_session.

    Parameters:
        mocker (pytest.MockerFixture): Fixture used to create and patch mocks.
        query_result (Optional[list]): If provided, configures the
        session.query().all() and session.query().filter_by().all() to return
        this list (for UserConversation queries).
        db_turns (Optional[list]): If provided, configures UserTurn queries
        to return this list.

    Returns:
        Mock: The mocked session object that will be yielded by the patched
        get_session context manager.
    """
    mock_session = mocker.Mock()

    def query_side_effect(model_class: type[Any]) -> Any:
        """Handle different model queries."""
        mock_query = mocker.Mock()
        if model_class == UserTurn:
            _setup_user_turn_query(mock_query, db_turns)
        else:
            _setup_user_conversation_query(mock_query, query_result)
        return mock_query

    mock_session.query.side_effect = query_side_effect

    # Create context manager mock for get_session
    mock_session_context = mocker.MagicMock()
    mock_session_context.__enter__.return_value = mock_session
    mock_session_context.__exit__.return_value = None

    _patch_get_session_functions(mocker, mock_session_context)

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
            - tool_calls: list of tool call summaries (empty by default)
            - tool_results: list of tool result summaries (empty by default)
            - started_at: ISO 8601 UTC timestamp string for the turn start
            - completed_at: ISO 8601 UTC timestamp string for the turn end
    """
    return [
        {
            "messages": [
                {"content": "Hello", "type": "user"},
                {"content": "Hi there!", "type": "assistant"},
            ],
            "tool_calls": [],
            "tool_results": [],
            "provider": "google",
            "model": "gemini-2.0-flash-exp",
            "started_at": "2024-01-01T00:01:00Z",
            "completed_at": "2024-01-01T00:01:05Z",
        },
        {
            "messages": [
                {"content": "How are you?", "type": "user"},
                {"content": "I'm doing well, thanks!", "type": "assistant"},
            ],
            "tool_calls": [],
            "tool_results": [],
            "provider": "google",
            "model": "gemini-2.0-flash-exp",
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


class TestBuildConversationTurnsFromItems:
    """Test cases for the build_conversation_turns_from_items function."""

    @pytest.mark.asyncio
    async def test_build_conversation_turns_from_items_with_model_dump(
        self,
        mocker: MockerFixture,
        mock_session_data: dict[str, Any],  # pylint: disable=unused-argument
        expected_chat_history: list[dict[str, Any]],
    ) -> None:
        """Test build_conversation_turns_from_items with items data."""
        # Create mock items from session_data structure
        mock_items = [
            mocker.Mock(type="message", role="user", content="Hello"),
            mocker.Mock(type="message", role="assistant", content="Hi there!"),
            mocker.Mock(type="message", role="user", content="How are you?"),
            mocker.Mock(
                type="message", role="assistant", content="I'm doing well, thanks!"
            ),
        ]
        # Create mock db_turns matching the expected turns
        mock_db_turns = [
            create_mock_db_turn(
                mocker, 1, "2024-01-01T00:01:00Z", "2024-01-01T00:01:05Z"
            ),
            create_mock_db_turn(
                mocker, 2, "2024-01-01T00:02:00Z", "2024-01-01T00:02:03Z"
            ),
        ]
        conversation_start_time = datetime.fromisoformat(
            "2024-01-01T00:00:00Z"
        ).replace(tzinfo=UTC)
        result = build_conversation_turns_from_items(
            mock_items, mock_db_turns, conversation_start_time
        )
        actual_history = [turn.model_dump() for turn in result]
        assert actual_history == expected_chat_history

    @pytest.mark.asyncio
    async def test_build_conversation_turns_from_items_empty_turns(self) -> None:
        """Test build_conversation_turns_from_items with empty items."""
        conversation_start_time = datetime.fromisoformat(
            "2024-01-01T00:00:00Z"
        ).replace(tzinfo=UTC)
        result = build_conversation_turns_from_items([], [], conversation_start_time)

        assert not result


class TestGetConversationEndpoint:
    """Test cases for the GET /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mocker.patch("app.endpoints.conversations_v1.configuration", mock_config)

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=False)

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
        mock_conversation: MockType,
    ) -> None:
        """Test the endpoint when LlamaStack connection fails."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)

        mock_database_session(mocker, query_result=[mock_conversation], db_turns=[])

        mock_client = mocker.AsyncMock()
        mock_client.conversations.items.list.side_effect = APIConnectionError(
            request=None  # type: ignore
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch("app.endpoints.conversations_v1.retrieve_conversation")

        mock_database_session(mocker, db_turns=[])

        mock_client = mocker.AsyncMock()
        mock_client.conversations.items.list.side_effect = NotFoundError(
            message="Conversation not found",
            response=mocker.Mock(request=None),
            body=None,
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
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
    async def test_get_conversation_forbidden(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test forbidden access when user lacks permission to read conversation."""
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value=set(Action.GET_CONVERSATION),
        )

        mock_row = mocker.Mock()
        mock_row.user_id = "different_user_id"

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
    ) -> None:
        """Test allowed access to another user's conversation for authorized user."""
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value={Action.GET_CONVERSATION, Action.READ_OTHERS_CONVERSATIONS},
        )
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)

        mock_db_turns = [
            create_mock_db_turn(
                mocker, 1, "2024-01-01T00:01:00Z", "2024-01-01T00:01:05Z"
            ),
        ]
        mock_database_session(
            mocker, query_result=[mock_conversation], db_turns=mock_db_turns
        )

        mock_client = mocker.AsyncMock()
        mock_items_response = mocker.Mock()
        mock_item1 = mocker.Mock()
        mock_item1.type = "message"
        mock_item1.role = "user"
        mock_item1.content = "Hello"
        mock_item2 = mocker.Mock()
        mock_item2.type = "message"
        mock_item2.role = "assistant"
        mock_item2.content = "Hi there!"
        mock_items_response.data = [mock_item1, mock_item2]
        mock_client.conversations.items.list.return_value = mock_items_response

        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
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
        expected_chat_history: list[dict[str, Any]],
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test successful conversation retrieval with simplified response structure."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)

        mock_db_turns = [
            create_mock_db_turn(
                mocker, 1, "2024-01-01T00:01:00Z", "2024-01-01T00:01:05Z"
            ),
            create_mock_db_turn(
                mocker, 2, "2024-01-01T00:02:00Z", "2024-01-01T00:02:03Z"
            ),
        ]
        mock_database_session(
            mocker, query_result=[mock_conversation], db_turns=mock_db_turns
        )

        mock_client = mocker.AsyncMock()
        mock_items = mocker.Mock()
        mock_items.data = [
            mocker.Mock(type="message", role="user", content="Hello"),
            mocker.Mock(type="message", role="assistant", content="Hi there!"),
            mocker.Mock(type="message", role="user", content="How are you?"),
            mocker.Mock(
                type="message", role="assistant", content="I'm doing well, thanks!"
            ),
        ]
        mock_client.conversations.items.list.return_value = mock_items

        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await get_conversation_endpoint_handler(
            request=dummy_request, conversation_id=VALID_CONVERSATION_ID, auth=MOCK_AUTH
        )

        assert isinstance(response, ConversationResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        actual_history = [turn.model_dump() for turn in response.chat_history]
        assert actual_history == expected_chat_history

    @pytest.mark.asyncio
    async def test_retrieve_conversation_returns_none(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when retrieve_conversation returns None."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mock_database_session(mocker, query_result=[])
        mock_client = mocker.AsyncMock()
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
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
    async def test_no_sessions_found_in_get_conversation(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test when no sessions are found for the conversation."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_database_session(mocker, db_turns=[])

        mock_client = mocker.AsyncMock()
        mock_items_response = mocker.Mock()
        mock_items_response.data = []
        mock_client.conversations.items.list.return_value = mock_items_response
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_client = mocker.AsyncMock()
        mock_items_response = mocker.Mock()
        mock_items_response.data = [
            mocker.Mock(type="message", role="user", content="Hello"),
            mocker.Mock(type="message", role="assistant", content="Hi!"),
        ]
        mock_client.conversations.items.list.return_value = mock_items_response
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        mock_session = mocker.Mock()

        def query_side_effect(model_class: type[Any]) -> Any:
            if model_class == UserTurn:
                mock_query = mocker.Mock()
                mock_query.filter_by.return_value.order_by.return_value.all.side_effect = SQLAlchemyError(  # pylint: disable=line-too-long
                    "Database error"
                )
                return mock_query
            if model_class == UserConversation:
                mock_query = mocker.Mock()
                mock_query.filter_by.return_value.first.return_value = mock_conversation
                return mock_query
            # Other queries work normally
            mock_query = mocker.Mock()
            mock_query.all.return_value = []
            mock_query.filter_by.return_value.all.return_value = []
            mock_query.filter_by.return_value.first.return_value = None
            return mock_query

        mock_session.query.side_effect = query_side_effect
        mock_session_context = mocker.MagicMock()
        mock_session_context.__enter__.return_value = mock_session
        mock_session_context.__exit__.return_value = None
        mocker.patch(
            "app.endpoints.conversations_v1.get_session",
            return_value=mock_session_context,
        )
        mocker.patch(
            "utils.endpoints.get_session",
            return_value=mock_session_context,
        )
        mocker.patch(
            "utils.endpoints.can_access_conversation",
            return_value=True,
        )

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

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_in_retrieve_conversation(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when SQLAlchemyError is raised during retrieve_conversation call."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch(
            "utils.endpoints.can_access_conversation",
            return_value=True,
        )

        mock_session = mocker.Mock()
        mock_query = mocker.Mock()
        mock_query.filter_by.return_value.first.side_effect = SQLAlchemyError(
            "Database error"
        )
        mock_session.query.return_value = mock_query
        mock_session_context = mocker.MagicMock()
        mock_session_context.__enter__.return_value = mock_session
        mock_session_context.__exit__.return_value = None
        mocker.patch(
            "utils.endpoints.get_session",
            return_value=mock_session_context,
        )

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
        mocker.patch("app.endpoints.conversations_v1.configuration", mock_config)

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=False)

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch("app.endpoints.conversations_v1.retrieve_conversation")

        mocker.patch(
            "app.endpoints.conversations_v1.delete_conversation", return_value=True
        )

        mock_client = mocker.AsyncMock()
        mock_client.conversations.delete.side_effect = APIConnectionError(
            request=None  # type: ignore
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch("app.endpoints.conversations_v1.retrieve_conversation")

        mocker.patch(
            "app.endpoints.conversations_v1.delete_conversation", return_value=True
        )

        mock_client = mocker.AsyncMock()
        mock_client.conversations.delete.side_effect = APIStatusError(
            message="Conversation not found",
            response=mocker.Mock(status_code=404, request=None),
            body=None,
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert "deleted successfully" in response.response

    @pytest.mark.asyncio
    async def test_delete_conversation_forbidden(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test forbidden deletion when user lacks permission to delete conversation."""
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value=set(Action.DELETE_CONVERSATION),
        )

        mock_row = mocker.Mock()
        mock_row.user_id = "different_user_id"

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
        )

        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )
        mocker.patch(
            "app.endpoints.conversations_v1.delete_conversation", return_value=True
        )

        mock_client = mocker.AsyncMock()
        mock_delete_response = mocker.Mock()
        mock_delete_response.deleted = True
        mock_client.conversations.delete.return_value = mock_delete_response
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch("app.endpoints.conversations_v1.retrieve_conversation")

        mock_delete = mocker.patch(
            "app.endpoints.conversations_v1.delete_conversation", return_value=True
        )

        mock_client = mocker.AsyncMock()
        mock_delete_response = mocker.Mock()
        mock_delete_response.deleted = True
        mock_client.conversations.delete.return_value = mock_delete_response
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await delete_conversation_endpoint_handler(
            request=dummy_request, conversation_id=VALID_CONVERSATION_ID, auth=MOCK_AUTH
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert "deleted successfully" in response.response
        mock_delete.assert_called_once()
        mock_client.conversations.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_conversation_returns_none_in_delete(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when conversation doesn't exist in delete endpoint."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations_v1.can_access_conversation", return_value=True
        )
        mocker.patch(
            "app.endpoints.conversations_v1.delete_conversation", return_value=False
        )

        mock_client = mocker.AsyncMock()
        mock_delete_response = mocker.Mock()
        mock_delete_response.deleted = True
        mock_client.conversations.delete.return_value = mock_delete_response
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        response = await delete_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            auth=MOCK_AUTH,
        )

        assert isinstance(response, ConversationDeleteResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert "cannot be deleted" in response.response  # Not found locally

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_client = mocker.AsyncMock()
        mock_session_list_response = mocker.Mock()
        mock_session_list_response.data = [{"session_id": VALID_CONVERSATION_ID}]
        mock_client.agents.session.list.return_value = mock_session_list_response
        mock_client.agents.session.delete.return_value = None
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        mocker.patch(
            "app.endpoints.conversations_v1.delete_conversation",
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
        mocker.patch("app.endpoints.conversations_v1.configuration", mock_config)

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
            "app.endpoints.conversations_v1.get_session",
            return_value=mock_session_context,
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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )

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


class TestUpdateConversationEndpoint:
    """Test cases for the PUT /conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_configuration_not_loaded(
        self, mocker: MockerFixture, dummy_request: Request
    ) -> None:
        """Test the endpoint when configuration is not loaded."""
        mock_authorization_resolvers(mocker)
        mock_config = AppConfig()
        mocker.patch("app.endpoints.conversations_v1.configuration", mock_config)

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
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
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test the endpoint with an invalid conversation ID format."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=False)

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=INVALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Invalid conversation ID format" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_update_conversation_forbidden(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test forbidden access when user lacks permission to update conversation."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )
        mocker.patch(
            "authorization.resolvers.NoopAccessResolver.get_actions",
            return_value=set(Action.UPDATE_CONVERSATION),
        )  # User can only update their own conversations

        # Mock can_access_conversation to return False (user doesn't have access)
        mocker.patch(
            "app.endpoints.conversations_v1.can_access_conversation", return_value=False
        )

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "does not have permission" in detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_conversation_not_found_in_update(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when conversation is not found in update endpoint."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation", return_value=None
        )

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_in_retrieve_conversation_update(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
    ) -> None:
        """Test when SQLAlchemyError is raised during retrieve_conversation in update."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            side_effect=SQLAlchemyError("Database error"),
        )

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Database" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_successful_conversation_update(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test successful conversation update."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock database session for update
        mock_session = mocker.Mock()
        mock_db_conv = mocker.Mock()
        mock_db_conv.topic_summary = None
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_db_conv
        )
        mock_session_context = mocker.MagicMock()
        mock_session_context.__enter__.return_value = mock_session
        mock_session_context.__exit__.return_value = None
        mocker.patch(
            "app.endpoints.conversations_v1.get_session",
            return_value=mock_session_context,
        )

        # Mock AsyncLlamaStackClientHolder
        mock_client = mocker.AsyncMock()
        mock_client.conversations.update.return_value = None
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        update_request = ConversationUpdateRequest(topic_summary="New topic summary")

        response = await update_conversation_endpoint_handler(
            request=dummy_request,
            conversation_id=VALID_CONVERSATION_ID,
            update_request=update_request,
            auth=MOCK_AUTH,
        )

        assert isinstance(response, ConversationUpdateResponse)
        assert response.conversation_id == VALID_CONVERSATION_ID
        assert response.success is True
        assert "updated successfully" in response.message
        mock_client.conversations.update.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_llama_stack_connection_error_in_update(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test the endpoint when LlamaStack connection fails during update."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder to raise APIConnectionError
        mock_client = mocker.AsyncMock()
        mock_client.conversations.update.side_effect = APIConnectionError(
            request=None  # type: ignore
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore

    @pytest.mark.asyncio
    async def test_llama_stack_not_found_error_in_update(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test the endpoint when LlamaStack returns NotFoundError during update."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder to raise APIStatusError
        mock_client = mocker.AsyncMock()
        mock_client.conversations.update.side_effect = APIStatusError(
            message="Conversation not found",
            response=mocker.Mock(status_code=404, request=None),
            body=None,
        )
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Conversation not found" in detail["response"]  # type: ignore

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_in_database_update(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,
        dummy_request: Request,
        mock_conversation: MockType,
    ) -> None:
        """Test when SQLAlchemyError is raised during database update."""
        mock_authorization_resolvers(mocker)
        mocker.patch(
            "app.endpoints.conversations_v1.configuration", setup_configuration
        )
        mocker.patch("app.endpoints.conversations_v1.check_suid", return_value=True)
        mocker.patch("app.endpoints.conversations_v1.can_access_conversation")
        mocker.patch(
            "app.endpoints.conversations_v1.retrieve_conversation",
            return_value=mock_conversation,
        )

        # Mock AsyncLlamaStackClientHolder - update succeeds
        mock_client = mocker.AsyncMock()
        mock_client.conversations.update.return_value = None
        mock_client_holder = mocker.patch(
            "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        # Mock database session - commit raises SQLAlchemyError
        mock_session = mocker.Mock()
        mock_db_conv = mocker.Mock()
        mock_db_conv.topic_summary = None
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_db_conv
        )
        mock_session.commit.side_effect = SQLAlchemyError("Database error")
        mock_session_context = mocker.MagicMock()
        mock_session_context.__enter__.return_value = mock_session
        mock_session_context.__exit__.return_value = None
        mocker.patch(
            "app.endpoints.conversations_v1.get_session",
            return_value=mock_session_context,
        )

        update_request = ConversationUpdateRequest(topic_summary="New topic")

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation_endpoint_handler(
                request=dummy_request,
                conversation_id=VALID_CONVERSATION_ID,
                update_request=update_request,
                auth=MOCK_AUTH,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Database" in detail["response"]  # type: ignore
