"""Shared fixtures for integration tests."""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any, Optional, cast

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client.types import VersionInfo
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.messages import (
    ModelResponse,
    NativeToolCallPart,
    NativeToolReturnPart,
    PartEndEvent,
    PartStartEvent,
    TextPart,
)
from pydantic_ai.native_tools import FileSearchTool, MCPServerTool
from pydantic_ai.usage import RunUsage
from pytest_mock import MockerFixture
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.database
from authentication.interface import AuthTuple
from authentication.noop import NoopAuthDependency
from configuration import configuration
from models.config import Action
from models.database.base import Base

# ==========================================
# Common Test Constants
# ==========================================

# Test UUIDs - Use these constants for consistent test data across integration tests
TEST_USER_ID = "00000000-0000-0000-0000-000"
TEST_USERNAME = "lightspeed-user"
TEST_CONVERSATION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
TEST_SECOND_CONVERSATION_ID = "22222222-2222-2222-2222-222222222222"
TEST_REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"
TEST_OTHER_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_NON_EXISTENT_ID = "00000000-0000-0000-0000-000000000001"
TEST_INVALID_ID = "invalid-id-format"

# Test Model/Provider
TEST_MODEL = "test-provider/test-model"
TEST_PROVIDER = "test-provider"
TEST_MODEL_NAME = "test-model"

# ==========================================
# Helper Functions
# ==========================================


def create_mock_llm_response(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker: MockerFixture,
    content: str = "This is a test response about Ansible.",
    tool_calls: Optional[list[Any]] = None,
    refusal: Optional[str] = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Any:
    """Create a customizable mock LLM response.

    Helper function to create mock LLM responses with configurable content,
    tool calls, refusals, and token counts. Useful for tests that need to
    customize the response behavior.

    Args:
        mocker: pytest-mock fixture
        content: Response content text
        tool_calls: Optional list of tool calls
        refusal: Optional refusal message (for shield violations)
        input_tokens: Input token count for usage
        output_tokens: Output token count for usage

    Returns:
        Mock LLM response object with the specified configuration.
    """
    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-123"

    # Create output message
    mock_output_item = mocker.MagicMock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = content
    mock_output_item.refusal = refusal

    mock_response.output = [mock_output_item]
    mock_response.stop_reason = "end_turn" if not refusal else "stop"
    mock_response.tool_calls = tool_calls or []

    # Mock usage
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens
    mock_response.usage = mock_usage

    return mock_response


def create_mock_vector_store_response(
    mocker: MockerFixture,
    chunks: Optional[list[dict[str, Any]]] = None,
) -> Any:
    """Create a mock vector store response.

    Helper function to create mock vector store responses for RAG testing.

    Args:
        mocker: pytest-mock fixture
        chunks: Optional list of chunk dictionaries with keys: text, score, metadata

    Returns:
        Mock vector store response object.
    """
    mock_response = mocker.MagicMock()

    if chunks:
        mock_response.data = []
        for chunk in chunks:
            mock_chunk = mocker.MagicMock()
            mock_chunk.text = chunk.get("text", "Sample text")
            mock_chunk.score = chunk.get("score", 0.9)
            mock_chunk.metadata = chunk.get("metadata", {})
            mock_response.data.append(mock_chunk)
    else:
        mock_response.data = []

    return mock_response


def create_mock_tool_call(
    mocker: MockerFixture,
    tool_name: str = "test_tool",
    arguments: Optional[dict[str, Any]] = None,
    call_id: str = "call-123",
) -> Any:
    """Create a mock tool call.

    Helper function to create mock tool calls for testing tool integration.

    Args:
        mocker: pytest-mock fixture
        tool_name: Name of the tool being called
        arguments: Tool arguments as a dictionary
        call_id: Unique identifier for the tool call

    Returns:
        Mock tool call object.
    """
    mock_tool_call = mocker.MagicMock()
    mock_tool_call.id = call_id
    mock_tool_call.name = tool_name
    mock_tool_call.arguments = arguments or {}
    mock_tool_call.type = "tool_call"
    return mock_tool_call


def create_agent_run_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker: MockerFixture,
    *,
    content: str = "This is a test response about Ansible.",
    response_id: str = "response-123",
    input_tokens: int = 10,
    output_tokens: int = 5,
    model_response: Any = None,
    new_messages: Optional[list[Any]] = None,
) -> Any:
    """Create a mock AgentRunResult wired for retrieve_agent_response.

    Uses real pydantic-ai message types so build_turn_summary_from_agent_run
    exercises the same path as production agent runs.

    Args:
        mocker: pytest-mock fixture.
        content: Assistant text content for the run.
        response_id: Provider response identifier.
        input_tokens: Input token count for the run.
        output_tokens: Output token count for the run.
        model_response: Optional pre-built ModelResponse.
        new_messages: Optional message sequence returned by new_messages().

    Returns:
        Mock AgentRunResult compatible with build_turn_summary_from_agent_run.
    """
    if model_response is None:
        parts = [TextPart(content)] if content else []
        model_response = ModelResponse(
            parts=parts,
            finish_reason="stop",
            provider_response_id=response_id,
        )

    messages = new_messages if new_messages is not None else [model_response]
    run_result = mocker.MagicMock()
    run_result.response = model_response
    run_result.usage = RunUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        requests=1,
    )
    run_result.new_messages.return_value = messages
    return run_result


