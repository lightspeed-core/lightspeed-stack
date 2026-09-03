"""Integration tests for OpenTelemetry span tree on POST /v1/responses."""

from collections.abc import Sequence
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.responses import responses_endpoint_handler
from models.api.requests import ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from tests.integration.endpoints.test_responses_integration import (
    MOCK_AUTH,
    _setup_test,
)
from tests.unit.app.endpoints.responses_otel_helpers import (
    configure_streaming_client,
    consume_streaming_response,
)

ROOT_SPAN_NAME = "responses.handle_request"
EXPECTED_OPERATIONAL_SPANS = {
    "quota.check",
    "shield.moderate",
    "rag.retrieve",
    "llm.inference",
}


@pytest.fixture(autouse=True)
def _clear_spans(otel_collector: InMemorySpanExporter) -> None:
    """Clear collected spans before each test."""
    otel_collector.clear()


def _assert_span_tree_parentage(spans: Sequence[Any], root_name: str) -> None:
    """Assert expected operational spans exist and nest under the root."""
    span_names = {span.name for span in spans}
    missing = (EXPECTED_OPERATIONAL_SPANS | {root_name}) - span_names
    assert not missing, f"Missing expected spans: {missing}"

    root = next(span for span in spans if span.name == root_name)
    assert root.context is not None

    trace_ids = {span.context.trace_id for span in spans if span.context is not None}
    assert len(trace_ids) == 1

    child_spans = [span for span in spans if span.name != root_name]
    assert child_spans, "Expected at least one child span"

    for child in child_spans:
        assert child.parent is not None, f"Span {child.name!r} should have a parent"
        assert (
            child.parent.span_id == root.context.span_id
        ), f"Span {child.name!r} should be parented to {root_name}"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.usefixtures("test_config")
async def test_responses_span_tree_parentage(
    stream: bool,
    mocker: MockerFixture,
    mock_request_with_auth: Request,
    otel_collector: InMemorySpanExporter,
) -> None:
    """Responses emits expected spans with correct parentage for both stream modes."""
    mock_client = _setup_test(mocker)
    if stream:
        configure_streaming_client(mocker, mock_client)

    result = await responses_endpoint_handler(
        request=mock_request_with_auth,
        responses_request=ResponsesRequest(
            input="What is Ansible?",
            model="test-provider/test-model",
            stream=stream,
            store=False,
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

    _assert_span_tree_parentage(otel_collector.get_finished_spans(), ROOT_SPAN_NAME)
