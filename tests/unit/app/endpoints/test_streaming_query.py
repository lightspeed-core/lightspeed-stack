import pytest
import json

from fastapi import HTTPException, status
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem

from app.endpoints.query import get_rag_toolgroups
from app.endpoints.streaming_query import (
    streaming_query_endpoint_handler,
    retrieve_response,
    stream_build_event,
)
from llama_stack_client import APIConnectionError
from models.requests import QueryRequest, Attachment
from models.config import ModelContextProtocolServer
from llama_stack_client.types import UserMessage  # type: ignore


SAMPLE_KNOWLEDGE_SEARCH_RESULTS = [
    """knowledge_search tool found 2 chunks:
BEGIN of knowledge_search tool results.
""",
    """Result 1
Content: ABC
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}
""",
    """Result 2
Content: ABC
Metadata: {'docs_url': 'https://example.com/doc2', 'title': 'Doc2', 'document_id': 'doc-2'}
""",
    """END of knowledge_search tool results.
""",
    # Following metadata contains an intentionally incorrect keyword "Title" (instead of "title")
    # and it is not picked as a referenced document.
    """Result 3
Content: ABC
Metadata: {'docs_url': 'https://example.com/doc3', 'Title': 'Doc3', 'document_id': 'doc-3'}
""",
    """The above results were retrieved to help answer the user\'s query: "Sample Query".
Use them as supporting information only in answering this query.
""",
]


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_configuration_not_loaded(mocker):
    """Test the streaming query endpoint handler if configuration is not loaded."""
    # simulate state when no configuration is loaded
    mocker.patch(
        "app.endpoints.streaming_query.configuration",
        return_value=mocker.Mock(),
    )
    mocker.patch("app.endpoints.streaming_query.configuration", None)

    query = "What is OpenStack?"
    query_request = QueryRequest(query=query)

    # await the async function
    with pytest.raises(HTTPException) as e:
        await streaming_query_endpoint_handler(None, query_request, auth="mock_auth")
        assert e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Configuration is not loaded"


@pytest.mark.asyncio
async def test_streaming_query_endpoint_on_connection_error(mocker):
    """Test the streaming query endpoint handler if connection can not be established."""
    # simulate state when no configuration is loaded
    mocker.patch(
        "app.endpoints.streaming_query.configuration",
        return_value=mocker.Mock(),
    )

    query = "What is OpenStack?"
    query_request = QueryRequest(query=query)

    # simulate situation when it is not possible to connect to Llama Stack
    mocker.patch(
        "app.endpoints.streaming_query.get_async_llama_stack_client",
        side_effect=APIConnectionError(request=query_request),
    )

    # await the async function
    with pytest.raises(HTTPException) as e:
        await streaming_query_endpoint_handler(None, query_request, auth="mock_auth")
        assert e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Configuration is not loaded"


