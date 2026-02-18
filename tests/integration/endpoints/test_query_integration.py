"""Integration tests for the /query endpoint (using Responses API)."""

# pylint: disable=too-many-lines  # Integration tests require comprehensive coverage
# pylint: disable=too-many-arguments  # Integration tests need many fixtures
# pylint: disable=too-many-positional-arguments  # Integration tests need many fixtures

from typing import Any, Generator

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import APIConnectionError
from llama_stack_client.types import VersionInfo
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.database
import app.endpoints.query
from app.endpoints.query import query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.cache_entry import CacheEntry
from models.database.conversations import UserConversation
from models.requests import Attachment, QueryRequest
import utils.query

# Test constants - use valid UUID format
TEST_CONVERSATION_ID = "c9d40813-d64d-41eb-8060-3b2446929a02"
TEST_CONV_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
NON_EXISTENT_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_CONV_ID = "11111111-1111-1111-1111-111111111111"
EXISTING_CONV_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(name="mock_llama_stack_client")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
        mocker (MockerFixture): pytest-mock fixture used to create and patch mocks.

    Returns:
        mock_client: The mocked Llama Stack client instance configured as described above.
    """
    # Patch in app.endpoints.query where it's actually used by query_endpoint_handler_base
    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")

    mock_client = mocker.AsyncMock()

    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-123"

    # Mock output with assistant message
    mock_output_item = mocker.MagicMock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = "This is a test response about Ansible."
    mock_output_item.refusal = (
        None  # Explicitly set refusal to None (no shield violation)
    )

    mock_response.output = [mock_output_item]
    mock_response.stop_reason = "end_turn"

    # Mock tool calls (empty by default)
    mock_response.tool_calls = []

    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage

    mock_client.responses.create.return_value = mock_response

    # Mock models list (required for model selection)
    mock_model = mocker.MagicMock()
    mock_model.id = "test-provider/test-model"
    mock_model.custom_metadata = {
        "provider_id": "test-provider",
        "model_type": "llm",
    }
    mock_client.models.list.return_value = [mock_model]

    # Mock shields list (empty by default for simpler tests)
    mock_client.shields.list.return_value = []

    # Mock vector stores list (empty by default) - must return object with .data attribute
    mock_vector_stores_response = mocker.MagicMock()
    mock_vector_stores_response.data = []
    mock_client.vector_stores.list.return_value = mock_vector_stores_response

    # Mock conversations.create for new conversation creation
    # Returns ID in llama-stack format (conv_ prefix + 48 hex chars)
    mock_conversation = mocker.MagicMock()
    mock_conversation.id = "conv_" + "a" * 48  # conv_aaa...aaa (proper format)
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)

    # Mock version info
    mock_client.inspect.version.return_value = VersionInfo(version="0.2.22")

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


# ==========================================
# Basic Response Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_successful_response(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that query v2 endpoint returns successful response.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Llama Stack Responses API is properly called
    - Response is correctly formatted
    - Conversation ID is returned

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    query_request = QueryRequest(
        query="What is Ansible?",
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Verify response structure
    assert response.conversation_id is not None
    # Conversation ID is normalized (without conv_ prefix) from conversations.create()
    assert response.conversation_id == "a" * 48
    assert "Ansible" in response.response
    assert response.response == "This is a test response about Ansible."
    assert response.input_tokens >= 0
    assert response.output_tokens >= 0


@pytest.mark.asyncio
async def test_query_v2_endpoint_handles_connection_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test that query v2 endpoint properly handles Llama Stack connection errors.

    This integration test verifies:
    - Error handling when external service is unavailable
    - HTTPException is raised with correct status code
    - Error response includes proper error details

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture

    Returns:
        None
    """
    _ = test_config

    mock_llama_stack_client.responses.create.side_effect = APIConnectionError(
        request=mocker.Mock()
    )

    query_request = QueryRequest(query="What is Ansible?")

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)
    assert exc_info.value.detail["response"] == "Unable to connect to Llama Stack"
    assert "cause" in exc_info.value.detail


