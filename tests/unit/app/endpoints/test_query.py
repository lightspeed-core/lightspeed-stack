"""Unit tests for the /query REST API endpoint."""

# pylint: disable=too-many-lines

import json
from fastapi import HTTPException, status
import pytest

from llama_stack_client import APIConnectionError
from llama_stack_client.types import UserMessage  # type: ignore

from configuration import AppConfig
from app.endpoints.query import (
    query_endpoint_handler,
    select_model_and_provider_id,
    retrieve_response,
    validate_attachments_metadata,
    is_transcripts_enabled,
    construct_transcripts_path,
    store_transcript,
    get_rag_toolgroups,
    get_agent,
    _agent_cache,
)

from models.requests import QueryRequest, Attachment
from models.config import ModelContextProtocolServer

MOCK_AUTH = ("mock_user_id", "mock_username", "mock_token")


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


@pytest.fixture(autouse=True, name="prepare_agent_mocks")
def prepare_agent_mocks_fixture(mocker):
    """Fixture that yields mock agent when called."""
    mock_client = mocker.Mock()
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.steps = []
    yield mock_client, mock_agent
    # cleanup agent cache after tests
    _agent_cache.clear()


def test_query_endpoint_handler_configuration_not_loaded(mocker):
    """Test the query endpoint handler if configuration is not loaded."""
    # simulate state when no configuration is loaded
    mocker.patch(
        "app.endpoints.query.configuration",
        return_value=mocker.Mock(),
    )
    mocker.patch("app.endpoints.query.configuration", None)

    request = None
    with pytest.raises(HTTPException) as e:
        query_endpoint_handler(request)
        assert e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Configuration is not loaded"


def test_is_transcripts_enabled(setup_configuration, mocker):
    """Test that is_transcripts_enabled returns True when transcripts is not disabled."""
    # Override the transcripts_enabled setting
    mocker.patch.object(
        setup_configuration.user_data_collection_configuration,
        "transcripts_enabled",
        True,
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    assert is_transcripts_enabled() is True, "Transcripts should be enabled"


def test_is_transcripts_disabled(setup_configuration, mocker):
    """Test that is_transcripts_enabled returns False when transcripts is disabled."""
    # Use default transcripts_enabled=False from setup
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    assert is_transcripts_enabled() is False, "Transcripts should be disabled"


def _test_query_endpoint_handler(mocker, store_transcript_to_file=False):
    """Test the query endpoint handler."""
    mock_metric = mocker.patch("metrics.llm_calls_total")
    mock_client = mocker.Mock()
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
    ]

    mock_config = mocker.Mock()
    mock_config.user_data_collection_configuration.transcripts_enabled = (
        store_transcript_to_file
    )
    mocker.patch("app.endpoints.query.configuration", mock_config)

    llm_response = "LLM answer"
    conversation_id = "fake_conversation_id"
    query = "What is OpenStack?"

    mocker.patch(
        "app.endpoints.query.retrieve_response",
        return_value=(llm_response, conversation_id),
    )
    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_provider_id"),
    )
    mocker.patch(
        "app.endpoints.query.is_transcripts_enabled",
        return_value=store_transcript_to_file,
    )
    mock_transcript = mocker.patch("app.endpoints.query.store_transcript")

    query_request = QueryRequest(query=query)

    response = query_endpoint_handler(query_request, auth=MOCK_AUTH)

    # Assert the response is as expected
    assert response.response == llm_response
    assert response.conversation_id == conversation_id

    # Assert the metric for successful LLM calls is incremented
    mock_metric.labels("fake_provider_id", "fake_model_id").inc.assert_called_once()

    # Assert the store_transcript function is called if transcripts are enabled
    if store_transcript_to_file:
        mock_transcript.assert_called_once_with(
            user_id="user_id_placeholder",
            conversation_id=conversation_id,
            query_is_valid=True,
            query=query,
            query_request=query_request,
            response=llm_response,
            attachments=[],
            rag_chunks=[],
            truncated=False,
        )
    else:
        mock_transcript.assert_not_called()