async def _test_streaming_query_endpoint_handler(mocker, store_transcript=False):
    """Test the streaming query endpoint handler."""
    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
    ]

    # Mock the streaming response from LLama Stack
    mock_streaming_response = mocker.AsyncMock()
    # Currently usage is not returned by the API, we simulate by using del to prevent pytest from returning a Mock
    del mock_streaming_response.usage
    mock_streaming_response.__aiter__.return_value = [
        mocker.Mock(
            event=mocker.Mock(
                payload=mocker.Mock(
                    event_type="step_progress",
                    delta=mocker.Mock(text="LLM answer"),
                    step_type="inference",
                )
            )
        ),
        mocker.Mock(
            event=mocker.Mock(
                payload=mocker.Mock(
                    event_type="step_complete",
                    step_type="tool_execution",
                    step_details=mocker.Mock(
                        step_type="tool_execution",
                        tool_responses=[
                            mocker.Mock(
                                tool_name="knowledge_search",
                                content=[
                                    TextContentItem(text=s, type="text")
                                    for s in SAMPLE_KNOWLEDGE_SEARCH_RESULTS
                                ],
                            )
                        ],
                        tool_calls=[
                            mocker.Mock(
                                tool_name="knowledge_search",
                            )
                        ],
                    ),
                )
            )
        ),
    ]

    mocker.patch(
        "app.endpoints.streaming_query.configuration",
        return_value=mocker.Mock(),
    )
    query = "What is OpenStack?"
    mocker.patch(
        "app.endpoints.streaming_query.get_async_llama_stack_client",
        return_value=mock_client,
    )
    mocker.patch(
        "app.endpoints.streaming_query.retrieve_response",
        return_value=(
            mock_streaming_response,
            "test_conversation_id",
            {"input_tokens": 10, "output_tokens": 20},
        ),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_id", return_value="fake_model_id"
    )
    mocker.patch(
        "app.endpoints.streaming_query.is_transcripts_enabled",
        return_value=store_transcript,
    )
    mocker.patch(
        "app.endpoints.streaming_query.retrieve_user_id",
        return_value="user_id_placeholder",
    )
    mock_transcript = mocker.patch("app.endpoints.streaming_query.store_transcript")

    query_request = QueryRequest(query=query)

    # Await the async function
    response = await streaming_query_endpoint_handler(
        None, query_request, auth="mock_auth"
    )

    # Assert the response is a StreamingResponse
    from fastapi.responses import StreamingResponse

    assert isinstance(response, StreamingResponse)

    # Collect the streaming response content
    streaming_content = []
    # response.body_iterator is an async generator, iterate over it directly
    async for chunk in response.body_iterator:
        streaming_content.append(chunk)

    # Convert to string for assertions
    full_content = "".join(streaming_content)

    # Assert the streaming content contains expected SSE format
    assert "data: " in full_content
    assert '"event": "start"' in full_content
    assert '"event": "token"' in full_content
    assert '"event": "end"' in full_content
    assert "LLM answer" in full_content

    # Assert referenced documents
    assert len(streaming_content) == 4
    d = json.loads(streaming_content[3][5:])
    referenced_documents = d["data"]["referenced_documents"]
    assert len(referenced_documents) == 2
    assert referenced_documents[1]["doc_title"] == "Doc2"

    # Assert the store_transcript function is called if transcripts are enabled
    if store_transcript:
        mock_transcript.assert_called_once_with(
            user_id="user_id_placeholder",
            conversation_id="test_conversation_id",
            query_is_valid=True,
            query=query,
            query_request=query_request,
            response="LLM answerknowledge_search",
            attachments=[],
            rag_chunks=[],
            truncated=False,
        )
    else:
        mock_transcript.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler(mocker):
    """Test the streaming query endpoint handler with transcript storage disabled."""
    await _test_streaming_query_endpoint_handler(mocker, store_transcript=False)


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_store_transcript(mocker):
    """Test the streaming query endpoint handler with transcript storage enabled."""
    await _test_streaming_query_endpoint_handler(mocker, store_transcript=True)


async def test_retrieve_response_vector_db_available(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    # For streaming, the response should be the streaming object and conversation_id should be returned
    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


async def test_retrieve_response_no_available_shields(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    # For streaming, the response should be the streaming object and conversation_id should be returned
    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


async def test_retrieve_response_one_available_shield(mocker):
    """Test the retrieve_response function."""

    class MockShield:
        def __init__(self, identifier):
            self.identifier = identifier

        def identifier(self):
            return self.identifier

    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = [MockShield("shield1")]
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


async def test_retrieve_response_two_available_shields(mocker):
    """Test the retrieve_response function."""

    class MockShield:
        def __init__(self, identifier):
            self.identifier = identifier

        def identifier(self):
            return self.identifier

    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = [
        MockShield("shield1"),
        MockShield("shield2"),
    ]
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


async def test_retrieve_response_with_one_attachment(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)

    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="this is attachment",
        ),
    ]
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        stream=True,  # Should be True for streaming endpoint
        documents=[
            {
                "content": "this is attachment",
                "mime_type": "text/plain",
            },
        ],
        toolgroups=None,
    )


