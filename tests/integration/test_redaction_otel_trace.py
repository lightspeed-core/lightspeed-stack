"""Integration tests: real handlers -> RedactingSpanExporter -> collector.

These complement the exporter unit tests (``test_redacting_span_exporter.py``),
which feed hand-built spans. Here the *real* request handlers emit the spans, so
the tests pin down which attributes each handler actually sets and whether the
in-process redaction scrubs them. That is the gap fake spans cannot cover: if a
handler starts writing user input into a new span attribute and nobody adds it to
``CONTENT_ATTRIBUTES``, only a handler-driven test notices.

Redaction here uses ``FakeAnonymizer`` (see conftest), not Presidio: it replaces a
single sentinel token. Presidio's detection accuracy is out of scope — these tests
verify wiring and attribute coverage, including the deliberate non-redaction of
``request.safety_identifier``.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
from ogx_client.models.open_ai_response_object import OpenAIResponseObject
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.feedback import feedback_endpoint_handler
from app.endpoints.responses import responses_endpoint_handler
from authentication.interface import AuthTuple
from configuration import configuration
from models.api.requests import FeedbackRequest, ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from models.common.feedback import FeedbackCategory
from tests.integration.conftest import REDACTION_MARKER, REDACTION_SENTINEL
from tests.integration.endpoints.test_query_byok_integration import (
    _make_byok_vector_io_response,
)
from tests.integration.endpoints.test_responses_byok_integration import (
    _build_responses_mock_client,
    _patch_all_client_holders,
)
from tests.integration.endpoints.test_responses_integration import (
    MOCK_AUTH,
    _setup_test,
)

RESPONSES_ROOT_SPAN = "responses.handle_request"
RAG_SPAN = "rag.retrieve"
FEEDBACK_ROOT_SPAN = "feedback.submit"


def _span(spans: Sequence[ReadableSpan], name: str) -> ReadableSpan:
    """Return the first finished span with ``name`` (fails with a helpful list)."""
    matches = [s for s in spans if s.name == name]
    assert matches, f"span {name!r} not in {sorted({s.name for s in spans})}"
    return matches[0]


def _attr(span: ReadableSpan, key: str) -> Any:
    """Return a span attribute value (fails if the attribute is absent)."""
    assert span.attributes is not None and key in span.attributes, (
        f"attribute {key!r} not on span {span.name!r}: "
        f"{dict(span.attributes or {})}"
    )
    return span.attributes[key]


def _responses_output_dump(text: str) -> dict[str, Any]:
    """Minimal OGX responses.create payload whose output text is ``text``."""
    return {
        "id": "resp_redaction_test",
        "object": "response",
        "created_at": 1700000000,
        "status": "completed",
        "model": "test-provider/test-model",
        "store": False,
        "output": [
            {
                "type": "message",
                "id": "msg-1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config")
async def test_responses_input_and_output_are_redacted(
    mocker: MockerFixture,
    mock_request_with_auth: Request,
    redacting_otel_collector: InMemorySpanExporter,
) -> None:
    """request.input and response.output are scrubbed on the responses root span."""
    mock_client = _setup_test(mocker)
    # Make the (mocked) LLM echo the sentinel so response.output carries PII too.
    mock_client.responses.create = mocker.AsyncMock(
        return_value=OpenAIResponseObject.from_dict(
            _responses_output_dump(f"Sure, reaching {REDACTION_SENTINEL} now.")
        )
    )

    result = await responses_endpoint_handler(
        request=mock_request_with_auth,
        responses_request=ResponsesRequest(
            input=f"Contact me at {REDACTION_SENTINEL} please",
            model="test-provider/test-model",
            stream=False,
            store=False,
            generate_topic_summary=False,
        ),
        auth=MOCK_AUTH,
        mcp_headers={},
    )
    assert isinstance(result, ResponsesResponse)

    root = _span(redacting_otel_collector.get_finished_spans(), RESPONSES_ROOT_SPAN)
    request_input = _attr(root, "request.input")
    response_output = _attr(root, "response.output")

    assert REDACTION_SENTINEL not in request_input
    assert REDACTION_MARKER in request_input
    assert REDACTION_SENTINEL not in response_output
    assert REDACTION_MARKER in response_output


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config")
async def test_feedback_comment_is_redacted(
    tmp_path: Path,
    test_auth: AuthTuple,
    mocker: MockerFixture,
    redacting_otel_collector: InMemorySpanExporter,
) -> None:
    """feedback.comment is scrubbed on the feedback.submit span."""
    user_id, _, _, _ = test_auth
    configuration.user_data_collection_configuration.feedback_storage = str(tmp_path)

    mock_conversation = mocker.Mock()
    mock_conversation.user_id = user_id
    mocker.patch(
        "app.endpoints.feedback.retrieve_conversation",
        return_value=mock_conversation,
    )

    await feedback_endpoint_handler(
        feedback_request=FeedbackRequest(
            conversation_id="12345678-abcd-0000-0123-456789abcdef",
            user_question="What is Kubernetes?",
            llm_response="Kubernetes is a container orchestrator.",
            user_feedback=f"Call me at {REDACTION_SENTINEL} to discuss.",
            sentiment=-1,
            categories=[FeedbackCategory.INCORRECT],
        ),
        auth=test_auth,
        _ensure_feedback_enabled=None,
    )

    root = _span(redacting_otel_collector.get_finished_spans(), FEEDBACK_ROOT_SPAN)
    comment = _attr(root, "feedback.comment")
    assert REDACTION_SENTINEL not in comment
    assert REDACTION_MARKER in comment


@pytest.mark.asyncio
async def test_rag_input_is_redacted(
    test_config: Any,
    mocker: MockerFixture,
    test_request: Request,
    redacting_otel_collector: InMemorySpanExporter,
) -> None:
    """rag.input is scrubbed on the rag.retrieve span when inline BYOK RAG runs."""
    entry = mocker.MagicMock()
    entry.rag_id = "test-knowledge"
    entry.vector_db_id = "vs-byok-knowledge"
    entry.score_multiplier = 1.0
    test_config.configuration.rag.byok.stores = [entry]
    test_config.configuration.rag.retrieval.inline.sources = ["test-knowledge"]

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)
    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )
    mock_client.vector_stores.list.return_value = []

    await responses_endpoint_handler(
        request=test_request,
        responses_request=ResponsesRequest(
            input=f"What is {REDACTION_SENTINEL}?",
            stream=False,
        ),
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    rag = _span(redacting_otel_collector.get_finished_spans(), RAG_SPAN)
    rag_input = _attr(rag, "rag.input")
    assert REDACTION_SENTINEL not in rag_input
    assert REDACTION_MARKER in rag_input


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config")
async def test_safety_identifier_is_not_redacted(
    mocker: MockerFixture,
    mock_request_with_auth: Request,
    redacting_otel_collector: InMemorySpanExporter,
) -> None:
    """safety_identifier is a caller tracking id and must survive redaction verbatim.

    Proves the exporter scrubs an allow-list of content fields, not every attribute.
    """
    _setup_test(mocker)

    await responses_endpoint_handler(
        request=mock_request_with_auth,
        responses_request=ResponsesRequest(
            input="What is Ansible?",
            model="test-provider/test-model",
            stream=False,
            store=False,
            generate_topic_summary=False,
            safety_identifier=f"caller-{REDACTION_SENTINEL}",
        ),
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    root = _span(redacting_otel_collector.get_finished_spans(), RESPONSES_ROOT_SPAN)
    safety_id = _attr(root, "request.safety_identifier")
    assert safety_id == f"caller-{REDACTION_SENTINEL}"
    assert REDACTION_MARKER not in safety_id


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config")
async def test_pii_free_input_exports_unchanged(
    mocker: MockerFixture,
    mock_request_with_auth: Request,
    redacting_otel_collector: InMemorySpanExporter,
) -> None:
    """A request with no PII exports normally and the content is left untouched.

    (``request.input`` cannot be empty — the request model rejects that — so a
    PII-free value is the realistic "nothing to redact" case: export still happens
    and no redaction marker is introduced.)
    """
    _setup_test(mocker)

    original_input = "What is Ansible?"
    await responses_endpoint_handler(
        request=mock_request_with_auth,
        responses_request=ResponsesRequest(
            input=original_input,
            model="test-provider/test-model",
            stream=False,
            store=False,
            generate_topic_summary=False,
        ),
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    root = _span(redacting_otel_collector.get_finished_spans(), RESPONSES_ROOT_SPAN)
    request_input = _attr(root, "request.input")
    assert request_input == original_input
    assert REDACTION_MARKER not in request_input


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_config")
async def test_no_user_pii_leaks_across_any_span_attribute(
    mocker: MockerFixture,
    mock_request_with_auth: Request,
    redacting_otel_collector: InMemorySpanExporter,
) -> None:
    """Regression guard: the sentinel must not survive in ANY content attribute.

    safety_identifier is the sole intentional exception. This is the test that would
    have caught ``tool_calls`` leaking: it does not enumerate known fields, so a new
    handler attribute echoing user input fails it automatically.
    """
    mock_client = _setup_test(mocker)
    mock_client.responses.create = mocker.AsyncMock(
        return_value=OpenAIResponseObject.from_dict(
            _responses_output_dump(f"Noted: {REDACTION_SENTINEL}.")
        )
    )

    await responses_endpoint_handler(
        request=mock_request_with_auth,
        responses_request=ResponsesRequest(
            input=f"Reach {REDACTION_SENTINEL} today",
            model="test-provider/test-model",
            stream=False,
            store=False,
            generate_topic_summary=False,
        ),
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    leaks: list[str] = []
    for span in redacting_otel_collector.get_finished_spans():
        for key, value in dict(span.attributes or {}).items():
            if key == "request.safety_identifier":
                continue
            if isinstance(value, str) and REDACTION_SENTINEL in value:
                leaks.append(f"{span.name}.{key}")

    assert not leaks, f"unredacted PII leaked into span attributes: {leaks}"
