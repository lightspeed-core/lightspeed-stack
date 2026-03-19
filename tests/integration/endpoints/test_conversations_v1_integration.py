"""Integration tests for the /v1/conversations REST API endpoints."""

# pylint: disable=too-many-lines  # Integration tests require comprehensive coverage
# pylint: disable=too-many-arguments  # Integration tests need many fixtures
# pylint: disable=too-many-positional-arguments  # Integration tests need many fixtures

from typing import Any
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, APIStatusError
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.database
import app.endpoints.conversations_v1
from app.endpoints.conversations_v1 import (
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    update_conversation_endpoint_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.config import Action
from models.database.conversations import UserConversation, UserTurn
from models.requests import ConversationUpdateRequest

# Test constants - use valid UUID format
TEST_CONVERSATION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
OTHER_USER_CONV_ID = "11111111-1111-1111-1111-111111111111"
NON_EXISTENT_ID = "00000000-0000-0000-0000-000000000001"
INVALID_ID = "invalid-id-format"


@pytest.fixture(name="mock_llama_stack_client")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
        mocker: pytest-mock fixture used to create and patch mocks.

    Returns:
        mock_client: The mocked Llama Stack client instance.
    """
    mock_holder_class = mocker.patch(
        "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder"
    )

    mock_client = mocker.AsyncMock()

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


@pytest.fixture(name="patch_db_session", autouse=True)
def patch_db_session_fixture(
    test_db_session: Session,
    test_db_engine: Engine,
) -> Generator[Session, None, None]:
    """Initialize database session for integration tests.

    This sets up the global session_local in app.database to use the test database.
    Uses an in-memory SQLite database, isolating tests from production data.
    This fixture is autouse=True, so it applies to all tests in this module automatically.

    Returns:
        The test database Session instance to be used by the test.
    """
    # Store original values to restore later
    original_engine = app.database.engine
    original_session_local = app.database.session_local

    # Set the test database engine and session maker globally
    app.database.engine = test_db_engine
    app.database.session_local = sessionmaker(bind=test_db_engine)

    yield test_db_session

    # Restore original values
    app.database.engine = original_engine
    app.database.session_local = original_session_local


@pytest.fixture(name="mock_request_with_auth")
def mock_request_with_auth_fixture() -> Request:
    """Create a test FastAPI Request with full authorization.

    Returns:
        Request: Request object with all actions authorized.
    """
    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [],
        }
    )
    # Grant all permissions for integration tests
    request.state.authorized_actions = set(Action)
    return request


# ==========================================
# List Conversations Tests
# ==========================================


@pytest.mark.asyncio
async def test_list_conversations_returns_user_conversations(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that list endpoint returns all conversations for authenticated user.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Database queries retrieve correct user conversations
    - Response structure matches expected format
    - Real noop authentication is used

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create test conversations in database
    conversation1 = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test topic 1",
        message_count=3,
    )
    conversation2 = UserConversation(
        id=OTHER_USER_CONV_ID,
        user_id=user_id,
        last_used_model="test-model-2",
        last_used_provider="test-provider-2",
        topic_summary="Test topic 2",
        message_count=5,
    )
    patch_db_session.add(conversation1)
    patch_db_session.add(conversation2)
    patch_db_session.commit()

    response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )

    # Verify response structure
    assert response.conversations is not None
    assert len(response.conversations) == 2

    # Verify conversation details
    conv_ids = [conv.conversation_id for conv in response.conversations]
    assert TEST_CONVERSATION_ID in conv_ids
    assert OTHER_USER_CONV_ID in conv_ids

    # Verify metadata for first conversation
    conv1 = next(
        c for c in response.conversations if c.conversation_id == TEST_CONVERSATION_ID
    )
    assert conv1.last_used_model == "test-model"
    assert conv1.last_used_provider == "test-provider"
    assert conv1.topic_summary == "Test topic 1"
    assert conv1.message_count == 3
    assert conv1.created_at is not None
    assert conv1.last_message_at is not None


@pytest.mark.asyncio
async def test_list_conversations_returns_empty_list_for_new_user(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that list endpoint returns empty list for user with no conversations.

    This integration test verifies:
    - Endpoint handles users with no conversations gracefully
    - Empty database query returns empty list
    - Response structure is correct even when empty

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = patch_db_session

    response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )

    # Verify empty response
    assert response.conversations is not None
    assert len(response.conversations) == 0


@pytest.mark.asyncio
async def test_list_conversations_returns_multiple_conversations(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that list endpoint returns multiple conversations for user.

    This integration test verifies:
    - Multiple conversations can be retrieved
    - All user's conversations are returned
    - Database query works correctly with multiple records

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create multiple conversations for authenticated user
    conversation1 = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="First conversation",
        message_count=1,
    )

    conversation2 = UserConversation(
        id=OTHER_USER_CONV_ID,
        user_id=user_id,
        last_used_model="test-model-2",
        last_used_provider="test-provider-2",
        topic_summary="Second conversation",
        message_count=2,
    )

    patch_db_session.add(conversation1)
    patch_db_session.add(conversation2)
    patch_db_session.commit()

    response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )

    # Verify both conversations are returned
    assert len(response.conversations) == 2
    conv_ids = {conv.conversation_id for conv in response.conversations}
    assert TEST_CONVERSATION_ID in conv_ids
    assert OTHER_USER_CONV_ID in conv_ids


# ==========================================
# Get Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_get_conversation_returns_chat_history(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that get conversation endpoint returns complete chat history.

    This integration test verifies:
    - Endpoint retrieves conversation from database
    - Llama Stack client is called to get conversation items
    - Chat history is properly structured
    - Integration between database and Llama Stack

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=2,
        created_at=datetime.now(UTC),
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Mock Llama Stack conversation items - use paginator pattern
    mock_user_message = mocker.Mock(
        type="message", role="user", content="What is Ansible?"
    )
    mock_assistant_message = mocker.Mock(
        type="message", role="assistant", content="Ansible is an automation tool."
    )

    # Mock paginator response
    mock_items = mocker.Mock()
    mock_items.data = [mock_user_message, mock_assistant_message]
    mock_items.has_next_page.return_value = False
    mock_llama_stack_client.conversations.items.list = mocker.AsyncMock(
        return_value=mock_items
    )

    response = await get_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response structure
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.chat_history is not None
    assert len(response.chat_history) > 0

    # Verify Llama Stack client was called
    mock_llama_stack_client.conversations.items.list.assert_called_once()


@pytest.mark.asyncio
async def test_get_conversation_invalid_id_format_returns_400(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that get conversation with invalid ID format returns HTTP 400.

    This integration test verifies:
    - Invalid conversation ID format is detected
    - HTTPException is raised with 400 status code
    - Error message indicates bad request

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
    """
    _ = test_config

    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=INVALID_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_get_conversation_not_found_returns_404(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that get conversation with non-existent ID returns HTTP 404.

    This integration test verifies:
    - Non-existent conversation ID is detected
    - HTTPException is raised with 404 status code
    - Error message indicates not found

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = patch_db_session

    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=NON_EXISTENT_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_get_conversation_handles_connection_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that get conversation handles Llama Stack connection errors.

    This integration test verifies:
    - Error handling when Llama Stack is unavailable
    - HTTPException is raised with 503 status code
    - Error response includes proper error details

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=1,
        created_at=datetime.now(UTC),
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Configure mock to raise connection error
    mock_llama_stack_client.conversations.items.list.side_effect = APIConnectionError(
        request=mocker.Mock()
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_get_conversation_handles_api_status_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that get conversation handles Llama Stack API status errors.

    This integration test verifies:
    - API status errors from Llama Stack are handled
    - HTTPException is raised with 500 status code
    - Error handling works through the full stack

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=1,
        created_at=datetime.now(UTC),
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Configure mock to raise API status error
    mock_llama_stack_client.conversations.items.list.side_effect = APIStatusError(
        message="Not found",
        response=mocker.Mock(status_code=404),
        body=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )

    # Verify error details - APIStatusError from items.list is mapped to 500
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_get_conversation_with_turns_metadata(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that get conversation includes turn metadata from database.

    This integration test verifies:
    - Turn metadata is retrieved from database
    - Timestamps, provider, and model are included in response
    - Integration between database turns and Llama Stack items

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database with turn metadata
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=1,
        created_at=datetime.now(UTC),
    )
    patch_db_session.add(conversation)

    # Add turn metadata
    turn = UserTurn(
        conversation_id=TEST_CONVERSATION_ID,
        turn_number=1,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        provider="test-provider",
        model="test-model",
    )
    patch_db_session.add(turn)
    patch_db_session.commit()

    # Mock Llama Stack conversation items - use paginator pattern
    mock_user_message = mocker.Mock(
        type="message", role="user", content="What is Ansible?"
    )
    mock_assistant_message = mocker.Mock(
        type="message", role="assistant", content="Ansible is an automation tool."
    )

    # Mock paginator response
    mock_items = mocker.Mock()
    mock_items.data = [mock_user_message, mock_assistant_message]
    mock_items.has_next_page.return_value = False
    mock_llama_stack_client.conversations.items.list = mocker.AsyncMock(
        return_value=mock_items
    )

    response = await get_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response includes turn metadata
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.chat_history is not None


# ==========================================
# Delete Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_delete_conversation_deletes_from_database_and_llama_stack(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that delete conversation removes from both database and Llama Stack.

    This integration test verifies:
    - Conversation is deleted from local database
    - Llama Stack delete API is called
    - Response indicates successful deletion
    - Integration between database and Llama Stack operations

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=1,
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Mock Llama Stack delete response
    mock_delete_response = mocker.MagicMock()
    mock_delete_response.deleted = True
    mock_llama_stack_client.conversations.delete.return_value = mock_delete_response

    response = await delete_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True

    # Verify conversation was deleted from database
    deleted_conversation = (
        patch_db_session.query(UserConversation)
        .filter_by(id=TEST_CONVERSATION_ID)
        .first()
    )
    assert deleted_conversation is None

    # Verify Llama Stack delete was called
    mock_llama_stack_client.conversations.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_conversation_invalid_id_format_returns_400(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that delete conversation with invalid ID format returns HTTP 400.

    This integration test verifies:
    - Invalid conversation ID format is detected
    - HTTPException is raised with 400 status code
    - Error message indicates bad request

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
    """
    _ = test_config

    with pytest.raises(HTTPException) as exc_info:
        await delete_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=INVALID_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_delete_conversation_handles_connection_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that delete conversation handles Llama Stack connection errors.

    This integration test verifies:
    - Error handling when Llama Stack is unavailable
    - HTTPException is raised with 503 status code
    - Local deletion still occurs before error

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=1,
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Configure mock to raise connection error
    mock_llama_stack_client.conversations.delete.side_effect = APIConnectionError(
        request=mocker.Mock()
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)

    # Verify local deletion occurred
    deleted_conversation = (
        patch_db_session.query(UserConversation)
        .filter_by(id=TEST_CONVERSATION_ID)
        .first()
    )
    assert deleted_conversation is None


@pytest.mark.asyncio
async def test_delete_conversation_handles_not_found_in_llama_stack(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that delete conversation handles not found in Llama Stack gracefully.

    This integration test verifies:
    - API status error from Llama Stack is handled
    - Local deletion still succeeds
    - Response indicates successful deletion

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test conversation",
        message_count=1,
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Configure mock to raise not found error
    mock_llama_stack_client.conversations.delete.side_effect = APIStatusError(
        message="Not found",
        response=mocker.Mock(status_code=404),
        body=None,
    )

    response = await delete_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response indicates success (local deletion succeeded)
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True

    # Verify local deletion occurred
    deleted_conversation = (
        patch_db_session.query(UserConversation)
        .filter_by(id=TEST_CONVERSATION_ID)
        .first()
    )
    assert deleted_conversation is None


@pytest.mark.asyncio
async def test_delete_conversation_non_existent_returns_success(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that deleting non-existent conversation returns success.

    This integration test verifies:
    - Deleting non-existent conversation is idempotent
    - Response indicates deletion (deleted=False)
    - No error is raised

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config
    _ = patch_db_session

    # Mock Llama Stack delete response
    mock_delete_response = mocker.MagicMock()
    mock_delete_response.deleted = False
    mock_llama_stack_client.conversations.delete.return_value = mock_delete_response

    response = await delete_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=NON_EXISTENT_ID,
        auth=test_auth,
    )

    # Verify response indicates no deletion occurred
    assert response.conversation_id == NON_EXISTENT_ID
    assert response.success is True


# ==========================================
# Update Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_update_conversation_updates_topic_summary(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that update conversation updates topic summary in database and Llama Stack.

    This integration test verifies:
    - Topic summary is updated in local database
    - Llama Stack update API is called
    - Response indicates successful update
    - Integration between database and Llama Stack operations

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Old topic",
        message_count=1,
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Mock Llama Stack update response
    mock_llama_stack_client.conversations.update.return_value = None

    update_request = ConversationUpdateRequest(topic_summary="New topic summary")

    response = await update_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        update_request=update_request,
        auth=test_auth,
    )

    # Verify response
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True
    assert "updated successfully" in response.message.lower()

    # Verify database was updated
    patch_db_session.refresh(conversation)
    assert conversation.topic_summary == "New topic summary"

    # Verify Llama Stack update was called
    mock_llama_stack_client.conversations.update.assert_called_once()
    call_kwargs = mock_llama_stack_client.conversations.update.call_args.kwargs
    assert "metadata" in call_kwargs
    assert call_kwargs["metadata"]["topic_summary"] == "New topic summary"


@pytest.mark.asyncio
async def test_update_conversation_invalid_id_format_returns_400(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that update conversation with invalid ID format returns HTTP 400.

    This integration test verifies:
    - Invalid conversation ID format is detected
    - HTTPException is raised with 400 status code
    - Error message indicates bad request

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
    """
    _ = test_config

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=INVALID_ID,
            update_request=update_request,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_update_conversation_not_found_returns_404(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that update conversation with non-existent ID returns HTTP 404.

    This integration test verifies:
    - Non-existent conversation ID is detected
    - HTTPException is raised with 404 status code
    - Error message indicates not found

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = patch_db_session

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=NON_EXISTENT_ID,
            update_request=update_request,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_update_conversation_handles_connection_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that update conversation handles Llama Stack connection errors.

    This integration test verifies:
    - Error handling when Llama Stack is unavailable
    - HTTPException is raised with 503 status code
    - Error response includes proper error details

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Old topic",
        message_count=1,
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Configure mock to raise connection error
    mock_llama_stack_client.conversations.update.side_effect = APIConnectionError(
        request=mocker.Mock()
    )

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            update_request=update_request,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_update_conversation_handles_api_status_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that update conversation handles Llama Stack API status errors.

    This integration test verifies:
    - API status errors from Llama Stack are handled
    - HTTPException is raised with 404 status code
    - Error indicates conversation not found in backend

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create conversation in database
    conversation = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Old topic",
        message_count=1,
    )
    patch_db_session.add(conversation)
    patch_db_session.commit()

    # Configure mock to raise API status error
    mock_llama_stack_client.conversations.update.side_effect = APIStatusError(
        message="Not found",
        response=mocker.Mock(status_code=404),
        body=None,
    )

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            update_request=update_request,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert isinstance(exc_info.value.detail, dict)
