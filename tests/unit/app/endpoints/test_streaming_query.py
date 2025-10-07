"""Unit tests for the /streaming-query REST API endpoint."""

from datetime import datetime

# pylint: disable=too-many-lines

import json

import pytest

from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse

from llama_stack_client import APIConnectionError
from llama_stack_client.types import UserMessage  # type: ignore
from llama_stack_client.types.agents import Turn
from llama_stack_client.types.shared.completion_message import CompletionMessage
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem
from llama_stack_client.types.shared.safety_violation import SafetyViolation
from llama_stack_client.types.shield_call_step import ShieldCallStep
from llama_stack_client.types.shared.tool_call import ToolCall
from llama_stack_client.types.shared.content_delta import TextDelta, ToolCallDelta
from llama_stack_client.types.agents.turn_response_event import TurnResponseEvent
from llama_stack_client.types.agents.agent_turn_response_stream_chunk import (
    AgentTurnResponseStreamChunk,
)
from llama_stack_client.types.agents.turn_response_event_payload import (
    AgentTurnResponseStepProgressPayload,
    AgentTurnResponseStepCompletePayload,
    AgentTurnResponseTurnStartPayload,
    AgentTurnResponseTurnAwaitingInputPayload,
    AgentTurnResponseTurnCompletePayload,
)
from llama_stack_client.types.tool_execution_step import ToolExecutionStep
from llama_stack_client.types.tool_response import ToolResponse

from configuration import AppConfig
from app.endpoints.query import get_rag_toolgroups
from app.endpoints.streaming_query import (
    streaming_query_endpoint_handler,
    retrieve_response,
    stream_build_event,
    stream_event,
    stream_end_event,
    prompt_too_long_error,
    generic_llm_error,
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
)

from authorization.resolvers import NoopRolesResolver
from constants import MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT
from models.config import ModelContextProtocolServer, Action
from models.requests import QueryRequest, Attachment
from models.responses import RAGChunk
from utils.token_counter import TokenCounter
from utils.types import ToolCallSummary, TurnSummary

MOCK_AUTH = (
    "017adfa4-7cc6-46e4-b663-3653e1ae69df",
    "mock_username",
    False,
    "mock_token",
)


def mock_database_operations(mocker):
    """Helper function to mock database operations for streaming query endpoints."""
    mocker.patch(
        "app.endpoints.streaming_query.validate_conversation_ownership",
        return_value=True,
    )
    mocker.patch("app.endpoints.streaming_query.persist_user_conversation_details")

    # Mock the database session and query
    mock_session = mocker.Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session.__enter__ = mocker.Mock(return_value=mock_session)
    mock_session.__exit__ = mocker.Mock(return_value=None)
    mocker.patch("app.endpoints.streaming_query.get_session", return_value=mock_session)


def mock_metrics(mocker):
    """Helper function to mock metrics operations for streaming query endpoints."""
    # Mock the metrics that are used in the streaming query endpoints
    mocker.patch("metrics.llm_token_sent_total")
    mocker.patch("metrics.llm_token_received_total")
    mocker.patch("metrics.llm_calls_total")


SAMPLE_KNOWLEDGE_SEARCH_RESULTS = [
    """knowledge_search tool found 2 chunks:
BEGIN of knowledge_search tool results.
""",
    """Result 1
Content: ABC
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1', \
'source': None}
""",
    """Result 2
Content: ABC
Metadata: {'docs_url': 'https://example.com/doc2', 'title': 'Doc2', 'document_id': 'doc-2', \
'source': None}
""",
    """END of knowledge_search tool results.
""",
    # Following metadata contains an intentionally incorrect keyword "Title" (instead of "title")
    # and it is not picked as a referenced document.
    """Result 3
Content: ABC
Metadata: {'docs_url': 'https://example.com/doc3', 'Title': 'Doc3', 'document_id': 'doc-3', \
'source': None}
""",
    """The above results were retrieved to help answer the user\'s query: "Sample Query".
Use them as supporting information only in answering this query.
""",
]


