# pylint: disable=redefined-outer-name
"""OpenTelemetry unit tests for the /query REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from ogx_client import AsyncOgxClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.query import query_endpoint_handler
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.api.responses.error import QuotaExceededResponse
from models.common.moderation import ShieldModerationPassed
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import TurnSummary
from quota.quota_exceed_error import QuotaExceedError
from utils.otel_tracing import SpanAttributes, SpanEvents

MODULE = "app.endpoints.query"
QUERY_SPAN_NAME = "query.handle_request"
QUERY_TEXT = "What is Kubernetes?"

# User ID must be a proper UUID.
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture(name="dummy_request")
def dummy_request_fixture() -> Request:
    """Minimal FastAPI Request for query endpoint unit tests."""
    return Request(scope={"type": "http", "headers": []})


@pytest.fixture(name="minimal_config")
def minimal_config_fixture() -> AppConfig:
    """Minimal AppConfig for query endpoint OTEL tests."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "ogx": {
                "api_key": "test-key",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {"transcripts_enabled": False},
            "mcp_servers": [],
            "conversation_cache": {"type": "noop"},
        }
    )
    return cfg


def _patch_query_success(mocker: MockerFixture) -> None:
    """Patch the query handler dependencies for a successful turn."""
    mocker.patch(f"{MODULE}.check_configuration_loaded")
    mocker.patch(f"{MODULE}.check_tokens_available")
    mocker.patch(f"{MODULE}.validate_model_provider_override")
    mocker.patch(f"{MODULE}.check_mcp_auth", new=mocker.AsyncMock())

    mock_response_obj = mocker.Mock()
    mock_response_obj.output = []
    mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
    mock_client.responses = mocker.Mock()
    mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
    mock_holder = mocker.Mock()
    mock_holder.get_client.return_value = mock_client
    mocker.patch(f"{MODULE}.AsyncOgxClientHolder", return_value=mock_holder)

    mocker.patch(
        f"{MODULE}.maybe_get_topic_summary",
        new=mocker.AsyncMock(return_value=None),
    )
    mocker.patch(
        f"{MODULE}.run_shield_moderation",
        new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
    )

    mock_params = mocker.Mock(spec=ResponsesApiParams)
    mock_params.model = "provider1/model1"
    mock_params.conversation = "conv_123"
    mock_params.tools = None
    mock_params.model_dump.return_value = {"input": "test", "model": "provider1/model1"}
    mocker.patch(
        f"{MODULE}.prepare_responses_params",
        new=mocker.AsyncMock(return_value=mock_params),
    )

    turn_summary = TurnSummary()
    turn_summary.llm_response = "Kubernetes is a container orchestration platform"
    mocker.patch(
        f"{MODULE}.retrieve_agent_response",
        new=mocker.AsyncMock(return_value=turn_summary),
    )

    mocker.patch(f"{MODULE}.normalize_conversation_id", return_value="123")
    mocker.patch(f"{MODULE}.store_query_results")
    mocker.patch(f"{MODULE}.consume_query_tokens")
    mocker.patch(f"{MODULE}.get_available_quotas", return_value={})


@pytest.mark.asyncio
async def test_query_root_span_attributes_and_events(
    dummy_request: Request,
    minimal_config: AppConfig,
    mocker: MockerFixture,
    otel: tuple[Any, InMemorySpanExporter],
) -> None:
    """The /query root span carries setup attributes and all lifecycle events.

    The mocked success path validates the request, persists the turn, and
    completes the LLM response, so the validation/turn-persisted/LLM-response
    events are all recorded, and the anonymized user/input attributes are set.
    """
    tracer, exporter = otel
    mocker.patch(f"{MODULE}.configuration", minimal_config)
    mocker.patch(f"{MODULE}.tracer", tracer)
    mocker.patch(
        f"{MODULE}.anonymize_value", side_effect=lambda value: f"[anon:{value}]"
    )
    _patch_query_success(mocker)

    await query_endpoint_handler(
        request=dummy_request,
        query_request=QueryRequest(
            query=QUERY_TEXT
        ),  # pyright: ignore[reportCallIssue]
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    root = next(s for s in exporter.get_finished_spans() if s.name == QUERY_SPAN_NAME)
    attrs = dict(root.attributes or {})
    assert attrs[SpanAttributes.USER_ID] == f"[anon:{MOCK_AUTH[0]}]"
    assert attrs[SpanAttributes.INPUT] == f"[anon:{QUERY_TEXT}]"
    assert attrs[SpanAttributes.REQUEST_ATTACHMENTS_COUNT] == 0
    assert SpanAttributes.OUTPUT in attrs
    assert SpanAttributes.SESSION_ID in attrs

    event_names = {event.name for event in root.events}
    assert SpanEvents.VALIDATION_COMPLETED in event_names
    assert SpanEvents.TURN_PERSISTED in event_names
    assert SpanEvents.LLM_RESPONSE_COMPLETED in event_names


@pytest.mark.asyncio
async def test_query_quota_exceeded_records_attributes_without_events(
    dummy_request: Request,
    minimal_config: AppConfig,
    mocker: MockerFixture,
    otel: tuple[Any, InMemorySpanExporter],
) -> None:
    """A 429 from the quota check leaves the root span attributes but no events.

    The quota check runs after the root attributes are recorded but before any
    lifecycle event fires. When it raises HTTP 429 the request is aborted, so the
    ``query.handle_request`` span is still exported with its user/input
    attributes, but none of the validation/turn-persisted/LLM-response events are
    recorded, and tracing does not crash on the error path.
    """
    tracer, exporter = otel
    mocker.patch(f"{MODULE}.configuration", minimal_config)
    mocker.patch(f"{MODULE}.tracer", tracer)
    mocker.patch(
        f"{MODULE}.anonymize_value", side_effect=lambda value: f"[anon:{value}]"
    )
    mocker.patch(f"{MODULE}.check_configuration_loaded")
    mocker.patch(f"{MODULE}.check_mcp_auth", new=mocker.AsyncMock())

    def _raise_quota_exceeded(*_args: object, **_kwargs: object) -> None:
        error = QuotaExceedError(subject_id=MOCK_AUTH[0], subject_type="u", available=0)
        raise HTTPException(**QuotaExceededResponse.from_exception(error).model_dump())

    mocker.patch(f"{MODULE}.check_tokens_available", side_effect=_raise_quota_exceeded)

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(  # pyright: ignore[reportCallIssue]
                query=QUERY_TEXT
            ),
            auth=MOCK_AUTH,
            mcp_headers={},
        )
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    root = next(s for s in exporter.get_finished_spans() if s.name == QUERY_SPAN_NAME)
    attrs = dict(root.attributes or {})
    assert attrs[SpanAttributes.USER_ID] == f"[anon:{MOCK_AUTH[0]}]"
    assert attrs[SpanAttributes.INPUT] == f"[anon:{QUERY_TEXT}]"
    assert attrs[SpanAttributes.REQUEST_ATTACHMENTS_COUNT] == 0

    event_names = {event.name for event in root.events}
    assert SpanEvents.VALIDATION_COMPLETED not in event_names
    assert SpanEvents.TURN_PERSISTED not in event_names
    assert SpanEvents.LLM_RESPONSE_COMPLETED not in event_names
