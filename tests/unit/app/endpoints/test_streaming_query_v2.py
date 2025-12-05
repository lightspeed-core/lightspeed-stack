# pylint: disable=redefined-outer-name, import-error
"""Unit tests for the /streaming_query (v2) endpoint using Responses API."""

from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture

from app.endpoints.streaming_query_v2 import (
    retrieve_response,
    streaming_query_endpoint_handler_v2,
)
from models.config import Action, ModelContextProtocolServer
from models.requests import QueryRequest


@pytest.fixture
def dummy_request() -> Request:
    """Create a dummy FastAPI Request for testing with authorized actions."""
    req = Request(scope={"type": "http"})
    # Provide a permissive authorized_actions set to satisfy RBAC check
    req.state.authorized_actions = set(Action)
    return req


@pytest.mark.asyncio
async def test_retrieve_response_builds_rag_and_mcp_tools(
    mocker: MockerFixture,
) -> None:
    """Test that retrieve_response correctly builds RAG and MCP tools."""
    mock_client = mocker.Mock()
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = [mocker.Mock(id="db1")]
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    mock_client.responses.create = mocker.AsyncMock(return_value=mocker.Mock())
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch(
        "app.endpoints.streaming_query_v2.get_system_prompt", return_value="PROMPT"
    )

    mock_cfg = mocker.Mock()
    mock_cfg.mcp_servers = [
        ModelContextProtocolServer(name="fs", url="http://localhost:3000"),
    ]
    mocker.patch("app.endpoints.streaming_query_v2.configuration", mock_cfg)

    qr = QueryRequest(query="hello")
    await retrieve_response(mock_client, "model-z", qr, token="tok")

    kwargs = mock_client.responses.create.call_args.kwargs
    assert kwargs["stream"] is True
    tools = kwargs["tools"]
    assert isinstance(tools, list)
    types = {t.get("type") for t in tools}
    assert types == {"file_search", "mcp"}


