# pylint: disable=redefined-outer-name
"""OpenTelemetry unit tests for the /responses REST API endpoint."""

from collections.abc import Sequence
from typing import Any, cast

import pytest
from fastapi import HTTPException, Request
from ogx_client import ApiException
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.responses import (
    _complete_llm_inference_span,
    _finalize_responses_root_span,
    _record_inference_span_exception,
    _start_llm_inference_span,
    responses_endpoint_handler,
)
from configuration import AppConfig
from models.api.requests import ResponsesRequest
from models.api.responses.error import ServiceUnavailableResponse
from models.config import Action
from tests.unit.app.endpoints.responses_otel_helpers import (
    MOCK_AUTH,
    MODULE,
    assert_root_setup_attributes,
    find_span,
    make_turn_summary_with_tools,
    make_turn_summary_without_tools,
    patch_responses_endpoint_setup,
    patch_responses_otel_tracers,
    run_responses_setup_smoke,
)
from utils.otel_tracing import SpanAttributes, SpanEvents

INPUT_TEXT = "What is Kubernetes?"


@pytest.fixture(name="dummy_request")
def dummy_request_fixture() -> Request:
    """Minimal FastAPI Request with authorized_actions for responses endpoint."""
    req = Request(scope={"type": "http", "headers": []})
    req.state.authorized_actions = {Action.RESPONSES, Action.READ_OTHERS_CONVERSATIONS}
    return req


@pytest.fixture(name="minimal_config")
def minimal_config_fixture() -> AppConfig:
    """Minimal AppConfig for responses endpoint OTEL tests."""
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
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "authorization": {"access_rules": []},
        }
    )
    return cfg


class TestFinalizeResponsesRootSpanOtel:  # pylint: disable=too-few-public-methods
    """OTEL attrs/events for _finalize_responses_root_span."""

    @pytest.mark.parametrize(
        ("tool_names", "expect_tool_event"),
        [
            ([], False),
            (["file_search", "mcp_tool"], True),
        ],
    )
    def test_finalize_tool_attrs_and_events(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
        tool_names: list[str],
        expect_tool_event: bool,
    ) -> None:
        """Tool count/names are always set; tool event only when tools ran."""
        tracer, exporter = otel
        root_span = tracer.start_span("responses.handle_request")
        turn_summary = (
            make_turn_summary_with_tools(tool_names)
            if tool_names
            else make_turn_summary_without_tools()
        )
        mocker.patch(
            f"{MODULE}.anonymize_value",
            side_effect=lambda value: f"[anon:{value}]",
        )

        _finalize_responses_root_span(root_span, turn_summary)
        root_span.end()

        span = find_span(exporter.get_finished_spans(), "responses.handle_request")
        assert span.attributes is not None
        assert span.attributes[SpanAttributes.TOOL_CALLS_COUNT] == len(tool_names)
        assert (
            list(cast(Sequence[str], span.attributes[SpanAttributes.TOOL_CALLS_NAMES]))
            == tool_names
        )
        assert span.attributes[SpanAttributes.LLM_USAGE_INPUT_TOKENS] == 10
        assert span.attributes[SpanAttributes.LLM_USAGE_OUTPUT_TOKENS] == 5
        assert span.attributes[SpanAttributes.OUTPUT] == "[anon:The answer is 42]"

        event_names = [event.name for event in span.events]
        assert SpanEvents.LLM_RESPONSE_COMPLETED in event_names
        if expect_tool_event:
            tool_events = [
                event
                for event in span.events
                if event.name == SpanEvents.TOOL_EXECUTION_COMPLETED
            ]
            assert len(tool_events) == 1
            tool_event_attrs = tool_events[0].attributes
            assert tool_event_attrs is not None
            assert tool_event_attrs["tool.calls"] == ", ".join(tool_names)
        else:
            assert SpanEvents.TOOL_EXECUTION_COMPLETED not in event_names


