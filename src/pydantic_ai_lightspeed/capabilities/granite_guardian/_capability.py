"""Granite Guardian safety capability for input/output guardrail moderation."""

import asyncio
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Optional
from uuid import uuid4

import httpx
from openai import AsyncOpenAI
from pydantic import StrictBool
from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai._agent_graph import GraphAgentState
from pydantic_ai.capabilities import ValidatedToolArgs, WrapRunHandler
from pydantic_ai.direct import model_request
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    AgentStreamEvent,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    NativeToolCallPart,
    NativeToolReturnPart,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.native_tools import MCPServerTool
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage

from client.ogx import AsyncOgxClientHolder
from log import get_logger
from models.common.moderation import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import GraniteGuardianConfig, RiskDefinition
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.granite_guardian.utils import (
    aclose_if_supported,
    build_guardian_block,
    event_text,
    is_safe,
    tool_result_to_str,
)
from pydantic_ai_lightspeed.capabilities.utils import (
    extract_conversation_id,
    message_to_str,
)
from utils.conversations import (
    append_turn_to_conversation,
    replace_last_assistant_message,
)
from utils.token_estimator import estimate_tokens

type Guardrail = tuple[str, str, float, str]

logger = get_logger(__name__)


class _OutputGuardrailViolation(Exception):
    """Raised when streamed output violates an OUTPUT-point guardrail."""


class _ToolGuardrailViolation(Exception):
    """Raised when a tool's result violates a TOOL-point guardrail.

    Raised from ``after_tool_execute`` rather than ``wrap_tool_execute``: the
    tool-execution machinery wraps any exception from ``wrap_tool_execute``
    into ``on_tool_execute_error`` (feeding it back to the model as a tool
    failure), but exceptions from ``after_tool_execute`` other than
    ``ModelRetry``/``ValidationError``/``ToolFailed`` propagate to the caller
    unchanged -- all the way up through ``handler()`` in ``wrap_run``, where
    it's caught alongside ``_OutputGuardrailViolation`` and turned into the
    same kind of run-aborting rejection.

    Carries the offending tool call so ``_reject`` can preserve it in the
    rejection's message history -- ``tool_calls`` still shows what was
    actually called, even though the model's synthesized answer is replaced.
    The tool's *result* is deliberately never carried here: it's the
    content that failed the risk check, so it must not reach the caller via
    ``tool_results`` either.
    """

    def __init__(
        self,
        message: str,
        *,
        response_parts: Sequence[ModelResponsePart] = (),
        request_parts: Sequence[ModelRequestPart] = (),
    ) -> None:
        """Store the violation message alongside the tool activity to preserve.

        Parameters:
            message: The violation message shown to the caller.
            response_parts: Parts (e.g. the offending ``ToolCallPart``, or a
                native tool's ``NativeToolCallPart`` paired with a
                content-stripped, ``outcome="denied"`` ``NativeToolReturnPart``)
                to include in the rejection's ``ModelResponse``. Never
                includes the tool's actual (flagged) result content.
            request_parts: Reserved for a client function tool's
                ``ToolReturnPart`` between the tool call and the rejection
                message; currently always empty, since a denied function
                tool call's result is never preserved either.
        """
        super().__init__(message)
        self.response_parts: tuple[ModelResponsePart, ...] = tuple(response_parts)
        self.request_parts: tuple[ModelRequestPart, ...] = tuple(request_parts)


async def _drain_remaining(stream: AsyncIterable[AgentStreamEvent]) -> None:
    """Exhaust an agent stream without yielding or acting on its events.

    Called after an OUTPUT-point violation is detected, before the
    violation is raised to the caller, so the underlying provider call
    still runs to natural completion instead of being torn down
    mid-generation.

    Cutting the stream immediately on violation (the previous behavior)
    meant the provider's final usage totals were never received (most
    providers only report usage in the terminating chunk), and OGX's own
    conversation-persistence side effect for the turn -- tied to the
    response completing -- could be left half-done. Draining lets both
    finish normally; only the *content* released to the end user is
    withheld.

    Parameters:
        stream: The stream to exhaust.
    """
    try:
        async for _ in stream:
            pass
    except Exception:  # pylint: disable=broad-except
        # Best-effort: a failure while draining (e.g. the connection dropping)
        # must not mask the guardrail violation that's about to be raised.
        logger.debug(
            "Ignoring error while draining stream after guardrail violation",
            exc_info=True,
        )


