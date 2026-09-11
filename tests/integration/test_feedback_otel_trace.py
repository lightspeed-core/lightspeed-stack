"""Integration tests for OpenTelemetry span tree on POST /feedback.

This module covers the component interaction the feedback handler produces:
the ``feedback.storage`` span is opened inside the ``feedback.submit`` span,
so the two must share a trace and ``feedback.storage`` must be parented to
``feedback.submit``.
"""

from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.feedback import feedback_endpoint_handler
from authentication.interface import AuthTuple
from configuration import configuration
from models.api.requests import FeedbackRequest
from models.common.feedback import FeedbackCategory

ROOT_SPAN_NAME = "feedback.submit"
STORAGE_SPAN_NAME = "feedback.storage"
FEEDBACK_CONVERSATION_ID = "12345678-abcd-0000-0123-456789abcdef"


@pytest.fixture(autouse=True)
def _clear_spans(otel_collector: InMemorySpanExporter) -> None:
    """Clear collected spans before each test."""
    otel_collector.clear()


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config")
async def test_feedback_storage_span_nested_under_submit(
    tmp_path: Path,
    test_auth: AuthTuple,
    otel_collector: InMemorySpanExporter,
    mocker: MockerFixture,
) -> None:
    """POST /feedback nests feedback.storage under feedback.submit.

    Feedback storage is pointed at a writable temp directory so the real
    filesystem write drives a successful storage span. The test asserts only the
    parent-child hierarchy: both spans exist, share a single trace, and
    ``feedback.storage`` is parented to ``feedback.submit``. Individual span
    attributes and events are covered at the unit level.

    Args:
        tmp_path: Writable temp directory used as the feedback storage location.
        test_auth: Authentication tuple from the real noop auth dependency.
        otel_collector: In-memory OTEL exporter collecting finished spans.
        mocker: pytest-mock fixture used to patch conversation retrieval.
    """
    user_id, _, _, _ = test_auth
    configuration.user_data_collection_configuration.feedback_storage = str(tmp_path)

    # The conversation must exist and belong to the authenticated user.
    mock_conversation = mocker.Mock()
    mock_conversation.user_id = user_id
    mocker.patch(
        "app.endpoints.feedback.retrieve_conversation",
        return_value=mock_conversation,
    )

    result = await feedback_endpoint_handler(
        feedback_request=FeedbackRequest(
            conversation_id=FEEDBACK_CONVERSATION_ID,
            user_question="What is Kubernetes?",
            llm_response="Kubernetes is an open-source container orchestrator.",
            user_feedback="The answer was too vague.",
            sentiment=-1,
            categories=[FeedbackCategory.INCORRECT, FeedbackCategory.INCOMPLETE],
        ),
        auth=test_auth,
        _ensure_feedback_enabled=None,
    )
    assert result.response == "feedback received"

    spans = otel_collector.get_finished_spans()
    span_names = {span.name for span in spans}
    missing = {ROOT_SPAN_NAME, STORAGE_SPAN_NAME} - span_names
    assert not missing, f"Missing expected spans: {missing}"

    root = next(span for span in spans if span.name == ROOT_SPAN_NAME)
    storage = next(span for span in spans if span.name == STORAGE_SPAN_NAME)
    assert root.context is not None
    assert storage.context is not None

    assert root.context.trace_id == storage.context.trace_id
    assert storage.parent is not None, "feedback.storage should have a parent"
    assert (
        storage.parent.span_id == root.context.span_id
    ), "feedback.storage should be parented to feedback.submit"
