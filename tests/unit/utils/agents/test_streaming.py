"""Unit tests for utils.agents.streaming module."""

# pylint: disable=too-many-lines

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import HTTPException
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage as ResponseMessage,
)
from llama_stack_client import APIStatusError
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import (
    FinishReason,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelResponse,
    NativeToolCallPart,
    NativeToolReturnPart,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.native_tools import WebSearchTool
from pydantic_ai.usage import RunUsage
from pytest_mock import MockerFixture

from constants import (
    ENDPOINT_PATH_STREAMING_QUERY,
    INTERRUPTED_RESPONSE_MESSAGE,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
)
from models.api.requests import QueryRequest
from models.api.responses.error import PromptTooLongResponse
from models.common.agents import (
    AgentTurnAccumulator,
    TokenStreamPayload,
    ToolCallStreamPayload,
    ToolResultStreamPayload,
    TurnCompleteStreamPayload,
)
from models.common.moderation import ShieldModerationBlocked, ShieldModerationPassed
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import RAGContext, TurnSummary
from utils.agents.query import AgentFinishReason
from utils.agents.streaming import (
    DEFAULT_REFUSAL_RESPONSE,
    agent_response_generator,
    dispatch_stream_event,
    generate_agent_response,
    retrieve_agent_response_generator,
    serialize_event,
)
from utils.token_counter import TokenCounter

TEST_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"


@pytest.fixture(name="turn_state")
def turn_state_fixture() -> AgentTurnAccumulator:
    """Create a fresh agent turn accumulator for dispatch tests."""
    return AgentTurnAccumulator(
        vector_store_ids=["vs-001"],
        rag_id_mapping={"vs-001": "ocp-docs"},
        turn_summary=TurnSummary(),
    )


@pytest.fixture(name="make_responses_params")
def make_responses_params_fixture() -> Callable[..., ResponsesApiParams]:
    """Return a factory that builds ResponsesApiParams for streaming tests."""

    def _make(
        *,
        model: str = "provider1/model1",
        input_text: str = "What is OpenShift?",
        conversation: str | None = TEST_CONVERSATION_ID,
        omit_conversation: bool = False,
    ) -> ResponsesApiParams:
        return ResponsesApiParams.model_validate(
            {
                "model": model,
                "input": input_text,
                "conversation": conversation,
                "stream": True,
                "store": True,
                "omit_conversation": omit_conversation,
            }
        )

    return _make


@pytest.fixture(name="responses_params")
def responses_params_fixture(
    make_responses_params: Callable[..., ResponsesApiParams],
) -> ResponsesApiParams:
    """Default ResponsesApiParams for agent streaming tests."""
    return make_responses_params()


@pytest.fixture(name="blocked_moderation")
def blocked_moderation_fixture() -> ShieldModerationBlocked:
    """Blocked shield moderation result for streaming tests."""
    return ShieldModerationBlocked(
        message="Content blocked by shield.",
        moderation_id="modr-test-456",
        refusal_response=ResponseMessage(
            role="assistant",
            content="Content blocked by shield.",
        ),
    )


@pytest.fixture(name="make_generator_context")
def make_generator_context_fixture(
    mocker: MockerFixture,
) -> Callable[..., ResponseGeneratorContext]:
    """Return a factory that builds ResponseGeneratorContext mocks."""

    def _make(
        *,
        conversation_id: str = TEST_CONVERSATION_ID,
        request_id: str = "223e4567-e89b-12d3-a456-426614174000",
        user_id: str = "user_123",
        query: str = "What is OpenShift?",
        media_type: str | None = MEDIA_TYPE_JSON,
        generate_topic_summary: bool = False,
        conversation_id_in_request: str | None = TEST_CONVERSATION_ID,
        moderation_result: (
            ShieldModerationPassed | ShieldModerationBlocked | None
        ) = None,
    ) -> ResponseGeneratorContext:
        context = mocker.Mock(spec=ResponseGeneratorContext)
        context.conversation_id = conversation_id
        context.request_id = request_id
        context.user_id = user_id
        context.skip_userid_check = False
        context.model_id = "provider1/model1"
        context.started_at = "2024-01-01T00:00:00Z"
        context.client = mocker.AsyncMock()
        context.moderation_result = moderation_result or ShieldModerationPassed()
        context.inline_rag_context = RAGContext()
        context.vector_store_ids = []
        context.rag_id_mapping = {}
        context.query_request = QueryRequest(
            query=query,
            media_type=media_type,
            conversation_id=conversation_id_in_request,
            generate_topic_summary=generate_topic_summary,
        )  # pyright: ignore[reportCallIssue]
        return context

    return _make


@pytest.fixture(name="make_agent_run_result")
def make_agent_run_result_fixture(mocker: MockerFixture) -> Callable[..., Any]:
    """Return a factory that builds mock AgentRunResult objects."""

    def _make(
        *,
        content: str = "Hello from the agent.",
        response_id: str = "response-123",
        input_tokens: int = 10,
        output_tokens: int = 5,
        finish_reason: FinishReason | None = "stop",
        provider_details: dict[str, Any] | None = None,
    ) -> Any:
        model_response = ModelResponse(
            parts=[TextPart(content=content)],
            finish_reason=finish_reason,
            provider_response_id=response_id,
            provider_details=provider_details,
        )
        run_result = mocker.MagicMock()
        run_result.response = model_response
        run_result.usage = RunUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=1,
        )
        return run_result

    return _make