async def _package_risk_check_task(
    prompt: str, guardrail: Guardrail, model: Model
) -> tuple[ModelResponse, float, str]:
    """Run a single Guardian risk check and return its result.

    Parameters:
        prompt: The text to evaluate.
        guardrail: A guardrail tuple of (name, block, threshold, violation_message).
        model: The Granite Guardian model to use for evaluation.

    Returns:
        A tuple of (model_response, threshold, violation_message).
    """
    name, block, threshold, violation_message = guardrail
    start = asyncio.get_event_loop().time()
    result = await model_request(
        model=model,
        messages=[ModelRequest.user_text_prompt(prompt, instructions=block)],
        model_settings=OpenAIChatModelSettings(
            openai_logprobs=True, openai_top_logprobs=20
        ),
    )
    elapsed = asyncio.get_event_loop().time() - start
    logger.info("Guardian risk '%s' completed in %.3fs", name, elapsed)
    return result, threshold, violation_message


async def _run_risk_check(
    prompt: str,
    model: Model,
    guardrails: list[Guardrail],
    batch_size: int = 3,
) -> tuple[Optional[str], RequestUsage]:
    """Evaluate the prompt against guardrails in parallel batches.

    Guardrails are dispatched concurrently in batches. Within each batch,
    all checks run in parallel; if any violation is found the remaining
    batches are skipped. Per-rule latency is logged at INFO level.

    Parameters:
        prompt: The text to evaluate.
        model: The Granite Guardian model to use for evaluation.
        guardrails: Ordered list of guardrail tuples to check.
        batch_size: Number of risk checks to run in parallel per batch.

    Returns:
        A tuple of (violation_message, token_usage). violation_message is
        None when all checks pass.

    Raises:
        UnexpectedModelBehavior: When the model response is missing
            provider_details or logprobs.
    """
    token_usage = RequestUsage()

    for i in range(0, len(guardrails), batch_size):
        batch = [
            _package_risk_check_task(prompt, g, model)
            for g in guardrails[i : i + batch_size]
        ]

        results = await asyncio.gather(*batch)

        for result, _, _ in results:
            token_usage.incr(result.usage)

        for result, threshold, violation_message in results:
            if not result.provider_details:
                raise UnexpectedModelBehavior(
                    "No provider_details provided from granite guardian's response"
                )

            logprobs = result.provider_details.get("logprobs")
            if not logprobs:
                raise UnexpectedModelBehavior("No logprobs field in provider_details")

            if not is_safe(threshold, logprobs):
                return violation_message, token_usage

    return None, token_usage


_MCP_SERVER_TOOL_PREFIX = f"{MCPServerTool.kind}:"


def _is_mcp_list_tools_call(call_part: NativeToolCallPart) -> bool:
    """Check whether a native tool call is an MCP ``list_tools`` discovery call.

    ``list_tools`` calls just enumerate what an MCP server offers -- they
    carry no user-supplied or tool-produced content, so TOOL-point risks
    (which screen tool *content*) have nothing meaningful to evaluate and
    should never flag them.

    Parameters:
        call_part: The native tool call part to check.

    Returns:
        True if this call is an MCP ``list_tools`` discovery call.
    """
    if not call_part.tool_name.startswith(_MCP_SERVER_TOOL_PREFIX):
        return False
    return call_part.args_as_dict().get("action") == "list_tools"