@pytest.fixture(autouse=True, name="setup_configuration")
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
        "conversation_cache": {
            "type": "noop",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


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

    request = Request(
        scope={
            "type": "http",
        }
    )
    # await the async function
    with pytest.raises(HTTPException) as e:
        await streaming_query_endpoint_handler(request, query_request, auth=MOCK_AUTH)
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
    mock_client = mocker.AsyncMock()
    mock_client.models.side_effect = APIConnectionError(request=query_request)
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_async_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_async_lsc.return_value = mock_client

    request = Request(
        scope={
            "type": "http",
        }
    )
    # await the async function - should return a streaming response with error
    response = await streaming_query_endpoint_handler(
        request, query_request, auth=MOCK_AUTH
    )

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


async def _test_streaming_query_endpoint_handler(mocker, store_transcript=False):
    """Test the streaming query endpoint handler."""
    mock_client = mocker.AsyncMock()
    mock_async_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_async_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
    ]

    # Construct the streaming response from Llama Stack.
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    mock_streaming_response = mocker.AsyncMock()
    mock_streaming_response.__aiter__.return_value = [
        AgentTurnResponseStreamChunk(
            event=TurnResponseEvent(
                payload=AgentTurnResponseStepProgressPayload(
                    event_type="step_progress",
                    step_type="inference",
                    delta=TextDelta(text="LLM ", type="text"),
                    step_id="s1",
                )
            )
        ),
        AgentTurnResponseStreamChunk(
            event=TurnResponseEvent(
                payload=AgentTurnResponseStepProgressPayload(
                    event_type="step_progress",
                    step_type="inference",
                    delta=TextDelta(text="answer", type="text"),
                    step_id="s2",
                )
            )
        ),
        AgentTurnResponseStreamChunk(
            event=TurnResponseEvent(
                payload=AgentTurnResponseStepCompletePayload(
                    event_type="step_complete",
                    step_id="s1",
                    step_type="tool_execution",
                    step_details=ToolExecutionStep(
                        turn_id="t1",
                        step_id="s3",
                        step_type="tool_execution",
                        tool_responses=[
                            ToolResponse(
                                call_id="t1",
                                tool_name="knowledge_search",
                                content=[
                                    TextContentItem(text=s, type="text")
                                    for s in SAMPLE_KNOWLEDGE_SEARCH_RESULTS
                                ],
                            )
                        ],
                        tool_calls=[
                            ToolCall(
                                call_id="t1", tool_name="knowledge_search", arguments={}
                            )
                        ],
                    ),
                )
            )
        ),
        AgentTurnResponseStreamChunk(
            event=TurnResponseEvent(
                payload=AgentTurnResponseTurnCompletePayload(
                    event_type="turn_complete",
                    turn=Turn(
                        turn_id="t1",
                        input_messages=[],
                        output_message=CompletionMessage(
                            role="assistant",
                            content=[TextContentItem(text="LLM answer", type="text")],
                            stop_reason="end_of_turn",
                        ),
                        session_id="test_session_id",
                        started_at=datetime.now(),
                        steps=[],
                        completed_at=datetime.now(),
                        output_attachments=[],
                    ),
                )
            )
        ),
    ]

    query = "What is OpenStack?"
    mocker.patch(
        "app.endpoints.streaming_query.retrieve_response",
        return_value=(mock_streaming_response, "00000000-0000-0000-0000-000000000000"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.is_transcripts_enabled",
        return_value=store_transcript,
    )
    mock_transcript = mocker.patch("app.endpoints.streaming_query.store_transcript")

    # Mock get_topic_summary function
    mocker.patch(
        "app.endpoints.streaming_query.get_topic_summary",
        return_value="Test topic summary",
    )

    mock_database_operations(mocker)

    query_request = QueryRequest(query=query)

    request = Request(
        scope={
            "type": "http",
        }
    )
    # Await the async function
    response = await streaming_query_endpoint_handler(
        request, query_request, auth=MOCK_AUTH
    )

    # assert the response is a StreamingResponse
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
    assert len(streaming_content) == 7
    d = json.loads(streaming_content[6][5:])
    referenced_documents = d["data"]["referenced_documents"]
    assert len(referenced_documents) == 2
    assert referenced_documents[1]["doc_title"] == "Doc2"

    # Assert the store_transcript function is called if transcripts are enabled
    if store_transcript:
        mock_transcript.assert_called_once_with(
            user_id="017adfa4-7cc6-46e4-b663-3653e1ae69df",
            conversation_id="00000000-0000-0000-0000-000000000000",
            model_id="fake_model_id",
            provider_id="fake_provider_id",
            query_is_valid=True,
            query=query,
            query_request=query_request,
            summary=TurnSummary(
                llm_response="LLM answer",
                tool_calls=[
                    ToolCallSummary(
                        id="t1",
                        name="knowledge_search",
                        args={},
                        response=" ".join(SAMPLE_KNOWLEDGE_SEARCH_RESULTS),
                    )
                ],
                rag_chunks=[
                    RAGChunk(
                        content=" ".join(SAMPLE_KNOWLEDGE_SEARCH_RESULTS),
                        source="knowledge_search",
                        score=None,
                    )
                ],
            ),
            attachments=[],
            rag_chunks=[
                {
                    "content": " ".join(SAMPLE_KNOWLEDGE_SEARCH_RESULTS),
                    "source": "knowledge_search",
                    "score": None,
                }
            ],
            truncated=False,
        )
    else:
        mock_transcript.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler(mocker):
    """Test the streaming query endpoint handler with transcript storage disabled."""
    mock_metrics(mocker)
    await _test_streaming_query_endpoint_handler(mocker, store_transcript=False)


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_store_transcript(mocker):
    """Test the streaming query endpoint handler with transcript storage enabled."""
    mock_metrics(mocker)
    await _test_streaming_query_endpoint_handler(mocker, store_transcript=True)


async def test_retrieve_response_vector_db_available(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    # For streaming, the response should be the streaming object and
    # conversation_id should be returned
    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


async def test_retrieve_response_no_available_shields(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    # Mock configuration with empty MCP servers
    mock_config = mocker.Mock()
    mock_config.mcp_servers = []
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    # For streaming, the response should be the streaming object and
    # conversation_id should be returned
    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"

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
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


async def test_retrieve_response_with_one_attachment(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
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
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        stream=True,  # Should be True for streaming endpoint
        documents=[
            {
                "content": "this is attachment",
                "mime_type": "text/plain",
            },
        ],
        toolgroups=None,
    )


async def test_retrieve_response_with_two_attachments(prepare_agent_mocks, mocker):
    """Test the retrieve_response function."""
    mock_client, mock_agent = prepare_agent_mocks
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client.shields.list.return_value = []
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
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"
    token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
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


def test_stream_build_event_turn_start():
    """Test stream_build_event function with turn_start event type."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseTurnStartPayload(
                event_type="turn_start",
                turn_id="t1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "start"' in result
    assert '"conversation_id"' in result


def test_stream_build_event_turn_awaiting_input():
    """Test stream_build_event function with turn_awaiting_input event type."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseTurnAwaitingInputPayload(
                event_type="turn_awaiting_input",
                turn=Turn(
                    input_messages=[],
                    output_message=CompletionMessage(
                        content="content",
                        role="assistant",
                        stop_reason="end_of_turn",
                    ),
                    session_id="session-1",
                    started_at=datetime.now(),
                    steps=[],
                    turn_id="t1",
                ),
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "start"' in result
    assert '"conversation_id"' in result


def test_stream_build_event_turn_complete():
    """Test stream_build_event function with turn_complete event type."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseTurnCompletePayload(
                event_type="turn_complete",
                turn=Turn(
                    input_messages=[],
                    output_message=CompletionMessage(
                        content="content",
                        role="assistant",
                        stop_reason="end_of_turn",
                    ),
                    session_id="session-1",
                    started_at=datetime.now(),
                    steps=[],
                    turn_id="t1",
                ),
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "turn_complete"' in result
    assert '"token": "content"' in result


def test_stream_build_event_shield_call_step_complete_no_violation(mocker):
    """Test stream_build_event function with shield_call_step_complete event type."""
    # Mock the metric for validation errors
    mock_metric = mocker.patch("metrics.llm_calls_validation_errors_total")

    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepCompletePayload(
                event_type="step_complete",
                step_type="shield_call",
                step_details=ShieldCallStep(
                    step_id="s1",
                    step_type="shield_call",
                    turn_id="t1",
                ),
                step_id="s1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert '"token": "No Violation"' in result
    # Role field removed for OLS compatibility
    assert '"id": 0' in result
    # Assert that the metric for validation errors is NOT incremented
    mock_metric.inc.assert_not_called()


def test_stream_build_event_shield_call_step_complete_with_violation(mocker):
    """Test stream_build_event function with shield_call_step_complete event type with violation."""
    # Mock the metric for validation errors
    mock_metric = mocker.patch("metrics.llm_calls_validation_errors_total")

    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepCompletePayload(
                event_type="step_complete",
                step_type="shield_call",
                step_details=ShieldCallStep(
                    step_id="s1",
                    step_type="shield_call",
                    turn_id="t1",
                    violation=SafetyViolation(
                        metadata={},
                        violation_level="info",
                        user_message="I don't like the cut of your jib",
                    ),
                ),
                step_id="s1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert (
        '"token": "Violation: I don\'t like the cut of your jib (Metadata: {})"'
        in result
    )
    # Role field removed for OLS compatibility
    assert '"id": 0' in result
    # Assert that the metric for validation errors is incremented
    mock_metric.inc.assert_called_once()


def test_stream_build_event_step_progress():
    """Test stream_build_event function with step_progress event type."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepProgressPayload(
                event_type="step_progress",
                step_type="inference",
                delta=TextDelta(text="This is a test response", type="text"),
                step_id="s1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert '"token": "This is a test response"' in result
    # Role field removed for OLS compatibility
    assert '"id": 0' in result


def test_stream_build_event_step_progress_tool_call_str():
    """Test stream_build_event function with step_progress_tool_call event type with a string."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepProgressPayload(
                event_type="step_progress",
                step_type="inference",
                delta=ToolCallDelta(
                    parse_status="succeeded", tool_call="tool-called", type="tool_call"
                ),
                step_id="s1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "tool_call"' in result
    assert '"token": "tool-called"' in result
    # Role field removed for OLS compatibility
    assert '"id": 0' in result


def test_stream_build_event_step_progress_tool_call_tool_call():
    """Test stream_build_event function with step_progress_tool_call event type with a ToolCall."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepProgressPayload(
                event_type="step_progress",
                step_type="inference",
                delta=ToolCallDelta(
                    parse_status="succeeded",
                    tool_call=ToolCall(
                        arguments={}, call_id="tc1", tool_name="my-tool"
                    ),
                    type="tool_call",
                ),
                step_id="s1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert "data: " in result
    assert '"event": "tool_call"' in result
    assert '"token": "my-tool"' in result
    # Role field removed for OLS compatibility
    assert '"id": 0' in result


def test_stream_build_event_step_complete():
    """Test stream_build_event function with step_complete event type."""
    # Create a properly nested chunk structure
    # We cannot use 'mock' as 'hasattr(mock, "xxx")' adds the missing
    # attribute and therefore makes checks to see whether it is missing fail.
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepCompletePayload(
                event_type="step_complete",
                step_id="s1",
                step_type="tool_execution",
                step_details=ToolExecutionStep(
                    turn_id="t1",
                    step_id="s2",
                    step_type="tool_execution",
                    tool_responses=[
                        ToolResponse(
                            call_id="c1",
                            tool_name="knowledge_search",
                            content=[
                                TextContentItem(text=s, type="text")
                                for s in SAMPLE_KNOWLEDGE_SEARCH_RESULTS
                            ],
                        )
                    ],
                    tool_calls=[
                        ToolCall(
                            call_id="t1", tool_name="knowledge_search", arguments={}
                        )
                    ],
                ),
            )
        )
    )

    itr = stream_build_event(chunk, 0, {})

    result = next(itr)
    assert result is not None
    assert "data: " in result
    assert '"event": "tool_call"' in result
    assert '"token": {"tool_name": "knowledge_search", "arguments": {}}' in result

    result = next(itr)
    assert (
        '"token": {"tool_name": "knowledge_search", '
        '"summary": "knowledge_search tool found 2 chunks:"}' in result
    )
    # Role field removed for OLS compatibility
    assert '"id": 0' in result


def test_stream_build_event_error():
    """Test stream_build_event function returns a 'error' when chunk contains error information."""
    # Create a mock chunk without an expected payload structure

    # pylint: disable=R0903
    class MockError:
        """Dummy class to mock an exception."""

        error = {"message": "Something went wrong"}

    result = next(stream_build_event(MockError(), 0, {}))

    assert result is not None
    assert '"id": 0' in result
    assert '"event": "error"' in result
    assert '"token": "Something went wrong"' in result


def test_stream_build_event_returns_heartbeat():
    """Test stream_build_event function returns a 'heartbeat' when chunk is unrecognised."""
    # Create a mock chunk without an expected payload structure
    chunk = AgentTurnResponseStreamChunk(
        event=TurnResponseEvent(
            payload=AgentTurnResponseStepProgressPayload(
                event_type="step_progress",
                step_type="memory_retrieval",
                delta=TextDelta(text="", type="text"),
                step_id="s1",
            )
        )
    )

    result = next(stream_build_event(chunk, 0, {}))

    assert result is not None
    assert '"id": 0' in result
    assert '"event": "token"' in result
    assert '"token": "heartbeat"' in result


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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = "test_token_123"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"

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
        session_id="test_session_id",
        documents=[],
        stream=True,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
    )

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"
    access_token = ""  # Empty token

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"

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

    # Check that the agent's extra_headers property was set correctly (empty mcp_headers)
    expected_extra_headers = {
        "X-LlamaStack-Provider-Data": json.dumps({"mcp_headers": {}})
    }
    assert mock_agent.extra_headers == expected_extra_headers

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


