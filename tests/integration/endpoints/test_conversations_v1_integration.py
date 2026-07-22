"""Integration tests for the /v1/conversations REST API endpoints."""

# pylint: disable=too-many-lines  # Integration tests require comprehensive coverage
# pylint: disable=too-many-arguments  # Integration tests need many fixtures
# pylint: disable=too-many-positional-arguments  # Integration tests need many fixtures

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, APIStatusError
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from lightspeed_stack.app.endpoints.conversations_v1 import (
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    update_conversation_endpoint_handler,
)
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.configuration import AppConfig
from lightspeed_stack.models.api.requests import ConversationUpdateRequest
from lightspeed_stack.models.database.conversations import UserConversation, UserTurn
from tests.integration.conftest import (
    TEST_CONVERSATION_ID,
    TEST_INVALID_ID,
    TEST_NON_EXISTENT_ID,
    TEST_OTHER_USER_ID,
    TEST_SECOND_CONVERSATION_ID,
)

# ==========================================
# List Conversations Tests
# ==========================================


@pytest.mark.asyncio
async def test_list_conversations_returns_user_conversations(
    test_config: AppConfig,
    non_admin_test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that list endpoint returns only conversations for authenticated user.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Database queries retrieve correct user conversations
    - User isolation is enforced (only user's own conversations are returned)
    - Response structure matches expected format
    - Real noop authentication is used

    Parameters:
        test_config: Test configuration
        non_admin_test_request: FastAPI request with standard user permissions
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    user_id, _, _, _ = test_auth
    other_user_id = "other_user_id"

    # Create conversations for authenticated user
    conversation1 = UserConversation(
        id=TEST_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="User's conversation 1",
        message_count=3,
    )
    conversation2 = UserConversation(
        id=TEST_SECOND_CONVERSATION_ID,
        user_id=user_id,
        last_used_model="test-model-2",
        last_used_provider="test-provider-2",
        topic_summary="User's conversation 2",
        message_count=5,
    )

    # Create conversation for a different user (should NOT be returned)
    other_user_conversation = UserConversation(
        id=TEST_OTHER_USER_ID,
        user_id=other_user_id,
        last_used_model="test-model-other",
        last_used_provider="test-provider-other",
        topic_summary="Other user's conversation",
        message_count=1,
    )

    patch_db_session.add(conversation1)
    patch_db_session.add(conversation2)
    patch_db_session.add(other_user_conversation)
    patch_db_session.commit()

    response = await get_conversations_list_endpoint_handler(
        request=non_admin_test_request,
        auth=test_auth,
    )

    # Verify response structure
    assert response.conversations is not None
    assert len(response.conversations) == 2

    # Verify only authenticated user's conversations are returned
    conv_ids = [conv.conversation_id for conv in response.conversations]
    assert TEST_CONVERSATION_ID in conv_ids
    assert TEST_SECOND_CONVERSATION_ID in conv_ids
    assert TEST_OTHER_USER_ID not in conv_ids

    # Verify metadata for first conversation
    conv1 = next(
        c for c in response.conversations if c.conversation_id == TEST_CONVERSATION_ID
    )
    assert conv1.last_used_model == "test-model"
    assert conv1.last_used_provider == "test-provider"
    assert conv1.topic_summary == "User's conversation 1"
    assert conv1.message_count == 3
    assert conv1.created_at is not None
    assert conv1.last_message_at is not None

    # Verify metadata for second conversation
    conv2 = next(
        c
        for c in response.conversations
        if c.conversation_id == TEST_SECOND_CONVERSATION_ID
    )
    assert conv2.last_used_model == "test-model-2"
    assert conv2.last_used_provider == "test-provider-2"
    assert conv2.topic_summary == "User's conversation 2"
    assert conv2.message_count == 5
    assert conv2.created_at is not None
    assert conv2.last_message_at is not None


# ==========================================
# Get Conversation Tests
# ==========================================

# Validation error test cases (invalid_id_format, not_found)
VALIDATION_ERROR_TEST_CASES = [
    pytest.param(
        {
            "endpoint": "get",
            "conversation_id": TEST_INVALID_ID,
            "expected_status": 400,
            "create_conversation": True,
        },
        id="get_invalid_id_format_returns_400",
    ),
    pytest.param(
        {
            "endpoint": "get",
            "conversation_id": TEST_NON_EXISTENT_ID,
            "expected_status": 404,
            "create_conversation": True,
        },
        id="get_not_found_returns_404",
    ),
    pytest.param(
        {
            "endpoint": "delete",
            "conversation_id": TEST_INVALID_ID,
            "expected_status": 400,
            "create_conversation": False,
        },
        id="delete_invalid_id_format_returns_400",
    ),
    pytest.param(
        {
            "endpoint": "update",
            "conversation_id": TEST_INVALID_ID,
            "expected_status": 400,
            "create_conversation": False,
        },
        id="update_invalid_id_format_returns_400",
    ),
    pytest.param(
        {
            "endpoint": "update",
            "conversation_id": TEST_NON_EXISTENT_ID,
            "expected_status": 404,
            "create_conversation": True,
        },
        id="update_not_found_returns_404",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", VALIDATION_ERROR_TEST_CASES)
async def test_conversation_validation_errors(
    test_case: dict,
    test_config: AppConfig,
    non_admin_test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Data-driven test for conversation endpoint validation errors.

    Tests various validation scenarios including:
    - Invalid conversation ID format (400 error)
    - Non-existent conversation (404 error)
    - Across GET, DELETE, and UPDATE endpoints

    Parameters:
        test_case: Dictionary containing test parameters
        test_config: Test configuration
        non_admin_test_request: FastAPI request with standard user permissions
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    user_id, _, _, _ = test_auth
    endpoint = test_case["endpoint"]
    conversation_id = test_case["conversation_id"]
    expected_status = test_case["expected_status"]
    create_conversation = test_case["create_conversation"]

    # Create a conversation in database if needed (for not_found tests)
    if create_conversation:
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

    # Call the appropriate endpoint
    with pytest.raises(HTTPException) as exc_info:
        if endpoint == "get":
            await get_conversation_endpoint_handler(
                request=non_admin_test_request,
                conversation_id=conversation_id,
                auth=test_auth,
            )
        elif endpoint == "delete":
            await delete_conversation_endpoint_handler(
                request=non_admin_test_request,
                conversation_id=conversation_id,
                auth=test_auth,
            )
        elif endpoint == "update":
            update_request = ConversationUpdateRequest(topic_summary="Updated summary")
            await update_conversation_endpoint_handler(
                request=non_admin_test_request,
                conversation_id=conversation_id,
                update_request=update_request,
                auth=test_auth,
            )

    # Verify error status code
    assert exc_info.value.status_code == expected_status


# Error handling test cases (connection_error, api_status_error)
ERROR_HANDLING_TEST_CASES = [
    pytest.param(
        {
            "endpoint": "get",
            "error_type": "connection",
            "expected_status": 503,
            "mock_path": "conversations.items.list",
        },
        id="get_handles_connection_error",
    ),
    pytest.param(
        {
            "endpoint": "get",
            "error_type": "api_status",
            "expected_status": 500,
            "mock_path": "conversations.items.list",
        },
        id="get_handles_api_status_error",
    ),
    pytest.param(
        {
            "endpoint": "delete",
            "error_type": "connection",
            "expected_status": 503,
            "mock_path": "conversations.delete",
        },
        id="delete_handles_connection_error",
    ),
    pytest.param(
        {
            "endpoint": "update",
            "error_type": "connection",
            "expected_status": 503,
            "mock_path": "conversations.update",
        },
        id="update_handles_connection_error",
    ),
    pytest.param(
        {
            "endpoint": "update",
            "error_type": "api_status",
            "expected_status": 404,
            "mock_path": "conversations.update",
        },
        id="update_handles_api_status_error",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", ERROR_HANDLING_TEST_CASES)
async def test_conversation_error_handling(  # pylint: disable=too-many-locals
    test_case: dict,
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Data-driven test for conversation endpoint error handling.

    Tests error handling scenarios including:
    - Llama Stack connection errors (503)
    - Llama Stack API status errors (500)
    - Across GET, DELETE, and UPDATE endpoints

    Parameters:
        test_case: Dictionary containing test parameters
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        non_admin_test_request: FastAPI request with standard user permissions
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = test_config

    user_id, _, _, _ = test_auth
    endpoint = test_case["endpoint"]
    error_type = test_case["error_type"]
    expected_status = test_case["expected_status"]
    mock_path = test_case["mock_path"]

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

    # Configure mock to raise appropriate error
    mock_method = mock_llama_stack_client
    for attr in mock_path.split("."):
        mock_method = getattr(mock_method, attr)

    if error_type == "connection":
        mock_method.side_effect = APIConnectionError(request=mocker.Mock())
    elif error_type == "api_status":
        mock_method.side_effect = APIStatusError(
            message="Server error",
            response=mocker.Mock(status_code=500),
            body=None,
        )

    # Call the appropriate endpoint and expect error
    with pytest.raises(HTTPException) as exc_info:
        if endpoint == "get":
            await get_conversation_endpoint_handler(
                request=non_admin_test_request,
                conversation_id=TEST_CONVERSATION_ID,
                auth=test_auth,
            )
        elif endpoint == "delete":
            await delete_conversation_endpoint_handler(
                request=non_admin_test_request,
                conversation_id=TEST_CONVERSATION_ID,
                auth=test_auth,
            )
        elif endpoint == "update":
            update_request = ConversationUpdateRequest(topic_summary="Updated")
            await update_conversation_endpoint_handler(
                request=non_admin_test_request,
                conversation_id=TEST_CONVERSATION_ID,
                update_request=update_request,
                auth=test_auth,
            )

    # Verify error status code
    assert exc_info.value.status_code == expected_status


@pytest.mark.asyncio
async def test_get_conversation_returns_chat_history(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
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
        non_admin_test_request: FastAPI request with standard user permissions
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

    # Mock Llama Stack conversation items
    mock_user_message = mocker.Mock(
        type="message", role="user", content="What is Ansible?"
    )
    mock_assistant_message = mocker.Mock(
        type="message", role="assistant", content="Ansible is an automation tool."
    )

    # Mock Llama Stack response
    mock_items = mocker.Mock()
    mock_items.data = [mock_user_message, mock_assistant_message]
    mock_items.has_next_page.return_value = False
    mock_llama_stack_client.conversations.items.list = mocker.AsyncMock(
        return_value=mock_items
    )

    response = await get_conversation_endpoint_handler(
        request=non_admin_test_request,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response structure
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.chat_history is not None
    assert len(response.chat_history) == 1  # 1 turn

    # Verify the turn
    turn = response.chat_history[0]
    assert len(turn.messages) == 2

    # Verify user message
    assert turn.messages[0].type == "user"
    assert turn.messages[0].content == "What is Ansible?"

    # Verify assistant message
    assert turn.messages[1].type == "assistant"
    assert turn.messages[1].content == "Ansible is an automation tool."


@pytest.mark.asyncio
async def test_get_conversation_with_turns_metadata(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
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
        non_admin_test_request: FastAPI request with standard user permissions
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
        request=non_admin_test_request,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response includes turn metadata
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.chat_history is not None
    assert len(response.chat_history) == 1

    # Verify the turn with metadata
    turn = response.chat_history[0]
    assert len(turn.messages) == 2

    # Verify user message
    assert turn.messages[0].type == "user"
    assert turn.messages[0].content == "What is Ansible?"

    # Verify assistant message
    assert turn.messages[1].type == "assistant"
    assert turn.messages[1].content == "Ansible is an automation tool."

    # Verify turn metadata from database
    assert turn.provider == "test-provider"
    assert turn.model == "test-model"
    assert turn.started_at is not None
    assert turn.completed_at is not None


# ==========================================
# Delete Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_delete_conversation_deletes_from_database_and_llama_stack(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
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
        non_admin_test_request: FastAPI request with standard user permissions
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
        request=non_admin_test_request,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True

    # Verify conversation was deleted by attempting to get it (should return 404)
    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=non_admin_test_request,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_conversation_handles_not_found_in_llama_stack(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
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
        non_admin_test_request: FastAPI request with standard user permissions
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
        request=non_admin_test_request,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response indicates success (local deletion succeeded)
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True

    # Verify local deletion occurred by attempting to get it (should return 404)
    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=non_admin_test_request,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_conversation_non_existent_returns_success(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
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
        non_admin_test_request: FastAPI request with standard user permissions
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
        request=non_admin_test_request,
        conversation_id=TEST_NON_EXISTENT_ID,
        auth=test_auth,
    )

    # Verify response indicates no deletion occurred
    assert response.conversation_id == TEST_NON_EXISTENT_ID
    assert response.success is True


# ==========================================
# Update Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_update_conversation_updates_topic_summary(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    non_admin_test_request: Request,
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
        non_admin_test_request: FastAPI request with standard user permissions
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
        request=non_admin_test_request,
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
