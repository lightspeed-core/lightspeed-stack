"""Build the harness ``TieredCompaction`` capability from the compaction config.

Conversation compaction after the Pydantic AI cutover runs as one agent
capability: ``TieredCompaction`` from ``pydantic-ai-harness``. Before every
model request it estimates the history size and, when the history exceeds
``threshold_ratio`` of the context window, applies three tiers in a fixed
order until the history fits: clamp oversized messages, clear old tool
results, then summarize the older history with the chat model.

The builder is not wired into ``build_agent`` or any request handler yet;
the cutover attaches it. With ``keep_user_messages=True``, harness 0.30.0
gives retained user turns the ``keep_messages`` tail slots and drops the
unsummarized messages that no longer fit. At the default configuration this
usually includes the request being answered, so this must be resolved
before the cutover attaches the capability. ``token_floor`` has no harness
equivalent and is ignored, and ``buffer_turns`` becomes a count of messages,
not turn pairs.

Streaming clients learn that compaction started through the run event stream
(LCORE-4693): :class:`SignallingTieredCompaction` emits a
:class:`CompactionStartedEvent` once the harness has decided to compact and
before the first tier runs. Neither pydantic-ai 2.38 nor harness 0.30 has a
compaction lifecycle event of its own; when one arrives, the subclass goes and
the stream handler maps the core event instead.

Delivery timing, checked against pydantic-ai 2.38: ``RunContext.emit`` puts
the event in the run's event buffer, and the buffer is drained into
``run_stream_events`` when the model stream of that request starts, after
``before_model_request`` has returned. The consumer therefore receives the
event after the summarization, but before the first part of the answer.
Immediate dispatch would not move it: it only makes capability listeners run
before ``emit`` returns and leaves the stream position unchanged. A signal
before the summarization needs either the core lifecycle event or a
pydantic-ai change that drains the buffer while the hook runs.
"""

from dataclasses import dataclass, replace
from typing import Final, Optional

from pydantic_ai._run_context import AgentDepsT
from pydantic_ai.messages import CapabilityEvent, ModelMessage
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.tools import RunContext
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

from constants import DEFAULT_CONTEXT_WINDOW
from models.common.agents.run_deps import AgentRunDeps
from models.config import CompactionConfiguration
from utils.token_estimator import estimate_tokens

# The harness requires a clamp threshold and the configuration has no knob for
# it; 50_000 is the value the harness documentation uses.
CLAMP_MAX_PART_TOKENS: Final[int] = 50_000
"""Size in tokens above which an assistant text or tool-call part is clamped."""

# TieredCompaction decides when to compact and calls each tier directly, so a
# tier's own trigger is never read; the harness still requires one to be set.
_UNUSED_TIER_TRIGGER: Final[int] = 1


@dataclass(kw_only=True)
class CompactionStartedEvent(CapabilityEvent, namespace="lcore_compaction"):
    """Emitted on the run stream when tiered compaction is about to shrink the history.

    Attributes:
        message_count: Number of messages in the history being compacted.
        target_tokens: Token budget the tiers escalate toward.

    """

    message_count: int
    target_tokens: int


class SignallingTieredCompaction(TieredCompaction[AgentDepsT]):
    """``TieredCompaction`` that announces each compaction on the run event stream.

    The harness decides whether to compact in ``before_model_request`` and only
    then calls ``_escalate``; overriding ``_escalate`` therefore leaves requests
    under the threshold untouched and emits exactly once per compaction, before
    the first tier runs.

    When the run carries :class:`AgentRunDeps` and a tier changed the history,
    the capability also marks the run's ``context_status`` as ``"compacted"``
    (LCORE-4694). That is the design's definition of the value: any tier that
    altered what the model receives, not only a summary.
    """

    async def _escalate(
        self,
        messages: list[ModelMessage],
        ctx: RunContext[AgentDepsT],
        target: int,
        model_request_parameters: Optional[ModelRequestParameters] = None,
    ) -> list[ModelMessage]:
        """Emit :class:`CompactionStartedEvent`, apply the tiers, record the outcome."""
        await ctx.emit(
            CompactionStartedEvent(message_count=len(messages), target_tokens=target)
        )
        compacted = await super()._escalate(
            messages, ctx, target, model_request_parameters
        )
        if compacted != messages and isinstance(ctx.deps, AgentRunDeps):
            ctx.deps.context_status = "compacted"
        return compacted


def build_tiered_compaction(
    config: CompactionConfiguration,
    model: Model | str,
    context_window: Optional[int] = None,
) -> Optional[TieredCompaction[object]]:
    """Build the tiered compaction capability for an agent.

    Parameters:
        config: Compaction configuration. Its ``summary_prompt``, already
            validated when the configuration was loaded, replaces the harness
            default prompt of the summarizing tier when set.
        model: Chat model that answers the user query; the summarizing tier
            uses it too.
        context_window: Context window of the model in tokens, when known.
            When omitted, the harness resolves it from the model name and
            falls back to ``DEFAULT_CONTEXT_WINDOW``.

    Returns:
        The capability, a :class:`SignallingTieredCompaction` so that streaming
        clients learn when it compacts, or None when compaction is disabled.

    Raises:
        ValueError: If the harness rejects the configuration (for example
            ``threshold_ratio`` of 0).

    """
    if not config.enabled:
        return None
    summarizer = SummarizingCompaction[object](
        model=model,
        max_messages=_UNUSED_TIER_TRIGGER,
        keep_messages=config.buffer_turns,
        keep_tokens=(
            None
            if context_window is None
            else int(context_window * config.buffer_max_ratio)
        ),
        tokenizer=estimate_tokens,
        incremental=True,
        preserve_first_user_message=True,
        keep_user_messages=True,
    )
    if config.summary_prompt is not None:
        summarizer = replace(summarizer, summary_prompt=config.summary_prompt)
    return SignallingTieredCompaction[object](
        tiers=[
            ClampOversizedMessages[object](
                max_part_tokens=CLAMP_MAX_PART_TOKENS, tokenizer=estimate_tokens
            ),
            ClearToolResults[object](
                max_tokens=_UNUSED_TIER_TRIGGER, tokenizer=estimate_tokens
            ),
            summarizer,
        ],
        target_fraction=config.threshold_ratio,
        context_window=context_window,
        fallback_context_window=DEFAULT_CONTEXT_WINDOW,
        tokenizer=estimate_tokens,
    )