def create_file_search_agent_run_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker: MockerFixture,
    *,
    content: str,
    response_id: str = "response-tool-rag",
    queries: Optional[list[str]] = None,
    results: Optional[list[dict[str, Any]]] = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Any:
    """Create an AgentRunResult containing a native file_search tool call."""
    call = NativeToolCallPart(
        tool_name=FileSearchTool.kind,
        args={"queries": queries or ["test query"]},
        tool_call_id="call-fs-1",
    )
    return_part = NativeToolReturnPart(
        tool_name=FileSearchTool.kind,
        tool_call_id="call-fs-1",
        content={
            "status": "success",
            "results": results or [],
        },
    )
    model_response = ModelResponse(
        parts=[call, return_part, TextPart(content)],
        finish_reason="stop",
        provider_response_id=response_id,
    )
    return create_agent_run_result(
        mocker,
        content=content,
        response_id=response_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_response=model_response,
    )


def create_mcp_list_tools_agent_run_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker: MockerFixture,
    *,
    content: str,
    response_id: str = "response-mcplist",
    server_label: str = "kubernetes-server",
    tools: Optional[list[dict[str, Any]]] = None,
    input_tokens: int = 15,
    output_tokens: int = 20,
) -> Any:
    """Create an AgentRunResult containing an MCP list-tools native tool call."""
    call = NativeToolCallPart(
        tool_name=f"{MCPServerTool.kind}:{server_label}",
        args={"action": "list_tools"},
        tool_call_id="mcplist-101",
    )
    return_part = NativeToolReturnPart(
        tool_name=f"{MCPServerTool.kind}:{server_label}",
        tool_call_id="mcplist-101",
        content={"tools": tools or []},
    )
    model_response = ModelResponse(
        parts=[call, return_part, TextPart(content)],
        finish_reason="stop",
        provider_response_id=response_id,
    )
    return create_agent_run_result(
        mocker,
        content=content,
        response_id=response_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_response=model_response,
    )


def configure_query_agent_mock(
    mocker: MockerFixture,
    *,
    run_result: Any = None,
    run_side_effect: Any = None,
) -> Any:
    """Patch build_agent for /query integration tests and return the mock agent.

    Args:
        mocker: pytest-mock fixture.
        run_result: AgentRunResult returned by agent.run().
        run_side_effect: Optional exception side effect for agent.run().

    Returns:
        Mock agent exposing AsyncMock run().
    """
    if run_result is None:
        run_result = create_agent_run_result(mocker)

    mock_agent = mocker.AsyncMock()
    if run_side_effect is not None:
        mock_agent.run = mocker.AsyncMock(side_effect=run_side_effect)
    else:
        mock_agent.run = mocker.AsyncMock(return_value=run_result)

    build_agent_mock = mocker.patch(
        "utils.agents.query.build_agent",
        return_value=mock_agent,
    )
    mock_agent.build_agent_mock = build_agent_mock
    return mock_agent


