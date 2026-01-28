"""Unit tests for the /query REST API endpoint."""

# pylint: disable=redefined-outer-name
# pylint: disable=too-many-lines
# pylint: disable=ungrouped-imports

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from app.endpoints.query import (
    evaluate_model_hints,
    is_transcripts_enabled,
    select_model_and_provider_id,
    validate_attachments_metadata,
)
from configuration import AppConfig
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import Attachment, QueryRequest
from utils.token_counter import TokenCounter

# User ID must be proper UUID
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture
def dummy_request() -> Request:
    """Dummy request fixture for testing.

    Create a minimal FastAPI Request with test-ready authorization state.

    The returned Request has a minimal HTTP scope and a
    `state.authorized_actions` attribute initialized to a set containing all
    members of the `Action` enum, suitable for use in unit tests that require
    an authenticated request context.

    Returns:
        req (Request): FastAPI Request with `state.authorized_actions` set to `set(Action)`.
    """
    req = Request(
        scope={
            "type": "http",
        }
    )

    req.state.authorized_actions = set(Action)
    return req


def mock_metrics(mocker: MockerFixture) -> None:
    """Helper function to mock metrics operations for query endpoints.

    Configure the provided pytest-mock `mocker` to stub token metrics and
    related metrics counters used by query endpoint tests.

    Patches the token metrics extraction helper and the LLM metrics counters so
    tests can run without emitting real metrics.
    """
    mocker.patch(
        "app.endpoints.query.extract_and_update_token_metrics",
        return_value=TokenCounter(),
    )
    # Mock the metrics that are called inside extract_and_update_token_metrics
    mocker.patch("metrics.llm_token_sent_total")
    mocker.patch("metrics.llm_token_received_total")
    mocker.patch("metrics.llm_calls_total")


