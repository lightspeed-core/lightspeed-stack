# pylint: disable=too-many-arguments,too-many-positional-arguments
"""Shared helpers for responses endpoint OpenTelemetry unit tests."""

from collections.abc import AsyncIterator, Sequence
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse
from ogx_client import AsyncOgxClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import Tracer
from pytest_mock import MockerFixture

from app.endpoints.responses import responses_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from models.common.responses.responses_conversation_context import (
    ResponsesConversationContext,
)
from models.common.turn_summary import ToolCallSummary, TurnSummary
from utils.otel_tracing import SpanAttributes, SpanEvents

MODULE = "app.endpoints.responses"
UTILS_RESPONSES_MODULE = "utils.responses"
VECTOR_SEARCH_MODULE = "utils.vector_search"

MOCK_AUTH: AuthTuple = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)
OTEL_CONV_ID = "conv_e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
OTEL_SESSION_ID = "e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
MODEL = "google-vertex/publishers/google/models/gemini-2.5-flash"
ROOT_SPAN_NAME = "responses.handle_request"


def find_span(spans: Sequence[ReadableSpan], name: str) -> ReadableSpan:
    """Return the single finished span with the given name."""
    matches = [span for span in spans if span.name == name]
    assert len(matches) == 1, f"Expected one span named {name!r}, got {len(matches)}"
    return matches[0]


def make_turn_summary_without_tools(
    *,
    llm_response: str = "The answer is 42",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> TurnSummary:
    """Build a turn summary with no tool calls."""
    turn_summary = TurnSummary()
    turn_summary.llm_response = llm_response
    turn_summary.token_usage.input_tokens = input_tokens
    turn_summary.token_usage.output_tokens = output_tokens
    return turn_summary


def make_turn_summary_with_tools(
    tool_names: list[str],
    *,
    llm_response: str = "The answer is 42",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> TurnSummary:
    """Build a turn summary containing the given tool call names."""
    turn_summary = make_turn_summary_without_tools(
        llm_response=llm_response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    turn_summary.tool_calls = [
        ToolCallSummary(id=f"call-{index}", name=name, args={})
        for index, name in enumerate(tool_names)
    ]
    return turn_summary


def patch_responses_otel_tracers(
    mocker: MockerFixture,
    tracer: Tracer,
    minimal_config: AppConfig,
) -> None:
    """Patch responses and downstream tracers to use the test tracer."""
    mocker.patch(f"{MODULE}.configuration", minimal_config)
    mocker.patch(f"{MODULE}.tracer", tracer)
    mocker.patch(f"{UTILS_RESPONSES_MODULE}.tracer", tracer)
    mocker.patch("utils.shields.tracer", tracer)
    mocker.patch("utils.quota_utils.tracer", tracer)
    mocker.patch("utils.vector_search.tracer", tracer)
    mocker.patch(
        f"{MODULE}.anonymize_value",
        side_effect=lambda value: f"[anon:{value}]",
    )
    mocker.patch(
        f"{VECTOR_SEARCH_MODULE}._fetch_byok_rag",
        new=mocker.AsyncMock(return_value=([], [])),
    )
    mocker.patch(
        f"{VECTOR_SEARCH_MODULE}._fetch_okp_rag",
        new=mocker.AsyncMock(return_value=([], [])),
    )


def patch_responses_endpoint_setup(
    mocker: MockerFixture,
    _minimal_config: AppConfig,
) -> Any:
    """Patch endpoint setup dependencies and return the mock OGX client.

    Returns:
        Mock AsyncOgxClient wired through AsyncOgxClientHolder.
    """
    mocker.patch(f"{MODULE}.check_configuration_loaded")
    mocker.patch(f"{MODULE}.validate_model_provider_override")
    mocker.patch(
        f"{UTILS_RESPONSES_MODULE}.prepare_tools",
        new=mocker.AsyncMock(return_value=None),
    )

    mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.list = mocker.AsyncMock(return_value=mocker.Mock(data=[]))
    mock_client.vector_stores = mock_vector_stores
    mock_holder = mocker.Mock()
    mock_holder.get_client.return_value = mock_client
    mocker.patch(f"{MODULE}.AsyncOgxClientHolder", return_value=mock_holder)

    mocker.patch(
        f"{MODULE}.resolve_response_context",
        new=mocker.AsyncMock(
            return_value=ResponsesConversationContext(
                conversation=OTEL_CONV_ID,
                user_conversation=None,
                generate_topic_summary=False,
            )
        ),
    )
    mocker.patch(
        f"{MODULE}.select_model_for_responses",
        new=mocker.AsyncMock(return_value="provider1/model1"),
    )
    mocker.patch(
        f"{MODULE}.check_model_configured",
        new=mocker.AsyncMock(return_value=True),
    )
    return mock_client


def patch_handler_success_mocks(mocker: MockerFixture) -> None:
    """Patch inference, quota, and persistence helpers for a success path."""
    mocker.patch(f"{MODULE}.recording.record_llm_inference_duration")
    mocker.patch(f"{MODULE}.consume_query_tokens")
    mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
    mocker.patch(
        f"{MODULE}.extract_provider_and_model_from_model_id",
        return_value=("provider1", "model1"),
    )
    mocker.patch(
        f"{MODULE}.extract_token_usage",
        return_value=TurnSummary().token_usage,
    )
    mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
    mocker.patch(
        f"{MODULE}.build_turn_summary",
        return_value=TurnSummary(referenced_documents=[]),
    )
    mocker.patch(f"{MODULE}.store_query_results")
    mocker.patch(
        f"{MODULE}.normalize_conversation_id",
        return_value=OTEL_SESSION_ID,
    )


def configure_non_streaming_client(
    mocker: MockerFixture,
    mock_client: Any,
    *,
    output_text: str = "The answer is 42",
) -> None:
    """Configure mock_client.responses.create for a non-streaming success response."""
    mock_response = mocker.Mock()
    mock_response.id = "resp_1"
    mock_response.output = []
    mock_response.usage = mocker.Mock(input_tokens=10, output_tokens=5, total_tokens=15)
    mock_response.status = "completed"
    mock_response.model = "provider1/model1"
    mock_response.model_dump.return_value = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "provider1/model1",
        "output": [],
        "conversation": OTEL_CONV_ID,
        "completed_at": 0,
        "output_text": output_text,
        "available_quotas": {},
    }
    mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)
    mocker.patch(
        f"{MODULE}.extract_text_from_response_items",
        return_value=output_text,
    )


def make_completed_stream_chunk(mocker: MockerFixture) -> Any:
    """Build a minimal response.completed streaming chunk mock."""
    mock_chunk = mocker.Mock()
    mock_chunk.type = "response.completed"
    mock_chunk.response = mocker.Mock(
        id="r1",
        output=[],
        usage=mocker.Mock(input_tokens=1, output_tokens=2, total_tokens=3),
    )
    mock_chunk.model_dump.return_value = {
        "type": "response.completed",
        "response": {"id": "r1", "usage": {"input_tokens": 1}},
    }
    return mock_chunk


def configure_streaming_client(mocker: MockerFixture, mock_client: Any) -> None:
    """Configure mock_client.responses.create for a one-chunk streaming success."""

    async def mock_stream() -> AsyncIterator[Any]:
        yield make_completed_stream_chunk(mocker)

    mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())
    mocker.patch(
        f"{MODULE}.extract_text_from_response_items",
        return_value="Hello",
    )