async def test_retrieve_response_with_mcp_servers_and_mcp_headers(mocker):
    """Test the retrieve_response function with MCP servers configured."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mock_get_agent = mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(
            mock_agent,
            "00000000-0000-0000-0000-000000000000",
            "test_session_id",
        ),
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

    assert response is not None
    assert conversation_id == "00000000-0000-0000-0000-000000000000"

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
        "X-LlamaStack-Provider-Data": json.dumps({"mcp_headers": expected_mcp_headers})
    }
    assert mock_agent.extra_headers == expected_extra_headers

    # Check that create_turn was called with the correct parameters
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(role="user", content="What is OpenStack?")],
        session_id="test_session_id",
        documents=[],
        stream=True,
        toolgroups=[mcp_server.name for mcp_server in mcp_servers],
    )


@pytest.mark.asyncio
async def test_auth_tuple_unpacking_in_streaming_query_endpoint_handler(mocker):
    """Test that auth tuple is correctly unpacked in streaming query endpoint handler."""
    # Mock dependencies
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)

    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1")
    ]
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )

    # Mock retrieve_response to verify token is passed correctly
    mock_streaming_response = mocker.AsyncMock()
    mock_streaming_response.__aiter__.return_value = iter([])
    mock_retrieve_response = mocker.patch(
        "app.endpoints.streaming_query.retrieve_response",
        return_value=(mock_streaming_response, "00000000-0000-0000-0000-000000000000"),
    )

    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("test_model", "test_model", "test_provider"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.is_transcripts_enabled", return_value=False
    )
    # Mock get_topic_summary function
    mocker.patch(
        "app.endpoints.streaming_query.get_topic_summary",
        return_value="Test topic summary",
    )
    mock_database_operations(mocker)

    request = Request(
        scope={
            "type": "http",
        }
    )
    await streaming_query_endpoint_handler(
        request,
        QueryRequest(query="test query"),
        auth=("user123", "username", False, "auth_token_123"),
        mcp_headers=None,
    )

    assert mock_retrieve_response.call_args[0][3] == "auth_token_123"


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_no_tools_true(mocker):
    """Test the streaming query endpoint handler with no_tools=True."""
    mock_client = mocker.AsyncMock()
    mock_async_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_async_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]

    mock_config = mocker.Mock()
    mock_config.user_data_collection_configuration.transcripts_disabled = True
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)

    # Mock the streaming response
    mock_streaming_response = mocker.AsyncMock()
    mock_streaming_response.__aiter__.return_value = iter([])

    mocker.patch(
        "app.endpoints.streaming_query.retrieve_response",
        return_value=(mock_streaming_response, "00000000-0000-0000-0000-000000000000"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.is_transcripts_enabled", return_value=False
    )
    # Mock get_topic_summary function
    mocker.patch(
        "app.endpoints.streaming_query.get_topic_summary",
        return_value="Test topic summary",
    )
    # Mock database operations
    mock_database_operations(mocker)

    query_request = QueryRequest(query="What is OpenStack?", no_tools=True)

    request = Request(
        scope={
            "type": "http",
        }
    )
    response = await streaming_query_endpoint_handler(
        request, query_request, auth=MOCK_AUTH
    )

    # Assert the response is a StreamingResponse
    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_no_tools_false(mocker):
    """Test the streaming query endpoint handler with no_tools=False (default behavior)."""
    mock_client = mocker.AsyncMock()
    mock_async_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_async_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]

    mock_config = mocker.Mock()
    mock_config.user_data_collection_configuration.transcripts_disabled = True
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)

    # Mock the streaming response
    mock_streaming_response = mocker.AsyncMock()
    mock_streaming_response.__aiter__.return_value = iter([])

    mocker.patch(
        "app.endpoints.streaming_query.retrieve_response",
        return_value=(mock_streaming_response, "00000000-0000-0000-0000-000000000000"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.is_transcripts_enabled", return_value=False
    )
    # Mock get_topic_summary function
    mocker.patch(
        "app.endpoints.streaming_query.get_topic_summary",
        return_value="Test topic summary",
    )
    # Mock database operations
    mock_database_operations(mocker)

    query_request = QueryRequest(query="What is OpenStack?", no_tools=False)

    request = Request(
        scope={
            "type": "http",
        }
    )
    response = await streaming_query_endpoint_handler(
        request, query_request, auth=MOCK_AUTH
    )

    # Assert the response is a StreamingResponse
    assert isinstance(response, StreamingResponse)


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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", no_tools=True)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response is not None
    assert conversation_id == "fake_conversation_id"

    # Verify that agent.extra_headers is empty (no MCP headers)
    assert mock_agent.extra_headers == {}

    # Verify that create_turn was called with toolgroups=None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=True,
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
    mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
    mocker.patch(
        "app.endpoints.streaming_query.get_agent",
        return_value=(mock_agent, "fake_conversation_id", "fake_session_id"),
    )

    query_request = QueryRequest(query="What is OpenStack?", no_tools=False)
    model_id = "fake_model_id"
    access_token = "test_token"

    response, conversation_id = await retrieve_response(
        mock_client, model_id, query_request, access_token
    )

    assert response is not None
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

    expected_toolgroups = get_rag_toolgroups(["VectorDB-1"]) + ["filesystem-server"]
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user")],
        session_id="fake_session_id",
        documents=[],
        stream=True,
        toolgroups=expected_toolgroups,
    )


@pytest.mark.asyncio
async def test_streaming_query_endpoint_rejects_model_provider_override_without_permission(
    mocker,
):
    """Assert 403 when request includes model/provider without MODEL_OVERRIDE."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
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
            "user_data_collection": {"transcripts_enabled": False},
            "mcp_servers": [],
        }
    )
    mocker.patch("app.endpoints.streaming_query.configuration", cfg)

    # Patch authorization to exclude MODEL_OVERRIDE from authorized actions
    access_resolver = mocker.Mock()
    access_resolver.check_access.return_value = True
    access_resolver.get_actions.return_value = set(Action) - {Action.MODEL_OVERRIDE}
    mocker.patch(
        "authorization.middleware.get_authorization_resolvers",
        return_value=(NoopRolesResolver(), access_resolver),
    )

    # Build a query request that tries to override model/provider
    query_request = QueryRequest(query="What?", model="m", provider="p")

    request = Request(
        scope={
            "type": "http",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await streaming_query_endpoint_handler(request, query_request, auth=MOCK_AUTH)

    expected_msg = (
        "This instance does not permit overriding model/provider in the query request "
        "(missing permission: MODEL_OVERRIDE). Please remove the model and provider "
        "fields from your request."
    )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail["response"] == expected_msg


@pytest.mark.asyncio
async def test_streaming_query_handles_none_event(mocker):
    """Test that streaming query handles chunks with None events gracefully."""
    mock_metrics(mocker)
    # Mock the client
    mock_client = mocker.AsyncMock()
    mock_async_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_async_lsc.return_value = mock_client
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
    ]
    # Create a mock chunk with None event
    mock_chunk = mocker.Mock()
    mock_chunk.event = None
    # Create mock streaming response with None event chunk
    mock_streaming_response = mocker.AsyncMock()
    mock_streaming_response.__aiter__.return_value = [mock_chunk]
    # Mock the retrieve_response to return our mock streaming response
    mocker.patch(
        "app.endpoints.streaming_query.retrieve_response",
        return_value=(mock_streaming_response, "00000000-0000-0000-0000-000000000000"),
    )
    # Mock other dependencies
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("fake_model_id", "fake_model_id", "fake_provider_id"),
    )
    mocker.patch(
        "app.endpoints.streaming_query.is_transcripts_enabled",
        return_value=False,
    )
    mock_database_operations(mocker)
    query_request = QueryRequest(query="test query")
    request = Request(scope={"type": "http"})
    # This should not raise an exception
    response = await streaming_query_endpoint_handler(
        request, query_request, auth=MOCK_AUTH
    )
    assert isinstance(response, StreamingResponse)


