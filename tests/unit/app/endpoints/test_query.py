import json
from fastapi import HTTPException, status
import pytest

from configuration import AppConfig
from app.endpoints.query import (
    query_endpoint_handler,
    select_model_id,
    retrieve_response,
    retrieve_conversation_id,
    validate_attachments_metadata,
    is_transcripts_enabled,
    construct_transcripts_path,
    store_transcript,
    get_rag_toolgroups,
)
from models.requests import QueryRequest, Attachment
from models.config import ModelContextProtocolServer
from llama_stack_client.types import UserMessage  # type: ignore


@pytest.fixture
def setup_configuration():
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
            "transcripts_disabled": True,
        },
        "mcp_servers": [],
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


def test_is_transcripts_enabled(setup_configuration, mocker):
    """Test that is_transcripts_enabled returns True when transcripts is not disabled."""
    # Override the transcripts_disabled setting
    mocker.patch.object(
        setup_configuration.user_data_collection_configuration,
        "transcripts_disabled",
        False,
    )
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    assert is_transcripts_enabled() is True, "Transcripts should be enabled"


def test_is_transcripts_disabled(setup_configuration, mocker):
    """Test that is_transcripts_enabled returns False when transcripts is disabled."""
    # Use default transcripts_disabled=True from setup
    mocker.patch("app.endpoints.query.configuration", setup_configuration)

    assert is_transcripts_enabled() is False, "Transcripts should be disabled"


def test_retrieve_conversation_id():
    """Test the retrieve_conversation_id function."""
    query_request = QueryRequest(query="What is OpenStack?", conversation_id=None)
    conversation_id = retrieve_conversation_id(query_request)

    assert conversation_id is not None, "Conversation ID should be generated"
    assert len(conversation_id) > 0, "Conversation ID should not be empty"


def test_retrieve_conversation_id_existing():
    # Test with an existing conversation ID
    existing_conversation_id = "123e4567-e89b-12d3-a456-426614174000"
    query_request = QueryRequest(
        query="What is OpenStack?", conversation_id=existing_conversation_id
    )

    conversation_id = retrieve_conversation_id(query_request)

    assert (
        conversation_id == existing_conversation_id
    ), "Should return the existing conversation ID"


def _test_query_endpoint_handler(mocker, store_transcript=False):
    """Test the query endpoint handler."""
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
    ]

    mocker.patch(
        "app.endpoints.query.configuration",
        return_value=mocker.Mock(),
    )
    llm_response = "LLM answer"
    query = "What is OpenStack?"
    mocker.patch("app.endpoints.query.get_llama_stack_client", return_value=mock_client)
    mocker.patch("app.endpoints.query.retrieve_response", return_value=llm_response)
    mocker.patch("app.endpoints.query.select_model_id", return_value="fake_model_id")
    mocker.patch(
        "app.endpoints.query.is_transcripts_enabled", return_value=store_transcript
    )
    mock_transcript = mocker.patch("app.endpoints.query.store_transcript")

    query_request = QueryRequest(query=query)

    response = query_endpoint_handler(query_request)

    # Assert the response is as expected
    assert response.response == "LLM answer"

    # Assert the store_transcript function is called if transcripts are enabled
    if store_transcript:
        mock_transcript.assert_called_once_with(
            user_id="user_id_placeholder",
            conversation_id=mocker.ANY,
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


def test_query_endpoint_handler(mocker):
    """Test the query endpoint handler with transcript storage disabled."""
    _test_query_endpoint_handler(mocker, store_transcript=False)


def test_query_endpoint_handler_store_transcript(mocker):
    """Test the query endpoint handler with transcript storage enabled."""
    _test_query_endpoint_handler(mocker, store_transcript=True)


def test_select_model_id(mocker):
    """Test the select_model_id function."""
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
    ]

    query_request = QueryRequest(
        query="What is OpenStack?", model="model1", provider="provider1"
    )

    model_id = select_model_id(mock_client.models.list(), query_request)

    assert model_id == "model1"


def test_select_model_id_no_model(mocker):
    """Test the select_model_id function when no model is specified."""
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
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

    model_id = select_model_id(mock_client.models.list(), query_request)

    # Assert return the first available LLM model
    assert model_id == "first_model"


def test_select_model_id_invalid_model(mocker):
    """Test the select_model_id function with an invalid model."""
    mock_client = mocker.Mock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]

    query_request = QueryRequest(
        query="What is OpenStack?", model="invalid_model", provider="provider1"
    )

    with pytest.raises(Exception) as exc_info:
        select_model_id(mock_client.models.list(), query_request)

    assert (
        "Model invalid_model from provider provider1 not found in available models"
        in str(exc_info.value)
    )