@pytest.fixture(name="patch_recording_metrics")
def patch_recording_metrics_fixture(mocker: MockerFixture) -> None:
    """Patch LLM recording helpers so agent streaming tests stay isolated."""
    mocker.patch("utils.agents.query.recording.record_llm_token_usage")
    mocker.patch("utils.agents.query.recording.record_llm_call")


@pytest.fixture(autouse=True, name="stream_interrupt_mocks")
def stream_interrupt_mocks_fixture(mocker: MockerFixture) -> dict[str, Any]:
    """Patch stream interrupt registry and deregister for wrapper tests."""
    registry = mocker.Mock()
    mocker.patch(
        "utils.stream_interrupts.get_stream_interrupt_registry",
        return_value=registry,
    )
    deregister = mocker.patch("utils.agents.streaming.deregister_stream")
    return {"registry": registry, "deregister": deregister}


class TestSerializeEvent:
    """Tests for serialize_event."""

    def test_serializes_json_payload(self) -> None:
        """Test JSON media type uses payload.serialize_json."""
        payload = TokenStreamPayload.create(chunk_id=0, token="Hello")

        result = serialize_event(payload, MEDIA_TYPE_JSON)

        assert result.startswith("data: ")
        parsed = json.loads(result.replace("data: ", "").strip())
        assert parsed["event"] == "token"
        assert parsed["data"]["token"] == "Hello"

    def test_serializes_text_payload(self) -> None:
        """Test text media type uses payload.serialize_text."""
        payload = TokenStreamPayload.create(chunk_id=0, token="Hello")

        result = serialize_event(payload, MEDIA_TYPE_TEXT)

        assert result == "Hello"