def test_query_endpoint_handler_transcript_storage_disabled(mocker):
    """Test the query endpoint handler with transcript storage disabled."""
    _test_query_endpoint_handler(mocker, store_transcript_to_file=False)


def test_query_endpoint_handler_store_transcript(mocker):
    """Test the query endpoint handler with transcript storage enabled."""
    _test_query_endpoint_handler(mocker, store_transcript_to_file=True)


def test_select_model_and_provider_id_from_request(mocker):
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
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
        mocker.Mock(
            identifier="default_model", model_type="llm", provider_id="default_provider"
        ),
    ]

    # Create a query request with model and provider specified
    query_request = QueryRequest(
        query="What is OpenStack?", model="model2", provider="provider2"
    )

    # Assert the model and provider from request take precedence from the configuration one
    model_id, provider_id = select_model_and_provider_id(model_list, query_request)

    assert model_id == "model2"
    assert provider_id == "provider2"


def test_select_model_and_provider_id_from_configuration(mocker):
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
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(
            identifier="default_model", model_type="llm", provider_id="default_provider"
        ),
    ]

    # Create a query request without model and provider specified
    query_request = QueryRequest(
        query="What is OpenStack?",
    )

    model_id, provider_id = select_model_and_provider_id(model_list, query_request)

    # Assert that the default model and provider from the configuration are returned
    assert model_id == "default_model"
    assert provider_id == "default_provider"


def test_select_model_and_provider_id_first_from_list(mocker):
    """Test the select_model_and_provider_id function when no model is specified."""
    model_list = [
        mocker.Mock(
            identifier="not_llm_type", model_type="embedding", provider_id="provider1"
        ),
        mocker.Mock(
            identifier="first_model", model_type="llm", provider_id="provider1"
        ),
        mocker.Mock(
            identifier="second_model", model_type="llm", provider_id="provider2"
        ),
    ]

    query_request = QueryRequest(query="What is OpenStack?")

    model_id, provider_id = select_model_and_provider_id(model_list, query_request)

    # Assert return the first available LLM model when no model/provider is
    # specified in the request or in the configuration
    assert model_id == "first_model"
    assert provider_id == "provider1"


def test_select_model_and_provider_id_invalid_model(mocker):
    """Test the select_model_and_provider_id function with an invalid model."""
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]

    query_request = QueryRequest(
        query="What is OpenStack?", model="invalid_model", provider="provider1"
    )

    with pytest.raises(HTTPException) as exc_info:
        select_model_and_provider_id(mock_client.models.list(), query_request)

    assert (
        "Model invalid_model from provider provider1 not found in available models"
        in str(exc_info.value)
    )


def test_select_model_and_provider_id_no_available_models(mocker):
    """Test the select_model_and_provider_id function with no available models."""
    mock_client = mocker.Mock()
    # empty list of models
    mock_client.models.list.return_value = []

    query_request = QueryRequest(query="What is OpenStack?", model=None, provider=None)

    with pytest.raises(HTTPException) as exc_info:
        select_model_and_provider_id(mock_client.models.list(), query_request)

    assert "No LLM model found in available models" in str(exc_info.value)


def test_validate_attachments_metadata():
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


def test_validate_attachments_metadata_invalid_type():
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
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert (
        "Attachment with improper type invalid_type detected"
        in exc_info.value.detail["cause"]
    )


def test_validate_attachments_metadata_invalid_content_type():
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
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert (
        "Attachment with improper content type text/invalid_content_type detected"
        in exc_info.value.detail["cause"]
    )