# ============================================================================
# OLS Compatibility Tests
# ============================================================================


class TestOLSStreamEventFormatting:
    """Test the stream_event function for both media types (OLS compatibility)."""

    def test_stream_event_json_token(self):
        """Test token event formatting for JSON media type."""
        data = {"id": 0, "token": "Hello"}
        result = stream_event(data, LLM_TOKEN_EVENT, MEDIA_TYPE_JSON)

        expected = 'data: {"event": "token", "data": {"id": 0, "token": "Hello"}}\n\n'
        assert result == expected

    def test_stream_event_text_token(self):
        """Test token event formatting for text media type."""

        data = {"id": 0, "token": "Hello"}
        result = stream_event(data, LLM_TOKEN_EVENT, MEDIA_TYPE_TEXT)

        assert result == "Hello"

    def test_stream_event_json_tool_call(self):
        """Test tool call event formatting for JSON media type."""

        data = {
            "id": 0,
            "token": {"tool_name": "search", "arguments": {"query": "test"}},
        }
        result = stream_event(data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_JSON)

        expected = (
            'data: {"event": "tool_call", "data": {"id": 0, "token": '
            '{"tool_name": "search", "arguments": {"query": "test"}}}}\n\n'
        )
        assert result == expected

    def test_stream_event_text_tool_call(self):
        """Test tool call event formatting for text media type."""

        data = {
            "id": 0,
            "token": {"tool_name": "search", "arguments": {"query": "test"}},
        }
        result = stream_event(data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_TEXT)

        expected = (
            '\nTool call: {"id": 0, "token": '
            '{"tool_name": "search", "arguments": {"query": "test"}}}\n'
        )
        assert result == expected

    def test_stream_event_json_tool_result(self):
        """Test tool result event formatting for JSON media type."""

        data = {
            "id": 0,
            "token": {"tool_name": "search", "response": "Found results"},
        }
        result = stream_event(data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_JSON)

        expected = (
            'data: {"event": "tool_result", "data": {"id": 0, "token": '
            '{"tool_name": "search", "response": "Found results"}}}\n\n'
        )
        assert result == expected

    def test_stream_event_text_tool_result(self):
        """Test tool result event formatting for text media type."""

        data = {
            "id": 0,
            "token": {"tool_name": "search", "response": "Found results"},
        }
        result = stream_event(data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_TEXT)

        expected = (
            '\nTool result: {"id": 0, "token": '
            '{"tool_name": "search", "response": "Found results"}}\n'
        )
        assert result == expected

    def test_stream_event_unknown_type(self):
        """Test handling of unknown event types."""

        data = {"id": 0, "token": "test"}
        result = stream_event(data, "unknown_event", MEDIA_TYPE_TEXT)

        assert result == ""


