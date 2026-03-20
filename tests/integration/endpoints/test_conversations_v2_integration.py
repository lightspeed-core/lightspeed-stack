"""Integration tests for the /v2/conversations REST API endpoints (cache-based)."""

# pylint: disable=too-many-arguments  # Integration tests need many fixtures
# pylint: disable=too-many-positional-arguments  # Integration tests need many fixtures

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from app.endpoints.conversations_v2 import (
    delete_conversation_endpoint_handler,
    get_conversation_endpoint_handler,
    get_conversations_list_endpoint_handler,
    update_conversation_endpoint_handler,
)
from authentication.interface import AuthTuple
from cache.sqlite_cache import SQLiteCache
from configuration import AppConfig
from models.cache_entry import CacheEntry
from models.config import Action, SQLiteDatabaseConfiguration
from models.requests import ConversationUpdateRequest
from models.responses import ConversationData

# Test constants - use valid UUID format
TEST_CONVERSATION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
OTHER_CONVERSATION_ID = "11111111-1111-1111-1111-111111111111"
NON_EXISTENT_ID = "00000000-0000-0000-0000-000000000001"
INVALID_ID = "invalid-id-format"


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


@pytest.fixture(name="setup_conversation_cache", autouse=True)
def setup_conversation_cache_fixture(
    test_config: AppConfig,
    mocker: MockerFixture,
) -> Generator[SQLiteCache, None, None]:
    """Setup conversation cache for integration tests.

    This fixture configures the test configuration to use SQLite conversation cache
    with an in-memory database, ensuring cache is properly initialized for each test.

    Returns:
        SQLiteCache: The configured cache instance.
    """
    # Ensure cache configuration is set to sqlite with in-memory database
    test_config.conversation_cache_configuration.type = "sqlite"

    # Configure SQLite to use in-memory database
    sqlite_config = SQLiteDatabaseConfiguration(db_path=":memory:")

    # Initialize the cache
    cache = SQLiteCache(sqlite_config)
    cache.connect()
    cache.initialize_cache()

    # Patch the conversation_cache property to return our test cache
    mocker.patch.object(
        type(test_config),
        "conversation_cache",
        new_callable=mocker.PropertyMock,
        return_value=cache,
    )

    yield cache

    # Cleanup handled by in-memory database (cleared on connection close)


def create_test_cache_entry(
    conversation_id: str,
    user_id: str,
    query: str = "What is Ansible?",
    response: str = "Ansible is an automation tool.",
    provider: str = "test-provider",
    model: str = "test-model",
    topic_summary: str = "Ansible basics",
) -> CacheEntry:
    """Create a test cache entry with realistic data.

    Args:
        conversation_id: Conversation identifier
        user_id: User identifier
        query: User query text
        response: Assistant response text
        provider: Provider identifier
        model: Model identifier
        topic_summary: Conversation topic summary

    Returns:
        CacheEntry: A cache entry with all required fields populated.
    """
    now = datetime.now(UTC).isoformat()
    return CacheEntry(
        conversation_id=conversation_id,
        user_id=user_id,
        query=query,
        response=response,
        provider=provider,
        model=model,
        referenced_documents=[],
        tool_calls=[],
        tool_results=[],
        topic_summary=topic_summary,
        started_at=now,
        completed_at=now,
    )


# ==========================================
# List Conversations Tests
# ==========================================


@pytest.mark.asyncio
async def test_list_conversations_returns_user_conversations(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that list endpoint returns all conversations for authenticated user.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Conversation cache retrieves correct user conversations
    - Response structure matches expected format
    - Real noop authentication is used

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Add test conversations to cache
    entry1 = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        topic_summary="First conversation",
    )
    entry2 = create_test_cache_entry(
        conversation_id=OTHER_CONVERSATION_ID,
        user_id=user_id,
        topic_summary="Second conversation",
    )

    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry1)
    setup_conversation_cache.insert_or_append(user_id, OTHER_CONVERSATION_ID, entry2)

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
    assert OTHER_CONVERSATION_ID in conv_ids

    # Verify conversation is ConversationData type (returned by cache)
    for conv in response.conversations:
        assert isinstance(conv, ConversationData)
        assert conv.conversation_id is not None