class TestResponsesInferenceSpanOtel:
    """OTEL attrs/events for llm.inference helper spans."""

    def test_start_sets_model_provider_and_started_event(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """_start_llm_inference_span sets model attrs and started event."""
        tracer, exporter = otel
        mocker.patch(f"{MODULE}.tracer", tracer)
        mocker.patch(
            f"{MODULE}.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        parent = tracer.start_span("responses.handle_request")

        inference_span = _start_llm_inference_span("provider1/model1", parent=parent)
        inference_span.end()
        parent.end()

        span = find_span(exporter.get_finished_spans(), "llm.inference")
        assert span.attributes is not None
        assert span.attributes[SpanAttributes.LLM_MODEL_ID] == "model1"
        assert span.attributes[SpanAttributes.LLM_PROVIDER_ID] == "provider1"
        event_names = [event.name for event in span.events]
        assert event_names == [SpanEvents.LLM_INFERENCE_STARTED]

    def test_complete_sets_tokens_and_completed_event(
        self,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """_complete_llm_inference_span records usage and completed event."""
        tracer, exporter = otel
        inference_span = tracer.start_span("llm.inference")

        _complete_llm_inference_span(inference_span, input_tokens=12, output_tokens=7)

        span = find_span(exporter.get_finished_spans(), "llm.inference")
        assert span.attributes is not None
        assert span.attributes[SpanAttributes.LLM_USAGE_INPUT_TOKENS] == 12
        assert span.attributes[SpanAttributes.LLM_USAGE_OUTPUT_TOKENS] == 7
        event_names = [event.name for event in span.events]
        assert SpanEvents.LLM_INFERENCE_COMPLETED in event_names

    def test_record_exception_adds_response_attrs(
        self,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """_record_inference_span_exception enriches mapped error attrs."""
        tracer, exporter = otel
        inference_span = tracer.start_span("llm.inference")
        error_response = ServiceUnavailableResponse(backend_name="OGX", cause="down")

        _record_inference_span_exception(
            inference_span,
            ApiException(status=None, reason="connection failed"),
            error_response,
        )
        inference_span.end()

        span = find_span(exporter.get_finished_spans(), "llm.inference")
        exception_events = [event for event in span.events if event.name == "exception"]
        assert len(exception_events) == 1
        assert exception_events[0].attributes is not None
        assert (
            exception_events[0].attributes[SpanAttributes.RESPONSE_ERROR]
            == "Unable to connect to OGX"
        )
        assert exception_events[0].attributes[SpanAttributes.RESPONSE_CAUSE] == "down"


class TestResponsesRootSpanSetupOtel:
    """OTEL attrs/events on the responses root span during setup."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True])
    async def test_root_setup_attributes_and_validation_event(
        self,
        stream: bool,
        mocker: MockerFixture,
        dummy_request: Request,
        minimal_config: AppConfig,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Root span carries setup attributes and validation.completed for both modes."""
        tracer, exporter = otel
        root = await run_responses_setup_smoke(
            mocker,
            dummy_request,
            tracer,
            minimal_config,
            exporter,
            stream=stream,
            input_text=INPUT_TEXT,
        )
        assert_root_setup_attributes(root, input_text=INPUT_TEXT)

    @pytest.mark.asyncio
    async def test_safety_identifier_recorded_raw_when_present(
        self,
        mocker: MockerFixture,
        dummy_request: Request,
        minimal_config: AppConfig,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """safety_identifier is recorded verbatim (not anonymized) on the root span."""
        tracer, exporter = otel
        root = await run_responses_setup_smoke(
            mocker,
            dummy_request,
            tracer,
            minimal_config,
            exporter,
            stream=False,
            input_text=INPUT_TEXT,
            safety_identifier="e2e-otel-delivery-marker",
        )
        assert root.attributes is not None
        assert (
            root.attributes[SpanAttributes.SAFETY_IDENTIFIER]
            == "e2e-otel-delivery-marker"
        )

    @pytest.mark.asyncio
    async def test_safety_identifier_absent_when_not_provided(
        self,
        mocker: MockerFixture,
        dummy_request: Request,
        minimal_config: AppConfig,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """No safety_identifier attribute is set when the request omits it."""
        tracer, exporter = otel
        root = await run_responses_setup_smoke(
            mocker,
            dummy_request,
            tracer,
            minimal_config,
            exporter,
            stream=False,
            input_text=INPUT_TEXT,
        )
        assert root.attributes is not None
        assert SpanAttributes.SAFETY_IDENTIFIER not in root.attributes

    @pytest.mark.asyncio
    async def test_streaming_root_span_closed_on_setup_error(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Streaming root span is ended when setup raises before the stream starts."""
        tracer, exporter = otel
        patch_responses_otel_tracers(mocker, tracer, minimal_config)
        patch_responses_endpoint_setup(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.check_configuration_loaded",
            side_effect=HTTPException(status_code=500, detail="not loaded"),
        )

        with pytest.raises(HTTPException):
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=ResponsesRequest(input="test", stream=True),
                auth=MOCK_AUTH,
                mcp_headers={},
            )

        find_span(exporter.get_finished_spans(), "responses.handle_request")