def test_no_available_models(mocker):
    """Test the select_model_id function with an invalid model."""
    mock_client = mocker.Mock()
    # empty list of models
    mock_client.models.list.return_value = []

    query_request = QueryRequest(query="What is OpenStack?", model=None, provider=None)

    with pytest.raises(Exception) as exc_info:
        select_model_id(mock_client.models.list(), query_request)

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


def test_retrieve_response_vector_db_available(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch("app.endpoints.query.Agent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        documents=[],
        stream=False,
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


def test_retrieve_response_no_available_shields(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch("app.endpoints.query.Agent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_one_available_shield(mocker):
    """Test the retrieve_response function."""

    class MockShield:
        def __init__(self, identifier):
            self.identifier = identifier

        def identifier(self):
            return self.identifier

    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
    mock_client.shields.list.return_value = [MockShield("shield1")]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch("app.endpoints.query.Agent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_two_available_shields(mocker):
    """Test the retrieve_response function."""

    class MockShield:
        def __init__(self, identifier):
            self.identifier = identifier

        def identifier(self):
            return self.identifier

    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
    mock_client.shields.list.return_value = [
        MockShield("shield1"),
        MockShield("shield2"),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mocker.patch("app.endpoints.query.Agent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        documents=[],
        stream=False,
        toolgroups=None,
    )


def test_retrieve_response_with_one_attachment(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
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
    mocker.patch("app.endpoints.query.Agent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    access_token = "test_token"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        stream=False,
        documents=[
            {
                "content": "this is attachment",
                "mime_type": "text/plain",
            },
        ],
        toolgroups=None,
    )


def test_retrieve_response_with_two_attachments(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
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
    mocker.patch("app.endpoints.query.Agent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    access_token = "test_token"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
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


def test_retrieve_response_with_mcp_servers(mocker):
    """Test the retrieve_response function with MCP servers configured."""
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
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
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token_123"

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"

    # Verify Agent was created with MCP server tools and headers
    mock_agent_class.assert_called_once()
    agent_kwargs = mock_agent_class.call_args[1]

    # Check that tools include MCP server names
    assert "filesystem-server" in agent_kwargs["tools"]
    assert "git-server" in agent_kwargs["tools"]

    # Check that extra_headers contains MCP headers with authorization

    extra_headers_data = json.loads(
        agent_kwargs["extra_headers"]["X-LlamaStack-Provider-Data"]
    )
    mcp_headers = extra_headers_data["mcp_headers"]

    assert "http://localhost:3000" in mcp_headers
    assert (
        mcp_headers["http://localhost:3000"]["Authorization"] == "Bearer test_token_123"
    )
    assert "https://git.example.com/mcp" in mcp_headers
    assert (
        mcp_headers["https://git.example.com/mcp"]["Authorization"]
        == "Bearer test_token_123"
    )


def test_retrieve_response_with_mcp_servers_empty_token(mocker):
    """Test the retrieve_response function with MCP servers and empty access token."""
    mock_agent = mocker.Mock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.Mock()
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(name="test-server", url="http://localhost:8080"),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.query.configuration", mock_config)
    mock_agent_class = mocker.patch(
        "app.endpoints.query.Agent", return_value=mock_agent
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = ""  # Empty token

    response = retrieve_response(mock_client, model_id, query_request, access_token)

    assert response == "LLM answer"

    # Verify Agent was created with MCP server tools and empty bearer header
    mock_agent_class.assert_called_once()
    agent_kwargs = mock_agent_class.call_args[1]

    # Check that tools include MCP server names
    assert "test-server" in agent_kwargs["tools"]

    # Check that extra_headers contains MCP headers with empty authorization

    extra_headers_data = json.loads(
        agent_kwargs["extra_headers"]["X-LlamaStack-Provider-Data"]
    )
    mcp_headers = extra_headers_data["mcp_headers"]
    assert len(mcp_headers) == 0


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


def test_get_rag_toolgroups(mocker):
    """Test get_rag_toolgroups function."""
    vector_db_ids = []
    result = get_rag_toolgroups(vector_db_ids)
    assert result is None

    vector_db_ids = ["Vector-DB-1", "Vector-DB-2"]
    result = get_rag_toolgroups(vector_db_ids)
    assert len(result) == 1
    assert result[0]["name"] == "builtin::rag/knowledge_search"
    assert result[0]["args"]["vector_db_ids"] == vector_db_ids