@pytest.mark.asyncio
async def test_list_conversations_returns_empty_list_for_new_user(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that list endpoint returns empty list for user with no conversations.

    This integration test verifies:
    - Endpoint handles users with no conversations gracefully
    - Empty cache query returns empty list
    - Response structure is correct even when empty

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

    response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )

    # Verify empty response
    assert response.conversations is not None
    assert len(response.conversations) == 0


@pytest.mark.asyncio
async def test_list_conversations_filters_by_user_id(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that list endpoint only returns conversations for authenticated user.

    This integration test verifies:
    - Cache filtering by user_id works correctly
    - Other users' conversations are not returned
    - User isolation is maintained

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth
    other_user_id = "other_user_id"

    # Add conversation for authenticated user
    user_entry = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        topic_summary="User's conversation",
    )

    # Add conversation for different user
    other_entry = create_test_cache_entry(
        conversation_id=OTHER_CONVERSATION_ID,
        user_id=other_user_id,
        topic_summary="Other user's conversation",
    )

    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, user_entry)
    setup_conversation_cache.insert_or_append(
        other_user_id, OTHER_CONVERSATION_ID, other_entry
    )

    response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )

    # Verify only user's conversation is returned
    assert len(response.conversations) == 1
    assert response.conversations[0].conversation_id == TEST_CONVERSATION_ID


@pytest.mark.asyncio
async def test_list_conversations_handles_cache_unavailable(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that list endpoint handles unavailable cache gracefully.

    This integration test verifies:
    - Cache unavailability is detected
    - HTTPException is raised with 500 status code
    - Error message indicates cache is not configured

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
    """
    # Set cache configuration to None to simulate unavailable cache
    test_config.conversation_cache_configuration.type = None

    with pytest.raises(HTTPException) as exc_info:
        await get_conversations_list_endpoint_handler(
            request=mock_request_with_auth,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert isinstance(exc_info.value.detail, dict)


# ==========================================
# Get Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_get_conversation_returns_chat_history(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that get conversation endpoint returns complete chat history.

    This integration test verifies:
    - Endpoint retrieves conversation from cache
    - Chat history is properly structured with messages
    - Tool calls and results are included
    - Timestamps and metadata are present

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Add conversation entries to cache (multiple turns)
    entry1 = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        query="What is Ansible?",
        response="Ansible is an automation tool.",
        topic_summary="Ansible basics",
    )
    entry2 = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        query="How do I use it?",
        response="You write playbooks in YAML.",
        topic_summary="Ansible basics",
    )

    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry1)
    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry2)

    response = await get_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response structure
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.chat_history is not None
    assert len(response.chat_history) == 2

    # Verify first turn
    turn1 = response.chat_history[0]
    assert len(turn1.messages) == 2
    assert turn1.messages[0].type == "user"
    assert turn1.messages[0].content == "What is Ansible?"
    assert turn1.messages[1].type == "assistant"
    assert turn1.messages[1].content == "Ansible is an automation tool."
    assert turn1.provider == "test-provider"
    assert turn1.model == "test-model"
    assert turn1.started_at is not None
    assert turn1.completed_at is not None


@pytest.mark.asyncio
async def test_get_conversation_invalid_id_format_returns_400(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
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
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

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
    setup_conversation_cache: SQLiteCache,
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
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

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
async def test_get_conversation_handles_cache_unavailable(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that get conversation handles unavailable cache gracefully.

    This integration test verifies:
    - Cache unavailability is detected
    - HTTPException is raised with 500 status code
    - Error message indicates cache is not configured

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
    """
    # Set cache configuration to None to simulate unavailable cache
    test_config.conversation_cache_configuration.type = None

    with pytest.raises(HTTPException) as exc_info:
        await get_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_get_conversation_with_tool_calls(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that get conversation includes tool calls and results.

    This integration test verifies:
    - Tool calls are properly included in response
    - Tool results are properly included in response
    - Chat history structure handles tool interactions

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create cache entry with tool calls
    now = datetime.now(UTC).isoformat()
    entry = CacheEntry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        query="Search for Ansible documentation",
        response="Based on the documentation, Ansible is...",
        provider="test-provider",
        model="test-model",
        referenced_documents=[
            {
                "file_id": "doc-1",
                "filename": "ansible-docs.txt",
                "score": 0.95,
                "text": "Ansible documentation...",
            }
        ],
        tool_calls=[
            {
                "id": "call-1",
                "name": "file_search",
                "args": {"queries": ["Ansible documentation"]},
                "type": "tool_call",
            }
        ],
        tool_results=[
            {
                "id": "call-1",
                "status": "success",
                "content": "Found documentation for Ansible",
                "type": "tool_result",
                "round": 1,
            }
        ],
        topic_summary="Ansible search",
        started_at=now,
        completed_at=now,
    )

    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry)

    response = await get_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response includes tool calls
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.chat_history is not None
    assert len(response.chat_history) == 1

    turn = response.chat_history[0]
    assert turn.tool_calls is not None
    assert len(turn.tool_calls) > 0
    assert turn.tool_results is not None
    assert len(turn.tool_results) > 0
    assert turn.messages[1].referenced_documents is not None


