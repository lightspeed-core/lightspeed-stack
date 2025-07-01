import pytest

from app.endpoints.query import get_rag_toolgroups
from app.endpoints.streaming_query import (
    streaming_query_endpoint_handler,
    retrieve_response,
    stream_build_event,
)
from models.requests import QueryRequest, Attachment
from llama_stack_client.types import UserMessage  # type: ignore


async def _test_streaming_query_endpoint_handler(mocker, store_transcript=False):
    """Test the streaming query endpoint handler."""
    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = [
        mocker.Mock(identifier="model1", model_type="llm", provider_id="provider1"),
        mocker.Mock(identifier="model2", model_type="llm", provider_id="provider2"),
    ]

    # Mock the streaming response from LLama Stack
    mock_streaming_response = mocker.AsyncMock()
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
        return_value=mock_streaming_response,
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

    # Assert the store_transcript function is called if transcripts are enabled
    if store_transcript:
        mock_transcript.assert_called_once_with(
            user_id="user_id_placeholder",
            conversation_id=mocker.ANY,
            query_is_valid=True,
            query=query,
            query_request=query_request,
            response="LLM answer",
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
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_vector_db = mocker.Mock()
    mock_vector_db.identifier = "VectorDB-1"
    mock_client.vector_dbs.list.return_value = [mock_vector_db]

    mocker.patch("app.endpoints.streaming_query.AsyncAgent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"

    response = await retrieve_response(mock_client, model_id, query_request)

    # For streaming, the response should be the streaming object
    assert response is not None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=get_rag_toolgroups(["VectorDB-1"]),
    )


async def test_retrieve_response_no_available_shields(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    mocker.patch("app.endpoints.streaming_query.AsyncAgent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"

    response = await retrieve_response(mock_client, model_id, query_request)

    # For streaming, the response should be the streaming object
    assert response is not None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
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
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = [MockShield("shield1")]

    mocker.patch("app.endpoints.streaming_query.AsyncAgent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"

    response = await retrieve_response(mock_client, model_id, query_request)

    assert response is not None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
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
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = [
        MockShield("shield1"),
        MockShield("shield2"),
    ]
    mock_client.vector_dbs.list.return_value = []

    mocker.patch("app.endpoints.streaming_query.AsyncAgent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?")
    model_id = "fake_model_id"

    response = await retrieve_response(mock_client, model_id, query_request)

    assert response is not None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
        documents=[],
        stream=True,  # Should be True for streaming endpoint
        toolgroups=None,
    )


async def test_retrieve_response_with_one_attachment(mocker):
    """Test the retrieve_response function."""
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="this is attachment",
        ),
    ]
    mocker.patch("app.endpoints.streaming_query.AsyncAgent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"

    response = await retrieve_response(mock_client, model_id, query_request)

    assert response is not None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
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
    mock_agent.create_turn.return_value.output_message.content = "LLM answer"
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_client.vector_dbs.list.return_value = []

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
    mocker.patch("app.endpoints.streaming_query.AsyncAgent", return_value=mock_agent)

    query_request = QueryRequest(query="What is OpenStack?", attachments=attachments)
    model_id = "fake_model_id"

    response = await retrieve_response(mock_client, model_id, query_request)

    assert response is not None
    mock_agent.create_turn.assert_called_once_with(
        messages=[UserMessage(content="What is OpenStack?", role="user", context=None)],
        session_id=mocker.ANY,
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
    result = stream_build_event(mock_chunk, chunk_id)

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert '"token": "This is a test response"' in result
    assert '"role": "inference"' in result
    assert '"id": 0' in result


def test_stream_build_event_step_complete(mocker):
    """Test stream_build_event function with step_complete event type."""
    # Create a properly nested mock chunk structure
    mock_chunk = mocker.Mock()
    mock_chunk.event = mocker.Mock()
    mock_chunk.event.payload = mocker.Mock()
    mock_chunk.event.payload.event_type = "step_complete"
    mock_chunk.event.payload.step_type = "tool_execution"
    mock_chunk.event.payload.step_details = mocker.Mock()
    mock_chunk.event.payload.step_details.step_type = "tool_execution"
    mock_chunk.event.payload.step_details.tool_calls = [
        mocker.Mock(tool_name="search_tool")
    ]

    chunk_id = 0
    result = stream_build_event(mock_chunk, chunk_id)

    assert result is not None
    assert "data: " in result
    assert '"event": "token"' in result
    assert '"token": "search_tool"' in result
    assert '"role": "tool_execution"' in result
    assert '"id": 0' in result


def test_stream_build_event_returns_none(mocker):
    """Test stream_build_event function returns None when chunk doesn't have expected structure."""
    # Create a mock chunk without the expected payload structure
    mock_chunk = mocker.Mock()
    mock_chunk.event = mocker.Mock()
    # Deliberately not setting payload attribute

    chunk_id = 0
    result = stream_build_event(mock_chunk, chunk_id)

    assert result is None