class TestOLSStreamEndEvent:
    """Test the stream_end_event function for both media types (OLS compatibility)."""

    def test_stream_end_event_json(self):
        """Test end event formatting for JSON media type."""

        metadata_map = {
            "doc1": {"title": "Test Doc 1", "docs_url": "https://example.com/doc1"},
            "doc2": {"title": "Test Doc 2", "docs_url": "https://example.com/doc2"},
        }
        # Create mock objects for the test
        mock_summary = TurnSummary(llm_response="Test response", tool_calls=[])
        mock_token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        result = stream_end_event(
            metadata_map, mock_summary, mock_token_usage, MEDIA_TYPE_JSON
        )

        # Parse the result to verify structure
        data_part = result.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "end"
        assert "referenced_documents" in parsed["data"]
        assert len(parsed["data"]["referenced_documents"]) == 2
        assert parsed["data"]["referenced_documents"][0]["doc_title"] == "Test Doc 1"
        assert (
            parsed["data"]["referenced_documents"][0]["doc_url"]
            == "https://example.com/doc1"
        )
        assert "available_quotas" in parsed

    def test_stream_end_event_text(self):
        """Test end event formatting for text media type."""

        metadata_map = {
            "doc1": {"title": "Test Doc 1", "docs_url": "https://example.com/doc1"},
            "doc2": {"title": "Test Doc 2", "docs_url": "https://example.com/doc2"},
        }
        # Create mock objects for the test
        mock_summary = TurnSummary(llm_response="Test response", tool_calls=[])
        mock_token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        result = stream_end_event(
            metadata_map, mock_summary, mock_token_usage, MEDIA_TYPE_TEXT
        )

        expected = (
            "\n\n---\n\nTest Doc 1: https://example.com/doc1\n"
            "Test Doc 2: https://example.com/doc2"
        )
        assert result == expected

    def test_stream_end_event_text_no_docs(self):
        """Test end event formatting for text media type with no documents."""

        metadata_map = {}
        # Create mock objects for the test
        mock_summary = TurnSummary(llm_response="Test response", tool_calls=[])
        mock_token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        result = stream_end_event(
            metadata_map, mock_summary, mock_token_usage, MEDIA_TYPE_TEXT
        )

        assert result == ""