def create_text_agent_stream_events(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker: MockerFixture,
    *,
    content: str = "Based on the documentation, OpenShift is a Kubernetes distribution.",
    response_id: str = "response-inline-stream",
    input_tokens: int = 50,
    output_tokens: int = 20,
) -> list[Any]:
    """Build pydantic-ai stream events for a simple text agent response."""
    run_result = create_agent_run_result(
        mocker,
        content=content,
        response_id=response_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    text_part = TextPart(content=content)
    return [
        PartStartEvent(index=0, part=text_part),
        PartEndEvent(index=0, part=text_part),
        AgentRunResultEvent(result=run_result),
    ]


def create_file_search_agent_stream_events(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker: MockerFixture,
    *,
    content: str,
    response_id: str = "response-tool-stream",
    queries: Optional[list[str]] = None,
    results: Optional[list[dict[str, Any]]] = None,
    input_tokens: int = 60,
    output_tokens: int = 25,
) -> list[Any]:
    """Build pydantic-ai stream events for a file_search tool agent response."""
    run_result = create_file_search_agent_run_result(
        mocker,
        content=content,
        response_id=response_id,
        queries=queries,
        results=results,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    call_part, return_part, text_part = run_result.response.parts
    return [
        PartEndEvent(index=0, part=call_part),
        PartStartEvent(index=1, part=return_part),
        PartStartEvent(index=2, part=text_part),
        PartEndEvent(index=2, part=text_part),
        AgentRunResultEvent(result=run_result),
    ]


def configure_streaming_agent_mock(
    mocker: MockerFixture,
    *,
    stream_events: Optional[list[Any]] = None,
) -> Any:
    """Patch build_agent for /streaming_query integration tests.

    Args:
        mocker: pytest-mock fixture.
        stream_events: Optional pydantic-ai events yielded by run_stream_events.

    Returns:
        Mock agent exposing run_stream_events().
    """
    events = stream_events or create_text_agent_stream_events(mocker)

    def _run_stream_events_side_effect(_prompt: str) -> Any:
        async def _event_stream() -> Any:
            for event in events:
                yield event

        ctx = mocker.MagicMock()
        ctx.__aenter__ = mocker.AsyncMock(return_value=_event_stream())
        ctx.__aexit__ = mocker.AsyncMock(return_value=None)
        return ctx

    mock_agent = mocker.MagicMock()
    mock_agent.run_stream_events = mocker.MagicMock(
        side_effect=_run_stream_events_side_effect
    )

    build_agent_mock = mocker.patch(
        "utils.agents.streaming.build_agent",
        return_value=mock_agent,
    )
    mock_agent.build_agent_mock = build_agent_mock
    return mock_agent


def get_agent_responses_params(mock_client: Any) -> Any:
    """Return ResponsesApiParams passed to the patched streaming build_agent."""
    return mock_client.build_agent_mock.call_args[0][1]


def get_agent_input_text(mock_client: Any) -> str:
    """Return the agent prompt text from the patched streaming build_agent call."""
    return cast(str, get_agent_responses_params(mock_client).input)


# ==========================================
# Fixtures
# ==========================================


@pytest.fixture(autouse=True)
def reset_configuration_state() -> Generator:
    """Reset configuration state before each integration test.

    This autouse fixture ensures test independence by resetting the
    singleton configuration state before each test runs. This allows
    tests to verify both loaded and unloaded configuration states
    regardless of execution order.
    """
    # pylint: disable=protected-access
    configuration._configuration = None
    yield


@pytest.fixture(name="test_config", scope="function")
def test_config_fixture() -> Generator:
    """Load real configuration for integration tests.

    This fixture loads the actual configuration file used in testing,
    demonstrating integration with the configuration system.

    Yields:
        The `configuration` module with the loaded settings.
    """
    config_path = (
        Path(__file__).parent.parent / "configuration" / "lightspeed-stack.yaml"
    )
    assert config_path.exists(), f"Config file not found: {config_path}"

    # Load configuration
    configuration.load_configuration(str(config_path))

    yield configuration
    # Note: Cleanup is handled by the autouse reset_configuration_state fixture


@pytest.fixture(name="current_config", scope="function")
def current_config_fixture() -> Generator:
    """Load current configuration for integration tests.

    This fixture loads the actual configuration file from project root (current configuration),
    demonstrating integration with the configuration system.

    Yields:
        configuration: The loaded configuration object.
    """
    config_path = Path(__file__).parent.parent.parent / "lightspeed-stack.yaml"
    assert config_path.exists(), f"Config file not found: {config_path}"

    # Load configuration
    configuration.load_configuration(str(config_path))

    yield configuration
    # Note: Cleanup is handled by the autouse reset_configuration_state fixture


@pytest.fixture(name="test_db_engine", scope="function")
def test_db_engine_fixture() -> Generator:
    """Create an in-memory SQLite database engine for testing.

    This provides a real database (not mocked) for integration tests.
    Each test gets a fresh database.

    Uses StaticPool to ensure the same in-memory database is shared across
    all threads (including background tasks like quota_scheduler).

    Yields:
        engine (Engine): A SQLAlchemy Engine connected to a new in-memory SQLite database.
    """
    # Create in-memory SQLite database with StaticPool for thread safety
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Set to True to see SQL queries
        connect_args={"check_same_thread": False},  # Allow multi-threaded access
        poolclass=StaticPool,  # Share single in-memory DB across all threads
    )

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(name="test_db_session", scope="function")
def test_db_session_fixture(test_db_engine: Engine) -> Generator[Session, None, None]:
    """Create a database session for testing.

    Provides a real database session connected to the in-memory test database.

    Yields:
        session (Session): A database session bound to the test engine; the
        fixture closes the session after the test.
    """
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = session_local()

    yield session

    session.close()


@pytest.fixture(name="test_request")
def test_request_fixture() -> Request:
    """Create a test FastAPI Request object with proper scope.

    Returns:
        request (fastapi.Request): A Request object whose scope has `"type":
        "http"`, an empty `query_string`, and no headers.
    """
    return Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [],
        }
    )