def assert_root_setup_attributes(
    root: ReadableSpan,
    *,
    input_text: str,
    attachments_count: int = 0,
) -> None:
    """Assert root span carries setup attributes and validation.completed."""
    assert root.name == ROOT_SPAN_NAME
    assert root.attributes is not None
    assert root.attributes[SpanAttributes.USER_ID] == f"[anon:{MOCK_AUTH[0]}]"
    assert root.attributes[SpanAttributes.INPUT] == f"[anon:{input_text}]"
    assert (
        root.attributes[SpanAttributes.REQUEST_ATTACHMENTS_COUNT] == attachments_count
    )
    assert root.attributes[SpanAttributes.SESSION_ID] == OTEL_SESSION_ID
    event_names = [event.name for event in root.events]
    assert SpanEvents.VALIDATION_COMPLETED in event_names


async def consume_streaming_response(response: StreamingResponse) -> None:
    """Drain a StreamingResponse body so spans are finalized."""
    async for _ in response.body_iterator:
        pass


async def run_responses_setup_smoke(
    mocker: MockerFixture,
    dummy_request: Request,
    tracer: Tracer,
    minimal_config: AppConfig,
    exporter: InMemorySpanExporter,
    *,
    stream: bool,
    input_text: str = "What is Kubernetes?",
) -> ReadableSpan:
    """Run the handler through setup and return the root span."""
    patch_responses_otel_tracers(mocker, tracer, minimal_config)
    mock_client = patch_responses_endpoint_setup(mocker, minimal_config)
    patch_handler_success_mocks(mocker)

    if stream:
        configure_streaming_client(mocker, mock_client)
    else:
        configure_non_streaming_client(mocker, mock_client)

    result = await responses_endpoint_handler(
        request=dummy_request,
        responses_request=ResponsesRequest(
            input=input_text,
            model=MODEL,
            stream=stream,
            store=False,
            conversation=OTEL_CONV_ID,
            generate_topic_summary=False,
        ),
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    if stream:
        assert isinstance(result, StreamingResponse)
        await consume_streaming_response(result)
    else:
        assert isinstance(result, ResponsesResponse)

    return find_span(exporter.get_finished_spans(), ROOT_SPAN_NAME)