def test_retrieve_response_vector_db_available(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_metric = mocker.patch("metrics.llm_calls_validation_errors_total")
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    # Assert that the metric for validation errors is NOT incremented
    mock_metric.inc.assert_not_called()
    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


def test_retrieve_response_no_available_shields(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_one_available_shield(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""

    class MockShield:
        """Mock for Llama Stack shield to be used."""

        def __init__(self, identifier):
            self.identifier = identifier

        def __str__(self):
            return "MockShield"

        def __repr__(self):
            return "MockShield"

    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = [MockShield("shield1")]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_two_available_shields(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""

    class MockShield:
        """Mock for Llama Stack shield to be used."""

        def __init__(self, identifier):
            self.identifier = identifier

        def __str__(self):
            return "MockShield"

        def __repr__(self):
            return "MockShield"

    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = [
        MockShield("shield1"),
        MockShield("shield2"),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_four_available_shields(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""

    class MockShield:
        """Mock for Llama Stack shield to be used."""

        def __init__(self, identifier):
            self.identifier = identifier

        def __str__(self):
            return "MockShield"

        def __repr__(self):
            return "MockShield"

    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = [
        MockShield("shield1"),
        MockShield("input_shield2"),
        MockShield("output_shield3"),
        MockShield("inout_shield4"),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        ["shield1", "input_shield2", "inout_shield4"],  # available_input_shields
        ["output_shield3", "inout_shield4"],  # available_output_shields
        None,  # conversation_id
    )

    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_with_one_attachment(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)

    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="this is attachment",
        ),
    ]
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        stream=False,
        documents=[
            {
                "content": "this is attachment",
                "mime_type": "text/plain",
            },
        ],
        toolgroups=None,
    )


def test_retrieve_response_with_two_attachments(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)

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
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        stream=False,
        documents=[
            {
                "content": "this is attachment",
                "mime_type": "text/plain",
            },
            {
                "content": "kind: Pod\n" " metadata:\n" " name:    private-reg",
                "mime_type": "application/yaml",
            },
        ],
        toolgroups=None,
    )


def test_retrieve_response_with_mcp_servers(prepare_agent_mocks, mocker):
    """Test the retrieve_response function with MCP servers configured."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(
            name="filesystem-server", url="http://localhost:3000"
        ),
        ModelContextProtocolServer(
            name="git-server",
            provider_id="custom-git",
            url="https://git.example.com/mcp",
        ),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token_123"

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_input_shields
        [],  # available_output_shields
        None,  # conversation_id
    )

    # Check that the agent's extra_headers property was set correctly
    expected_extra_headers = {
        "X-LlamaStack-Provider-Data": json.dumps(
            {
                "mcp_headers": {
                    "http://localhost:3000": {"Authorization": "Bearer test_token_123"},
                    "https://git.example.com/mcp": {
                        "Authorization": "Bearer test_token_123"
                    },
                }
            }
        )
    }
    assert mock_agent.extra_headers == expected_extra_headers

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


def test_retrieve_response_with_mcp_servers_empty_token(prepare_agent_mocks, mocker):
    """Test the retrieve_response function with MCP servers and empty access token."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(name="test-server", url="http://localhost:8080"),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = ""  # Empty token

    response, conversation_id = retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_input_shields
        [],  # available_output_shields
        None,  # conversation_id
    )

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


def test_retrieve_response_with_mcp_servers_and_mcp_headers(
    prepare_agent_mocks, mocker
):
    """Test the retrieve_response function with MCP servers configured."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(
            name="filesystem-server", url="http://localhost:3000"
        ),
        ModelContextProtocolServer(
            name="git-server",
            provider_id="custom-git",
            url="https://git.example.com/mcp",
        ),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = ""
    mcp_headers = {
        "filesystem-server": {"Authorization": "Bearer test_token_123"},
        "git-server": {"Authorization": "Bearer test_token_456"},
        "http://another-server-mcp-server:3000": {
            "Authorization": "Bearer test_token_789"
        },
        "unknown-mcp-server": {
            "Authorization": "Bearer test_token_for_unknown-mcp-server"
        },
    }

    response, conversation_id = retrieve_response(
        mock_client,
        model_id,
        query_request,
        access_token,
        mcp_headers=mcp_headers,
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_session_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_input_shields
        [],  # available_output_shields
        None,  # conversation_id
    )

    expected_mcp_headers = {
        "http://localhost:3000": {"Authorization": "Bearer test_token_123"},
        "https://git.example.com/mcp": {"Authorization": "Bearer test_token_456"},
        "http://another-server-mcp-server:3000": {
            "Authorization": "Bearer test_token_789"
        },
        # we do not put "unknown-mcp-server" url as it's unknown to lightspeed-stack
    }

    # Check that the agent's extra_headers property was set correctly
    expected_extra_headers = {
        "X-LlamaStack-Provider-Data": json.dumps(
            {
                "mcp_headers": expected_mcp_headers,
            }
        )
    }

    assert mock_agent.extra_headers == expected_extra_headers

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


def test_retrieve_response_shield_violation(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_metric = mocker.patch("metrics.llm_calls_validation_errors_total")
    mock_client, mock_agent = prepare_agent_mocks
    # Mock the agent's create_turn method to return a response with a shield violation
    steps = [
        mocker.Mock(
            step_type="shield_call",
            violation=True,
        ),
    ]
    mock_agent.create_turn.return_value.steps = steps
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent", return_value=(mock_agent, "fake_session_id")
    )

    query_request = QueryRequest(query="What is OpenStack?")

    _, conversation_id = retrieve_response(
        mock_client, "fake_model_id", query_request, "test_token"
    )

    # Assert that the metric for validation errors is incremented
    mock_metric.inc.assert_called_once()

    assert conversation_id == "fake_session_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


def test_construct_transcripts_path(setup_configuration, mocker):
    """Test the construct_transcripts_path function."""
    # Update configuration for this test
    setup_configuration.user_data_collection_configuration.transcripts_storage = (
        "/tmp/transcripts"
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    user_id = "user123"
    conversation_id = "123e4567-e89b-12d3-a456-426614174000"

    path = construct_transcripts_path(user_id, conversation_id)

    assert (
        str(path) == "/tmp/transcripts/user123/123e4567-e89b-12d3-a456-426614174000"
    ), "Path should be constructed correctly"


def test_store_transcript(mocker):
    """Test the store_transcript function."""

    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch(
        "app.endpoints.query.construct_transcripts_path",
        return_value=mocker.MagicMock(),
    )

    # Mock the JSON to assert the data is stored correctly
    mock_json = mocker.patch("app.endpoints.query.json")

    # Mock parameters
    user_id = "user123"
    conversation_id = "123e4567-e89b-12d3-a456-426614174000"
    query = "What is OpenStack?"
    model = "fake-model"
    provider = "fake-provider"
    query_request = QueryRequest(query=query, model=model, provider=provider)
    response = "LLM answer"
    query_is_valid = True
    rag_chunks = []
    truncated = False
    attachments = []

    store_transcript(
        user_id,
        conversation_id,
        query_is_valid,
        query,
        query_request,
        response,
        rag_chunks,
        truncated,
        attachments,
    )

    # Assert that the transcript was stored correctly
    mock_json.dump.assert_called_once_with(
        {
            "metadata": {
                "provider": query_request.provider,
                "model": query_request.model,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "timestamp": mocker.ANY,
            },
            "redacted_query": query,
            "query_is_valid": query_is_valid,
            "llm_response": response,
            "rag_chunks": rag_chunks,
            "truncated": truncated,
            "attachments": attachments,
        },
        mocker.ANY,
    )


def test_get_rag_toolgroups():
    """Test get_rag_toolgroups function."""
    vector_db_ids = []
    result = get_rag_toolgroups(vector_db_ids)
    assert result is None

    vector_db_ids = ["Vector-DB-1", "Vector-DB-2"]
    result = get_rag_toolgroups(vector_db_ids)
    assert len(result) == 1
    assert result[0]["name"] == "builtin::rag/knowledge_search"
    assert result[0]["args"]["vector_db_ids"] == vector_db_ids


def test_query_endpoint_handler_on_connection_error(mocker):
    """Test the query endpoint handler."""
    mock_metric = mocker.patch("metrics.llm_calls_failures_total")

    mocker.patch(
        "app.endpoints.query.configuration",
        return_value=mocker.Mock(),
    )

    query_request = QueryRequest(query="What is OpenStack?")

    # simulate situation when it is not possible to connect to Llama Stack
    mock_get_client = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_get_client.side_effect = APIConnectionError(request=query_request)

    with pytest.raises(HTTPException) as exc_info:
        query_endpoint_handler(query_request, auth=MOCK_AUTH)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Unable to connect to Llama Stack" in str(exc_info.value.detail)
    mock_metric.inc.assert_called_once()


def test_get_agent_cache_hit(prepare_agent_mocks):
    """Test get_agent function when agent exists in cache."""
    mock_client, mock_agent = prepare_agent_mocks

    # Set up cache with existing agent
    conversation_id = "test_conversation_id"
    _agent_cache[conversation_id] = mock_agent

    result_agent, result_conversation_id = get_agent(
        client=mock_client,
        model_id="test_model",
        system_prompt="test_prompt",
        available_input_shields=["shield1"],
        available_output_shields=["output_shield2"],
        conversation_id=conversation_id,
    )

    # Assert cached agent is returned
    assert result_agent == mock_agent
    assert result_conversation_id == conversation_id


def test_get_agent_cache_miss_with_conversation_id(
    setup_configuration, prepare_agent_mocks, mocker
):
    """Test get_agent function when conversation_id is provided but agent not in cache."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_session.return_value = "new_session_id"

    # Mock Agent class
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    # Mock get_suid
    mocker.patch("app.endpoints.query.get_suid", return_value="new_session_id")

    # Mock configuration
    mock_mcp_server = mocker.Mock()
    mock_mcp_server.name = "mcp_server_1"
    mocker.patch.object(
        type(setup_configuration),
        "mcp_servers",
        new_callable=mocker.PropertyMock,
        return_value=[mock_mcp_server],
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Call function with conversation_id but no cached agent
    result_agent, result_conversation_id = get_agent(
        client=mock_client,
        model_id="test_model",
        system_prompt="test_prompt",
        available_input_shields=["shield1"],
        available_output_shields=["output_shield2"],
        conversation_id="non_existent_conversation_id",
    )

    # Assert new agent is created
    assert result_agent == mock_agent
    assert result_conversation_id == "new_session_id"

    # Verify Agent was created with correct parameters
    mock_agent_class.assert_called_once_with(
        mock_client,
        model="test_model",
        instructions="test_prompt",
        input_shields=["shield1"],
        output_shields=["output_shield2"],
        tool_parser=None,
        enable_session_persistence=True,
    )

    # Verify agent was stored in cache
    assert _agent_cache["new_session_id"] == mock_agent


def test_get_agent_no_conversation_id(setup_configuration, prepare_agent_mocks, mocker):
    """Test get_agent function when conversation_id is None."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_session.return_value = "new_session_id"

    # Mock Agent class
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    # Mock get_suid
    mocker.patch("app.endpoints.query.get_suid", return_value="new_session_id")

    # Mock configuration
    mock_mcp_server = mocker.Mock()
    mock_mcp_server.name = "mcp_server_1"
    mocker.patch.object(
        type(setup_configuration),
        "mcp_servers",
        new_callable=mocker.PropertyMock,
        return_value=[mock_mcp_server],
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Call function with None conversation_id
    result_agent, result_conversation_id = get_agent(
        client=mock_client,
        model_id="test_model",
        system_prompt="test_prompt",
        available_input_shields=["shield1"],
        available_output_shields=["output_shield2"],
        conversation_id=None,
    )

    # Assert new agent is created
    assert result_agent == mock_agent
    assert result_conversation_id == "new_session_id"

    # Verify Agent was created with correct parameters
    mock_agent_class.assert_called_once_with(
        mock_client,
        model="test_model",
        instructions="test_prompt",
        input_shields=["shield1"],
        output_shields=["output_shield2"],
        tool_parser=None,
        enable_session_persistence=True,
    )

    # Verify agent was stored in cache
    assert _agent_cache["new_session_id"] == mock_agent


def test_get_agent_empty_shields(setup_configuration, prepare_agent_mocks, mocker):
    """Test get_agent function with empty shields list."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_session.return_value = "new_session_id"

    # Mock Agent class
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    # Mock get_suid
    mocker.patch("app.endpoints.query.get_suid", return_value="new_session_id")

    # Mock configuration
    mock_mcp_server = mocker.Mock()
    mock_mcp_server.name = "mcp_server_1"
    mocker.patch.object(
        type(setup_configuration),
        "mcp_servers",
        new_callable=mocker.PropertyMock,
        return_value=[mock_mcp_server],
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Call function with empty shields list
    result_agent, result_conversation_id = get_agent(
        client=mock_client,
        model_id="test_model",
        system_prompt="test_prompt",
        available_input_shields=[],
        available_output_shields=[],
        conversation_id=None,
    )

    # Assert new agent is created
    assert result_agent == mock_agent
    assert result_conversation_id == "new_session_id"

    # Verify Agent was created with empty shields
    mock_agent_class.assert_called_once_with(
        mock_client,
        model="test_model",
        instructions="test_prompt",
        input_shields=[],
        output_shields=[],
        tool_parser=None,
        enable_session_persistence=True,
    )


def test_get_agent_multiple_mcp_servers(
    setup_configuration, prepare_agent_mocks, mocker
):
    """Test get_agent function with multiple MCP servers."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_session.return_value = "new_session_id"

    # Mock Agent class
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    # Mock get_suid
    mocker.patch("app.endpoints.query.get_suid", return_value="new_session_id")

    # Mock configuration with multiple MCP servers
    mock_mcp_server1 = mocker.Mock()
    mock_mcp_server1.name = "mcp_server_1"
    mock_mcp_server2 = mocker.Mock()
    mock_mcp_server2.name = "mcp_server_2"
    mocker.patch.object(
        type(setup_configuration),
        "mcp_servers",
        new_callable=mocker.PropertyMock,
        return_value=[mock_mcp_server1, mock_mcp_server2],
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Call function
    result_agent, result_conversation_id = get_agent(
        client=mock_client,
        model_id="test_model",
        system_prompt="test_prompt",
        available_input_shields=["shield1", "shield2"],
        available_output_shields=["output_shield3", "output_shield4"],
        conversation_id=None,
    )

    # Assert new agent is created
    assert result_agent == mock_agent
    assert result_conversation_id == "new_session_id"

    # Verify Agent was created with tools from both MCP servers
    mock_agent_class.assert_called_once_with(
        mock_client,
        model="test_model",
        instructions="test_prompt",
        input_shields=["shield1", "shield2"],
        output_shields=["output_shield3", "output_shield4"],
        tool_parser=None,
        enable_session_persistence=True,
    )


def test_get_agent_session_persistence_enabled(
    setup_configuration, prepare_agent_mocks, mocker
):
    """Test get_agent function ensures session persistence is enabled."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_session.return_value = "new_session_id"

    # Mock Agent class
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    # Mock get_suid
    mocker.patch("app.endpoints.query.get_suid", return_value="new_session_id")

    # Mock configuration
    mock_mcp_server = mocker.Mock()
    mock_mcp_server.name = "mcp_server_1"
    mocker.patch.object(
        type(setup_configuration),
        "mcp_servers",
        new_callable=mocker.PropertyMock,
        return_value=[mock_mcp_server],
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Call function
    get_agent(
        client=mock_client,
        model_id="test_model",
        system_prompt="test_prompt",
        available_input_shields=["shield1"],
        available_output_shields=["output_shield2"],
        conversation_id=None,
    )

    # Verify Agent was created with session persistence enabled
    mock_agent_class.assert_called_once_with(
        mock_client,
        model="test_model",
        instructions="test_prompt",
        input_shields=["shield1"],
        output_shields=["output_shield2"],
        tool_parser=None,
        enable_session_persistence=True,
    )


def test_auth_tuple_unpacking_in_query_endpoint_handler(mocker):
    """Test that auth tuple is correctly unpacked in query endpoint handler."""
    # Mock dependencies
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mocker.patch("app.endpoints.query.configuration", mock_config)

    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1")
    ]
    mocker.patch("client.LlamaStackClientHolder.get_client", return_value=mock_client)

    mock_retrieve_response = mocker.patch(
        "app.endpoints.query.retrieve_response",
        return_value=("test response", "test_conversation_id"),
    )

    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("test_model", "test_provider"),
    )
    mocker.patch("app.endpoints.query.is_transcripts_enabled", return_value=False)

    _ = query_endpoint_handler(
        QueryRequest(query="test query"),
        auth=("user123", "username", "auth_token_123"),
        mcp_headers=None,
    )

    assert mock_retrieve_response.call_args[0][3] == "auth_token_123"
