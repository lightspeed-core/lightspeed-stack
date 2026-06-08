# Conversation Compaction Design

|                          |                                                                                   |
|--------------------------|-----------------------------------------------------------------------------------|
|--------------------------|-----------------------------------------------------------------------------------|
| **Date**                 | 2026-03-16                                                                        |
| **Component**            | lightspeed-stack                                                                  |
| **Authors**              | Maxim Svistunov                                                                   |
| **Feature / Initiative** | [LCORE-1311](https://issues.redhat.com/browse/LCORE-1311)                         |
| **Spike**                | [LCORE-1314](https://issues.redhat.com/browse/LCORE-1314)                         |
| **Links**                | Spike doc: `docs/design/conversation-compaction/conversation-compaction-spike.md` |

# What

Conversation history compaction for lightspeed-stack. When a conversation's token count approaches the model's context window limit, lightspeed-stack summarizes older turns using the LLM and keeps recent turns verbatim. The conversation continues without hitting HTTP 413.

Full conversation history is preserved in Llama Stack for UI display and audit. Only the LLM's input context is compacted.

# Why

Today, when a conversation exceeds the model's context window, Llama Stack's inference provider rejects the request. lightspeed-stack catches this and returns HTTP 413 (`PromptTooLongResponse`). The conversation is stuck — the user must start over.

Current failure path (verified in code):

```
Llama Stack sends full prompt → provider rejects (400/413, "context_length")
→ lightspeed-stack catches RuntimeError or APIStatusError
→ returns PromptTooLongResponse (HTTP 413)
→ no recovery, no truncation, no summarization
```

Evidence: `query.py:321-325`, `streaming_query.py:312-317`.

# Requirements

R1  
When estimated input tokens exceed a configurable threshold (default 70% of the model's context window), lightspeed-stack must summarize older conversation turns before sending the request to the LLM.

R2
Recent turns must be preserved verbatim — not summarized. The buffer zone uses a degrading guard: start at N turns (default 4), but if those N turns exceed the token budget, degrade to N-1, then N-2, down to 0. This prevents compaction from producing output that still doesn't fit.

R3  
Summarization must be additive: each chunk's summary is generated once and kept. Summaries are only re-summarized when the total summary size itself approaches the context limit.

R4  
The summarization prompt must be domain-specific for Red Hat product support, preserving error messages, commands, outcomes, and user environment details.

R5  
The same model used for the user's query must be used for summarization.

R6  
Full conversation history must remain accessible via the Llama Stack Conversations API (for UI display and audit). Only the LLM's input context uses summaries.

R7  
The response must include a `context_status` field indicating `"full"` (no compaction) or `"summarized"` (compaction occurred).

R8  
Token estimation must run on every request using tiktoken. Cost is ~1-5ms, negligible compared to the LLM call.

R9  
Compaction configuration must be admin-configurable via YAML: threshold ratio, fixed token floor, and buffer zone size.

R10
After compaction, lightspeed-stack builds the LLM input explicitly — the summaries plus the recent verbatim turns plus the new query — and stops passing the Llama Stack `conversation` parameter for that request, because Llama Stack always reloads the full message history when the `conversation` parameter is set (verified empirically on llama-stack 0.6.0; see the Changelog and the spike doc). The summary is still written into the conversation as a marked item so it appears in the Conversations API, but the marker is lightspeed-stack's own boundary bookkeeping, not a Llama Stack selection mechanism. The `conversation_id` is preserved across the whole conversation, and the full history (including pre-compaction turns) remains in the conversation's items for UI/audit. Because the `conversation` parameter is no longer sent in compacted mode, lightspeed-stack appends each completed turn to the conversation itself.

This applies to every endpoint that builds context from a growing conversation and calls the Responses API: `/v1/query`, `/v1/streaming_query`, the A2A executor, and `/v1/responses`. (The `/v1/rlsapi` inference path is stateless — no stored conversation — and is therefore out of scope.)

R11
Compaction must be blocking per conversation. If a request triggers compaction, concurrent requests on the same conversation must wait until compaction completes. This prevents race conditions (e.g., two requests both triggering compaction, or a new message being appended mid-compaction).

R12
The native streaming endpoint (`/v1/streaming_query`) must emit a compaction event (e.g., `{"event": "compaction"}`) before the summarization LLM call begins, so the client can display a progress indicator. Non-streaming requests (`/v1/query`) have no mid-request notification mechanism. The A2A executor compacts inline (it is not a browser SSE stream). `/v1/responses` is the OpenAI-compatible endpoint and compacts **silently** here; emitting a `compaction` event on it would itself be spec-compliant under the OpenResponses extension-events convention, and that option is left open for a follow-up — silent is the initial choice to keep the endpoint a drop-in for clients written against the upstream OpenAI Responses API. Our own clients should use `/v1/streaming_query` to receive the event.

# Use Cases

U1  
As a user, I want long conversations to continue working instead of failing with HTTP 413, so that I don't lose my troubleshooting context.

U2  
As a user, I want the assistant to remember what we discussed earlier in the conversation (key decisions, error messages, steps tried), even if the raw messages were summarized.

U3  
As a user, I want to see my full conversation history in the UI, even if the LLM is working from a summarized version.

U4  
As an administrator, I want to configure when compaction triggers and how much recent context to preserve, so that I can tune the tradeoff between context quality and token usage.

U5  
As a developer integrating with the API, I want to know whether the response was generated from full context or summarized context, so that I can display an appropriate indicator.

# Architecture

## Overview

```
User Query → lightspeed-stack
  1. Resolve model, system prompt, tools
  2. Build input (query + RAG + attachments)
  3. Acquire per-conversation lock (blocks concurrent requests)
  4. Estimate total tokens (tiktoken): system + (summaries + recent items) + new query
  5. If compaction needed (tokens > threshold) OR a prior summary marker exists:
     a. Emit compaction event (native streaming endpoint only)
     b. Retrieve conversation items from Llama Stack
     c. Split into "old" (summarize) and "recent" (keep)
        — degrading guard: reduce recent turns if they exceed token budget
     d. Summarize old turns → write summary as a marked item into conversation
  6. Build EXPLICIT input: [summary markers] + [recent items after last marker] + new query
  7. Call Llama Stack Responses API WITHOUT the conversation parameter
     (so Llama Stack does not reload the full history)
  ↓
Llama Stack
  8. Processes exactly the explicit input
  ↓
lightspeed-stack
  9. Append the completed turn to the conversation items (continuous history,
     same conversation_id) — Llama Stack did not auto-store it (no conversation param)
  10. Release per-conversation lock
  11. Return response (context_status="summarized" when 1573 lands; "full" otherwise)
```

Note: when no prior summary exists and the request is below the threshold,
none of step 5–9 applies — the request takes the normal path with the
`conversation` parameter, byte-for-byte unchanged. The explicit-input path is
entered only for conversations that are actually being (or have been) compacted.

## Token estimation

Add tiktoken as a dependency. Create `src/utils/token_estimator.py`:

``` python
def estimate_tokens(text: str, encoding_name: str = "cl100k_base") -> int
def estimate_conversation_tokens(messages: list, system_prompt: str) -> int
```

Context window sizes are configured per model in YAML:

``` yaml
inference:
  default_model: openai/gpt-4o-mini
  context_windows:
    openai/gpt-4o-mini: 128000
    openai/gpt-4o: 128000
```

Token estimation runs on every request. Cost: ~1-5ms for a 10K token conversation, negligible compared to the LLM call (seconds).

## Trigger mechanism

Token-based, not turn-based. Turn sizes vary wildly (a turn with tool results can be 10x a simple Q&A).

`trigger_when(estimated_tokens > context_window * threshold_ratio)`

`threshold_ratio` defaults to 0.7 (70% of context window). A fixed token floor (e.g., 4096 tokens) prevents triggering on very small context windows.

Both values are admin-configurable via YAML:

``` yaml
compaction:
  enabled: true
  threshold_ratio: 0.7
  token_floor: 4096
  buffer_turns: 4
  buffer_max_ratio: 0.3
```

Example for a 128K context window at 70% threshold:

- Trigger at 89,600 tokens.
- Summarize ~70,000 tokens of old turns.
- Summary output: ~2,000-4,000 tokens.
- Cost: 1 additional LLM call of ~74,000 total tokens.

## Conversation partitioning

When triggered, split conversation into:

- **Summary zone**: Oldest turns that will be summarized.
- **Buffer zone**: Most recent turns kept verbatim.

Buffer zone uses a degrading guard: start with N turns (default 4), estimate their token count. If they exceed the available budget (context window minus summary minus new query), reduce to N-1 turns and re-estimate. Continue degrading (4→3→2→1→0) until the buffer fits. This handles pathological cases where a few large turns (e.g., with tool results) consume most of the context.

## Additive summarization

Each chunk's summary is generated independently and kept:

```
After 1st compaction:  [summary of turns 1-N] + [recent turns] + [query]
After 2nd compaction:  [summary of turns 1-N] + [summary of turns N+1-M] + [recent turns] + [query]
After 3rd compaction:  [summary 1] + [summary 2] + [summary 3] + [recent turns] + [query]
```

When the total summary token count itself approaches the context limit, the summary chunks are folded into a single chunk by recursive re-summarization. As built, the fold is **persisted** in the summary cache via `replace_summaries` and reused, not recomputed each request; an in-memory recompute-per-request fold was prototyped and rejected because it produces non-deterministic context across turns. Folding requires a persisting cache; marker-only mode keeps the additive chunks with no fold.

Why additive over recursive: a PoC experiment with 50 queries and 4 compaction cycles showed that recursive summarization progressively loses early-conversation context. By the 4th cycle, the summary had lost Kubernetes fundamentals, Helm, and Istio details that were discussed in the first 15 turns. See `poc-results/01-analysis.txt` for full evidence.

## Summarization prompt

Domain-specific for Red Hat product support:

```
Summarize this conversation history for an AI assistant that helps with
Red Hat product support. Preserve:
1. The user's original question and environment details.
2. All error messages, commands run, and their outcomes.
3. Key decisions and their rationale.
4. What was resolved and what remains open.
5. Clear attribution (what the user reported vs what the assistant suggested).

Be concise but complete. The assistant will use this summary as its only
memory of older conversation turns.
```

## Summary storage

Extend lightspeed's conversation cache with summary fields. Schema:

``` python
class ConversationSummary(BaseModel):
    summary_text: str
    summarized_through_turn: int  # last turn index included in this chunk
    token_count: int              # tokens in this summary chunk
    created_at: str               # ISO 8601
    model_used: str               # model used for summarization
```

A conversation may have multiple summary chunks (one per compaction event). All cache backends (SQLite, Postgres, memory) need this schema extension.

As built, the cache is the **preferred source of truth** for summary text at runtime: each chunk is written on compaction (`store_summary`) and the active set is read back from it (`get_summaries`). The Llama Stack marker items remain an authoritative fallback — used when no persisting cache is configured — and the audit record; the marker position still defines the recent-verbatim boundary. The recursive fold persists through `replace_summaries` (atomic delete-all + insert of the folded chunk), a cache operation added for this (LCORE-1571).

## Changed request flow after compaction

After compaction, lightspeed-stack writes the summary as a marked conversation item (a message whose text begins with a recognizable sentinel) so it appears in the Conversations API and serves as lightspeed-stack's own boundary marker.

When building context for a compacted conversation, lightspeed-stack fetches the conversation items, reads the active summaries from the summary cache (LCORE-1571) — falling back to the marker texts when no persisting cache is configured — takes the items after the last marker as the recent verbatim buffer, and sends `[summaries] + [recent items] + [new query]` as **explicit input**, **without** the `conversation` parameter. This is necessary because Llama Stack reloads the *full* stored message history whenever the `conversation` parameter is set — there is no marker-based selection hook (verified empirically; see the Changelog). Each completed turn is then appended back to the conversation items by lightspeed-stack, since Llama Stack no longer auto-stores it.

This preserves a single continuous conversation identity. The `conversation_id` never changes, the user sees one conversation in the UI, and the Conversations API returns the full history including the summary marker items.

## API response changes

Add `context_status` field to `QueryResponse` and `StreamingQueryResponse`:

``` python
context_status: str = Field(
    "full",
    description="Context status: 'full' (no compaction), "
    "'summarized' (older turns summarized).",
)
```

The existing `truncated` field remains deprecated.

## Configuration

Add to `models/config.py`, following the existing `ConfigurationBase` pattern:

``` python
class CompactionConfiguration(ConfigurationBase):
    enabled: bool = Field(
        False,
        title="Enable compaction",
        description="When true, older conversation turns are summarized "
        "when estimated tokens approach the context window limit.",
    )
    threshold_ratio: float = Field(
        0.7,
        title="Threshold ratio",
        description="Trigger compaction when estimated tokens exceed this "
        "fraction of the model's context window (0.0-1.0).",
    )
    token_floor: int = Field(
        4096,
        title="Token floor",
        description="Minimum token count before compaction can trigger. "
        "Prevents triggering on very small context windows.",
    )
    buffer_turns: int = Field(
        4,
        title="Buffer turns",
        description="Number of recent turns to keep verbatim.",
    )
    buffer_max_ratio: float = Field(
        0.3,
        title="Buffer max ratio",
        description="Maximum fraction of context window the buffer zone "
        "can occupy, regardless of buffer_turns.",
    )
```

Add `compaction` field to the root `Configuration` class.

**Limitation — disabling after a conversation is compacted.** `enabled: false` is a full off-switch: requests pass through unchanged, with the `conversation` parameter intact (full-history replay). If compaction is disabled *after* a conversation has already been compacted, that conversation reverts to full-history replay — which can re-hit the HTTP 413 path and resend summary marker text through the model. Toggling `enabled` mid-conversation on an already-compacted conversation is therefore unsupported; keep it enabled for the lifetime of such conversations.

# Implementation Suggestions

## Key files and insertion points

| File                                   | What to do                                                                 |
|----------------------------------------|----------------------------------------------------------------------------|
| `pyproject.toml`                       | Add `tiktoken` dependency                                                  |
| `src/utils/token_estimator.py`         | New module: `estimate_tokens()`, `estimate_conversation_tokens()`          |
| `src/utils/compaction.py`              | New module: summarization logic, partitioning, additive summary management |
| `src/models/config.py`                 | Add `CompactionConfiguration` (near `ConversationHistoryConfiguration`)    |
| `src/configuration.py`                 | Add `compaction_configuration` property to `AppConfig` singleton           |
| `src/utils/conversation_compaction.py` | New module: `apply_compaction()` / `apply_compaction_blocking()`, `needs_compaction_path()`, marker helpers, per-conversation lock |
| `src/models/common/responses/responses_api_params.py` | `omit_conversation` flag — drops the `conversation` parameter from the request body in compacted mode |
| `src/app/endpoints/query.py`           | Call `apply_compaction_blocking()` after preparing params; store the turn in compacted mode |
| `src/app/endpoints/streaming_query.py` | Compaction-aware SSE path that emits the `compaction` event before summarizing (R12) |
| `src/app/endpoints/a2a.py`             | Inline compaction (no SSE event); store the turn on `response.completed` |
| `src/app/endpoints/responses.py`       | Silent compaction (OpenAI-compatible); store the turn via `_append_previous_response_turn` |
| `src/models/responses.py` (now relocated) | `context_status` field — deferred to LCORE-1573 |
| `src/cache/` (all backends)            | `ConversationSummary` storage — LCORE-1571 |

## How compaction is invoked

Rather than a hook buried inside `prepare_responses_params()`, compaction is a
reusable unit in `src/utils/conversation_compaction.py` that each endpoint
calls after its params are prepared:

- `apply_compaction_blocking(client, params, inference_config, compaction_config)`
  returns a `CompactionResult` (possibly-rewritten params, a `summarized`
  flag, and the `original_input`). Non-streaming `/v1/query`, A2A, and
  `/v1/responses` use this.
- `apply_compaction(..., emit_events=True)` is the async-generator variant that
  yields a `CompactionStartedEvent` before the summarization LLM call; the
  native `/v1/streaming_query` SSE path uses it to satisfy R12.
- `needs_compaction_path(...)` is a cheap pre-stream predicate (no LLM, no lock)
  that the streaming endpoint uses to route only actually-compacting
  conversations through the in-stream path, leaving every other request on the
  unchanged flow.

When compaction is active, the endpoint builds explicit input, the
`conversation` parameter is omitted (via `ResponsesApiParams.omit_conversation`),
and the completed turn is appended to the conversation items afterward.

## Fetching conversation history

Use the same pattern as `conversations_v1.py:240-246`:

``` python
items_response = await client.conversations.items.list(
    conversation_id=llama_stack_conv_id,
    after=None,
    include=None,
    limit=None,
    order="asc",
)
```

## Config pattern

All config classes extend `ConfigurationBase` which sets `extra`"forbid"`.
Use =Field()` with defaults, title, and description. Add `@model_validator(mode`"after")= for cross-field validation if needed.

Example config files go in `examples/`.

## Test patterns

- Framework: pytest + pytest-asyncio + pytest-mock. unittest is banned by ruff.
- Mock Llama Stack client: `mocker.AsyncMock(spec=AsyncLlamaStackClient)`.
- Patch at module level: `mocker.patch("utils.responses.compact_conversation_if_needed", ...)`.
- Async mocking pattern: see `tests/unit/utils/test_shields.py`.
- Config validation tests: see `tests/unit/models/config/`.

# Latency and Cost

| Scenario          | Current             | With compaction                         |
|-------------------|---------------------|-----------------------------------------|
| Normal turn       | 1 LLM call          | 1 LLM call + ~2ms tiktoken (no change) |
| Trigger turn      | 1 LLM call (or 413) | 2 LLM calls (summarize + respond)       |
| Post-trigger turn | 1 LLM call          | 1 LLM call (no change)                  |

Compaction adds latency only on the trigger turn. In PoC testing, compaction turns took 14-40 seconds vs 9-20 seconds for normal turns (gpt-4o-mini).

# Open Questions for Future Work

- **Compaction-proof instructions**: Allow "pinned" messages that always survive compaction (inspired by Claude Code's CLAUDE.md pattern). Not needed for v1.
- **Tiered memory**: Add a recall storage tier (searchable vector DB of full conversation history) so the LLM can retrieve old context on demand. High complexity, defer unless long-running conversations become a key use case.
- **Provider-native compaction**: Use OpenAI's or Anthropic's native compaction APIs as an opt-in optimization. Not recommended as primary approach (breaks provider-agnostic principle).
- **Smaller model for summarization**: Allow configuring a cheaper model for the summarization call. Current design uses the same model for simplicity.
- **UI compaction indicator**: The `context_status` response field and the streaming compaction event (R12) provide the data. Coordinate with the UI team on how to display it.

# Changelog

**2026-05-26 — R10 redesign (Option A) during LCORE-1572 implementation.**
A live experiment on the deployed llama-stack 0.6.0 showed that passing the
`conversation` parameter to the Responses API always reloads the *full* stored
message history, with no marker-based selection hook. The original R10
(inject a marker, keep the `conversation` parameter, "select from the marker
onward") therefore cannot limit what the model sees. R10, R12, the
architecture flow, and the implementation guidance were revised to the
explicit-input approach: in compacted mode lightspeed-stack builds the input
itself and omits the `conversation` parameter, preserving `conversation_id`
and the full item history while controlling the LLM context. This restores the
spike's *original* Decision 6 recommendation (which a later spike edit had
changed to the marker approach). The summary cache (Decision 8 / LCORE-1571)
becomes a parallel persistence layer; the runtime boundary is the marker item
in Llama Stack. Compaction was also confirmed to apply to four endpoints —
`/v1/query`, `/v1/streaming_query`, the A2A executor, and `/v1/responses` —
not the two originally listed; `/v1/responses` compacts silently in this
iteration to keep the endpoint a drop-in for clients written against the
upstream OpenAI Responses API (see R12 for the spec-compliant extension-event
option). Evidence and full reasoning: the spike doc
(`conversation-compaction-spike.md`).

**2026-05-27 — Summary cache as source of truth + persisted recursive fold (LCORE-1571/1572).**
Refining the entry above (which framed the cache as "a parallel persistence
layer"): as built, the summary cache (LCORE-1571) is the *preferred source of
truth* for summary text. On each request the active summaries are read from the
cache; the Llama Stack marker texts remain an authoritative fallback (used when
no persisting cache is configured) and the audit record, and the marker position
still defines the recent-verbatim boundary. The recursive re-summarization
fallback (R3) is implemented as a *persisted* fold: when the accumulated
summaries' own token count crosses the threshold they are collapsed into one and
stored via a new cache operation, `replace_summaries` (atomic delete-all +
insert), so the fold is computed once and reused rather than recomputed per
request. An in-memory recompute-per-request fold was prototyped and rejected
(non-deterministic context across turns). The A2A executor runs marker-only (it
has no resolved `user_id` for the `(user_id, conversation_id)` cache key, so no
persisted fold). `enabled: false` stays a full off-switch; disabling compaction
mid-conversation on an already-compacted conversation reverts it to full-history
replay (unsupported — see Configuration). The `CompactionResult` mode flag was
renamed `summarized` → `compacted` for clarity.

# Appendix A: PoC Evidence

A proof-of-concept was built and tested.

**Experiment 1** (5 queries, threshold=3): Compaction triggered successfully. LLM response after compaction correctly referenced all 4 prior topics.

**Experiment 2** (50 queries, threshold=10): 4 compaction cycles. Demonstrated that recursive summarization loses early-conversation context after multiple cycles — this is why the spec requires additive summarization (R3).

Evidence files:

- `poc-results/01-analysis.txt` — full analysis with glossary
- `poc-results/02-conversation-log.txt` — all 50 query/response pairs
- `poc-results/05-summaries-extracted.txt` — the 4 generated summaries
- `poc-results/06-probe-responses.txt` — context fidelity check results

PoC code (not production quality, for reference only):

- `src/utils/compaction.py`
- `tests/unit/utils/test_compaction.py`

# Appendix B: How Other APIs Handle This

| Feature                      | OpenAI       | Anthropic                                                | Bedrock     |
|------------------------------|--------------|----------------------------------------------------------|-------------|
| State management             | Server-side  | Client-side                                              | Client-side |
| Auto compaction              | Yes (opaque) | Yes (transparent)                                        | No          |
| Custom summarization prompts | No           | Yes                                                      | N/A         |
| Context editing              | No           | Yes (clear\_tool\_uses, clear\_thinking) | N/A         |

See the spike doc (`conversation-compaction-spike.md`) for full comparison including ChatGPT, Claude Code, MemGPT/Letta, and LangChain.

# Appendix C: Reference Sources

- Anthropic Compaction: <https://platform.claude.com/docs/en/docs/build-with-claude/compaction>
- OpenAI Compaction: <https://developers.openai.com/docs/guides/compaction>
- AWS Bedrock Converse: <https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html>
- MemGPT Paper: <https://arxiv.org/abs/2310.08560>
- LangChain Conversational Memory: <https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/>