def _deny_native_results_from(
    native_pairs: Sequence[tuple[NativeToolCallPart, NativeToolReturnPart]],
    from_index: int,
) -> tuple[ModelResponsePart, ...]:
    """Build response parts denying every native result from an index on.

    Calls are always preserved. Return parts before ``from_index`` are kept
    as-is; return parts from ``from_index`` onward are replaced with a
    content-stripped, ``outcome="denied"`` placeholder, since pydantic-ai
    only recognizes a native call alongside a matching return.

    Parameters:
        native_pairs: All native tool call/return pairs from a response.
        from_index: Index of the first pair whose result should be denied;
            every later pair's result is denied too.

    Returns:
        Flattened call/return parts, ready to use as ``response_parts`` on
        a ``_ToolGuardrailViolation``.
    """
    response_parts: list[ModelResponsePart] = []
    for index, (call_part, return_part) in enumerate(native_pairs):
        response_parts.append(call_part)
        if index < from_index:
            response_parts.append(return_part)
        else:
            response_parts.append(
                NativeToolReturnPart(
                    tool_name=return_part.tool_name,
                    content={},
                    tool_call_id=return_part.tool_call_id,
                    outcome="denied",
                )
            )
    return tuple(response_parts)


def _filter_guardrails(
    risks: list[RiskDefinition], point: Literal["input", "output", "tool"]
) -> list[Guardrail]:
    """Filter risk definitions to guardrail tuples for a given guardrail point.

    Parameters:
        risks: All configured risk definitions.
        point: The guardrail point to filter by (INPUT, OUTPUT, or TOOL).

    Returns:
        A list of guardrail tuples for enabled risks matching the point.
    """
    return [
        (
            risk.name,
            build_guardian_block(risk.description, think=risk.enable_thinking),
            risk.threshold,
            risk.violation_message,
        )
        for risk in risks
        if risk.enabled and point in risk.points
    ]


def _get_batch_size(parallel: StrictBool | int, num_guardrail: int) -> int:
    """Resolve the parallel setting to a concrete batch size.

    Parameters:
        parallel: True for full parallelism, False for sequential, or an
            explicit batch size.
        num_guardrail: Total number of guardrails to run.

    Returns:
        The number of risk checks to run concurrently per batch.
    """
    if isinstance(parallel, bool):
        return max(1, num_guardrail) if parallel else 1

    return parallel