class TestDispatchStreamEvent:
    """Tests for dispatch_stream_event singledispatch handlers."""

    def test_unknown_event_returns_none(self, turn_state: AgentTurnAccumulator) -> None:
        """Test unregistered event kinds are ignored."""
        unknown = type("UnknownEvent", (), {"event_kind": "unknown"})()

        assert dispatch_stream_event(unknown, turn_state) is None  # type: ignore[arg-type]

    def test_part_start_text_emits_token(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test text part start emits a token payload and increments chunk id."""
        event = PartStartEvent(index=0, part=TextPart(content="Hi"))

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TokenStreamPayload)
        assert payload.data.token == "Hi"
        assert payload.data.id == 0
        assert turn_state.chunk_id == 1
        assert turn_state.text_parts == ["Hi"]

    def test_part_start_empty_text_emits_empty_token(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test empty text at part start still produces a token payload."""
        event = PartStartEvent(index=0, part=TextPart(content=""))

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TokenStreamPayload)
        assert payload.data.token == ""

    def test_part_delta_empty_text_emits_empty_token(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test empty text delta still produces a token payload."""
        event = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=""))

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TokenStreamPayload)
        assert payload.data.token == ""

    def test_part_end_empty_text_falls_back_to_buffered_parts(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test empty text part end appends buffered deltas when content is empty."""
        turn_state.text_parts = ["buffered"]
        event = PartEndEvent(index=0, part=TextPart(content=""))

        payload = dispatch_stream_event(event, turn_state)

        assert payload is None
        assert turn_state.turn_summary.llm_response == "buffered\n\n"
        assert turn_state.text_parts == []

    def test_part_delta_text_emits_token(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test text delta emits incremental token payload."""
        event = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" there"))

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TokenStreamPayload)
        assert payload.data.token == " there"

    def test_part_end_text_updates_turn_summary(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test text part end appends buffered text to turn summary."""
        turn_state.text_parts = ["Hello", " world"]
        event = PartEndEvent(index=0, part=TextPart(content="Hello world"))

        payload = dispatch_stream_event(event, turn_state)

        assert payload is None
        assert turn_state.turn_summary.llm_response == "Hello world"
        assert turn_state.text_parts == []

    def test_agent_run_result_sets_summary_and_emits_turn_complete(
        self,
        turn_state: AgentTurnAccumulator,
        make_agent_run_result: Callable[..., Any],
    ) -> None:
        """Test final run result stores id and emits turn_complete payload."""
        run_result = make_agent_run_result(
            content="Final answer",
            response_id="resp-final-1",
        )
        event = AgentRunResultEvent(result=run_result)

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TurnCompleteStreamPayload)
        assert payload.data.token == "Final answer"
        assert turn_state.run_result is run_result
        assert turn_state.turn_summary.id == "resp-final-1"

    def test_agent_run_result_content_filter_uses_refusal_text(
        self,
        turn_state: AgentTurnAccumulator,
        make_agent_run_result: Callable[..., Any],
    ) -> None:
        """Test content_filter finish reason prefers provider refusal text."""
        run_result = make_agent_run_result(
            content="",
            finish_reason="content_filter",
            provider_details={"refusal_response": "Policy blocked this."},
        )
        event = AgentRunResultEvent(result=run_result)

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TurnCompleteStreamPayload)
        assert payload.data.token == "Policy blocked this."

    def test_agent_run_result_content_filter_default_refusal(
        self,
        turn_state: AgentTurnAccumulator,
        make_agent_run_result: Callable[..., Any],
    ) -> None:
        """Test content_filter without refusal details uses default message."""
        run_result = make_agent_run_result(
            content="",
            finish_reason="content_filter",
            provider_details={},
        )
        event = AgentRunResultEvent(result=run_result)

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, TurnCompleteStreamPayload)
        assert payload.data.token == DEFAULT_REFUSAL_RESPONSE

    def test_function_tool_call_emits_tool_call_payload(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test function tool call events emit tool_call SSE payloads."""
        part = ToolCallPart(tool_name="fn", args={"x": 1}, tool_call_id="call-1")
        event = FunctionToolCallEvent(part=part)

        payload = dispatch_stream_event(event, turn_state)

        assert payload is not None
        assert payload.event == "tool_call"
        assert payload.data.name == "fn"

    def test_function_tool_result_emits_tool_result_payload(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test function tool result events emit tool_result SSE payloads."""
        part = ToolReturnPart(
            tool_name="fn",
            content={"result": 1},
            tool_call_id="call-1",
        )
        event = FunctionToolResultEvent(part=part)

        payload = dispatch_stream_event(event, turn_state)

        assert payload is not None
        assert payload.event == "tool_result"

    def test_part_start_native_tool_return_emits_tool_result(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test native tool return at part start emits tool_result SSE payload."""
        part = NativeToolReturnPart(
            tool_name=WebSearchTool.kind,
            tool_call_id="ws-return-1",
            content={"status": "success", "query": "OpenShift"},
        )
        event = PartStartEvent(index=0, part=part)

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, ToolResultStreamPayload)
        assert payload.event == "tool_result"
        assert payload.data.id == "ws-return-1"
        assert turn_state.turn_summary.tool_results == [payload.data]

    def test_part_start_native_tool_return_returns_none_when_skipped(
        self,
        turn_state: AgentTurnAccumulator,
        mocker: MockerFixture,
    ) -> None:
        """Test unknown native tool returns at part start are ignored."""
        mocker.patch("utils.agents.tool_processor.logger.warning")
        part = NativeToolReturnPart(
            tool_name="unknown",
            tool_call_id="unk-return",
            content={"status": "success"},
        )
        event = PartStartEvent(index=0, part=part)

        payload = dispatch_stream_event(event, turn_state)

        assert payload is None
        assert not turn_state.turn_summary.tool_results

    def test_part_end_native_tool_call_emits_tool_call(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test native tool call at part end emits tool_call SSE payload."""
        part = NativeToolCallPart(
            tool_name=WebSearchTool.kind,
            args={"query": "OpenShift"},
            tool_call_id="ws-call-1",
        )
        event = PartEndEvent(index=0, part=part)

        payload = dispatch_stream_event(event, turn_state)

        assert isinstance(payload, ToolCallStreamPayload)
        assert payload.event == "tool_call"
        assert payload.data.id == "ws-call-1"
        assert turn_state.turn_summary.tool_calls == [payload.data]

    def test_part_end_native_tool_call_returns_none_when_skipped(
        self,
        turn_state: AgentTurnAccumulator,
        mocker: MockerFixture,
    ) -> None:
        """Test unknown native tool calls at part end are ignored."""
        mocker.patch("utils.agents.tool_processor.logger.warning")
        part = NativeToolCallPart(
            tool_name="unknown",
            args={},
            tool_call_id="unk-call",
        )
        event = PartEndEvent(index=0, part=part)

        payload = dispatch_stream_event(event, turn_state)

        assert payload is None
        assert not turn_state.turn_summary.tool_calls


class TestRetrieveAgentResponseGenerator:
    """Tests for retrieve_agent_response_generator."""

    @pytest.mark.asyncio
    async def test_blocked_moderation_returns_shield_generator(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        make_responses_params: Callable[..., ResponsesApiParams],
        blocked_moderation: ShieldModerationBlocked,
    ) -> None:
        """Test blocked moderation returns shield violation stream and summary."""
        context = make_generator_context(moderation_result=blocked_moderation)
        responses_params = make_responses_params()
        mock_shield = mocker.patch(
            "utils.agents.streaming.shield_violation_generator",
            return_value=_async_iter(["shield-event"]),
        )
        mock_append = mocker.patch(
            "utils.agents.streaming.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )

        generator, turn_summary = await retrieve_agent_response_generator(
            responses_params,
            context,
            ENDPOINT_PATH_STREAMING_QUERY,
        )

        events = [event async for event in generator]
        assert events == ["shield-event"]
        mock_shield.assert_called_once_with(
            blocked_moderation.message,
            MEDIA_TYPE_JSON,
        )
        mock_append.assert_awaited_once()
        assert turn_summary.llm_response == blocked_moderation.message
        assert turn_summary.id == blocked_moderation.moderation_id

    @pytest.mark.asyncio
    async def test_blocked_moderation_skips_append_when_omit_conversation(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        make_responses_params: Callable[..., ResponsesApiParams],
        blocked_moderation: ShieldModerationBlocked,
    ) -> None:
        """Test compacted mode does not append blocked turn to conversation."""
        context = make_generator_context(moderation_result=blocked_moderation)
        responses_params = make_responses_params(omit_conversation=True)
        mocker.patch(
            "utils.agents.streaming.shield_violation_generator",
            return_value=_async_iter([]),
        )
        mock_append = mocker.patch(
            "utils.agents.streaming.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )

        await retrieve_agent_response_generator(
            responses_params,
            context,
            ENDPOINT_PATH_STREAMING_QUERY,
        )

        mock_append.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_returns_agent_generator(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test passed moderation builds agent and returns streaming generator."""
        context = make_generator_context()
        mock_agent = mocker.Mock()
        mocker.patch(
            "utils.agents.streaming.build_agent",
            return_value=mock_agent,
        )
        mock_agent_gen = mocker.patch(
            "utils.agents.streaming.agent_response_generator",
            return_value=_async_iter(["agent-event"]),
        )

        generator, turn_summary = await retrieve_agent_response_generator(
            responses_params,
            context,
            ENDPOINT_PATH_STREAMING_QUERY,
        )

        events = [event async for event in generator]
        assert events == ["agent-event"]
        assert isinstance(turn_summary, TurnSummary)
        mock_agent_gen.assert_called_once_with(
            mock_agent,
            responses_params,
            context,
            turn_summary,
            ENDPOINT_PATH_STREAMING_QUERY,
        )

    @pytest.mark.asyncio
    async def test_agent_error_raises_http_exception(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test agent inference errors are mapped to HTTPException."""
        context = make_generator_context()
        mocker.patch(
            "utils.agents.streaming.build_agent",
            side_effect=AgentRunError("agent failed"),
        )
        mock_error = mocker.Mock()
        mock_error.model_dump.return_value = {
            "status_code": 500,
            "detail": {"response": "Error", "cause": "agent failed"},
        }
        mocker.patch(
            "utils.agents.streaming.map_agent_inference_error",
            return_value=mock_error,
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_agent_response_generator(
                responses_params,
                context,
                ENDPOINT_PATH_STREAMING_QUERY,
            )

        assert exc_info.value.status_code == 500


class TestGenerateAgentResponse:
    """Tests for generate_agent_response wrapper."""

    @pytest.mark.asyncio
    async def test_emits_start_and_end_on_success(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test successful stream emits start, inner events, and end."""
        context = make_generator_context()
        turn_summary = TurnSummary()
        turn_summary.token_usage = TokenCounter(input_tokens=3, output_tokens=7)
        background_tasks: list[asyncio.Task[None]] = []

        async def inner() -> AsyncIterator[str]:
            yield serialize_event(
                TokenStreamPayload.create(chunk_id=0, token="Hi"),
                MEDIA_TYPE_JSON,
            )

        consume_mock = mocker.patch("utils.agents.streaming.consume_query_tokens")
        mocker.patch(
            "utils.agents.streaming.get_available_quotas",
            return_value={"daily": 100},
        )
        mocker.patch(
            "utils.agents.streaming.maybe_get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        store_mock = mocker.patch("utils.agents.streaming.store_query_results")
        mock_config = mocker.Mock()
        mock_config.quota_limiters = []
        mocker.patch("utils.agents.streaming.configuration", mock_config)

        result = [
            event
            async for event in generate_agent_response(
                inner(),
                context,
                responses_params,
                turn_summary,
                background_tasks,
            )
        ]

        assert _sse_event_types(result) == ["start", "token", "end"]
        consume_mock.assert_called_once()
        store_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_persists_interrupted_turn(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
        stream_interrupt_mocks: dict[str, Any],
    ) -> None:
        """Test CancelledError persists interrupted turn and emits interrupted event."""
        context = make_generator_context()
        turn_summary = TurnSummary()
        background_tasks: list[asyncio.Task[None]] = []

        async def inner() -> AsyncIterator[str]:
            yield serialize_event(
                TokenStreamPayload.create(chunk_id=0, token="partial"),
                MEDIA_TYPE_JSON,
            )
            raise asyncio.CancelledError()

        persist_mock = mocker.patch(
            "utils.agents.streaming.persist_interrupted_turn",
            new=mocker.AsyncMock(),
        )
        mocker.patch(
            "utils.agents.streaming.register_interrupt_callback",
            return_value=[False],
        )

        result = [
            event
            async for event in generate_agent_response(
                inner(),
                context,
                responses_params,
                turn_summary,
                background_tasks,
            )
        ]

        assert _sse_event_types(result) == ["start", "token", "interrupted"]
        persist_mock.assert_awaited_once()
        assert turn_summary.llm_response == INTERRUPTED_RESPONSE_MESSAGE
        stream_interrupt_mocks["deregister"].assert_called_once_with(context.request_id)

    @pytest.mark.asyncio
    async def test_inference_error_yields_error_event(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
        stream_interrupt_mocks: dict[str, Any],
    ) -> None:
        """Test agent inference errors during streaming yield error SSE events."""
        context = make_generator_context()

        async def inner() -> AsyncIterator[str]:
            yield serialize_event(
                TokenStreamPayload.create(chunk_id=0, token="partial"),
                MEDIA_TYPE_JSON,
            )
            raise APIStatusError(
                message="quota exceeded",
                response=mocker.Mock(),
                body=None,
            )

        mock_error = mocker.Mock()
        mock_error.status_code = 429
        mock_error.detail.response = "Quota exceeded"
        mock_error.detail.cause = "quota exceeded"
        mocker.patch(
            "utils.agents.streaming.map_agent_inference_error",
            return_value=mock_error,
        )
        mocker.patch(
            "utils.agents.streaming.register_interrupt_callback",
            return_value=[False],
        )

        result = [
            event
            async for event in generate_agent_response(
                inner(),
                context,
                responses_params,
                TurnSummary(),
                [],
                emit_start=False,
            )
        ]

        assert _sse_event_types(result) == ["token", "error"]
        stream_interrupt_mocks["deregister"].assert_called_once_with(context.request_id)

    @pytest.mark.asyncio
    async def test_interrupt_guard_skips_duplicate_persist(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test persist guard prevents double persistence when already handled."""
        context = make_generator_context()
        turn_summary = TurnSummary()

        async def inner() -> AsyncIterator[str]:
            yield serialize_event(
                TokenStreamPayload.create(chunk_id=0, token="partial"),
                MEDIA_TYPE_JSON,
            )
            raise asyncio.CancelledError()

        persist_mock = mocker.patch(
            "utils.agents.streaming.persist_interrupted_turn",
            new=mocker.AsyncMock(),
        )
        mocker.patch(
            "utils.agents.streaming.register_interrupt_callback",
            return_value=[True],
        )

        result = [
            event
            async for event in generate_agent_response(
                inner(),
                context,
                responses_params,
                turn_summary,
                [],
            )
        ]

        assert _sse_event_types(result) == ["start", "token", "interrupted"]
        persist_mock.assert_not_awaited()


class TestAgentResponseGenerator:
    """Tests for agent_response_generator."""

    @pytest.mark.asyncio
    async def test_streams_token_events_and_updates_summary(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
        make_agent_run_result: Callable[..., Any],
        patch_recording_metrics: None,
    ) -> None:
        """Test agent stream maps pydantic-ai events to SSE and updates summary."""
        context = make_generator_context()
        turn_summary = TurnSummary()
        run_result = make_agent_run_result(
            content="Answer",
            response_id="resp-stream-1",
            input_tokens=4,
            output_tokens=2,
        )
        events = [
            PartEndEvent(
                index=0,
                part=NativeToolCallPart(
                    tool_name=WebSearchTool.kind,
                    args={"query": "OpenShift"},
                    tool_call_id="ws-stream-call",
                ),
            ),
            PartStartEvent(
                index=1,
                part=NativeToolReturnPart(
                    tool_name=WebSearchTool.kind,
                    tool_call_id="ws-stream-call",
                    content={"status": "success"},
                ),
            ),
            PartStartEvent(index=2, part=TextPart(content="An")),
            PartDeltaEvent(index=2, delta=TextPartDelta(content_delta="swer")),
            AgentRunResultEvent(result=run_result),
        ]
        mock_agent = mocker.Mock()
        mock_agent.run_stream_events.return_value = _mock_run_stream(events)
        mocker.patch(
            "utils.agents.streaming.get_agent_finish_reason",
            return_value=AgentFinishReason.SUCCESS,
        )
        mocker.patch(
            "utils.agents.streaming.deduplicate_referenced_documents",
            side_effect=lambda docs: docs,
        )

        result = [
            event
            async for event in agent_response_generator(
                mock_agent,
                responses_params,
                context,
                turn_summary,
                ENDPOINT_PATH_STREAMING_QUERY,
            )
        ]

        assert _sse_event_types(result) == [
            "tool_call",
            "tool_result",
            "token",
            "token",
            "turn_complete",
        ]
        assert turn_summary.id == "resp-stream-1"
        assert turn_summary.token_usage.input_tokens == 4
        assert turn_summary.token_usage.output_tokens == 2

    @pytest.mark.asyncio
    async def test_non_success_finish_reason_yields_error_event(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
        make_agent_run_result: Callable[..., Any],
        patch_recording_metrics: None,
    ) -> None:
        """Test non-success finish reason emits error SSE after stream completes."""
        context = make_generator_context()
        turn_summary = TurnSummary()
        run_result = make_agent_run_result(finish_reason="length")
        mock_agent = mocker.Mock()
        mock_agent.run_stream_events.return_value = _mock_run_stream(
            [AgentRunResultEvent(result=run_result)]
        )
        mocker.patch(
            "utils.agents.streaming.get_agent_finish_reason",
            return_value=AgentFinishReason.LENGTH,
        )
        mock_error = PromptTooLongResponse(model=responses_params.model)
        mocker.patch(
            "utils.agents.streaming.get_finish_reason_error",
            return_value=mock_error,
        )
        mocker.patch(
            "utils.agents.streaming.deduplicate_referenced_documents",
            side_effect=lambda docs: docs,
        )

        result = [
            event
            async for event in agent_response_generator(
                mock_agent,
                responses_params,
                context,
                turn_summary,
                ENDPOINT_PATH_STREAMING_QUERY,
            )
        ]

        assert any('"event": "error"' in item for item in result)

    @pytest.mark.asyncio
    async def test_no_run_result_logs_and_returns_early(
        self,
        mocker: MockerFixture,
        make_generator_context: Callable[..., ResponseGeneratorContext],
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test missing AgentRunResultEvent skips post-stream processing."""
        context = make_generator_context()
        turn_summary = TurnSummary()
        mock_agent = mocker.Mock()
        mock_agent.run_stream_events.return_value = _mock_run_stream(
            [PartStartEvent(index=0, part=TextPart(content="partial"))]
        )

        result = [
            event
            async for event in agent_response_generator(
                mock_agent,
                responses_params,
                context,
                turn_summary,
                ENDPOINT_PATH_STREAMING_QUERY,
            )
        ]

        assert len(result) == 1
        assert turn_summary.token_usage.input_tokens == 0


def _sse_event_types(events: list[str]) -> list[str]:
    """Extract SSE event types from serialized stream lines."""
    types: list[str] = []
    for line in events:
        if not line.startswith("data: "):
            continue
        parsed = json.loads(line.removeprefix("data: ").strip())
        types.append(parsed["event"])
    return types


async def _async_iter(items: list[str]) -> AsyncIterator[str]:
    """Yield a fixed list as an async iterator."""
    for item in items:
        yield item


def _mock_run_stream(
    events: list[Any],
) -> Any:
    """Build an async context manager that yields pydantic-ai stream events."""

    async def _event_stream() -> AsyncIterator[Any]:
        for event in events:
            yield event

    class _RunStreamCtx:
        """Minimal async context manager matching agent.run_stream_events."""

        async def __aenter__(self) -> AsyncIterator[Any]:
            return _event_stream()

        async def __aexit__(self, *_args: object) -> None:
            return None

    return _RunStreamCtx()
