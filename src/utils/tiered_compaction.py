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
"""

from typing import Final, Optional

from pydantic_ai.models import Model
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

from constants import DEFAULT_CONTEXT_WINDOW
from models.config import CompactionConfiguration
from utils.token_estimator import estimate_tokens

# The harness requires a clamp threshold and the configuration has no knob for
# it; 50_000 is the value the harness documentation uses.
CLAMP_MAX_PART_TOKENS: Final[int] = 50_000
"""Size in tokens above which an assistant text or tool-call part is clamped."""

# TieredCompaction decides when to compact and calls each tier directly, so a
# tier's own trigger is never read; the harness still requires one to be set.
_UNUSED_TIER_TRIGGER: Final[int] = 1


def build_tiered_compaction(
    config: CompactionConfiguration,
    model: Model | str,
    context_window: Optional[int] = None,
) -> Optional[TieredCompaction[object]]:
    """Build the tiered compaction capability for an agent.

    Parameters:
        config: Compaction configuration.
        model: Chat model that answers the user query; the summarizing tier
            uses it too.
        context_window: Context window of the model in tokens, when known.
            When omitted, the harness resolves it from the model name and
            falls back to ``DEFAULT_CONTEXT_WINDOW``.

    Returns:
        The capability, or None when compaction is disabled.

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
    return TieredCompaction[object](
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