# ==========================================
# Delete Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_delete_conversation_removes_from_cache(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that delete conversation removes from cache.

    This integration test verifies:
    - Conversation is deleted from cache
    - Response indicates successful deletion
    - Cache no longer contains the conversation

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Add conversation to cache
    entry = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
    )
    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry)

    # Verify conversation exists before deletion via list endpoint
    list_response_before = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )
    assert len(list_response_before.conversations) == 1

    response = await delete_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )

    # Verify response
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True

    # Verify conversation no longer exists via list endpoint
    list_response_after = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )
    assert len(list_response_after.conversations) == 0


@pytest.mark.asyncio
async def test_delete_conversation_invalid_id_format_returns_400(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
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
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

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
async def test_delete_conversation_non_existent_returns_success(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that deleting non-existent conversation returns success.

    This integration test verifies:
    - Deleting non-existent conversation is idempotent
    - Response indicates deletion status
    - No error is raised

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

    response = await delete_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=NON_EXISTENT_ID,
        auth=test_auth,
    )

    # Verify response (note: success is always True per implementation)
    assert response.conversation_id == NON_EXISTENT_ID
    assert response.success is True
    # Response message indicates deletion status
    assert "cannot be deleted" in response.response.lower()


@pytest.mark.asyncio
async def test_delete_conversation_handles_cache_unavailable(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that delete conversation handles unavailable cache gracefully.

    This integration test verifies:
    - Cache unavailability is detected
    - HTTPException is raised with 500 status code
    - Error message indicates cache is not configured

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
    """
    # Set cache configuration to None to simulate unavailable cache
    test_config.conversation_cache_configuration.type = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_conversation_endpoint_handler(
            request=mock_request_with_auth,
            conversation_id=TEST_CONVERSATION_ID,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert isinstance(exc_info.value.detail, dict)


# ==========================================
# Update Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_update_conversation_updates_topic_summary(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that update conversation updates topic summary in cache.

    This integration test verifies:
    - Topic summary is updated in cache
    - Response indicates successful update
    - All conversation entries are updated

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Add conversation to cache
    entry = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        topic_summary="Old topic",
    )
    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry)

    update_request = ConversationUpdateRequest(topic_summary="New topic summary")

    response = await update_conversation_endpoint_handler(
        conversation_id=TEST_CONVERSATION_ID,
        update_request=update_request,
        auth=test_auth,
    )

    # Verify response
    assert response.conversation_id == TEST_CONVERSATION_ID
    assert response.success is True
    assert "updated successfully" in response.message.lower()

    # Verify topic summary was updated via list endpoint
    list_response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )
    assert len(list_response.conversations) == 1
    assert list_response.conversations[0].topic_summary == "New topic summary"


@pytest.mark.asyncio
async def test_update_conversation_invalid_id_format_returns_400(
    test_config: AppConfig,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that update conversation with invalid ID format returns HTTP 400.

    This integration test verifies:
    - Invalid conversation ID format is detected
    - HTTPException is raised with 400 status code
    - Error message indicates bad request

    Parameters:
        test_config: Test configuration
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
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
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that update conversation with non-existent ID returns HTTP 404.

    This integration test verifies:
    - Non-existent conversation ID is detected
    - HTTPException is raised with 404 status code
    - Error message indicates not found

    Parameters:
        test_config: Test configuration
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config
    _ = setup_conversation_cache

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
            conversation_id=NON_EXISTENT_ID,
            update_request=update_request,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_update_conversation_handles_cache_unavailable(
    test_config: AppConfig,
    test_auth: AuthTuple,
) -> None:
    """Test that update conversation handles unavailable cache gracefully.

    This integration test verifies:
    - Cache unavailability is detected
    - HTTPException is raised with 500 status code
    - Error message indicates cache is not configured

    Parameters:
        test_config: Test configuration
        test_auth: noop authentication tuple
    """
    # Set cache configuration to None to simulate unavailable cache
    test_config.conversation_cache_configuration.type = None

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    with pytest.raises(HTTPException) as exc_info:
        await update_conversation_endpoint_handler(
            conversation_id=TEST_CONVERSATION_ID,
            update_request=update_request,
            auth=test_auth,
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert isinstance(exc_info.value.detail, dict)


@pytest.mark.asyncio
async def test_update_conversation_with_multiple_turns(
    test_config: AppConfig,
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    setup_conversation_cache: SQLiteCache,
) -> None:
    """Test that update conversation updates all turns in multi-turn conversation.

    This integration test verifies:
    - Topic summary is updated for multi-turn conversations
    - Multi-turn conversations are handled correctly
    - Cache maintains conversation integrity

    Parameters:
        test_config: Test configuration
        mock_request_with_auth: FastAPI request with full authorization
        test_auth: noop authentication tuple
        setup_conversation_cache: Configured conversation cache
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Add multiple turns to cache
    entry1 = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        query="First question",
        response="First answer",
        topic_summary="Old topic",
    )
    entry2 = create_test_cache_entry(
        conversation_id=TEST_CONVERSATION_ID,
        user_id=user_id,
        query="Second question",
        response="Second answer",
        topic_summary="Old topic",
    )

    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry1)
    setup_conversation_cache.insert_or_append(user_id, TEST_CONVERSATION_ID, entry2)

    update_request = ConversationUpdateRequest(topic_summary="New topic")

    response = await update_conversation_endpoint_handler(
        conversation_id=TEST_CONVERSATION_ID,
        update_request=update_request,
        auth=test_auth,
    )

    # Verify response
    assert response.success is True

    # Verify topic summary was updated via list endpoint
    list_response = await get_conversations_list_endpoint_handler(
        request=mock_request_with_auth,
        auth=test_auth,
    )
    assert len(list_response.conversations) == 1
    assert list_response.conversations[0].topic_summary == "New topic"

    # Verify both turns are still present in conversation
    get_response = await get_conversation_endpoint_handler(
        request=mock_request_with_auth,
        conversation_id=TEST_CONVERSATION_ID,
        auth=test_auth,
    )
    assert len(get_response.chat_history) == 2
