"""Pydantic models for conversation compaction.

Defines ``ConversationSummary`` — one chunk produced each time
compaction triggers. The compaction module (``src/utils/compaction.py``)
creates instances of this model from raw Llama Stack conversation
items; the conversation cache (LCORE-1571) is responsible for
persisting them.

Each compaction run produces exactly one ``ConversationSummary``. The
additive design (decision 2 of the spike) keeps every chunk's summary
as a separate record — they are only re-summarized into a single
record by the recursive fallback when the total summary token count
itself approaches the context window.
"""

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt


class ConversationSummary(BaseModel):
    """A single compaction-produced summary chunk.

    Attributes:
        summary_text: The natural-language summary produced by the
            summarization LLM call. Used directly as context for
            subsequent requests (alongside any later summary chunks
            and the buffer of recent turns kept verbatim).
        summarized_through_turn: Running total of conversation items
            consumed by this and all preceding summaries. Used by the
            caller to advance the partition boundary on the next
            compaction so the new summary only covers items that
            have not yet been summarized.
        token_count: Number of tokens in ``summary_text``. Tracked so
            the recursive-resummarize fallback can decide when the
            cumulative summary size itself approaches the context
            limit without re-tokenizing.
        created_at: ISO 8601 timestamp recording when this summary was
            produced. Kept as a string (not datetime) to match the
            cache schema convention used elsewhere in the codebase.
        model_used: Fully-qualified model identifier used for the
            summarization LLM call (e.g., ``"openai/gpt-4o-mini"``).
            Preserved for audit and for diagnostics when summary
            quality varies between models.
    """

    summary_text: str = Field(
        ...,
        title="Summary text",
        description="Natural-language summary produced by the summarization LLM call.",
    )
    summarized_through_turn: NonNegativeInt = Field(
        ...,
        title="Summarized through turn",
        description="Running total of conversation items consumed by "
        "this and all preceding summaries.",
    )
    token_count: PositiveInt = Field(
        ...,
        title="Token count",
        description="Number of tokens in summary_text.",
    )
    created_at: str = Field(
        ...,
        title="Created at",
        description="ISO 8601 timestamp recording when this summary was produced.",
    )
    model_used: str = Field(
        ...,
        title="Model used",
        description="Fully-qualified model identifier used for the summarization call.",
    )