class TestOLSErrorHandling:
    """Test error handling functions (OLS compatibility)."""

    def test_prompt_too_long_error_json(self):
        """Test prompt too long error for JSON media type."""

        error = Exception("Prompt exceeds maximum length")
        result = prompt_too_long_error(error, MEDIA_TYPE_JSON)

        data_part = result.replace("data: ", "").strip()
        parsed = json.loads(data_part)
        assert parsed["event"] == "error"
        assert parsed["data"]["status_code"] == 413
        assert parsed["data"]["response"] == "Prompt is too long"
        assert parsed["data"]["cause"] == "Prompt exceeds maximum length"

    def test_prompt_too_long_error_text(self):
        """Test prompt too long error for text media type."""

        error = Exception("Prompt exceeds maximum length")
        result = prompt_too_long_error(error, MEDIA_TYPE_TEXT)

        assert result == "Prompt is too long: Prompt exceeds maximum length"

    def test_generic_llm_error_json(self):
        """Test generic LLM error for JSON media type."""

        error = Exception("Connection failed")
        result = generic_llm_error(error, MEDIA_TYPE_JSON)

        data_part = result.replace("data: ", "").strip()
        parsed = json.loads(data_part)
        assert parsed["event"] == "error"
        assert parsed["data"]["response"] == "Internal server error"
        assert parsed["data"]["cause"] == "Connection failed"

    def test_generic_llm_error_text(self):
        """Test generic LLM error for text media type."""

        error = Exception("Connection failed")
        result = generic_llm_error(error, MEDIA_TYPE_TEXT)

        assert result == "Error: Connection failed"


