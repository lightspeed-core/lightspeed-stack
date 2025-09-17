# pylint: disable=redefined-outer-name, import-error
"""Unit tests for the /streaming_query (v2) endpoint using Responses API."""

from types import SimpleNamespace
import pytest
from fastapi import HTTPException, status, Request
from fastapi.responses import StreamingResponse

from llama_stack_client import APIConnectionError

from models.requests import QueryRequest
from models.config import ModelContextProtocolServer

from app.endpoints.streaming_query_v2 import (
    retrieve_response,
    streaming_query_endpoint_handler_v2,
)


@pytest.fixture
def dummy_request() -> Request:
    req = Request(scope={"type": "http"})
    # Provide a permissive authorized_actions set to satisfy RBAC check
    from models.config import Action  # import here to avoid global import errors

    req.state.authorized_actions = set(Action)
    return req


@pytest.mark.asyncio
async def test_retrieve_response_builds_rag_and_mcp_tools(mocker):
    mock_client = mocker.Mock()
    mock_client.vector_dbs.list = mocker.AsyncMock(
        return_value=[mocker.Mock(identifier="db1")]
    )
    mock_client.responses.create = mocker.AsyncMock(return_value=mocker.Mock())

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
async def test_retrieve_response_no_tools_passes_none(mocker):
    mock_client = mocker.Mock()
    mock_client.vector_dbs.list = mocker.AsyncMock(return_value=[])
    mock_client.responses.create = mocker.AsyncMock(return_value=mocker.Mock())

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
    mocker, dummy_request
):
    # Skip real config checks
    mocker.patch("app.endpoints.streaming_query_v2.check_configuration_loaded")

    # Model selection plumbing
    mock_client = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mocker.Mock()])
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.evaluate_model_hints",
        return_value=(None, None),
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.select_model_and_provider_id",
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
        "app.endpoints.streaming_query_v2.stream_end_event", lambda _m: "END\n"
    )

    # Conversation persistence and transcripts disabled
    persist_spy = mocker.patch(
        "app.endpoints.streaming_query_v2.persist_user_conversation_details",
        return_value=None,
    )
    mocker.patch(
        "app.endpoints.streaming_query_v2.is_transcripts_enabled", return_value=False
    )

    # Build a fake async stream of chunks
    async def fake_stream():
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
        auth=("user123", "", False, "token-abc"),
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

    # Verify conversation persistence was invoked with the created id
    persist_spy.assert_called_once()


@pytest.mark.asyncio
async def test_streaming_query_endpoint_handler_v2_api_connection_error(
    mocker, dummy_request
):
    mocker.patch("app.endpoints.streaming_query_v2.check_configuration_loaded")

    def _raise(*_a, **_k):
        raise APIConnectionError(request=None)

    mocker.patch("client.AsyncLlamaStackClientHolder.get_client", side_effect=_raise)

    fail_metric = mocker.patch("metrics.llm_calls_failures_total")

    with pytest.raises(HTTPException) as exc:
        await streaming_query_endpoint_handler_v2(
            request=dummy_request,
            query_request=QueryRequest(query="hi"),
            auth=("user123", "", False, "tok"),
            mcp_headers={},
        )

    assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Unable to connect to Llama Stack" in str(exc.value.detail)
    fail_metric.inc.assert_called_once()