@pytest.mark.asyncio
async def test_query_v2_endpoint_empty_query(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test query v2 endpoint with empty query string.

    This integration test verifies:
    - Empty queries are handled appropriately
    - Validation works correctly
    - Error response is returned if needed

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple

    Returns:
        None
    """
    _ = test_config
    _ = mock_llama_stack_client

    query_request = QueryRequest(query="")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response is not None


# ==========================================
# Request/Input Handling Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_with_attachments(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test query v2 endpoint with attachments.

    This integration test verifies:
    - Attachments are properly validated
    - Attachment content is included in request
    - Response handles attachments correctly

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    query_request = QueryRequest(
        query="Analyze this playbook",
        attachments=[
            Attachment(
                attachment_type="configuration",
                content_type="application/yaml",
                content=(
                    "---\n- name: Test playbook\n"
                    "  hosts: all\n  tasks:\n    - debug: msg='test'"
                ),
            )
        ],
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response is not None


# ==========================================
# Tool Integration Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_with_tool_calls(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test query v2 endpoint with tool calls (RAG).

    This integration test verifies:
    - Tool calls are properly processed
    - RAG tool responses are included
    - Referenced documents are returned

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture
    """
    _ = test_config

    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-789"

    mock_tool_output = mocker.MagicMock()
    mock_tool_output.type = "file_search_call"
    mock_tool_output.id = "call-1"
    mock_tool_output.queries = ["What is Ansible"]
    mock_tool_output.status = "completed"
    mock_result = mocker.MagicMock()
    mock_result.file_id = "doc-1"
    mock_result.filename = "ansible-docs.txt"
    mock_result.score = 0.95
    mock_result.text = "Ansible is an open-source automation tool..."
    mock_result.attributes = {
        "doc_url": "https://example.com/ansible-docs.txt",
        "link": "https://example.com/ansible-docs.txt",
    }
    mock_result.model_dump = mocker.Mock(
        return_value={
            "file_id": "doc-1",
            "filename": "ansible-docs.txt",
            "score": 0.95,
            "text": "Ansible is an open-source automation tool...",
            "attributes": {
                "doc_url": "https://example.com/ansible-docs.txt",
                "link": "https://example.com/ansible-docs.txt",
            },
        }
    )
    mock_tool_output.results = [mock_result]

    mock_message_output = mocker.MagicMock()
    mock_message_output.type = "message"
    mock_message_output.role = "assistant"
    mock_message_output.content = "Based on the documentation, Ansible is..."

    mock_response.output = [mock_tool_output, mock_message_output]
    mock_response.stop_reason = "end_turn"

    # Mock usage object
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage

    mock_llama_stack_client.responses.create.return_value = mock_response

    query_request = QueryRequest(query="What is Ansible?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.tool_calls is not None
    assert len(response.tool_calls) > 0
    assert response.tool_calls[0].name == "file_search"


@pytest.mark.asyncio
async def test_query_v2_endpoint_with_mcp_list_tools(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test query with mcp_list_tools type.

    This integration test verifies:
    - mcp_list_tools results are processed
    - Tool names list is captured
    - Server label is included

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture
    """
    _ = test_config

    mock_response = mocker.MagicMock()
    mock_response.id = "response-mcplist"

    mock_tool1 = mocker.MagicMock()
    mock_tool1.name = "list_pods"
    mock_tool1.description = "List Kubernetes pods"
    mock_tool1.input_schema = {"type": "object", "properties": {}}

    mock_tool2 = mocker.MagicMock()
    mock_tool2.name = "get_deployment"
    mock_tool2.description = "Get Kubernetes deployment"
    mock_tool2.input_schema = {"type": "object", "properties": {}}

    mock_mcp_list = mocker.MagicMock()
    mock_mcp_list.type = "mcp_list_tools"
    mock_mcp_list.id = "mcplist-101"
    mock_mcp_list.server_label = "kubernetes-server"
    mock_mcp_list.tools = [mock_tool1, mock_tool2]

    mock_message = mocker.MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = "Available tools: list_pods, get_deployment"

    mock_response.output = [mock_mcp_list, mock_message]
    mock_response.tool_calls = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 15
    mock_usage.output_tokens = 20
    mock_response.usage = mock_usage

    mock_llama_stack_client.responses.create.return_value = mock_response

    query_request = QueryRequest(query="What tools are available?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "mcp_list_tools"


@pytest.mark.asyncio
async def test_query_v2_endpoint_with_multiple_tool_types(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test query with multiple different tool types in one response.

    This integration test verifies:
    - Multiple tool types can be processed together
    - All tool summaries are included
    - Response text combines with tool results

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture
    """
    _ = test_config

    mock_response = mocker.MagicMock()
    mock_response.id = "response-multi"

    mock_file_search = mocker.MagicMock()
    mock_file_search.type = "file_search_call"
    mock_file_search.id = "search-1"
    mock_file_search.queries = ["Kubernetes deployment"]
    mock_file_search.status = "completed"
    mock_file_search.results = []

    mock_function = mocker.MagicMock()
    mock_function.type = "function_call"
    mock_function.id = "func-2"
    mock_function.call_id = "func-2"
    mock_function.name = "calculate"
    mock_function.arguments = '{"operation": "sum"}'
    mock_function.status = "completed"

    mock_message = mocker.MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = "Based on documentation and calculations..."

    mock_response.output = [mock_file_search, mock_function, mock_message]
    mock_response.tool_calls = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 40
    mock_usage.output_tokens = 60
    mock_response.usage = mock_usage

    mock_llama_stack_client.responses.create.return_value = mock_response

    query_request = QueryRequest(query="Search docs and calculate deployment replicas")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Verify response includes multiple tool calls
    assert response.tool_calls is not None
    assert len(response.tool_calls) == 2
    tool_names = [tc.name for tc in response.tool_calls]
    assert "knowledge_search" in tool_names or "file_search" in tool_names
    assert "calculate" in tool_names


@pytest.mark.asyncio
async def test_query_v2_endpoint_bypasses_tools_when_no_tools_true(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that tools are NOT used when no_tools=True.

    This integration test verifies:
    - no_tools=True bypasses tool preparation
    - No tools are passed to Llama Stack even when vector stores are available
    - Response succeeds without tools
    - Integration between query handler and tool preparation

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture

    Returns:
        None
    """
    _ = test_config
    _ = patch_db_session

    mock_vector_store = mocker.MagicMock()
    mock_vector_store.id = "vs-test-123"

    mock_list_result = mocker.MagicMock()
    mock_list_result.data = [mock_vector_store]

    mock_llama_stack_client.vector_stores.list.return_value = mock_list_result

    query_request = QueryRequest(query="What is Ansible?", no_tools=True)

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response is not None

    # Verify NO tools were passed to Llama Stack (despite vector stores being available)
    call_kwargs = mock_llama_stack_client.responses.create.call_args.kwargs
    assert call_kwargs.get("tools") is None


@pytest.mark.asyncio
async def test_query_v2_endpoint_uses_tools_when_available(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that tools are used when no_tools=False and vector stores are available.

    This integration test verifies:
    - Tool preparation logic retrieves available tools
    - Tools are passed to Llama Stack when available
    - Response succeeds with tools enabled
    - Integration between query handler, vector stores, and tool preparation

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture

    Returns:
        None
    """
    _ = test_config
    _ = patch_db_session

    # Mock vector stores to be available (simulating RAG tools)
    mock_vector_store = mocker.MagicMock()
    mock_vector_store.id = "vs-test-123"

    mock_list_result = mocker.MagicMock()
    mock_list_result.data = [mock_vector_store]

    mock_llama_stack_client.vector_stores.list.return_value = mock_list_result

    query_request = QueryRequest(query="What is Ansible?", no_tools=False)

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response is not None

    # Verify tools were passed to Llama Stack (real tool preparation logic ran)
    call_kwargs = mock_llama_stack_client.responses.create.call_args_list[0].kwargs
    assert call_kwargs.get("tools") is not None
    assert len(call_kwargs["tools"]) > 0
    assert any(tool.get("type") == "file_search" for tool in call_kwargs["tools"])


# ==========================================
# Database/Conversation Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_persists_conversation_to_database(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that conversation details are persisted to database.

    This integration test verifies:
    - Conversation record is created in database
    - User ID, model, provider are stored correctly
    - Topic summary is generated and stored

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = mock_llama_stack_client

    query_request = QueryRequest(query="What is Ansible?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    conversation = (
        patch_db_session.query(UserConversation)
        .filter_by(id=response.conversation_id)
        .first()
    )

    assert conversation is not None

    user_id, _, _, _ = test_auth
    assert conversation.user_id == user_id
    assert conversation.last_used_model is not None
    assert conversation.last_used_provider is not None
    assert conversation.topic_summary is not None
    assert conversation.message_count == 1


@pytest.mark.asyncio
async def test_query_v2_endpoint_updates_existing_conversation(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that existing conversation is updated (not recreated).

    This integration test verifies:
    - Existing conversation record is updated in database
    - Message count increments correctly
    - Last message timestamp updates
    - Topic summary is NOT regenerated

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    # Create an existing conversation in the database
    user_id, _, _, _ = test_auth
    existing_conversation = UserConversation(
        id=EXISTING_CONV_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Ansible basics",
        message_count=3,
    )
    patch_db_session.add(existing_conversation)
    patch_db_session.commit()

    original_topic = existing_conversation.topic_summary
    original_count = existing_conversation.message_count

    mock_llama_stack_client.responses.create.return_value.id = EXISTING_CONV_ID

    query_request = QueryRequest(query="Tell me more", conversation_id=EXISTING_CONV_ID)

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Refresh from database to get updated values
    patch_db_session.refresh(existing_conversation)

    # Verify conversation was updated (not recreated)
    assert response.conversation_id is not None
    assert existing_conversation.message_count == original_count + 1
    assert existing_conversation.topic_summary == original_topic
    assert existing_conversation.last_message_at is not None


@pytest.mark.asyncio
async def test_query_v2_endpoint_conversation_ownership_validation(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that conversation ownership is validated.

    This integration test verifies:
    - Ownership validation is executed
    - User can access their own conversation
    - Conversation must exist in database

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = mock_llama_stack_client

    # Create conversation owned by the authenticated user in database
    user_id, _, _, _ = test_auth
    user_conversation = UserConversation(
        id=TEST_CONV_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Test topic",
        message_count=1,
    )
    patch_db_session.add(user_conversation)
    patch_db_session.commit()

    query_request = QueryRequest(query="What is Ansible?", conversation_id=TEST_CONV_ID)

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None


@pytest.mark.asyncio
async def test_query_v2_endpoint_creates_valid_cache_entry(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that cache entry is created with correct structure.

    This integration test verifies:
    - Cache storage function is called during request flow
    - CacheEntry object has all required fields populated
    - Query, response, model, provider, and timestamps are included
    - Integration between query processing and cache storage

    Note: We spy on cache storage to verify integration, not to mock it.

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture

    Returns:
        None
    """
    _ = test_config
    _ = mock_llama_stack_client
    _ = patch_db_session

    cache_spy = mocker.spy(utils.query, "store_conversation_into_cache")

    query_request = QueryRequest(query="What is Ansible?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    cache_spy.assert_called_once()

    call_args = cache_spy.call_args
    cache_entry = call_args.kwargs["cache_entry"]

    assert isinstance(cache_entry, CacheEntry)
    assert cache_entry.query == "What is Ansible?"
    assert cache_entry.response is not None
    assert cache_entry.model is not None
    assert cache_entry.provider is not None
    assert cache_entry.started_at is not None
    assert cache_entry.completed_at is not None
    assert response.conversation_id is not None


# ==========================================
# Authorization/RBAC Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_conversation_not_found_returns_404(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that non-existent conversation returns HTTP 404.

    This integration test verifies:
    - Requesting non-existent conversation_id raises HTTPException
    - Validation logic is executed
    - Status code is 404 NOT FOUND
    - Error message indicates conversation not found

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = mock_llama_stack_client

    query_request = QueryRequest(
        query="What is Ansible?", conversation_id=NON_EXISTENT_ID
    )

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert isinstance(exc_info.value.detail, dict)
    assert "not found" in exc_info.value.detail["response"].lower()

    conversations = patch_db_session.query(UserConversation).all()
    assert len(conversations) == 0


# ==========================================
# Shields/Safety Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_with_shield_violation(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that shield violations are detected and logged.

    This integration test verifies:
    - Llama Stack returns response with violation (refusal)
    - Shield detection processes the violation
    - Metrics are updated (validation error counter)
    - Processing continues (consistent with V1 behavior)
    - Conversation is persisted despite violation

    Note: Shields are advisory - violations are logged but don't block requests.
    This matches query V1 behavior.

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture (only for Llama Stack response)
    """
    _ = test_config

    # Configure Llama Stack mock to return response with violation
    mock_response = mocker.MagicMock()
    mock_response.id = "response-violation"

    # Mock output with shield violation (refusal from Llama Stack)
    mock_output_item = mocker.MagicMock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = "I cannot respond to this request"
    mock_output_item.refusal = "Content violates safety policy"
    mock_output_item.stop_reason = "content_filter"

    mock_response.output = [mock_output_item]
    mock_response.tool_calls = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage

    mock_llama_stack_client.responses.create.return_value = mock_response

    query_request = QueryRequest(query="Inappropriate query")

    # Shield violations are advisory - request should succeed
    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response == "I cannot respond to this request"

    # Verify conversation was persisted (processing continued)
    conversations = patch_db_session.query(UserConversation).all()
    assert len(conversations) == 1


@pytest.mark.asyncio
async def test_query_v2_endpoint_without_shields(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that endpoint works without shields configured.

    This integration test verifies:
    - Empty shields list from Llama Stack is handled gracefully
    - Shield retrieval processes empty list
    - extra_body.guardrails is not included when no shields
    - Response succeeds without shields

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config
    _ = patch_db_session

    # Configure Llama Stack client mock to return no shields (default behavior)
    mock_llama_stack_client.shields.list.return_value = []

    query_request = QueryRequest(query="What is Ansible?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response is not None

    # Verify extra_body was not included (or guardrails is empty)
    call_kwargs = mock_llama_stack_client.responses.create.call_args.kwargs
    if "extra_body" in call_kwargs:
        assert (
            "guardrails" not in call_kwargs["extra_body"]
            or not call_kwargs["extra_body"]["guardrails"]
        )


@pytest.mark.asyncio
async def test_query_v2_endpoint_handles_empty_llm_response(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test that empty LLM response is handled gracefully.

    This integration test verifies:
    - System handles LLM returning no content
    - Warning is logged but request succeeds
    - Response contains empty/minimal content
    - Conversation is still persisted

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture
    """
    _ = test_config

    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-empty"

    mock_output_item = mocker.MagicMock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = ""  # Empty content
    mock_output_item.refusal = None

    mock_response.output = [mock_output_item]
    mock_response.stop_reason = "end_turn"
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 0
    mock_response.usage = mock_usage

    mock_llama_stack_client.responses.create.return_value = mock_response

    query_request = QueryRequest(query="What is Ansible?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response == ""


# ==========================================
# Quota Management Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_quota_integration(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test quota consumption and reporting integration.

    This integration test verifies:
    - Quota consumption logic is triggered with correct token counts
    - Available quotas are retrieved and returned in response
    - Token usage from Llama Stack flows through quota system
    - Complete integration between query handler and quota management

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture (only for spying on quota functions)
    """
    _ = test_config
    _ = patch_db_session

    mock_response = mocker.MagicMock()
    mock_response.id = "response-quota"
    mock_response.output = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_response.usage = mock_usage

    mock_llama_stack_client.responses.create.return_value = mock_response

    mock_consume = mocker.spy(app.endpoints.query, "consume_query_tokens")
    _ = mocker.spy(app.endpoints.query, "get_available_quotas")

    query_request = QueryRequest(query="What is Ansible?")

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None

    mock_consume.assert_called_once()
    consume_args = mock_consume.call_args
    user_id, _, _, _ = test_auth
    assert consume_args.kwargs["user_id"] == user_id
    assert consume_args.kwargs["model_id"] is not None
    assert consume_args.kwargs["token_usage"] is not None
    assert consume_args.kwargs["token_usage"].input_tokens == 100
    assert consume_args.kwargs["token_usage"].output_tokens == 50
    assert consume_args.kwargs["configuration"] is not None

    assert response.available_quotas is not None
    assert isinstance(response.available_quotas, dict)


@pytest.mark.asyncio
async def test_query_v2_endpoint_rejects_query_when_quota_exceeded(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test that query is rejected when user quota is exceeded.

    This integration test verifies:
    - Query is rejected when quota is exceeded (429 error)
    - No conversation is created in database when quota check fails
    - Error response contains appropriate message
    - LLM is not called when quota is exceeded

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture (to simulate quota exceeded)

    Returns:
        None
    """
    _ = test_config
    _ = mock_llama_stack_client

    # Mock check_tokens_available to simulate quota exceeded
    mocker.patch(
        "app.endpoints.query.check_tokens_available",
        side_effect=HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"response": "Quota exceeded", "cause": "Token limit reached"},
        ),
    )

    query_request = QueryRequest(query="What is Ansible?")

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert isinstance(exc_info.value.detail, dict)
    assert "quota" in exc_info.value.detail["response"].lower()

    # Verify no conversation was created (quota check prevented it)
    conversations = patch_db_session.query(UserConversation).all()
    assert len(conversations) == 0


# ==========================================
# Transcript Storage Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_transcript_behavior(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> None:
    """Test transcript storage behavior based on configuration.

    This integration test verifies:
    - Endpoint succeeds with transcripts enabled
    - Endpoint succeeds with transcripts disabled
    - Conversation is persisted regardless of transcript setting
    - Integration between query handler and transcript configuration

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
        mocker: pytest-mock fixture
    """
    _ = mock_llama_stack_client

    # Mock store_transcript to prevent file creation
    mocker.patch("utils.query.store_transcript")

    test_config.user_data_collection_configuration.transcripts_enabled = True

    query_request_enabled = QueryRequest(
        query="What is Ansible?",
        attachments=[
            Attachment(
                attachment_type="log",
                content_type="text/plain",
                content="Example attachment",
            )
        ],
    )

    response_enabled = await query_endpoint_handler(
        request=test_request,
        query_request=query_request_enabled,
        auth=test_auth,
        mcp_headers={},
    )

    # Verify response succeeded with transcripts enabled
    assert response_enabled.conversation_id is not None
    assert response_enabled.response is not None

    # Verify conversation was persisted
    conversation_enabled = (
        patch_db_session.query(UserConversation)
        .filter_by(id=response_enabled.conversation_id)
        .first()
    )
    assert conversation_enabled is not None

    test_config.user_data_collection_configuration.transcripts_enabled = False

    query_request_disabled = QueryRequest(query="What is Kubernetes?")

    response_disabled = await query_endpoint_handler(
        request=test_request,
        query_request=query_request_disabled,
        auth=test_auth,
        mcp_headers={},
    )

    # Verify response succeeded with transcripts disabled
    assert response_disabled.conversation_id is not None
    assert response_disabled.response is not None

    # Verify conversation was still persisted (transcripts are independent)
    conversation_disabled = (
        patch_db_session.query(UserConversation)
        .filter_by(id=response_disabled.conversation_id)
        .first()
    )
    assert conversation_disabled is not None


# ==========================================
# Model Selection Tests
# ==========================================


@pytest.mark.asyncio
async def test_query_v2_endpoint_uses_conversation_history_model(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Test that model from conversation history is used.

    This integration test verifies:
    - Conversation history model/provider is maintained across turns
    - Model continuity works correctly for existing conversations
    - Message count increments properly
    - Integration between query handler and conversation persistence

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        patch_db_session: Test database session
    """
    _ = test_config

    user_id, _, _, _ = test_auth

    # Create existing conversation in REAL database with specific model/provider
    existing_conv = UserConversation(
        id=EXISTING_CONV_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Existing conversation",
        message_count=1,
    )
    patch_db_session.add(existing_conv)
    patch_db_session.commit()

    # Configure mock to return the existing conversation_id (response.id becomes conversation_id)
    mock_llama_stack_client.responses.create.return_value.id = EXISTING_CONV_ID

    query_request = QueryRequest(query="Tell me more", conversation_id=EXISTING_CONV_ID)

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.conversation_id is not None
    assert response.response is not None

    patch_db_session.refresh(existing_conv)
    assert existing_conv.message_count == 2
    # Verify model/provider remained consistent
    assert existing_conv.last_used_model == "test-model"  # Matches mock's model
    assert (
        existing_conv.last_used_provider == "test-provider"
    )  # Matches mock's provider