class TestOLSCompatibilityIntegration:
    """Integration tests for OLS compatibility."""

    def test_media_type_validation(self):
        """Test that media type validation works correctly."""

        # Valid media types
        valid_request = QueryRequest(query="test", media_type="application/json")
        assert valid_request.media_type == "application/json"

        valid_request = QueryRequest(query="test", media_type="text/plain")
        assert valid_request.media_type == "text/plain"

        # Invalid media type should raise error
        with pytest.raises(ValueError, match="media_type must be either"):
            QueryRequest(query="test", media_type="invalid/type")

    def test_ols_event_structure(self):
        """Test that events follow OLS structure."""

        # Test token event structure
        token_data = {"id": 0, "token": "Hello"}
        token_event = stream_event(token_data, LLM_TOKEN_EVENT, MEDIA_TYPE_JSON)

        data_part = token_event.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "token"
        assert "id" in parsed["data"]
        assert "token" in parsed["data"]
        assert "role" not in parsed["data"]  # Role field is not included

        # Test tool call event structure
        tool_data = {
            "id": 0,
            "token": {"tool_name": "search", "arguments": {"query": "test"}},
        }
        tool_event = stream_event(tool_data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_JSON)

        data_part = tool_event.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "tool_call"
        assert "id" in parsed["data"]
        assert "role" not in parsed["data"]
        assert "token" in parsed["data"]

        # Test tool result event structure
        result_data = {
            "id": 0,
            "token": {"tool_name": "search", "response": "Found results"},
        }
        result_event = stream_event(result_data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_JSON)

        data_part = result_event.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "tool_result"
        assert "id" in parsed["data"]
        assert "role" not in parsed["data"]
        assert "token" in parsed["data"]

    def test_ols_end_event_structure(self):
        """Test that end event follows OLS structure."""

        metadata_map = {
            "doc1": {"title": "Test Doc", "docs_url": "https://example.com/doc"}
        }
        # Create mock objects for the test
        mock_summary = TurnSummary(llm_response="Test response", tool_calls=[])
        mock_token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        end_event = stream_end_event(
            metadata_map, mock_summary, mock_token_usage, MEDIA_TYPE_JSON
        )
        data_part = end_event.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "end"
        assert "referenced_documents" in parsed["data"]
        assert "truncated" in parsed["data"]
        assert "input_tokens" in parsed["data"]
        assert "output_tokens" in parsed["data"]
        assert "available_quotas" in parsed  # At root level, not inside data