def mock_database_operations(mocker: MockerFixture) -> None:
    """Helper function to mock database operations for query endpoints.

    Patch common database operations used by query endpoint tests.

    This applies test-time patches so that conversation ownership checks
    succeed, persistence of conversation details is stubbed out, and
    `get_session` returns a context-manager mock whose
    `query(...).filter_by(...).first()` returns `None`.

    Parameters:
        mocker (MockerFixture): The pytest-mock fixture used to apply patches.
    """
    mocker.patch(
        "app.endpoints.query.validate_conversation_ownership", return_value=True
    )
    mocker.patch("app.endpoints.query.persist_user_conversation_details")

    # Mock the database session and query
    mock_session = mocker.Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session.__enter__ = mocker.Mock(return_value=mock_session)
    mock_session.__exit__ = mocker.Mock(return_value=None)
    mocker.patch("app.endpoints.query.get_session", return_value=mock_session)


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests.

    Create a reusable application configuration tailored for unit tests.

    The returned AppConfig is initialized from a fixed dictionary that sets:
    - a lightweight service configuration (localhost, port 8080, minimal workers, logging enabled),
    - a test Llama Stack configuration (test API key and URL, not used as a library client),
    - user data collection with transcripts disabled,
    - an empty MCP servers list,
    - a noop conversation cache.

    Returns:
        AppConfig: an initialized configuration instance suitable for test fixtures.
    """
    config_dict: dict[Any, Any] = {
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
        "conversation_cache": {
            "type": "noop",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


def test_is_transcripts_enabled(
    setup_configuration: AppConfig, mocker: MockerFixture
) -> None:
    """Test that is_transcripts_enabled returns True when transcripts is not disabled."""
    # Override the transcripts_enabled setting
    mocker.patch.object(
        setup_configuration.user_data_collection_configuration,
        "transcripts_enabled",
        True,
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    assert is_transcripts_enabled() is True, "Transcripts should be enabled"


def test_is_transcripts_disabled(
    setup_configuration: AppConfig, mocker: MockerFixture
) -> None:
    """Test that is_transcripts_enabled returns False when transcripts is disabled."""
    # Use default transcripts_enabled=False from setup
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    assert is_transcripts_enabled() is False, "Transcripts should be disabled"


def test_select_model_and_provider_id_from_request(mocker: MockerFixture) -> None:
    """Test the select_model_and_provider_id function."""
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        "default_provider",
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        "default_model",
    )

    model_list = [
        mocker.Mock(
            id="provider1/model1",
            custom_metadata={"model_type": "llm", "provider_id": "provider1"},
        ),
        mocker.Mock(
            id="provider2/model2",
            custom_metadata={"model_type": "llm", "provider_id": "provider2"},
        ),
        mocker.Mock(
            id="default_provider/default_model",
            custom_metadata={"model_type": "llm", "provider_id": "default_provider"},
        ),
    ]

    # Create a query request with model and provider specified
    query_request = QueryRequest(
        query="What is OpenStack?", model="model2", provider="provider2"
    )

    # Assert the model and provider from request take precedence from the configuration one
    llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
        model_list, query_request.model, query_request.provider
    )

    assert llama_stack_model_id == "provider2/model2"
    assert model_id == "model2"
    assert provider_id == "provider2"


def test_select_model_and_provider_id_from_configuration(mocker: MockerFixture) -> None:
    """Test the select_model_and_provider_id function."""
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        "default_provider",
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        "default_model",
    )

    model_list = [
        mocker.Mock(
            id="provider1/model1",
            custom_metadata={"model_type": "llm", "provider_id": "provider1"},
        ),
        mocker.Mock(
            id="default_provider/default_model",
            custom_metadata={"model_type": "llm", "provider_id": "default_provider"},
        ),
    ]

    # Create a query request without model and provider specified
    query_request = QueryRequest(
        query="What is OpenStack?",
    )

    llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
        model_list, query_request.model, query_request.provider
    )

    # Assert that the default model and provider from the configuration are returned
    assert llama_stack_model_id == "default_provider/default_model"
    assert model_id == "default_model"
    assert provider_id == "default_provider"


def test_select_model_and_provider_id_first_from_list(mocker: MockerFixture) -> None:
    """Test the select_model_and_provider_id function when no model is specified."""
    model_list = [
        mocker.Mock(
            id="not_llm_type",
            custom_metadata={"model_type": "embedding", "provider_id": "provider1"},
        ),
        mocker.Mock(
            id="first_model",
            custom_metadata={"model_type": "llm", "provider_id": "provider1"},
        ),
        mocker.Mock(
            id="second_model",
            custom_metadata={"model_type": "llm", "provider_id": "provider2"},
        ),
    ]

    query_request = QueryRequest(query="What is OpenStack?")

    llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
        model_list, query_request.model, query_request.provider
    )

    # Assert return the first available LLM model when no model/provider is
    # specified in the request or in the configuration
    assert llama_stack_model_id == "first_model"
    assert model_id == "first_model"
    assert provider_id == "provider1"


def test_select_model_and_provider_id_invalid_model(mocker: MockerFixture) -> None:
    """Test the select_model_and_provider_id function with an invalid model."""
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
        mocker.Mock(
            id="model1",
            custom_metadata={"model_type": "llm", "provider_id": "provider1"},
        ),
    ]

    query_request = QueryRequest(
        query="What is OpenStack?", model="invalid_model", provider="provider1"
    )

    with pytest.raises(HTTPException) as exc_info:
        select_model_and_provider_id(
            mock_client.models.list(), query_request.model, query_request.provider
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Model not found"
    assert "invalid_model" in detail["cause"]


def test_select_model_and_provider_id_no_available_models(
    mocker: MockerFixture,
) -> None:
    """Test the select_model_and_provider_id function with no available models."""
    mock_client = mocker.Mock()
    # empty list of models
    mock_client.models.list.return_value = []

    query_request = QueryRequest(query="What is OpenStack?", model=None, provider=None)

    with pytest.raises(HTTPException) as exc_info:
        select_model_and_provider_id(
            mock_client.models.list(), query_request.model, query_request.provider
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Model not found"
    # The cause may vary, but should indicate no model found
    assert "Model" in detail["cause"]


def test_validate_attachments_metadata() -> None:
    """Test the validate_attachments_metadata function."""
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="this is attachment",
        ),
        Attachment(
            attachment_type="configuration",
            content_type="application/yaml",
            content="kind: Pod\n metadata:\n name:    private-reg",
        ),
    ]

    # If no exception is raised, the test passes
    validate_attachments_metadata(attachments)


def test_validate_attachments_metadata_invalid_type() -> None:
    """Test the validate_attachments_metadata function with invalid attachment type."""
    attachments = [
        Attachment(
            attachment_type="invalid_type",
            content_type="text/plain",
            content="this is attachment",
        ),
    ]

    with pytest.raises(HTTPException) as exc_info:
        validate_attachments_metadata(attachments)
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Invalid attribute value"
    assert "Invalid attatchment type invalid_type" in detail["cause"]


def test_validate_attachments_metadata_invalid_content_type() -> None:
    """Test the validate_attachments_metadata function with invalid attachment type."""
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/invalid_content_type",
            content="this is attachment",
        ),
    ]

    with pytest.raises(HTTPException) as exc_info:
        validate_attachments_metadata(attachments)
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Invalid attribute value"
    assert (
        "Invalid attatchment content type text/invalid_content_type" in detail["cause"]
    )


def test_no_tools_parameter_backward_compatibility() -> None:
    """Test that default behavior is unchanged when no_tools parameter is not specified."""
    # This test ensures that existing code that doesn't specify no_tools continues to work
    query_request = QueryRequest(query="What is OpenStack?")

    # Verify default value
    assert query_request.no_tools is False

    # Test that QueryRequest can be created without no_tools parameter
    query_request_minimal = QueryRequest(query="Simple query")
    assert query_request_minimal.no_tools is False


@pytest.mark.parametrize(
    "user_conversation,request_values,expected_values",
    [
        # No user conversation, no request values
        (
            None,
            (None, None),
            # Expect no values to be used
            (None, None),
        ),
        # No user conversation, request values provided
        (
            None,
            ("foo", "bar"),
            # Expect request values to be used
            ("foo", "bar"),
        ),
        # User conversation exists, no request values
        (
            UserConversation(
                id="conv1",
                user_id="user1",
                last_used_provider="foo",
                last_used_model="bar",
                message_count=1,
            ),
            (
                None,
                None,
            ),
            # Expect conversation values to be used
            (
                "foo",
                "bar",
            ),
        ),
        # Request matches user conversation
        (
            UserConversation(
                id="conv1",
                user_id="user1",
                last_used_provider="foo",
                last_used_model="bar",
                message_count=1,
            ),
            (
                "foo",
                "bar",
            ),
            # Expect request values to be used
            (
                "foo",
                "bar",
            ),
        ),
    ],
    ids=[
        "No user conversation, no request values",
        "No user conversation, request values provided",
        "User conversation exists, no request values",
        "Request matches user conversation",
    ],
)
def test_evaluate_model_hints(
    user_conversation: list,
    request_values: list,
    expected_values: list,
) -> None:
    """Test evaluate_model_hints function with various scenarios."""
    # Unpack fixtures
    request_provider, request_model = request_values
    expected_provider, expected_model = expected_values

    query_request = QueryRequest(
        query="What is love?",
        provider=request_provider,
        model=request_model,
    )  # pylint: disable=missing-kwoa

    model_id, provider_id = evaluate_model_hints(user_conversation, query_request)

    assert provider_id == expected_provider
    assert model_id == expected_model
