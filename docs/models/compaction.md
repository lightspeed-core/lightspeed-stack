# Lightspeed Core Stack



---

# 📋 Schemas for compaction models



## ConversationSummary


A single compaction-produced summary chunk.

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


| Field | Type | Description |
|-------|------|-------------|
| summary_text | string | Natural-language summary produced by the summarization LLM call. |
| summarized_through_turn | integer | Running total of conversation items consumed by this and all preceding summaries. |
| token_count | integer | Number of tokens in summary_text. |
| created_at | string | ISO 8601 timestamp recording when this summary was produced. |
| model_used | string | Fully-qualified model identifier used for the summarization call. |