@pytest.fixture(name="test_response")
def test_response_fixture() -> Response:
    """Create a test FastAPI Response object with proper scope.

    Returns:
        Response: Response with empty content, status 200, and media_type "application/json".
    """
    return Response(content="", status_code=200, media_type="application/json")


@pytest.fixture(name="test_auth")
async def test_auth_fixture(test_request: Request) -> AuthTuple:
    """Create authentication using real noop auth module.

    This uses the actual NoopAuthDependency instead of mocking,
    making this a true integration test.

    Returns:
        AuthTuple: Authentication information produced by NoopAuthDependency.
    """
    noop_auth = NoopAuthDependency()
    return await noop_auth(test_request)


@pytest.fixture(name="non_admin_test_request")
def non_admin_test_request_fixture(
    test_request: Request, mocker: Any
) -> Generator[Request, None, None]:
    """Create a test request with standard user permissions (no elevated OTHERS permissions).

    This fixture patches the authorization system to grant only standard user actions,
    excluding elevated permissions like LIST_OTHERS_CONVERSATIONS, DELETE_OTHERS_CONVERSATIONS, etc.
    This allows testing user isolation in integration tests.

    Parameters:
        test_request: Base request fixture
        mocker: pytest-mock fixture

    Yields:
        Request: Test request that will have limited permissions when used with @authorize decorator
    """
    # Define standard user actions (excluding OTHERS and ADMIN permissions)
    standard_actions = {
        Action.LIST_CONVERSATIONS,
        Action.GET_CONVERSATION,
        Action.DELETE_CONVERSATION,
        Action.UPDATE_CONVERSATION,
    }

    # Patch the NoopAccessResolver to return limited actions
    mocker.patch(
        "authorization.resolvers.NoopAccessResolver.get_actions",
        return_value=standard_actions,
    )
    yield test_request


