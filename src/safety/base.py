"""Abstract base for safety capabilities with a standalone run interface."""

from __future__ import annotations

import dataclasses
from abc import abstractmethod
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import RunContext
from pydantic_ai._agent_graph import GraphAgentState
from pydantic_ai.capabilities import (
    AbstractCapability,
    ValidatedToolArgs,
    WrapModelRequestHandler,
    WrapRunHandler,
)
from pydantic_ai.exceptions import SkipModelRequest, UserError
from pydantic_ai.messages import (
    AgentStreamEvent,
    ModelResponse,
    PartStartEvent,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import AgentDepsT, ToolDefinition

from safety.exceptions import OutputBlocked, ToolBlocked
from safety.types import GuardrailResult, OutputState
from safety.utils import (
    extract_latest_message_text,
    replace_latest_message,
    tool_result_to_str,
)


@dataclass
class AbstractSafetyCapability(AbstractCapability[AgentDepsT]):
    """Interface for safety/moderation that can be called directly."""

    type: Sequence[Literal["input", "output", "tool"]]
    """Which points in the agent run this capability screens.

    - `'input'`: the user's prompt, via `wrap_model_request`.
    - `'output'`: the model's streamed and final text, via `wrap_run_event_stream` and `wrap_run`.
    - `'tool'`: function-tool results, via `after_tool_execute`.
    """

    check_tokens: int = 50
    """How often (in approximate output tokens) to re-run `evaluate` on streamed output.

    Only used when `'output'` is in `type`. Text generated since the last check is buffered and
    withheld from the caller until it clears `evaluate`, so a violation stops the response before
    the flagged content -- or anything after it -- is ever released.
    """

    @abstractmethod
    async def evaluate(self, prompt: str) -> GuardrailResult:
        """Evaluate safety on the given prompt text."""

    async def on_run_error(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        error: BaseException,
    ) -> AgentRunResult[Any]:
        """Recover a run blocked by an output or tool safety guard.

        `wrap_run_event_stream` raises `OutputBlocked` when `evaluate` blocks streamed
        output, and `after_tool_execute` raises `ToolBlocked` (a subclass) when
        `evaluate` blocks a tool result. Convert either into a successful
        `AgentRunResult` carrying the guard's message as the output, instead of
        letting the exception surface to the caller. Any other error is re-raised
        unchanged.
        """
        if isinstance(error, OutputBlocked):
            state = GraphAgentState(
                message_history=ctx.messages,
                usage=ctx.usage,
                metadata=ctx.metadata,
            )
            if ctx.run_id is not None:
                state = dataclasses.replace(state, run_id=ctx.run_id)
            if ctx.conversation_id is not None:
                state = dataclasses.replace(state, conversation_id=ctx.conversation_id)
            if isinstance(error, ToolBlocked):
                output = error.reason or "Tool result blocked by a safety guard."
            else:
                output = error.reason or "Response blocked by a safety guard."
            return AgentRunResult(output=output, _state=state)
        raise error

    async def wrap_run(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        handler: WrapRunHandler,
    ) -> AgentRunResult[Any]:
        """Re-apply the output verdict to the run's final result, not just the stream.

        `wrap_run_event_stream` only rewrites the `AgentStreamEvent`s a *streaming* caller
        observes -- `AgentRunResult.output` is built by the graph directly from the model's own
        response parts, which never pass through that wrapper. Without this, a `'replace'`
        verdict (e.g. `RedactionCapability`) would still leak the original text through
        `result.output`: the non-streaming `/query` endpoint reads only `result.output` and never
        sees the stream at all, and even a streaming caller's final `end`/`AgentRunResultEvent`
        payload would disagree with the (correctly redacted) `text` events it just received.

        Runs after `handler()` returns normally, so a run that errored and was recovered by
        `on_run_error` (e.g. a mid-stream `'block'` verdict) is unaffected -- `on_run_error` only
        gets a turn when the error propagates out of this method, which it does here since this
        method never catches it. Re-evaluating over the *complete* output text (rather than
        reusing whatever chunks `wrap_run_event_stream` already buffered) also avoids that
        wrapper's chunk-boundary blind spot, where a pattern split across two buffered chunks
        could otherwise slip through.
        """
        result = await handler()
        if "output" in self.type:
            verdict = await self.evaluate(result.output)
            match verdict.action:
                case "allow":
                    return result
                case "block":
                    return dataclasses.replace(
                        result,
                        output=verdict.message or "Response blocked by a safety guard.",
                    )
                case "replace":
                    return dataclasses.replace(result, output=str(verdict.replacement))
                case _:
                    raise UserError(
                        f"A Safety guard cannot return {verdict.action} on output; use allow, block, or replace."
                    )
        return result

    async def wrap_run_event_stream(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        stream: AsyncIterable[AgentStreamEvent],
    ) -> AsyncIterable[AgentStreamEvent]:
        """Evaluate the buffered output once `state` is ready, and act on the verdict."""

        async def release(state: OutputState) -> list[AgentStreamEvent]:
            text, events = state.flush()
            result = await self.evaluate(text)
            match result.action:
                case "allow":
                    return events
                case "block":
                    raise OutputBlocked(result.message)
                case "replace":
                    return [
                        PartStartEvent(
                            index=0, part=TextPart(content=str(result.replacement))
                        )
                    ]

        async def drain() -> None:
            """Exhaust `stream` without processing it further.

            Called after a block verdict instead of cancelling the stream, so the model still
            finishes its request and the provider's trailing usage chunk lands in `ctx.usage` --
            cancelling here would abandon the request before that arrives, leaving usage at zero.
            """
            async for _ in stream:
                pass

        if "output" not in self.type and "tool" not in self.type:
            async for event in stream:
                yield event
            return

        try:
            if "output" in self.type:
                state: OutputState = OutputState()
                async for event in stream:
                    state.append(event)
                    if state.ready(self.check_tokens):
                        for released in await release(state):
                            yield released
            else:
                async for event in stream:
                    yield event
        except OutputBlocked:
            await drain()
            raise
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()

    async def after_tool_execute(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        result: Any,
    ) -> Any:
        """Screen a function tool's result before it re-enters the run.

        Raised from this hook rather than `wrap_tool_execute`: pydantic-ai wraps
        exceptions from `wrap_tool_execute` into `on_tool_execute_error` (feeding
        them back to the model as a tool failure), but exceptions from
        `after_tool_execute` other than `ModelRetry`/`ValidationError`/`ToolFailed`
        propagate to the caller -- all the way up through `handler()` in `wrap_run`,
        where `on_run_error` turns a `ToolBlocked` into a run-aborting rejection.
        """
        _ = ctx, call, tool_def, args
        if "tool" not in self.type:
            return result
        verdict = await self.evaluate(tool_result_to_str(result))
        match verdict.action:
            case "allow":
                return result
            case "block":
                raise ToolBlocked(verdict.message)
            case _:
                raise UserError(
                    f"A Safety guard cannot return {verdict.action} on tool; use allow or block."
                )

    async def wrap_model_request(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        """Wrap the model request with safety, guarding the user's prompt."""
        if "input" in self.type:
            prompt = extract_latest_message_text(request_context.messages)
            result = (
                await self.evaluate(prompt)
                if prompt is not None
                else GuardrailResult.allow()
            )
            match result.action:
                case "allow":
                    pass
                case "block":
                    raise SkipModelRequest(
                        ModelResponse(parts=[TextPart(content=result.message or "")])
                    )
                case "replace":
                    if not replace_latest_message(
                        request_context.messages, str(result.replacement)
                    ):
                        raise UserError(
                            "A Safety guard could not find a user prompt to redact in the request."
                        )
                case _:
                    raise UserError(
                        f"A Safety guard cannot return {result.action} on input; use allow, block, or replace."
                    )

        return await handler(request_context)
