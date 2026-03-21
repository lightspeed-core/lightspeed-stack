"""Shared fixtures for integration tests."""

import os
from pathlib import Path
from collections.abc import Generator
from typing import Any

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

from authentication.noop import NoopAuthDependency
from authentication.interface import AuthTuple

from configuration import configuration
from models.config import Action
from models.database.base import Base

import app.database

# ==========================================
# Common Test Constants
# ==========================================

# Test UUIDs - Use these constants for consistent test data across integration tests
TEST_USER_ID = "00000000-0000-0000-0000-000"
TEST_USERNAME = "lightspeed-user"
TEST_CONVERSATION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
TEST_REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"
TEST_OTHER_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_NON_EXISTENT_ID = "00000000-0000-0000-0000-000000000001"

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
    tool_calls: list[Any] | None = None,
    refusal: str | None = None,
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
    # pylint: disable=import-outside-toplevel
    from llama_stack_api.openai_responses import OpenAIResponseObject

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
    chunks: list[dict[str, Any]] | None = None,
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
    arguments: dict[str, Any] | None = None,
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

    Yields:
        engine (Engine): A SQLAlchemy Engine connected to a new in-memory SQLite database.
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Set to True to see SQL queries
        connect_args={"check_same_thread": False},  # Allow multi-threaded access
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
    app.database.engine = test_db_engine
    app.database.session_local = sessionmaker(bind=test_db_engine)

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

    Args:
        mocker: pytest-mock fixture used to create and patch mocks.

    Yields:
        mock_client: The mocked Llama Stack client instance.
    """
    # pylint: disable=import-outside-toplevel
    from llama_stack_api.openai_responses import OpenAIResponseObject
    from llama_stack_client.types import VersionInfo

    # Patch AsyncLlamaStackClientHolder where it's commonly used
    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")

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