@pytest.mark.asyncio
async def test_retrieve_response_no_tools_passes_none(mocker: MockerFixture) -> None:
    """Test that retrieve_response passes None for tools when no_tools=True."""
    mock_client = mocker.Mock()
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    mock_client.responses.create = mocker.AsyncMock(return_value=mocker.Mock())
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch(
        "app.endpoints.streaming_query_v2.get_system_prompt", return_value="PROMPT"
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.configuration", mocker.Mock(mcp_servers=[])
    )

    qr = QueryRequest(query="hello", no_tools=True)
    await retrieve_response(mock_client, "model-z", qr, token="tok")

    kwargs = mock_client.responses.create.call_args.kwargs
    assert kwargs["tools"] is None
    assert kwargs["stream"] is True


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_v2_success_yields_events(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that streaming_query_endpoint_handler_v2 yields correct SSE events."""
    # Skip real config checks - patch in streaming_query where the base handler is
    mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")

    # Model selection plumbing
    mock_client = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mocker.Mock()])
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )
    mocker.patch(
        "app.endpoints.streaming_query.evaluate_model_hints",
        return_value=(None, None),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("llama/m", "m", "p"),
    )

    # Replace SSE helpers for deterministic output
    mocker.patch(
        "app.endpoints.streaming_query_v2.stream_start_event",
        lambda conv_id: f"START:{conv_id}\n",
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.format_stream_data",
        lambda obj: f"EV:{obj['event']}:{obj['data'].get('token','')}\n",
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.stream_end_event",
        lambda _m, _s, _t, _media: "END\n",
    )

    # Mock the cleanup function that handles all post-streaming database/cache work
    cleanup_spy = mocker.patch(
        "app.endpoints.streaming_query_v2.cleanup_after_streaming",
        mocker.AsyncMock(return_value=None),
    )

    # Build a fake async stream of chunks
    async def fake_stream() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(
            type="response.created", response=SimpleNamespace(id="conv-xyz")
        )
        yield SimpleNamespace(type="response.content_part.added")
        yield SimpleNamespace(type="response.output_text.delta", delta="Hello ")
        yield SimpleNamespace(type="response.output_text.delta", delta="world")
        yield SimpleNamespace(
            type="response.output_item.added",
            item=SimpleNamespace(
                type="function_call", id="item1", name="search", call_id="call1"
            ),
        )
        yield SimpleNamespace(
            type="response.function_call_arguments.delta", delta='{"q":"x"}'
        )
        yield SimpleNamespace(
            type="response.function_call_arguments.done",
            item_id="item1",
            arguments='{"q":"x"}',
        )
        yield SimpleNamespace(type="response.output_text.done", text="Hello world")
        yield SimpleNamespace(type="response.completed")

    mocker.patch(
        "app.endpoints.streaming_query_v2.retrieve_response",
        return_value=(fake_stream(), ""),
    )

    metric = mocker.patch("metrics.llm_calls_total")

    resp = await streaming_query_endpoint_handler_v2(
        request=dummy_request,
        query_request=QueryRequest(query="hi"),
        auth=("user123", "", True, "token-abc"),  # skip_userid_check=True
        mcp_headers={},
    )

    assert isinstance(resp, StreamingResponse)
    metric.labels("p", "m").inc.assert_called_once()

    # Collect emitted events
    events: list[str] = []
    async for chunk in resp.body_iterator:
        s = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        events.append(s)

    # Validate event sequence and content
    assert events[0] == "START:conv-xyz\n"
    # content_part.added triggers empty token
    assert events[1] == "EV:token:\n"
    assert events[2] == "EV:token:Hello \n"
    assert events[3] == "EV:token:world\n"
    # tool call delta
    assert events[4].startswith("EV:tool_call:")
    # turn complete and end
    assert "EV:turn_complete:Hello world\n" in events
    assert events[-1] == "END\n"

    # Verify cleanup function was invoked after streaming
    assert cleanup_spy.call_count == 1
    # Verify cleanup was called with correct user_id and conversation_id
    call_args = cleanup_spy.call_args
    assert call_args.kwargs["user_id"] == "user123"
    assert call_args.kwargs["conversation_id"] == "conv-xyz"
    assert call_args.kwargs["model_id"] == "m"
    assert call_args.kwargs["provider_id"] == "p"


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_v2_api_connection_error(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that streaming_query_endpoint_handler_v2 handles API connection errors."""
    mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")

    def _raise(*_a: Any, **_k: Any) -> None:
        raise APIConnectionError(request=None)  # type: ignore[arg-type]

    mocker.patch("client.AsyncLlamaStackClientHolder.get_client", side_effect=_raise)

    fail_metric = mocker.patch("metrics.llm_calls_failures_total")

    with pytest.raises(HTTPException) as exc:
        await streaming_query_endpoint_handler_v2(
            request=dummy_request,
            query_request=QueryRequest(query="hi"),
            auth=("user123", "", False, "tok"),
            mcp_headers={},
        )

    assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "Unable to connect to Llama Stack" in str(exc.value.detail)
    fail_metric.inc.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_response_with_shields_available(mocker: MockerFixture) -> None:
    """Test that shields are listed and passed to streaming responses API."""
    mock_client = mocker.Mock()

    # Mock shields.list to return available shields
    shield1 = mocker.Mock()
    shield1.identifier = "shield-1"
    shield2 = mocker.Mock()
    shield2.identifier = "shield-2"
    mock_client.shields.list = mocker.AsyncMock(return_value=[shield1, shield2])

    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    mock_client.responses.create = mocker.AsyncMock(return_value=mocker.Mock())

    mocker.patch(
        "app.endpoints.streaming_query_v2.get_system_prompt", return_value="PROMPT"
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.configuration", mocker.Mock(mcp_servers=[])
    )

    qr = QueryRequest(query="hello")
    await retrieve_response(mock_client, "model-shields", qr, token="tok")

    # Verify that shields were passed in extra_body
    kwargs = mock_client.responses.create.call_args.kwargs
    assert "extra_body" in kwargs
    assert "guardrails" in kwargs["extra_body"]
    assert kwargs["extra_body"]["guardrails"] == ["shield-1", "shield-2"]


@pytest.mark.asyncio
async def test_retrieve_response_with_no_shields_available(
    mocker: MockerFixture,
) -> None:
    """Test that no extra_body is added when no shields are available."""
    mock_client = mocker.Mock()

    # Mock shields.list to return no shields
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    mock_client.responses.create = mocker.AsyncMock(return_value=mocker.Mock())

    mocker.patch(
        "app.endpoints.streaming_query_v2.get_system_prompt", return_value="PROMPT"
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.configuration", mocker.Mock(mcp_servers=[])
    )

    qr = QueryRequest(query="hello")
    await retrieve_response(mock_client, "model-no-shields", qr, token="tok")

    # Verify that no extra_body was added
    kwargs = mock_client.responses.create.call_args.kwargs
    assert "extra_body" not in kwargs


@pytest.mark.asyncio
async def test_streaming_response_detects_shield_violation(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that shield violations in streaming responses are detected and metrics incremented."""
    # Skip real config checks
    mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")

    # Model selection plumbing
    mock_client = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mocker.Mock()])
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )
    mocker.patch(
        "app.endpoints.streaming_query.evaluate_model_hints",
        return_value=(None, None),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("llama/m", "m", "p"),
    )

    # SSE helpers
    mocker.patch(
        "app.endpoints.streaming_query_v2.stream_start_event",
        lambda conv_id: f"START:{conv_id}\n",
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.format_stream_data",
        lambda obj: f"EV:{obj['event']}:{obj['data'].get('token','')}\n",
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.stream_end_event",
        lambda _m, _s, _t, _media: "END\n",
    )

    # Mock the cleanup function that handles all post-streaming database/cache work
    mocker.patch(
        "app.endpoints.streaming_query_v2.cleanup_after_streaming",
        mocker.AsyncMock(return_value=None),
    )

    # Mock the validation error metric
    validation_metric = mocker.patch("metrics.llm_calls_validation_errors_total")

    # Build a fake async stream with shield violation
    async def fake_stream_with_violation() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(
            type="response.created", response=SimpleNamespace(id="conv-violation")
        )
        yield SimpleNamespace(type="response.output_text.delta", delta="I cannot ")
        yield SimpleNamespace(type="response.output_text.done", text="I cannot help")
        # Response completed with refusal in output
        violation_item = SimpleNamespace(
            type="message",
            role="assistant",
            refusal="Content violates safety policy",
        )
        response_with_violation = SimpleNamespace(
            id="conv-violation", output=[violation_item]
        )
        yield SimpleNamespace(
            type="response.completed", response=response_with_violation
        )

    mocker.patch(
        "app.endpoints.streaming_query_v2.retrieve_response",
        return_value=(fake_stream_with_violation(), ""),
    )

    mocker.patch("metrics.llm_calls_total")

    resp = await streaming_query_endpoint_handler_v2(
        request=dummy_request,
        query_request=QueryRequest(query="dangerous query"),
        auth=("user123", "", True, "token-abc"),
        mcp_headers={},
    )

    assert isinstance(resp, StreamingResponse)

    # Collect emitted events to trigger the generator
    events: list[str] = []
    async for chunk in resp.body_iterator:
        s = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        events.append(s)

    # Verify that the validation error metric was incremented
    validation_metric.inc.assert_called_once()


@pytest.mark.asyncio
async def test_streaming_response_no_shield_violation(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that no metric is incremented when there's no shield violation in streaming."""
    # Skip real config checks
    mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")

    # Model selection plumbing
    mock_client = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mocker.Mock()])
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )
    mocker.patch(
        "app.endpoints.streaming_query.evaluate_model_hints",
        return_value=(None, None),
    )
    mocker.patch(
        "app.endpoints.streaming_query.select_model_and_provider_id",
        return_value=("llama/m", "m", "p"),
    )

    # SSE helpers
    mocker.patch(
        "app.endpoints.streaming_query_v2.stream_start_event",
        lambda conv_id: f"START:{conv_id}\n",
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.format_stream_data",
        lambda obj: f"EV:{obj['event']}:{obj['data'].get('token','')}\n",
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.stream_end_event",
        lambda _m, _s, _t, _media: "END\n",
    )

    # Mock the cleanup function that handles all post-streaming database/cache work
    mocker.patch(
        "app.endpoints.streaming_query_v2.cleanup_after_streaming",
        mocker.AsyncMock(return_value=None),
    )

    # Mock the validation error metric
    validation_metric = mocker.patch("metrics.llm_calls_validation_errors_total")

    # Build a fake async stream without violation
    async def fake_stream_without_violation() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(
            type="response.created", response=SimpleNamespace(id="conv-safe")
        )
        yield SimpleNamespace(type="response.output_text.delta", delta="Safe ")
        yield SimpleNamespace(type="response.output_text.done", text="Safe response")
        # Response completed without refusal
        safe_item = SimpleNamespace(
            type="message",
            role="assistant",
            refusal=None,  # No violation
        )
        response_safe = SimpleNamespace(id="conv-safe", output=[safe_item])
        yield SimpleNamespace(type="response.completed", response=response_safe)

    mocker.patch(
        "app.endpoints.streaming_query_v2.retrieve_response",
        return_value=(fake_stream_without_violation(), ""),
    )

    mocker.patch("metrics.llm_calls_total")

    resp = await streaming_query_endpoint_handler_v2(
        request=dummy_request,
        query_request=QueryRequest(query="safe query"),
        auth=("user123", "", True, "token-abc"),
        mcp_headers={},
    )

    assert isinstance(resp, StreamingResponse)

    # Collect emitted events to trigger the generator
    events: list[str] = []
    async for chunk in resp.body_iterator:
        s = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        events.append(s)

    # Verify that the validation error metric was NOT incremented
    validation_metric.inc.assert_not_called()