@dataclass
class GraniteGuardian(AbstractSafetyCapability):
    """Safety capability using Granite Guardian for risk-based moderation.

    Uses Granite Guardian's logprob-based scoring to evaluate text against
    configured risk categories. When used as a pydantic-ai capability:

    - ``wrap_run`` applies INPUT-point risks to the user prompt before the
      real run starts.
    - ``wrap_run_event_stream`` applies OUTPUT-point risks to the generated
      response, checking each newly generated chunk roughly every
      ``config.streaming_output_check_interval_tokens`` tokens (plus a final
      check over any remainder), so a violation partway through generation
      stops the response before any more of it is released to the caller.
      Each check screens only the chunk generated since the previous check
      (not the whole response so far), so Guardian's workload stays linear
      in the response length instead of growing quadratically. None of the
      currently configured risk categories require cross-chunk context; if
      one ever does, that risk should carry its own overlap/context handling
      rather than reintroducing full-history re-checks for every risk.
    - ``after_tool_execute`` applies TOOL-point risks to each tool call's
      result once it's returned, screening content coming back from tools
      (e.g. MCP servers) before it can flow into the model's context.

    Any of these checks short-circuits the run with the same kind of
    rejection result. The ``run`` method provides a standalone shield
    interface for use outside the agent lifecycle (see
    ``run_moderation_guardrail_point``).

    Attributes:
        config: Granite Guardian configuration with risks and connection details.
        run_moderation_guardrail_point: The guardrail point used by the
            standalone ``run`` method.
    """

    config: GraniteGuardianConfig
    run_moderation_guardrail_point: Literal["input", "output", "tool"] = "input"
    _model: Model = field(init=False)
    # GraniteGuardian is re-instantiated on every request (see build_agent),
    # but its config objects are created once at startup and live for the
    # process's lifetime. This cache lets repeated instantiations for the
    # same shield reuse one HTTP client/connection pool instead of leaking a
    # new one per request. Keyed by id(config) since GraniteGuardianConfig is
    # unhashable; distinct config objects (even with identical values) are
    # intentionally cached separately.
    _model_cache: ClassVar[dict[int, Model]] = {}

    def __post_init__(self) -> None:
        """Initialize the Granite Guardian model with the configured provider."""
        cache_key = id(self.config)
        if cache_key in GraniteGuardian._model_cache:
            self._model = GraniteGuardian._model_cache[cache_key]
            return

        http_client = httpx.AsyncClient(
            verify=self.config.verify_ssl,
            timeout=self.config.timeout,
        )

        openai_client = AsyncOpenAI(
            base_url=self.config.url,
            api_key=(
                self.config.api_key.get_secret_value()  # pylint: disable=no-member
                if self.config.api_key is not None
                else "api-key-not-set"
            ),
            max_retries=self.config.max_retries,
            http_client=http_client,
        )

        provider = OpenAIProvider(openai_client=openai_client)

        self._model = OpenAIChatModel(self.config.model_id, provider=provider)
        GraniteGuardian._model_cache[cache_key] = self._model

    async def wrap_run(
        self, ctx: RunContext, *, handler: WrapRunHandler
    ) -> AgentRunResult:
        """Apply input guardrails before the agent run.

        Evaluates the user prompt against all INPUT-point risks. If any risk
        is violated, the run is short-circuited with a rejection message.
        Otherwise, the handler is called to proceed with the real run, which
        applies OUTPUT-point risks incrementally via ``wrap_run_event_stream``
        and TOOL-point risks to each tool result via ``after_tool_execute``.
        A violation surfaced by either is caught here and turned into the
        same kind of rejection.

        Parameters:
            ctx: The run context containing the user prompt and usage tracker.
            handler: The handler to call if the input passes all guardrails.

        Returns:
            The agent run result, either a rejection or the handler's result.
        """
        user_prompt = message_to_str(ctx.prompt)

        input_guardrails = _filter_guardrails(self.config.risks, "input")
        batch_size = _get_batch_size(self.config.parallel, len(input_guardrails))
        # TODO: We need to consider how we want to reveal the token usage for Granite Guardian,  # pylint: disable=fixme
        # since combining the token usage with the main inference model is not a right thing to do.
        violation_message, _ = await _run_risk_check(
            user_prompt, self._model, input_guardrails, batch_size
        )

        if violation_message is not None:
            return await self._reject(ctx, violation_message, real_turn_persisted=False)

        try:
            return await handler()  # proceed with the real run
        except (_OutputGuardrailViolation, _ToolGuardrailViolation) as exc:
            return await self._reject(
                ctx,
                str(exc),
                real_turn_persisted=True,
                response_parts=getattr(exc, "response_parts", ()),
                request_parts=getattr(exc, "request_parts", ()),
            )

    async def _reject(
        self,
        ctx: RunContext,
        violation_message: str,
        *,
        real_turn_persisted: bool,
        response_parts: Sequence[ModelResponsePart] = (),
        request_parts: Sequence[ModelRequestPart] = (),
    ) -> AgentRunResult:
        """Short-circuit the run with a rejection message and persist it.

        Shared by the input-guardrail check in ``wrap_run`` and the
        output-guardrail check in ``wrap_run_event_stream`` (surfaced via
        ``_OutputGuardrailViolation``): both replace the turn with a single
        rejection message rather than exposing any content flagged as unsafe.

        Parameters:
            ctx: The run context containing the user prompt and usage tracker.
            violation_message: The message describing the violated risk.
            real_turn_persisted: Whether OGX already persisted a real
                assistant turn for this request before the violation was
                caught. This is the case for OUTPUT-point violations, since
                the real model call has already completed (and been recorded
                by OGX) by the time streamed text fails a guardrail check.
                It's also the case for TOOL-point violations: the model
                response requesting the tool call has already completed (and
                been recorded by OGX) by the time the tool's result is
                screened. INPUT-point violations short-circuit before any
                model call is made, so no turn exists yet.
            response_parts: Tool call activity (e.g. a ``ToolCallPart``, or a
                native tool's call/return pair) to preserve in the
                rejection's ``ModelResponse``, from a ``_ToolGuardrailViolation``.
                Empty for INPUT- and OUTPUT-point violations.
            request_parts: A client function tool's ``ToolReturnPart`` to
                preserve in a ``ModelRequest`` between the tool call and the
                rejection message, from a ``_ToolGuardrailViolation``. Empty
                otherwise.

        Returns:
            An ``AgentRunResult`` whose output is the violation message, with
            ``tool_calls``/``tool_results`` still reflecting any preserved
            tool activity.
        """
        user_prompt = message_to_str(ctx.prompt)
        messages: list[ModelRequest | ModelResponse] = [
            ModelRequest.user_text_prompt(user_prompt)
        ]
        if response_parts:
            messages.append(ModelResponse(list(response_parts), finish_reason="stop"))
        if request_parts:
            messages.append(ModelRequest(list(request_parts)))
        messages.append(
            ModelResponse([TextPart(violation_message)], finish_reason="stop")
        )
        state = GraphAgentState(usage=ctx.usage, message_history=messages)

        conversation_id = extract_conversation_id(ctx.model)
        if conversation_id is not None:
            client = AsyncOgxClientHolder().get_client()
            if real_turn_persisted:
                # OGX already recorded the real (possibly unsafe) assistant
                # turn; replace it instead of appending a second turn. The
                # stream is always drained to natural completion before a
                # violation is raised (see _drain_remaining), so that turn
                # is reliably persisted by the time we get here.
                await replace_last_assistant_message(
                    client, conversation_id, violation_message
                )
            else:
                await append_turn_to_conversation(
                    client,
                    conversation_id,
                    user_prompt,
                    violation_message,
                )
        else:
            logger.warning(
                "Unable to determine conversation ID from model settings; "
                "skipping v1/conversation persistence for rejected question."
            )

        return AgentRunResult(output=violation_message, _state=state)

    async def wrap_run_event_stream(
        self,
        ctx: RunContext,
        *,
        stream: AsyncIterable[AgentStreamEvent],
    ) -> AsyncIterable[AgentStreamEvent]:
        """Screen streamed output against OUTPUT-point risks as it's generated.

        Text is buffered until ``config.streaming_output_check_interval_tokens``
        tokens accumulate, then that chunk (not the whole response so far) is
        checked against every OUTPUT-point risk. Events are released only
        after their text clears a check. A final check covers any remainder
        when the stream ends. When no OUTPUT-point risks are configured,
        events pass through unchanged. An event that contributes no text
        (e.g. a tool-call event) is also released immediately as long as no
        text is currently buffered; once text is pending, later non-text
        events are held with it and released together once that text clears.

        Checking only the newly generated chunk on each interval (instead of
        re-sending everything checked so far) keeps Guardian's workload
        linear in the response length. It does mean risky content split
        exactly across a check boundary could, in principle, evade detection;
        none of the currently configured risk categories require that kind
        of cross-chunk context. Token counts are accumulated per fragment
        (not by re-tokenizing the whole pending chunk on every event), so
        checking-interval bookkeeping also stays linear.

        On a mid-stream violation, the remainder of ``stream`` is drained
        (see ``_drain_remaining``) before the violation is raised, so the
        underlying provider call reaches natural completion -- giving
        accurate usage totals and letting OGX's own turn-persistence
        complete -- rather than being cut off mid-generation. Only the
        *content* is withheld from the caller.

        Parameters:
            ctx: The run context for the current agent run (unused).
            stream: The underlying agent stream to guard.

        Yields:
            Events from ``stream`` once their text has cleared guardrails. A
            synthetic ``PartEndEvent`` carrying the violation message is
            yielded immediately before raising, so callers that build up a
            response from stream events (e.g. conversation persistence) see
            the rejection text instead of an empty response.

        Raises:
            _OutputGuardrailViolation: When an OUTPUT-point risk is violated.
        """
        _ = ctx
        output_guardrails = _filter_guardrails(self.config.risks, "output")
        batch_size = (
            _get_batch_size(self.config.parallel, len(output_guardrails))
            if output_guardrails
            else 1
        )
        interval = self.config.streaming_output_check_interval_tokens

        pending_events: list[AgentStreamEvent] = []
        pending_fragments: list[str] = []
        pending_tokens = 0
        # Tracks the index of the currently open text part, so a synthetic
        # PartEndEvent reports a violation against the part it actually
        # belongs to instead of always assuming index 0.
        part_index = 0

        try:
            async for event in stream:
                if isinstance(event, PartStartEvent):
                    part_index = event.index

                if not output_guardrails:
                    yield event
                    continue

                text = event_text(event)
                if not text and not pending_fragments:
                    # Nothing buffered and this event carries no text of its
                    # own (e.g. a tool-call event): no reason to withhold it.
                    yield event
                    continue

                pending_events.append(event)
                if text:
                    pending_fragments.append(text)
                    pending_tokens += estimate_tokens(text)

                if pending_tokens >= interval:
                    pending_text = "".join(pending_fragments)
                    violation_message, _ = await _run_risk_check(
                        pending_text, self._model, output_guardrails, batch_size
                    )
                    if violation_message is not None:
                        yield PartEndEvent(
                            index=part_index, part=TextPart(violation_message)
                        )
                        # Let the underlying provider call finish instead of
                        # tearing it down mid-generation (see
                        # _drain_remaining).
                        await _drain_remaining(stream)
                        raise _OutputGuardrailViolation(violation_message)

                    pending_fragments = []
                    pending_tokens = 0
                    for pending_event in pending_events:
                        yield pending_event
                    pending_events = []

            if output_guardrails and pending_fragments:
                pending_text = "".join(pending_fragments)
                violation_message, _ = await _run_risk_check(
                    pending_text, self._model, output_guardrails, batch_size
                )
                if violation_message is not None:
                    yield PartEndEvent(
                        index=part_index, part=TextPart(violation_message)
                    )
                    raise _OutputGuardrailViolation(violation_message)

            for pending_event in pending_events:
                yield pending_event
        finally:
            await aclose_if_supported(stream)

    async def after_tool_execute(
        self,
        ctx: RunContext,
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        result: Any,
    ) -> Any:
        """Screen a tool's result against TOOL-point risks before it re-enters the run.

        Applies every enabled TOOL-point risk to the raw result returned by
        the tool function (rendered to text via ``tool_result_to_str``).
        Screening the result -- rather than the call's arguments -- guards
        against untrusted content coming back from tools (e.g. MCP servers)
        that could otherwise flow into the model's context unchecked, such
        as prompt-injection payloads embedded in fetched content.

        ``after_tool_execute`` (not ``wrap_tool_execute``) is used so a
        violation reaches ``wrap_run`` as a run-aborting exception instead of
        being fed back to the model as a tool failure -- see
        ``_ToolGuardrailViolation``. When no TOOL-point risks are configured,
        the result passes through unchanged.

        Parameters:
            ctx: The run context for the current agent run (unused).
            call: The tool call that produced this result. Preserved on a
                violation so the rejection's ``tool_calls`` still shows it.
            tool_def: The definition of the tool that was called (unused).
            args: The validated arguments the tool was called with (unused).
            result: The raw result returned by the tool function (unused on
                a violation: it's the flagged content, so it's never
                preserved -- the rejection's ``tool_results`` omits it
                entirely).

        Returns:
            ``result`` unchanged, once it clears every TOOL-point risk.

        Raises:
            _ToolGuardrailViolation: When a TOOL-point risk is violated.
        """
        _ = ctx, tool_def, args
        tool_guardrails = _filter_guardrails(self.config.risks, "tool")
        if not tool_guardrails:
            return result

        batch_size = _get_batch_size(self.config.parallel, len(tool_guardrails))
        result_text = tool_result_to_str(result)
        violation_message, _ = await _run_risk_check(
            result_text, self._model, tool_guardrails, batch_size
        )

        if violation_message is not None:
            raise _ToolGuardrailViolation(violation_message, response_parts=(call,))

        return result

    async def after_model_request(
        self,
        ctx: RunContext,
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        """Screen native tool results against TOOL-point risks.

        Native tools (e.g. MCP server tools, web search, file search) can be
        executed by the OGX backend itself as part of a single model
        response -- OGX calls the tool, gets its result, and hands
        pydantic-ai a ``ModelResponse`` that already contains both the call
        and its ``NativeToolReturnPart`` result. Because pydantic-ai never
        invokes a tool function itself in that case, ``after_tool_execute``
        (which only fires around pydantic-ai's own tool-execution machinery)
        never sees that result. This hook closes that gap by screening every
        ``NativeToolReturnPart`` in the response directly -- except MCP
        ``list_tools`` discovery calls, which carry no tool-produced content
        and are never evaluated (see ``_is_mcp_list_tools_call``).

        Parameters:
            ctx: The run context for the current agent run (unused).
            request_context: Context for the model request that produced
                this response (unused).
            response: The model response to screen, potentially containing
                native tool call/return pairs.

        Returns:
            ``response`` unchanged, once every native tool result clears all
            TOOL-point risks.

        Raises:
            _ToolGuardrailViolation: When a TOOL-point risk is violated.
                Every native tool call/return pair from this response is
                preserved on the exception so the rejection's ``tool_calls``
                still shows what else was called -- but starting from the
                pair that actually violated the risk, every return part from
                that point on (including later pairs never even checked) is
                replaced with a content-stripped, ``outcome="denied"``
                placeholder (pydantic-ai only recognizes a native call
                alongside a matching return, so the call can't be preserved
                without one). Once one result is flagged, later results in
                the same response are treated as suspect too and withheld,
                even if they'd individually pass the risk check. Pairs
                before the violation are unaffected.
        """
        _ = ctx, request_context
        tool_guardrails = _filter_guardrails(self.config.risks, "tool")
        if not tool_guardrails:
            return response

        native_pairs = response.native_tool_calls
        if not native_pairs:
            return response

        batch_size = _get_batch_size(self.config.parallel, len(tool_guardrails))
        for violating_index, (call_part, return_part) in enumerate(native_pairs):
            if _is_mcp_list_tools_call(call_part):
                continue
            result_text = tool_result_to_str(return_part.content)
            violation_message, _ = await _run_risk_check(
                result_text, self._model, tool_guardrails, batch_size
            )
            if violation_message is not None:
                raise _ToolGuardrailViolation(
                    violation_message,
                    response_parts=_deny_native_results_from(
                        native_pairs, violating_index
                    ),
                )

        return response

    async def run(self, input_text: str) -> ShieldModerationResult:
        """Run standalone shield moderation on the given text.

        Uses ``run_moderation_guardrail_point`` to filter which risks apply.

        Parameters:
            input_text: The text to evaluate.

        Returns:
            A blocked result with the violation message, or a passed result.
        """
        filtered_guardrails = _filter_guardrails(
            self.config.risks, self.run_moderation_guardrail_point
        )
        batch_size = _get_batch_size(self.config.parallel, len(filtered_guardrails))

        violation_message, _ = await _run_risk_check(
            input_text, self._model, filtered_guardrails, batch_size
        )

        if violation_message is not None:
            return ShieldModerationBlocked(
                message=violation_message, moderation_id=f"modr-{uuid4()}"
            )

        return ShieldModerationPassed()
