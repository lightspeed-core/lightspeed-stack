"""Unit tests for safety.base."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import SkipModelRequest, UserError
from pydantic_ai.messages import (
    AgentStreamEvent,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    SystemPromptPart,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import ToolDefinition

from safety.base import AbstractSafetyCapability
from safety.exceptions import OutputBlocked, ToolBlocked
from safety.types import GuardrailResult
from tests.unit.safety.helpers import request_context, run_context

_GuardPoint = Literal["input", "output", "tool"]


@dataclass
class ScriptedGuard(AbstractSafetyCapability[Any]):
    """Safety capability that returns queued verdicts."""

    verdicts: list[GuardrailResult] = field(default_factory=list)
    seen: list[str] = field(default_factory=list)
    before_verdict: Callable[[], None] | None = None

    async def evaluate(self, prompt: str) -> GuardrailResult:
        """Record `prompt` and return the next queued verdict."""
        self.seen.append(prompt)
        if self.before_verdict is not None:
            self.before_verdict()
        if not self.verdicts:
            return GuardrailResult.allow()
        return self.verdicts.pop(0)


def _guard(
    guard_type: Sequence[_GuardPoint],
    *verdicts: GuardrailResult,
    check_tokens: int = 50,
    before_verdict: Callable[[], None] | None = None,
) -> ScriptedGuard:
    """Return a guard that yields `verdicts` from successive evaluate calls."""
    return ScriptedGuard(
        type=guard_type,
        verdicts=list(verdicts),
        check_tokens=check_tokens,
        before_verdict=before_verdict,
    )


class EventStream:
    """One-shot async stream that records how far it was read and whether it closed."""

    def __init__(self, events: Sequence[AgentStreamEvent]) -> None:
        """Store `events` and reset the read cursor."""
        self.events = list(events)
        self.read_count = 0
        self.closed = False

    def __aiter__(self) -> "EventStream":
        """Return this stream as its own iterator."""
        return self

    async def __anext__(self) -> AgentStreamEvent:
        """Return the next event, or stop once the stream is exhausted."""
        if self.read_count >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self.read_count]
        self.read_count += 1
        return event

    async def aclose(self) -> None:
        """Record that the consumer closed the stream."""
        self.closed = True


class _UnclosableStream:  # pylint: disable=too-few-public-methods
    """Async stream that has no aclose method."""

    def __init__(self, events: Sequence[AgentStreamEvent]) -> None:
        """Store `events` and reset the read cursor."""
        self._events = list(events)
        self._index = 0

    def __aiter__(self) -> "_UnclosableStream":
        """Return this stream as its own iterator."""
        return self

    async def __anext__(self) -> AgentStreamEvent:
        """Return the next event, or stop once the stream is exhausted."""
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event


def _text_start(content: str, index: int = 0) -> PartStartEvent:
    """Return a text part-start event."""
    return PartStartEvent(index=index, part=TextPart(content=content))


def _text_delta(content: str, index: int = 0) -> PartDeltaEvent:
    """Return a text part-delta event."""
    return PartDeltaEvent(index=index, delta=TextPartDelta(content_delta=content))


def _text_end(content: str, index: int = 0) -> PartEndEvent:
    """Return a text part-end event."""
    return PartEndEvent(index=index, part=TextPart(content=content))


async def _collect(guard: ScriptedGuard, stream: EventStream) -> list[AgentStreamEvent]:
    """Read every event the guard releases from `stream`."""
    return [
        event
        async for event in guard.wrap_run_event_stream(run_context(), stream=stream)
    ]


async def _tool_result(guard: ScriptedGuard, result: Any) -> Any:
    """Run after_tool_execute with placeholder tool metadata."""
    return await guard.after_tool_execute(
        run_context(),
        call=ToolCallPart("lookup", {"q": "x"}),
        tool_def=ToolDefinition(name="lookup"),
        args={"q": "x"},
        result=result,
    )


class TestOnRunError:
    """Tests for AbstractSafetyCapability.on_run_error."""

    @pytest.mark.asyncio
    async def test_output_block_uses_the_reason_and_run_state(self) -> None:
        """Test that a blocked output becomes a successful run with the same state."""
        usage = run_context().usage
        messages = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        metadata = {"source": "unit"}
        ctx = run_context(
            usage=usage,
            messages=messages,
            metadata=metadata,
            run_id="run-1",
            conversation_id="conv-1",
        )

        result = await _guard(["output"]).on_run_error(
            ctx, error=OutputBlocked("blocked")
        )

        assert result.output == "blocked"
        assert result.run_id == "run-1"
        assert result.conversation_id == "conv-1"
        assert result.metadata is metadata
        assert result.usage is usage
        assert result.all_messages() is messages

    @pytest.mark.asyncio
    async def test_output_block_without_a_reason_uses_the_default_message(
        self,
    ) -> None:
        """Test that a missing output reason gets the generic response message."""
        result = await _guard(["output"]).on_run_error(
            run_context(), error=OutputBlocked()
        )

        assert result.output == "Response blocked by a safety guard."

    @pytest.mark.asyncio
    async def test_tool_block_uses_the_reason(self) -> None:
        """Test that a blocked tool result uses its own reason."""
        result = await _guard(["tool"]).on_run_error(
            run_context(), error=ToolBlocked("tool unsafe")
        )

        assert result.output == "tool unsafe"

    @pytest.mark.asyncio
    async def test_tool_block_without_a_reason_uses_the_tool_message(self) -> None:
        """Test that a missing tool reason gets the generic tool message."""
        result = await _guard(["tool"]).on_run_error(run_context(), error=ToolBlocked())

        assert result.output == "Tool result blocked by a safety guard."

    @pytest.mark.asyncio
    async def test_missing_ids_keep_generated_identifiers(self) -> None:
        """Test that absent run and conversation ids are not copied as None."""
        ctx = run_context()
        assert ctx.run_id is None
        assert ctx.conversation_id is None

        result = await _guard(["output"]).on_run_error(ctx, error=OutputBlocked("x"))

        assert result.output == "x"
        assert result.run_id
        assert result.conversation_id

    @pytest.mark.asyncio
    async def test_other_errors_propagate(self) -> None:
        """Test that an unrelated error is re-raised unchanged."""
        error = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom") as exc_info:
            await _guard(["output"]).on_run_error(run_context(), error=error)

        assert exc_info.value is error


class TestWrapRun:
    """Tests for AbstractSafetyCapability.wrap_run."""

    @pytest.mark.asyncio
    async def test_skips_evaluation_when_output_is_not_guarded(self) -> None:
        """Test that a non-output guard returns the handler result unchanged."""
        result = AgentRunResult(output="answer")
        guard = _guard(["input"])

        async def _handler() -> AgentRunResult[str]:
            return result

        assert await guard.wrap_run(run_context(), handler=_handler) is result
        assert not guard.seen

    @pytest.mark.asyncio
    async def test_allow_returns_the_handler_result(self) -> None:
        """Test that an allow verdict returns the same run result."""
        result = AgentRunResult(output="answer")
        guard = _guard(["output"], GuardrailResult.allow())

        async def _handler() -> AgentRunResult[str]:
            return result

        assert await guard.wrap_run(run_context(), handler=_handler) is result
        assert guard.seen == ["answer"]

    @pytest.mark.asyncio
    async def test_block_replaces_the_output(self) -> None:
        """Test that a block verdict replaces the output after the handler runs."""
        result = AgentRunResult(output="answer")
        guard = _guard(["output"], GuardrailResult.block("stop"))
        handler_called = False

        async def _handler() -> AgentRunResult[str]:
            nonlocal handler_called
            handler_called = True
            return result

        returned = await guard.wrap_run(run_context(), handler=_handler)

        assert handler_called is True
        assert returned is not result
        assert returned.output == "stop"
        assert result.output == "answer"

    @pytest.mark.asyncio
    async def test_block_without_a_message_uses_the_default(self) -> None:
        """Test that a block with no message uses the generic response text."""
        guard = _guard(["output"], GuardrailResult.block())

        async def _handler() -> AgentRunResult[str]:
            return AgentRunResult(output="answer")

        returned = await guard.wrap_run(run_context(), handler=_handler)

        assert returned.output == "Response blocked by a safety guard."

    @pytest.mark.asyncio
    async def test_replace_stringifies_the_replacement(self) -> None:
        """Test that a replace verdict becomes the string form of the replacement."""
        guard = _guard(["output"], GuardrailResult.replace(5))

        async def _handler() -> AgentRunResult[str]:
            return AgentRunResult(output="answer")

        returned = await guard.wrap_run(run_context(), handler=_handler)

        assert returned.output == "5"

    @pytest.mark.asyncio
    async def test_unknown_action_raises(self) -> None:
        """Test that an unsupported output verdict is a usage error."""
        guard = _guard(["output"], GuardrailResult(action="nope"))  # type: ignore[arg-type]

        async def _handler() -> AgentRunResult[str]:
            return AgentRunResult(output="answer")

        with pytest.raises(UserError, match="cannot return nope on output"):
            await guard.wrap_run(run_context(), handler=_handler)

    @pytest.mark.asyncio
    async def test_output_blocked_from_the_handler_propagates(self) -> None:
        """Test that a stream block is not converted inside wrap_run."""
        guard = _guard(["output"], GuardrailResult.allow())

        async def _handler() -> AgentRunResult[str]:
            raise OutputBlocked("from-stream")

        with pytest.raises(OutputBlocked) as exc_info:
            await guard.wrap_run(run_context(), handler=_handler)

        assert exc_info.value.reason == "from-stream"
        assert not guard.seen


class TestWrapModelRequest:
    """Tests for AbstractSafetyCapability.wrap_model_request."""

    @pytest.mark.asyncio
    async def test_skips_evaluation_when_input_is_not_guarded(self) -> None:
        """Test that a non-input guard forwards the request unchanged."""
        messages = [ModelRequest(parts=[UserPromptPart(content="secret")])]
        guard = _guard(["output"])

        async def _handler(context: ModelRequestContext) -> ModelResponse:
            assert context.messages is messages
            return ModelResponse(parts=[TextPart(content="ok")])

        response = await guard.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert not guard.seen
        assert messages[0].parts[0].content == "secret"
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"

    @pytest.mark.asyncio
    async def test_allow_calls_the_handler_with_the_prompt(self) -> None:
        """Test that an allow verdict screens the latest user prompt and continues."""
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        guard = _guard(["input"], GuardrailResult.allow())

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        await guard.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert guard.seen == ["hello"]
        assert messages[0].parts[0].content == "hello"

    @pytest.mark.asyncio
    async def test_block_skips_the_model_request(self) -> None:
        """Test that a block verdict skips the handler and returns its message."""
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        guard = _guard(["input"], GuardrailResult.block("stop"))
        called = False

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            nonlocal called
            called = True
            return ModelResponse(parts=[TextPart(content="unused")])

        with pytest.raises(SkipModelRequest) as exc_info:
            await guard.wrap_model_request(
                run_context(),
                request_context=request_context(messages),
                handler=_handler,
            )

        assert called is False
        part = exc_info.value.response.parts[0]
        assert isinstance(part, TextPart)
        assert part.content == "stop"

    @pytest.mark.asyncio
    async def test_block_without_a_message_uses_an_empty_response(self) -> None:
        """Test that a block with no message skips with empty text."""
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        guard = _guard(["input"], GuardrailResult.block())

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="unused")])

        with pytest.raises(SkipModelRequest) as exc_info:
            await guard.wrap_model_request(
                run_context(),
                request_context=request_context(messages),
                handler=_handler,
            )

        part = exc_info.value.response.parts[0]
        assert isinstance(part, TextPart)
        assert part.content == ""

    @pytest.mark.asyncio
    async def test_replace_rewrites_the_latest_prompt_before_the_handler(self) -> None:
        """Test that a replace verdict mutates the latest user prompt in place."""
        earlier = ModelRequest(parts=[UserPromptPart(content="old")])
        latest = ModelRequest(parts=[UserPromptPart(content="new")])
        messages = [earlier, latest]
        guard = _guard(["input"], GuardrailResult.replace("clean"))

        async def _handler(context: ModelRequestContext) -> ModelResponse:
            assert context.messages[1].parts[0].content == "clean"
            return ModelResponse(parts=[TextPart(content="ok")])

        await guard.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert earlier.parts[0].content == "old"
        assert latest.parts[0].content == "clean"
        assert guard.seen == ["new"]

    @pytest.mark.asyncio
    async def test_replace_raises_when_the_prompt_disappears(self) -> None:
        """Test that replace fails when the user prompt is gone after evaluation."""
        messages = [ModelRequest(parts=[UserPromptPart(content="secret")])]
        guard = _guard(
            ["input"],
            GuardrailResult.replace("clean"),
            before_verdict=messages.clear,
        )
        called = False

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            nonlocal called
            called = True
            return ModelResponse(parts=[TextPart(content="unused")])

        with pytest.raises(UserError, match="could not find a user prompt"):
            await guard.wrap_model_request(
                run_context(),
                request_context=request_context(messages),
                handler=_handler,
            )

        assert called is False
        assert guard.seen == ["secret"]

    @pytest.mark.asyncio
    async def test_replace_rejects_plain_text_over_a_multimodal_prompt(self) -> None:
        """Test that replacing a multimodal prompt with text raises."""
        messages = [
            ModelRequest(
                parts=[
                    UserPromptPart(content=[ImageUrl(url="https://example.com/a.png")])
                ]
            )
        ]
        guard = _guard(["input"], GuardrailResult.replace("text only"))

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="unused")])

        with pytest.raises(UserError, match="multimodal"):
            await guard.wrap_model_request(
                run_context(),
                request_context=request_context(messages),
                handler=_handler,
            )

        assert guard.seen

    @pytest.mark.asyncio
    async def test_missing_prompt_skips_evaluation(self) -> None:
        """Test that a request with no user prompt is allowed without evaluate."""
        messages = [ModelRequest(parts=[SystemPromptPart(content="sys")])]
        guard = _guard(["input"], GuardrailResult.block("stop"))

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        response = await guard.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert not guard.seen
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"

    @pytest.mark.asyncio
    async def test_unknown_action_raises(self) -> None:
        """Test that an unsupported input verdict is a usage error."""
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        guard = _guard(["input"], GuardrailResult(action="nope"))  # type: ignore[arg-type]

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="unused")])

        with pytest.raises(UserError, match="cannot return nope on input"):
            await guard.wrap_model_request(
                run_context(),
                request_context=request_context(messages),
                handler=_handler,
            )


class TestAfterToolExecute:
    """Tests for AbstractSafetyCapability.after_tool_execute."""

    @pytest.mark.asyncio
    async def test_skips_evaluation_when_tools_are_not_guarded(self) -> None:
        """Test that a non-tool guard returns the tool result unchanged."""
        guard = _guard(["input"])
        sentinel = object()

        assert await _tool_result(guard, sentinel) is sentinel
        assert not guard.seen

    @pytest.mark.asyncio
    async def test_allow_returns_the_same_result(self) -> None:
        """Test that an allow verdict returns the original tool result."""
        guard = _guard(["tool"], GuardrailResult.allow())
        payload = {"a": 1}

        assert await _tool_result(guard, payload) is payload
        assert guard.seen == ['{"a": 1}']

    @pytest.mark.asyncio
    async def test_block_raises_tool_blocked(self) -> None:
        """Test that a block verdict aborts with the verdict message."""
        guard = _guard(["tool"], GuardrailResult.block("stop"))

        with pytest.raises(ToolBlocked) as exc_info:
            await _tool_result(guard, "harmful")

        assert exc_info.value.reason == "stop"
        assert guard.seen == ["harmful"]

    @pytest.mark.asyncio
    async def test_replace_is_rejected(self) -> None:
        """Test that a tool guard cannot replace the tool result."""
        guard = _guard(["tool"], GuardrailResult.replace("clean"))

        with pytest.raises(UserError, match="cannot return replace on tool"):
            await _tool_result(guard, "secret")


class TestWrapRunEventStream:
    """Tests for AbstractSafetyCapability.wrap_run_event_stream."""

    @pytest.mark.asyncio
    async def test_input_guard_passes_events_through_without_closing(self) -> None:
        """Test that an input-only guard does not screen or close the stream."""
        start = _text_start("hello")
        stream = EventStream([start])
        guard = _guard(["input"])

        assert await _collect(guard, stream) == [start]
        assert not guard.seen
        assert stream.read_count == 1
        assert stream.closed is False

    @pytest.mark.asyncio
    async def test_tool_guard_passes_events_through_and_closes(self) -> None:
        """Test that a tool-only guard forwards events and closes the stream."""
        start = _text_start("hello")
        stream = EventStream([start])
        guard = _guard(["tool"])

        assert await _collect(guard, stream) == [start]
        assert not guard.seen
        assert stream.closed is True

    @pytest.mark.asyncio
    async def test_allow_releases_events_once_the_interval_is_reached(self) -> None:
        """Test that buffered events are released unchanged after a check."""
        start = _text_start("hel")
        delta = _text_delta("lo")
        stream = EventStream([start, delta])
        guard = _guard(
            ["output", "tool"],
            GuardrailResult.allow(),
            check_tokens=2,
        )

        yielded = await _collect(guard, stream)

        assert yielded == [start, delta]
        assert yielded[0] is start
        assert guard.seen == ["hello"]
        assert stream.closed is True

    @pytest.mark.asyncio
    async def test_part_end_flushes_before_the_default_interval(self) -> None:
        """Test that finishing a part checks the buffered text immediately."""
        start = _text_start("")
        delta = _text_delta("hello")
        end = _text_end("hello")
        stream = EventStream([start, delta, end])
        guard = ScriptedGuard(type=["output"], verdicts=[GuardrailResult.allow()])

        yielded = await _collect(guard, stream)

        assert guard.check_tokens == 50
        assert yielded == [start, delta, end]
        assert guard.seen == ["hello"]

    @pytest.mark.asyncio
    async def test_block_drains_the_rest_of_the_stream(self) -> None:
        """Test that a block releases nothing further and still reads the tail."""
        first = _text_start("ok")
        second = _text_delta("!")
        third = _text_start("bad", index=1)
        fourth = _text_end("bad", index=1)
        fifth = _text_delta("later", index=2)
        stream = EventStream([first, second, third, fourth, fifth])
        guard = _guard(
            ["output"],
            GuardrailResult.allow(),
            GuardrailResult.block("stop"),
            check_tokens=2,
        )
        yielded: list[AgentStreamEvent] = []

        with pytest.raises(OutputBlocked) as exc_info:
            async for event in guard.wrap_run_event_stream(
                run_context(), stream=stream
            ):
                yielded.append(event)

        assert exc_info.value.reason == "stop"
        assert yielded == [first, second]
        assert guard.seen == ["ok!", "bad"]
        assert stream.read_count == 5
        assert stream.closed is True

    @pytest.mark.asyncio
    async def test_replace_emits_a_single_text_event(self) -> None:
        """Test that a replace verdict substitutes one text part for the chunk."""
        event = _text_start("secret", index=3)
        stream = EventStream([event])
        guard = _guard(["output"], GuardrailResult.replace("clean"), check_tokens=1)

        yielded = await _collect(guard, stream)

        assert len(yielded) == 1
        released = yielded[0]
        assert isinstance(released, PartStartEvent)
        assert released.index == 0
        assert isinstance(released.part, TextPart)
        assert released.part.content == "clean"
        assert guard.seen == ["secret"]
        assert stream.closed is True

    @pytest.mark.asyncio
    async def test_unknown_action_closes_without_draining(self) -> None:
        """Test that an unsupported verdict is a usage error and stops the stream."""
        first = _text_start("x")
        second = _text_delta("y")
        stream = EventStream([first, second])
        guard = _guard(
            ["output"],
            GuardrailResult(action="nope"),  # type: ignore[arg-type]
            check_tokens=1,
        )

        with pytest.raises(UserError, match="cannot return nope on output"):
            await _collect(guard, stream)

        assert stream.read_count == 1
        assert stream.closed is True
        assert guard.seen == ["x"]

    @pytest.mark.asyncio
    async def test_stream_without_aclose_still_completes(self) -> None:
        """Test that a stream with no aclose method can be screened."""
        start = _text_start("hello")
        stream = _UnclosableStream([start])
        guard = _guard(["output"], GuardrailResult.allow(), check_tokens=1)
        yielded = [
            event
            async for event in guard.wrap_run_event_stream(run_context(), stream=stream)
        ]

        assert yielded == [start]
        assert guard.seen == ["hello"]

    @pytest.mark.asyncio
    async def test_empty_output_stream_closes_without_evaluating(self) -> None:
        """Test that an empty output stream performs no check."""
        stream = EventStream([])
        guard = _guard(["output"])

        assert await _collect(guard, stream) == []
        assert not guard.seen
        assert stream.closed is True