async def test_retrieve_response_with_two_attachments(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)

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
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        stream=True,  # Should be True for streaming endpoint
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


def test_stream_build_event_step_progress(mocker):
    """Test stream_build_event function with step_progress event type."""
    # Create a properly nested mock chunk structure
    mock_chunk = mocker.Mock()
    mock_chunk.event = mocker.Mock()
    mock_chunk.event.payload = mocker.Mock()
    mock_chunk.event.payload.event_type = "step_progress"
    mock_chunk.event.payload.step_type = "inference"
    mock_chunk.event.payload.delta = mocker.Mock()
    mock_chunk.event.payload.delta.text = "This is a test response"

    chunk_id = 0
    result = stream_build_event(mock_chunk, chunk_id, {})

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert '"token": "This is a test response"' in result
    assert '"role": "inference"' in result
    assert '"id": 0' in result


def test_stream_build_event_step_complete(mocker):
    """Test stream_build_event function with step_complete event type."""
    # Create a properly nested mock chunk structure
    mock_chunk = mocker.Mock(
        event=mocker.Mock(
            payload=mocker.Mock(
                event_type="step_complete",
                step_type="tool_execution",
                step_details=mocker.Mock(
                    step_type="tool_execution",
                    tool_responses=[
                        mocker.Mock(
                            tool_name="knowledge_search",
                            content=[
                                TextContentItem(text=s, type="text")
                                for s in SAMPLE_KNOWLEDGE_SEARCH_RESULTS
                            ],
                        )
                    ],
                    tool_calls=[
                        mocker.Mock(
                            tool_name="knowledge_search",
                        )
                    ],
                ),
            )
        )
    )

    chunk_id = 0
    result = stream_build_event(mock_chunk, chunk_id, {})

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert '"token": "knowledge_search"' in result
    assert '"role": "tool_execution"' in result
    assert '"id": 0' in result


def test_stream_build_event_returns_none(mocker):
    """Test stream_build_event function returns None when chunk doesn't have expected structure."""
    # Create a mock chunk without the expected payload structure
    mock_chunk = mocker.Mock()
    mock_chunk.event = mocker.Mock()
    # Deliberately not setting payload attribute

    chunk_id = 0
    result = stream_build_event(mock_chunk, chunk_id, {})

    assert result is None


async def test_retrieve_response_with_mcp_servers(mocker):
    """Test the retrieve_response function with MCP servers configured."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token_123"

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_shields
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
        session_id="test_conversation_id",
        documents=[],
        stream=True,
        toolgroups=None,
    )


async def test_retrieve_response_with_mcp_servers_empty_token(mocker):
    """Test the retrieve_response function with MCP servers and empty access token."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value = mocker.Mock(spec=["output_message"])
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.models.list.return_value = [
        mocker.Mock(
            identifier="fake_model_id", model_type="llm", provider_id="test_provider"
        ),
    ]
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with MCP servers
    mcp_servers = [
        ModelContextProtocolServer(name="test-server", url="http://localhost:8080"),
    ]
    mock_config = mocker.Mock()
    mock_config.mcp_servers = mcp_servers
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "test_conversation_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = ""  # Empty token

    response, conversation_id, token_usage = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response is not None
    assert conversation_id == "test_conversation_id"
    assert token_usage["input_tokens"] > 0

    # Verify get_agent was called with the correct parameters
    mock_get_agent.assert_called_once_with(
        mock_client,
        model_id,
        mocker.ANY,  # system_prompt
        [],  # available_shields
        None,  # conversation_id
    )

    # Check that the agent's extra_headers property was set correctly (empty mcp_headers)
    expected_extra_headers = {
        "X-LlamaStack-Provider-Data": json.dumps({"mcp_headers": {}})
    }
    assert mock_agent.extra_headers == expected_extra_headers

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_conversation_id",
        documents=[],
        stream=True,
        toolgroups=None,
    )