@pytest.fixture(name="integration_http_client")
def integration_http_client_fixture(
    test_config: object,
) -> Generator[TestClient, None, None]:
    """Provide a TestClient for the app with integration config.

    Use for integration tests that need to send real HTTP requests (e.g. empty
    body validation). Depends on test_config so configuration is loaded first.
    """
    _ = test_config
    config_path = (
        Path(__file__).resolve().parent.parent
        / "configuration"
        / "lightspeed-stack.yaml"
    )
    assert config_path.exists(), f"Config file not found: {config_path}"

    original = os.environ.get("LIGHTSPEED_STACK_CONFIG_PATH")
    os.environ["LIGHTSPEED_STACK_CONFIG_PATH"] = str(config_path)
    try:
        from app.main import (  # pylint: disable=import-outside-toplevel,redefined-outer-name
            app,
        )

        yield TestClient(app)
    finally:
        if original is not None:
            os.environ["LIGHTSPEED_STACK_CONFIG_PATH"] = original
        else:
            os.environ.pop("LIGHTSPEED_STACK_CONFIG_PATH", None)


@pytest.fixture(name="patch_db_session", autouse=True)
def patch_db_session_fixture(
    test_db_session: Session,
    test_db_engine: Engine,
) -> Generator[Session, None, None]:
    """Initialize database session for integration tests.

    This sets up the global session_local in app.database to use the test database.
    Uses an in-memory SQLite database, isolating tests from production data.
    This fixture is autouse=True, so it automatically applies to all integration tests.

    Args:
        test_db_session: Test database session
        test_db_engine: Test database engine

    Yields:
        The test database Session instance to be used by the test.
    """
    # Store original values to restore later
    original_engine = app.database.engine
    original_session_local = app.database.session_local

    # Set the test database engine and session maker globally
    # Match initialize_database() settings: autocommit=False, autoflush=False
    app.database.engine = test_db_engine
    app.database.session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )

    yield test_db_session

    # Restore original values
    app.database.engine = original_engine
    app.database.session_local = original_session_local


@pytest.fixture(name="mock_request_with_auth")
def mock_request_with_auth_fixture() -> Request:
    """Create a test FastAPI Request with full authorization.

    Creates a Request object with all actions authorized, useful for
    integration tests that need to bypass authorization checks.

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


@pytest.fixture(name="mock_llama_stack_client")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client for integration tests.

    This is a common fixture that mocks the Llama Stack client with sensible
    defaults for integration tests. Individual tests can override specific
    behaviors as needed.

    Patches AsyncLlamaStackClientHolder in both app.endpoints.query and app.main
    to ensure the mock is active during TestClient startup (when app.main imports
    and initializes the client) and during endpoint execution.

    Args:
        mocker: pytest-mock fixture used to create and patch mocks.

    Yields:
        mock_client: The mocked Llama Stack client instance.
    """
    # Patch AsyncLlamaStackClientHolder at multiple import locations
    # This ensures the mock is active both during app startup (app.main)
    # and during endpoint execution (query, conversations_v1, responses, etc.)
    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mocker.patch("app.main.AsyncLlamaStackClientHolder", mock_holder_class)
    mocker.patch(
        "app.endpoints.conversations_v1.AsyncLlamaStackClientHolder", mock_holder_class
    )

    mock_client = mocker.AsyncMock()

    # Mock responses.create with default assistant response
    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-123"

    mock_output_item = mocker.MagicMock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = "This is a test response about Ansible."
    mock_output_item.refusal = None

    mock_response.output = [mock_output_item]
    mock_response.stop_reason = "end_turn"
    mock_response.tool_calls = []

    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage

    mock_client.responses.create.return_value = mock_response

    mock_agent = configure_query_agent_mock(mocker)
    mock_client.query_agent = mock_agent
    mock_client.build_agent_mock = mock_agent.build_agent_mock

    # Mock models.list
    mock_model = mocker.MagicMock()
    mock_model.id = "test-provider/test-model"
    mock_model.custom_metadata = {
        "provider_id": "test-provider",
        "model_type": "llm",
    }
    mock_client.models.list.return_value = [mock_model]

    # Mock shields.list (empty by default)
    mock_client.shields.list.return_value = []

    # Mock vector_stores.list (empty by default)
    mock_vector_stores_response = mocker.MagicMock()
    mock_vector_stores_response.data = []
    mock_client.vector_stores.list.return_value = mock_vector_stores_response

    # Mock conversations.create
    mock_conversation = mocker.MagicMock()
    mock_conversation.id = "conv_" + "a" * 48  # Proper conv_ format
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)

    # Mock version info
    mock_client.inspect.version.return_value = VersionInfo(version="0.2.22")

    # Create mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client
