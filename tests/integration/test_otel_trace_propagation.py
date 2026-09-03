"""Integration tests for OpenTelemetry trace context propagation.

Verifies that trace context is correctly propagated across service
boundaries and that spans share trace IDs with correct parent-child
relationships when flowing through the query endpoint and its
downstream components.
"""

import pytest
from fastapi import Request
from opentelemetry import context as otel_context
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.endpoints.query import query_endpoint_handler
from authentication.interface import AuthTuple
from models.api.requests import QueryRequest

KNOWN_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
KNOWN_PARENT_SPAN_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{KNOWN_TRACE_ID}-{KNOWN_PARENT_SPAN_ID}-01"


@pytest.fixture(autouse=True)
def _clear_spans(otel_collector: InMemorySpanExporter) -> None:
    """Clear collected spans before each test."""
    otel_collector.clear()


def _inject_w3c_context(traceparent: str) -> object:
    """Extract a W3C traceparent header into OTel context and attach it.

    Parameters:
        traceparent: W3C Trace Context header value.

    Returns:
        Context token to pass to ``otel_context.detach``.
    """
    ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
    return otel_context.attach(ctx)


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config", "mock_ogx_client", "mock_query_agent")
async def test_incoming_trace_context_is_continued(
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    otel_collector: InMemorySpanExporter,
) -> None:
    """Spans continue the trace ID received in a W3C traceparent header."""
    token = _inject_w3c_context(TRACEPARENT)
    try:
        await query_endpoint_handler(
            request=mock_request_with_auth,
            query_request=QueryRequest(  # pyright: ignore[reportCallIssue]
                query="What is Ansible?"
            ),
            auth=test_auth,
            mcp_headers={},
        )
    finally:
        otel_context.detach(token)  # pyright: ignore[reportArgumentType]

    spans = otel_collector.get_finished_spans()
    assert len(spans) > 0, "Expected at least one span"

    expected_trace_id = int(KNOWN_TRACE_ID, 16)
    for span in spans:
        assert span.context is not None
        assert span.context.trace_id == expected_trace_id, (
            f"Span {span.name!r} has trace_id "
            f"{span.context.trace_id:#034x}, expected {expected_trace_id:#034x}"
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config", "mock_ogx_client", "mock_query_agent")
async def test_root_span_is_child_of_incoming_parent(
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    otel_collector: InMemorySpanExporter,
) -> None:
    """The endpoint root span's parent points to the incoming span ID."""
    token = _inject_w3c_context(TRACEPARENT)
    try:
        await query_endpoint_handler(
            request=mock_request_with_auth,
            query_request=QueryRequest(  # pyright: ignore[reportCallIssue]
                query="What is Ansible?"
            ),
            auth=test_auth,
            mcp_headers={},
        )
    finally:
        otel_context.detach(token)  # pyright: ignore[reportArgumentType]

    spans = otel_collector.get_finished_spans()
    root_spans = [s for s in spans if s.name == "query.handle_request"]
    assert len(root_spans) == 1

    root = root_spans[0]
    assert (
        root.parent is not None
    ), "Root span should be a child of the incoming context"
    assert root.parent.span_id == int(KNOWN_PARENT_SPAN_ID, 16)


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config", "mock_ogx_client", "mock_query_agent")
async def test_spans_across_components_share_trace_id(
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    otel_collector: InMemorySpanExporter,
) -> None:
    """All spans emitted during a single request share the same trace ID."""
    await query_endpoint_handler(
        request=mock_request_with_auth,
        query_request=QueryRequest(  # pyright: ignore[reportCallIssue]
            query="What is Ansible?"
        ),
        auth=test_auth,
        mcp_headers={},
    )

    spans = otel_collector.get_finished_spans()
    assert len(spans) > 1, "Expected spans from multiple components"

    trace_ids = {span.context.trace_id for span in spans if span.context is not None}
    assert (
        len(trace_ids) == 1
    ), f"All spans must share one trace ID, got {len(trace_ids)}"


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config", "mock_ogx_client", "mock_query_agent")
async def test_parent_child_relationships_preserved(
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    otel_collector: InMemorySpanExporter,
) -> None:
    """Child spans (quota, shield, RAG, inference) are parented to the root span."""
    await query_endpoint_handler(
        request=mock_request_with_auth,
        query_request=QueryRequest(  # pyright: ignore[reportCallIssue]
            query="What is Ansible?"
        ),
        auth=test_auth,
        mcp_headers={},
    )

    spans = otel_collector.get_finished_spans()

    root_spans = [s for s in spans if s.name == "query.handle_request"]
    assert len(root_spans) == 1
    root = root_spans[0]
    assert root.context is not None

    child_spans = [s for s in spans if s.name != "query.handle_request"]
    assert len(child_spans) >= 1, "Expected at least one child span"

    for child in child_spans:
        assert child.parent is not None, f"Span {child.name!r} should have a parent"
        assert (
            child.parent.span_id == root.context.span_id
        ), f"Span {child.name!r} should be parented to query.handle_request"


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config", "mock_ogx_client", "mock_query_agent")
async def test_expected_child_spans_are_emitted(
    mock_request_with_auth: Request,
    test_auth: AuthTuple,
    otel_collector: InMemorySpanExporter,
) -> None:
    """The query flow emits the expected set of child spans."""
    await query_endpoint_handler(
        request=mock_request_with_auth,
        query_request=QueryRequest(  # pyright: ignore[reportCallIssue]
            query="What is Ansible?"
        ),
        auth=test_auth,
        mcp_headers={},
    )

    span_names = {s.name for s in otel_collector.get_finished_spans()}

    expected = {
        "query.handle_request",
        "quota.check",
        "shield.moderate",
        "llm.inference",
    }
    missing = expected - span_names
    assert not missing, f"Missing expected spans: {missing}"
