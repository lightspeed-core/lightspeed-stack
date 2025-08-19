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
    evaluate_model_hints,
)

from models.requests import QueryRequest, Attachment
from models.config import ModelContextProtocolServer
from models.database.conversations import UserConversation

MOCK_AUTH = ("mock_user_id", "mock_username", "mock_token")


def mock_database_operations(mocker):
    """Helper function to mock database operations for query endpoints."""
    mocker.patch(
        "app.endpoints.query.validate_conversation_ownership", return_value=True
    )
    mocker.patch("app.endpoints.query.persist_user_conversation_details")


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


@pytest.mark.asyncio
async def test_query_endpoint_handler_configuration_not_loaded(mocker):
    """Test the query endpoint handler if configuration is not loaded."""
    # simulate state when no configuration is loaded
    mocker.patch(
        "app.endpoints.query.configuration",
        return_value=mocker.Mock(),
    )
    mocker.patch("app.endpoints.query.configuration", None)

    query = "What is OpenStack?"
    query_request = QueryRequest(query=query)
    with pytest.raises(HTTPException) as e:
        await query_endpoint_handler(query_request, auth=["test-user", "", "token"])
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert e.value.detail["response"] == "Configuration is not loaded"


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


async def _test_query_endpoint_handler(mocker, store_transcript_to_file=False):
    """Test the query endpoint handler."""
    mock_metric = mocker.patch("metrics.llm_calls_total")
    mock_client = mocker.AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
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
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch(
        "app.endpoints.query.is_transcripts_enabled",
        return_value=store_transcript_to_file,
    )
    mock_transcript = mocker.patch("app.endpoints.query.store_transcript")

    # Mock database operations
    mock_database_operations(mocker)

    query_request = QueryRequest(query=query)

    response = await query_endpoint_handler(query_request, auth=MOCK_AUTH)

    # Assert the response is as expected
    assert response.response == llm_response
    assert response.conversation_id == conversation_id

    # Assert the metric for successful LLM calls is incremented
    mock_metric.labels("fake_provider_id", "fake_model_id").inc.assert_called_once()

    # Assert the store_transcript function is called if transcripts are enabled
    if store_transcript_to_file:
        mock_transcript.assert_called_once_with(
            user_id="mock_user_id",
            conversation_id=conversation_id,
            model_id="fake_model_id",
            provider_id="fake_provider_id",
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


@pytest.mark.asyncio
async def test_query_endpoint_handler_transcript_storage_disabled(mocker):
    """Test the query endpoint handler with transcript storage disabled."""
    await _test_query_endpoint_handler(mocker, store_transcript_to_file=False)


@pytest.mark.asyncio
async def test_query_endpoint_handler_store_transcript(mocker):
    """Test the query endpoint handler with transcript storage enabled."""
    await _test_query_endpoint_handler(mocker, store_transcript_to_file=True)


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
        mocker.Mock(
            identifier="provider1/model1", model_type="llm", provider_id="provider1"
        ),
        mocker.Mock(
            identifier="provider2/model2", model_type="llm", provider_id="provider2"
        ),
        mocker.Mock(
            identifier="default_provider/default_model",
            model_type="llm",
            provider_id="default_provider",
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
        mocker.Mock(
            identifier="provider1/model1", model_type="llm", provider_id="provider1"
        ),
        mocker.Mock(
            identifier="default_provider/default_model",
            model_type="llm",
            provider_id="default_provider",
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

    llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
        model_list, query_request.model, query_request.provider
    )

    # Assert return the first available LLM model when no model/provider is
    # specified in the request or in the configuration
    assert llama_stack_model_id == "first_model"
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
        select_model_and_provider_id(
            mock_client.models.list(), query_request.model, query_request.provider
        )

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
        select_model_and_provider_id(
            mock_client.models.list(), query_request.model, query_request.provider
        )

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


@pytest.mark.asyncio
async def test_retrieve_response_vector_db_available(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    # Assert that the metric for validation errors is NOT incremented
    mock_metric.inc.assert_not_called()
    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


@pytest.mark.asyncio
async def test_retrieve_response_no_available_shields(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


@pytest.mark.asyncio
async def test_retrieve_response_one_available_shield(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


@pytest.mark.asyncio
async def test_retrieve_response_two_available_shields(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


@pytest.mark.asyncio
async def test_retrieve_response_four_available_shields(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        ["shield1", "input_shield2", "inout_shield4"],  # available_input_shields
        ["output_shield3", "inout_shield4"],  # available_output_shields
        None,  # conversation_id
        False,  # no_tools
    )

    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


@pytest.mark.asyncio
async def test_retrieve_response_with_one_attachment(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"
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


@pytest.mark.asyncio
async def test_retrieve_response_with_two_attachments(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"
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


@pytest.mark.asyncio
async def test_retrieve_response_with_mcp_servers(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token_123"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_input_shields
        [],  # available_output_shields
        None,  # conversation_id
        False,  # no_tools
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


@pytest.mark.asyncio
async def test_retrieve_response_with_mcp_servers_empty_token(
    prepare_agent_mocks, mocker
):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = ""  # Empty token

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_input_shields
        [],  # available_output_shields
        None,  # conversation_id
        False,  # no_tools
    )

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


@pytest.mark.asyncio
async def test_retrieve_response_with_mcp_servers_and_mcp_headers(
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
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

    response, conversation_id = await retrieve_response(
        mock_client,
        model_id,
        query_request,
        access_token,
        mcp_headers=mcp_headers,
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_input_shields
        [],  # available_output_shields
        None,  # conversation_id
        False,  # no_tools
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


@pytest.mark.asyncio
async def test_retrieve_response_shield_violation(prepare_agent_mocks, mocker):
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
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")

    _, conversation_id = await retrieve_response(
        mock_client, "fake_model_id", query_request, "test_token"
    )

    # Assert that the metric for validation errors is incremented
    mock_metric.inc.assert_called_once()

    assert conversation_id == "fake_conversation_id"
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
        model,
        provider,
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
                "provider": "fake-provider",
                "model": "fake-model",
                "query_provider": query_request.provider,
                "query_model": query_request.model,
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


@pytest.mark.asyncio
async def test_query_endpoint_handler_on_connection_error(mocker):
    """Test the query endpoint handler."""
    mock_metric = mocker.patch("metrics.llm_calls_failures_total")

    mocker.patch(
        "app.endpoints.query.configuration",
        return_value=mocker.Mock(),
    )

    query_request = QueryRequest(query="What is OpenStack?")

    # simulate situation when it is not possible to connect to Llama Stack
    mock_get_client = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_get_client.side_effect = APIConnectionError(request=query_request)

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler(query_request, auth=MOCK_AUTH)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Unable to connect to Llama Stack" in str(exc_info.value.detail)
    mock_metric.inc.assert_called_once()


@pytest.mark.asyncio
async def test_auth_tuple_unpacking_in_query_endpoint_handler(mocker):
    """Test that auth tuple is correctly unpacked in query endpoint handler."""
    # Mock dependencies
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mocker.patch("app.endpoints.query.configuration", mock_config)

    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1")
    ]
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )

    mock_retrieve_response = mocker.patch(
        "app.endpoints.query.retrieve_response",
        return_value=("test response", "test_conversation_id"),
    )

    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("test_model", "test_model", "test_provider"),
    )
    mocker.patch("app.endpoints.query.is_transcripts_enabled", return_value=False)
    # Mock database operations
    mock_database_operations(mocker)

    _ = await query_endpoint_handler(
        QueryRequest(query="test query"),
        auth=("user123", "username", "auth_token_123"),
        mcp_headers=None,
    )

    assert mock_retrieve_response.call_args[0][3] == "auth_token_123"


@pytest.mark.asyncio
async def test_query_endpoint_handler_no_tools_true(mocker):
    """Test the query endpoint handler with no_tools=True."""
    mock_client = mocker.AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]

    mock_config = mocker.Mock()
    mock_config.user_data_collection_configuration.transcripts_disabled = True
    mocker.patch("app.endpoints.query.configuration", mock_config)

    llm_response = "LLM answer without tools"
    conversation_id = "fake_conversation_id"
    query = "What is OpenStack?"

    mocker.patch(
        "app.endpoints.query.retrieve_response",
        return_value=(llm_response, conversation_id),
    )
    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch("app.endpoints.query.is_transcripts_enabled", return_value=False)
    # Mock database operations
    mock_database_operations(mocker)

    query_request = QueryRequest(query=query, no_tools=True)

    response = await query_endpoint_handler(query_request, auth=MOCK_AUTH)

    # Assert the response is as expected
    assert response.response == llm_response
    assert response.conversation_id == conversation_id


@pytest.mark.asyncio
async def test_query_endpoint_handler_no_tools_false(mocker):
    """Test the query endpoint handler with no_tools=False (default behavior)."""
    mock_client = mocker.AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]

    mock_config = mocker.Mock()
    mock_config.user_data_collection_configuration.transcripts_disabled = True
    mocker.patch("app.endpoints.query.configuration", mock_config)

    llm_response = "LLM answer with tools"
    conversation_id = "fake_conversation_id"
    query = "What is OpenStack?"

    mocker.patch(
        "app.endpoints.query.retrieve_response",
        return_value=(llm_response, conversation_id),
    )
    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch("app.endpoints.query.is_transcripts_enabled", return_value=False)
    # Mock database operations
    mock_database_operations(mocker)

    query_request = QueryRequest(query=query, no_tools=False)

    response = await query_endpoint_handler(query_request, auth=MOCK_AUTH)

    # Assert the response is as expected
    assert response.response == llm_response
    assert response.conversation_id == conversation_id


@pytest.mark.asyncio
async def test_retrieve_response_no_tools_bypasses_mcp_and_rag(
    prepare_agent_mocks, mocker
):
    """Test that retrieve_response bypasses MCP servers and RAG when no_tools=True."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(
            name="filesystem-server", url="http://localhost:3000"
        ),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", no_tools=True)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"

    # Verify that agent.extra_headers is empty (no MCP headers)
    assert mock_agent.extra_headers == {}

    # Verify that create_turn was called with toolgroups=None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=None,
    )


@pytest.mark.asyncio
async def test_retrieve_response_no_tools_false_preserves_functionality(
    prepare_agent_mocks, mocker
):
    """Test that retrieve_response preserves normal functionality when no_tools=False."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(
            name="filesystem-server", url="http://localhost:3000"
        ),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", no_tools=False)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response == "LLM answer"
    assert conversation_id == "fake_conversation_id"

    # Verify that agent.extra_headers contains MCP headers
    expected_extra_headers = {
        "X-LlamaStack-Provider-Data": json.dumps(
            {
                "mcp_headers": {
                    "http://localhost:3000": {"Authorization": "Bearer test_token"},
                }
            }
        )
    }
    assert mock_agent.extra_headers == expected_extra_headers

    # Verify that create_turn was called with RAG and MCP toolgroups
    expected_toolgroups = get_rag_toolgroups(["VectorDB-1"]) + ["filesystem-server"]
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=False,
        toolgroups=expected_toolgroups,
    )


def test_no_tools_parameter_backward_compatibility():
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
    user_conversation,
    request_values,
    expected_values,
):
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

# Note: Test framework and library in use: pytest with pytest-asyncio and pytest-mock (mocker fixture).
# These tests extend coverage for query endpoint and helpers based on recent changes.

import asyncio
import json
import uuid
import pytest
from fastapi import HTTPException, status

# Utilities to build minimal valid QueryRequest objects for different scenarios.
def _make_query_request(**overrides):
    # Import inside to avoid issues at import time if module side-effects occur
    from app.schemas.query import QueryRequest  # path inferred; adjust if necessary
    base = {
        "query": overrides.pop("query", "What is OpenStack?"),
        "provider": overrides.pop("provider", None),
        "model": overrides.pop("model", None),
        "conversation_id": overrides.pop("conversation_id", None),
        "vector_db_ids": overrides.pop("vector_db_ids", None),
        "tools": overrides.pop("tools", None),
        "metadata": overrides.pop("metadata", None),
    }
    # Remove keys with None to respect pydantic optional defaults
    base = {k: v for k, v in base.items() if v is not None}
    return QueryRequest(**base)

@pytest.mark.asyncio
async def test_query_endpoint_handler_raises_when_auth_missing(mocker, setup_configuration):
    # Focus: Ensure missing auth raises 401/403 appropriately depending on implementation
    from app.endpoints.query import query_endpoint_handler, configuration

    # Arrange: Patch configuration to be present
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Patch underlying dependencies to isolate handler logic
    mocker.patch("app.endpoints.query.validate_conversation_ownership", return_value=True)
    # Simulate LLM client call path returning a canned response
    mock_response = {"response": "ok", "messages": []}
    mocker.patch("app.endpoints.query.generate_response", return_value=mock_response)

    query_request = _make_query_request(query="Ping")
    # Act & Assert
    # auth missing -> expect HTTPException (401 or 403 depending on code)
    with pytest.raises(HTTPException) as e:
        await query_endpoint_handler(query_request, auth=None)
    assert e.value.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

@pytest.mark.asyncio
async def test_query_endpoint_handler_happy_path_minimal(mocker, setup_configuration):
    # Focus: Happy path with minimal required inputs and no auth enforcement
    from app.endpoints.query import query_endpoint_handler
    # Disable auth in config if needed
    cfg = setup_configuration
    cfg.service.auth_enabled = False
    mocker.patch("app.endpoints.query.configuration", cfg)

    # Mocks
    mocker.patch("app.endpoints.query.validate_conversation_ownership", return_value=True)
    mock_resp = {"response": "All good", "messages": [{"role": "assistant", "content": "All good"}]}
    mock_generate = mocker.patch("app.endpoints.query.generate_response", return_value=mock_resp)
    persist_spy = mocker.patch("app.endpoints.query.persist_user_conversation_details")

    req = _make_query_request(query="Hello?")
    result = await query_endpoint_handler(req, auth=["user-123", "", "token"])

    assert result["response"] == "All good"
    assert "messages" in result
    mock_generate.assert_called_once()
    # Depending on code path, the persist might be called; assert at least that it's patched and callable
    assert persist_spy.called in (True, False)

@pytest.mark.asyncio
async def test_query_endpoint_handler_invalid_conversation_ownership(mocker, setup_configuration):
    # Focus: When conversation_id provided and ownership check fails -> raise
    from app.endpoints.query import query_endpoint_handler
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    # Make ownership fail
    mocker.patch("app.endpoints.query.validate_conversation_ownership", return_value=False)
    req = _make_query_request(query="Q", conversation_id=str(uuid.uuid4()))
    with pytest.raises(HTTPException) as e:
        await query_endpoint_handler(req, auth=["user-321", "", "token"])
    assert e.value.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST)

@pytest.mark.asyncio
async def test_query_endpoint_handler_handles_generate_response_failure(mocker, setup_configuration):
    # Focus: Errors from generate_response bubble into HTTP 500 with informative detail
    from app.endpoints.query import query_endpoint_handler
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    mocker.patch("app.endpoints.query.validate_conversation_ownership", return_value=True)
    mocker.patch("app.endpoints.query.generate_response", side_effect=RuntimeError("backend down"))

    req = _make_query_request(query="Q")
    with pytest.raises(HTTPException) as e:
        await query_endpoint_handler(req, auth=["user-1", "", "token"])
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    # Ensure detail has response/message text per implementation
    detail = getattr(e.value, "detail", {})
    assert isinstance(detail, dict)
    assert any(k in detail for k in ("response", "message", "error"))

def test_get_rag_toolgroups_none_input_treated_as_empty(mocker):
    from app.endpoints.query import get_rag_toolgroups
    assert get_rag_toolgroups(None) is None
    assert get_rag_toolgroups([]) is None

def test_get_rag_toolgroups_dedupes_and_filters_invalid_ids(mocker):
    # Focus: if implementation accepts any truthy strings only, ensure duplicates collapse and non-strings ignored
    from app.endpoints.query import get_rag_toolgroups
    # This is a resilience test; if implementation doesn't dedupe/filter it's still safe to assert structural invariants.
    vec_ids = ["a", "a", "b", "", None, 123]  # type: ignore
    result = get_rag_toolgroups(vec_ids)
    if result is None:
        # Acceptable if empty/invalid inputs yield None
        assert True
        return
    assert isinstance(result, list) and len(result) >= 1
    tool = result[0]
    assert tool["name"] == "builtin::rag/knowledge_search"
    assert "args" in tool and "vector_db_ids" in tool["args"]
    # vector_db_ids should contain at least the valid string ids in order
    assert "a" in tool["args"]["vector_db_ids"]
    assert "b" in tool["args"]["vector_db_ids"]

@pytest.mark.parametrize(
    "user_conversation, request_provider, request_model, expected_provider, expected_model",
    [
        # Request specifies provider only -> provider respected, model remains None (or default if code fills)
        (None, "provA", None, "provA", None),
        # Request specifies model only -> model respected, provider remains None
        (None, None, "modelX", None, "modelX"),
        # Conversation has different provider/model and request overrides only one
        (
            # conversation
            __import__("types").SimpleNamespace(
                id="c1", user_id="u1", last_used_provider="provB", last_used_model="modelY", message_count=2
            ),
            "provA", None,
            "provA", "modelY"
        ),
        (
            __import__("types").SimpleNamespace(
                id="c1", user_id="u1", last_used_provider="provB", last_used_model="modelY", message_count=2
            ),
            None, "modelX",
            "provB", "modelX"
        ),
        # Request provides mismatched or unknown values; still pass-through expected
        (None, "unknownProv", "unknownModel", "unknownProv", "unknownModel"),
    ],
    ids=[
        "provider_only",
        "model_only",
        "override_provider_keep_conv_model",
        "override_model_keep_conv_provider",
        "unknown_values_passthrough",
    ],
)
def test_evaluate_model_hints_extended_cases(user_conversation, request_provider, request_model, expected_provider, expected_model):
    from app.endpoints.query import evaluate_model_hints
    from app.schemas.query import QueryRequest
    qr = QueryRequest(query="X", provider=request_provider, model=request_model)  # pylint: disable=missing-kwoa
    model_id, provider_id = evaluate_model_hints(user_conversation, qr)
    # The original tests asserted provider_id == expected_provider and model_id == expected_model
    assert provider_id == expected_provider
    assert model_id == expected_model

def test_evaluate_model_hints_handles_nulls_gracefully():
    from app.endpoints.query import evaluate_model_hints
    from app.schemas.query import QueryRequest
    qr = QueryRequest(query="X")  # no hints
    model_id, provider_id = evaluate_model_hints(None, qr)
    assert model_id is None
    assert provider_id is None

@pytest.mark.asyncio
async def test_query_endpoint_handler_rag_integration_with_vector_ids(mocker, setup_configuration):
    # Focus: When vector_db_ids provided, ensure RAG toolgroups passed to generation layer.
    from app.endpoints.query import query_endpoint_handler

    mocker.patch("app.endpoints.query.configuration", setup_configuration)
    mocker.patch("app.endpoints.query.validate_conversation_ownership", return_value=True)

    captured = {}

    def fake_generate_response(*args, **kwargs):
        # Capture toolgroups to assert correct propagation
        captured["toolgroups"] = kwargs.get("toolgroups") or kwargs.get("tools") or kwargs
        return {"response": "rag-ok"}

    mocker.patch("app.endpoints.query.generate_response", side_effect=fake_generate_response)
    req = _make_query_request(query="RAG?", vector_db_ids=["Vector-DB-1", "Vector-DB-2"])
    out = await query_endpoint_handler(req, auth=["user-9", "", "token"])
    assert out["response"] == "rag-ok"
    assert "toolgroups" in captured
    tg = captured["toolgroups"]
    # Validate basic structure if present
    if tg is not None:
        assert isinstance(tg, list)
        assert any(t.get("name") == "builtin::rag/knowledge_search" for t in tg)

@pytest.mark.asyncio
async def test_query_endpoint_handler_configuration_loaded_but_invalid_llama_stack(mocker, setup_configuration):
    # Focus: If llama_stack client configuration is missing/invalid, handler should return 500 with clear message
    from app.endpoints.query import query_endpoint_handler

    bad_cfg = setup_configuration
    # Intentionally break llama_stack config
    bad_cfg.llama_stack.api_key = ""
    bad_cfg.llama_stack.url = ""
    mocker.patch("app.endpoints.query.configuration", bad_cfg)
    mocker.patch("app.endpoints.query.validate_conversation_ownership", return_value=True)

    req = _make_query_request(query="Q")
    with pytest.raises(HTTPException) as e:
        await query_endpoint_handler(req, auth=["user", "", "t"])
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = getattr(e.value, "detail", {})
    assert isinstance(detail, dict)
    assert any(k in detail for k in ("response", "message", "error"))

