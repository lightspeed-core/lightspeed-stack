# Overview

This document is the deliverable for LCORE-1314. It presents the design options for conversation history compaction in lightspeed-stack, with a recommendation and a proof-of-concept validation.

**The problem**: When a conversation's token count exceeds the model's context window, Llama Stack's inference provider rejects the request. lightspeed-stack catches this and returns HTTP 413. The conversation is stuck — the user must start over.

**The recommendation**: Use LLM-based summarization. When estimated tokens approach the context window limit, summarize older turns and keep recent turns verbatim. This is provider-agnostic, proven (Anthropic and LangChain use the same pattern), and can use a domain-specific prompt for Red Hat product support.

**PoC validation**: A working proof-of-concept was built and tested with 50 queries across 4 compaction cycles. Results in [PoC results](#poc-results).

# Decisions for @ptisnovs and @sbunciak

These are the high-level decisions that determine scope, approach, and cost. Each has a recommendation — please confirm or override.

## Decision 1: Which approach to conversation history management?

When a conversation gets too long for the context window, what should lightspeed-stack do?

| Option | Description                      | Complexity | Context quality |
|--------|----------------------------------|------------|-----------------|
| A      | LLM summarization                | Medium     | Good            |
| B      | Tiered memory (MemGPT-style)     | High       | Excellent       |
| C      | Delegate to provider-native APIs | Low-Med    | Varies          |

See [Design alternatives](#design-alternatives) for full pros/cons of each.

**Recommendation**: **A** (LLM summarization). Proven pattern, provider-agnostic, good context quality. Option C is simpler but creates vendor lock-in and can't use a domain-specific prompt.

## Decision 2: Recursive or additive summarization?

When compaction triggers a second time, how should the new summary relate to the previous one?

**Recursive**: The LLM re-summarizes the previous summary together with new turns. Produces a single rolling summary. Simple, but early context gets progressively diluted — our PoC showed that after 4 cycles, the final summary lost major topics from the first cycle (Kubernetes fundamentals, Helm, Istio details were all missing).

**Additive**: Each chunk's summary is generated once and kept. The context becomes `[summary of turns 1-N] + [summary of turns N+1-M] + ... + [recent
turns]`. Preserves fidelity of each chunk. Total summary size grows linearly, and eventually the summaries themselves may need compaction (at which point you fall back to recursive).

See [PoC results](#poc-results) for the experimental evidence.

**Recommendation**: **Additive**, with recursive as a fallback when total summary size approaches the context limit.

## Decision 3: Which model for summarization?

| Option | Description                                | Cost     | Quality  |
|--------|--------------------------------------------|----------|----------|
| A      | Same model as the user's query             | Higher   | Best     |
| B      | Configurable (default=same, allow cheaper) | Flexible | Flexible |
| C      | Always a small/cheap model                 | Lowest   | Varies   |

**Recommendation**: **A** (same model as the user's query). Keeps it simple — one model, no additional configuration, no risk of quality mismatch.

## Decision 4: Compaction threshold strategy

How do we decide when to trigger compaction?

The threshold is a percentage of the model's context window. "70%" means: trigger when estimated input tokens exceed 70% of the window, leaving 30% for the new query and response. The percentage adapts automatically to different models — if you switch from a 128K model to a 32K model, the threshold changes from ~90K to ~22K with no config change.

| Combo | Description                              | Flexibility |
|-------|------------------------------------------|-------------|
| B     | Percentage of context window only        | Low         |
| B+A   | Percentage + fixed token floor           | Low-Med     |
| B+D   | Percentage + admin-configurable via YAML | Medium      |
| B+A+D | Percentage + floor + admin-configurable  | Medium-High |

(A = fixed token count, B = percentage, D = admin-configurable defaults.)

**Recommendation**: **B+A+D**. Percentage as the primary mechanism, a fixed token floor for safety (prevents triggering on very small windows), and admin-configurable via YAML so deployments can tune it.

Example for a 128K context window at 70% threshold:

- Trigger at 89,600 tokens.
- Summarize ~70,000 tokens of old turns.
- Summary output: ~2,000-4,000 tokens.
- Cost: 1 additional LLM call of ~74,000 total tokens.

## Decision 5: Where does summarization happen?

| Option | Description                                      |
|--------|--------------------------------------------------|
| A      | In lightspeed-stack (recommended)                |
| B      | In Llama Stack (upstream contribution)           |
| C      | Split: trigger in lightspeed, summarize in Llama |

**Recommendation**: **A**. lightspeed-stack controls the conversation flow, has the domain knowledge (Red Hat support), and doesn't require upstream coordination. Llama Stack upstream has no active work here — see [Appendix A](#llama-stack-upstream).

# Technical decisions for @ptisnovs

These are implementation-level decisions. They don't affect scope or cost significantly but determine how the code is structured.

## Decision 6: How to handle `conversation_id` after compaction?

After compaction, the LLM should see the summary + recent turns, not the full original history. How do we achieve this?

| Option | Description                                                            |
|--------|------------------------------------------------------------------------|
| A      | Stop using `conversation` param; build full input explicitly           |
| B      | Inject summary as a message into the existing Llama Stack conversation |
| C      | Create a new Llama Stack conversation with summary as first message    |

**Recommendation**: **B**. Inject summary as a marked item into the existing conversation, then select from the marker onward when building context. This preserves a single continuous conversation identity — the user sees one conversation, the Conversations API returns complete history, and the audit trail is unbroken. lightspeed-stack still controls what the LLM sees by filtering items at the marker boundary. The PoC used C (new conversation), which validated the summarization mechanism but breaks conversation identity.

## Decision 7: What to do with the `truncated` field?

The `truncated` field in `QueryResponse` is currently deprecated and hardcoded to `False`.

| Option | Description                                     |
|--------|-------------------------------------------------|
| A      | Un-deprecate it (`True` when summary is active) |
| B      | Keep deprecated; add `compacted: bool`          |
| C      | Add `context_status: "full" / "summarized"`     |

**Recommendation**: **C**. Distinguishes between "full context" (no compaction) and "summarized" (compaction happened). Can be extended with additional values later if needed.

## Decision 8: Summary storage location

| Option | Description                                          |
|--------|------------------------------------------------------|
| A      | Extend lightspeed conversation cache (`CacheEntry`)  |
| B      | New dedicated table                                  |
| C      | Store in Llama Stack (as conversation item metadata) |

**Recommendation**: **A**. Co-locates summary with existing conversation metadata. All cache backends (SQLite, Postgres, memory) would need the schema extension.

Schema:

``` python
class ConversationSummary(BaseModel):
    summary_text: str
    summarized_through_turn: int  # last turn included in summary
    token_count: int              # tokens in the summary itself
    created_at: str               # ISO 8601
    model_used: str               # model used for summarization
```

## Decision 9: Buffer zone calculation

The "buffer zone" is the most recent turns kept verbatim (not summarized).

| Approach | Description                           | Pros                 | Cons                           |
|----------|---------------------------------------|----------------------|--------------------------------|
| Turns    | Keep last N turns                     | Simple, intuitive    | Turns vary wildly in size      |
| Tokens   | Keep last T tokens of recent messages | Precise, predictable | May split a turn in the middle |
| Hybrid   | Keep last N turns, capped at T tokens | Intuitive + safe     | Slightly more logic            |

Anthropic's compaction uses token-based thresholds throughout — the buffer is implicit (whatever fits after the compaction block).

**Recommendation**: **Hybrid with degrading guard**. Start with the last 4 turns. If their token count exceeds the available budget, degrade to 3, then 2, then 1, then 0. This handles pathological cases where a few large turns (e.g., with tool results) would overflow the context even after summarizing everything else.

## Decision 10: Concurrency during compaction

What happens if a second request arrives for the same conversation while compaction is running?

| Option | Description                                                |
|--------|------------------------------------------------------------|
| A      | No protection (accept race condition risk)                 |
| B      | Blocking: per-conversation lock, concurrent requests wait  |
| C      | Optimistic: check if summary already exists, skip if so    |

**Recommendation**: **B** (blocking). Compaction modifies conversation state — concurrent requests could append messages mid-compaction or trigger duplicate compactions. A per-conversation lock ensures consistency. This matches industry practice (Cursor, Claude Code both use synchronous compaction).

## Decision 11: Compaction progress notification

Should the client be notified that compaction is in progress (before the summarization LLM call)?

| Option | Description                                                     |
|--------|-----------------------------------------------------------------|
| A      | No notification (client sees an unexplained delay)              |
| B      | Streaming event before compaction (e.g., `compaction_started`)  |
| C      | Response header or field after the fact only                    |

**Recommendation**: **B** for the streaming endpoint. Emit a compaction event before the summarization call so the client can display "Compacting conversation..." or similar. Non-streaming requests have no mid-request notification mechanism, so they just see a slower response.

# Proposed JIRAs

Each JIRA includes an agentic tool instruction that an assignee can optionally feed to Claude Code or similar.

### LCORE-????: Add token estimation to lightspeed-stack

**Description**: Add the ability to estimate token counts before sending requests to the LLM. This is the prerequisite for the compaction trigger — we need to know when conversation history is approaching the context window limit.

**Scope**:

- Add `tiktoken` as a dependency in `pyproject.toml`.
- Create `src/utils/token_estimator.py` with `estimate_tokens()` function.
- Add context window sizes per model in YAML config (`models/config.py`).

**Acceptance criteria**:

- `estimate_tokens("hello world")` returns a positive integer.
- Context window size is retrievable for configured models.
- Unit tests pass for estimation accuracy (within 5% of actual token count).

**Agentic tool instruction**:

```
Read the "Token estimation" and "Configuration" sections in
docs/design/conversation-compaction/conversation-compaction.md.
Key files: pyproject.toml, src/models/config.py, src/utils/ (new module).
Add config fields following the pattern in models/config.py around line 1418
(ConversationHistoryConfiguration).
```

### LCORE-????: Implement conversation summarization module

**Description**: Create the core summarization logic — given a list of conversation turns and a prompt, call the LLM and return a summary string. Includes the domain-specific summarization prompt for Red Hat product support.

**Scope**:

- Create `src/utils/compaction.py` (or `summarization.py`).
- Implement conversation partitioning: split into "old" (summarize) and "recent" (keep).
- Implement additive summarization: generate each chunk's summary independently.
- Fall back to recursive re-summarization when total summary size exceeds threshold.
- Add compaction config to `models/config.py`: threshold ratio, buffer size, floor.

**Acceptance criteria**:

- Given a conversation with 20+ turns, partitioning produces non-empty old and recent lists.
- Additive mode: second compaction appends a new summary chunk, does not re-summarize the first.
- Buffer zone respects both turn count and token cap.
- Summarization prompt includes all 5 preservation directives (see Alternative A).

**Agentic tool instruction**:

```
Read the "Architecture" section (especially "Additive summarization",
"Conversation partitioning", and "Summarization prompt") in
docs/design/conversation-compaction/conversation-compaction.md.
Key files: src/utils/ (new module), src/models/config.py.
```

### LCORE-????: Extend conversation cache for summaries

**Description**: Add summary storage to the conversation cache so summaries persist across requests and survive restarts.

**Scope**:

- Add `ConversationSummary` fields to the cache schema (SQLite + PostgreSQL).
- Schema migration for existing databases.
- Extend `CacheEntry` model or add a related table.
- Update all cache backends (SQLite, PostgreSQL, memory).

**Acceptance criteria**:

- A summary can be stored and retrieved by `conversation_id`.
- Multiple summary chunks per conversation are supported (additive mode).
- Schema migration runs without errors on an existing database.
- All cache backends (SQLite, PostgreSQL, memory) pass their existing tests plus new summary tests.

**Agentic tool instruction**:

```
Read the "Summary storage" section in
docs/design/conversation-compaction/conversation-compaction.md.
Key files: src/cache/, src/models/.
Follow existing cache backend patterns (test_sqlite_cache.py, test_postgres_cache.py).
```

### LCORE-????: Integrate compaction into the query flow

**Description**: Wire the token estimator, summarization module, and summary cache into the actual request path so compaction triggers automatically.

**Scope**:

- Modify `prepare_responses_params()` in `src/utils/responses.py`.
- Add trigger logic: estimate tokens, check threshold, invoke summarization if needed.
- After compaction: inject summary as a marked item into the Llama Stack conversation, then select from the marker onward when building context.
- Implement per-conversation blocking lock to prevent concurrent compaction races.
- Emit compaction streaming event before the summarization LLM call.

**Acceptance criteria**:

- A conversation exceeding the token threshold triggers compaction automatically.
- Both `/v1/query` and `/v1/streaming_query` endpoints trigger compaction correctly.
- Summary is injected into the existing Llama Stack conversation as a marked item.
- Subsequent requests select items from the last summary marker onward.
- Conversation identity is preserved (same `conversation_id` throughout).
- Full conversation history (including pre-compaction turns) remains accessible via the Conversations API.
- Concurrent requests on the same conversation are blocked during compaction.

**Agentic tool instruction**:

```
Read the "Changed request flow after compaction" and "Implementation Suggestions"
sections in docs/design/conversation-compaction/conversation-compaction.md.
Key files: src/utils/responses.py (around line 292), src/app/endpoints/query.py,
src/app/endpoints/streaming_query.py.
The insertion point is in prepare_responses_params(), after conversation_id is
resolved but before ResponsesApiParams is built.
```

### LCORE-????: Update response model and API

**Description**: Add a `context_status` field (or equivalent, per Decision 7) to the response so clients know whether compaction occurred.

**Scope**:

- Add field to `QueryResponse` and `StreamingQueryResponse` in `models/responses.py`.
- Set to `"full"` (no compaction) or `"summarized"` (compaction occurred).
- Update OpenAPI spec (`docs/openapi.json`).

**Acceptance criteria**:

- Responses include `context_status` with value `"full"` when no compaction occurred.
- Responses include `context_status` with value `"summarized"` when compaction occurred.
- OpenAPI spec reflects the new field.

**Agentic tool instruction**:

```
Read the "API response changes" section in
docs/design/conversation-compaction/conversation-compaction.md.
Key files: src/models/responses.py (around line 410, the existing truncated field).
```

### LCORE-????: Verify test coverage for compaction

**Description**: Review all compaction-related code and verify that unit tests, integration tests, and E2E tests cover the critical paths. Add any missing tests.

**Scope**:

- Review all compaction-related code for test gaps.
- Add missing unit tests: trigger logic, token estimation, partitioning, summarization, summary storage.
- Add missing integration tests: full compaction flow with mocked Llama Stack.
- Add missing E2E tests: conversations that exceed context window, verify compaction kicks in.

**Acceptance criteria**:

- Every public function in `token_estimator.py` and `compaction.py` has at least one unit test.
- At least one integration test exercises the full compaction flow end-to-end.
- At least one E2E test verifies that a long conversation triggers compaction and continues.

**Agentic tool instruction**:

```
Read the "Appendix A: PoC Evidence" section in
docs/design/conversation-compaction/conversation-compaction.md
and the full experiment data in docs/design/conversation-compaction/poc-results/.
Key test files: tests/unit/utils/, tests/integration/endpoints/,
tests/e2e/features/.
```

### LCORE-????: Coordinate with UI team on compaction indicator

**Description**: Define the API contract for communicating compaction status to the UI. Two signals: (1) `context_status` field in the response, and (2) a `compaction_started` streaming event emitted before the summarization call.

**Scope**:

- Define what the UI receives (`context_status` field + streaming compaction event).
- Provide test data and example responses/events.

**Acceptance criteria**:

- UI team has a documented API contract for both the `context_status` field and the streaming event.
- UI displays a progress indicator when the `compaction_started` event is received.
- UI displays a status indicator when `context_status` is `"summarized"`.
- End-to-end verification: trigger compaction, confirm both indicators work.

# PoC results

A proof-of-concept was built in lightspeed-stack and tested against a real Llama Stack + OpenAI (gpt-4o-mini) setup.

## What the PoC does

The PoC hooks into `prepare_responses_params()` in `src/utils/responses.py`. When `message_count` (from the lightspeed DB) exceeds a threshold, it:

1.  Fetches full conversation history from Llama Stack.
2.  Splits into "old" (to summarize) and "recent" (to keep verbatim).
3.  Calls the LLM with a summarization prompt to produce a summary.
4.  Creates a new Llama Stack conversation seeded with \[summary + recent turns\].
5.  Uses the new conversation for the current query.

**Important**: The PoC diverges from the production design in several ways:
- **Recursive** summarization (production: additive)
- **Message-count** trigger (production: token-based)
- **Creates a new conversation** on compaction (production: injects summary marker into the same conversation)
- **No concurrency protection** (production: per-conversation blocking lock)
- **No streaming notification** (production: emits compaction event)

The PoC is not production code — it validates the core summarization mechanism.

## Experiment 1: 5 queries, threshold=3

- Compaction triggered on query 5.
- New conversation created with summary (1133 chars) + 1 recent turn.
- The LLM's response after compaction correctly referenced all 4 prior topics (Kubernetes, Docker, Podman, OpenShift).
- Full evidence in `poc-results/`.

## Experiment 2: 50 queries, threshold=10

50 queries across 10 topic blocks (Kubernetes, Docker, Podman, OpenShift, Helm, Istio, Tekton/ArgoCD, observability, security, wrap-up). 6 "probe" queries placed at turns 11, 21, 31, 41, 46, 50 — these ask the LLM to recall specific earlier topics to test whether compaction preserved them.

### Results

- **4 compactions** at turns 12, 23, 34, 45.
- **Token usage**: sawtooth pattern. Input tokens grow from ~1500 to ~12000 per cycle, then drop on compaction.

### Context fidelity

- **Probes 1-4 (before compaction)**: Accurate. Full history still in context.
- **Probe 5 (after 4th compaction)**: Asked about Docker/Podman/containerd. Correct and detailed — specific facts survived 4 layers of recursive summarization.
- **Probe 6 (final, after 4th compaction)**: Asked for comprehensive summary of ALL topics. **Significant fidelity loss** — response was dominated by recent topics (observability, security) and missed Kubernetes fundamentals, namespaces, ConfigMaps, Helm, and Istio details from earlier turns.

### Post-compaction baseline growth

Post-compaction input tokens: 1565 → 2362 → 3280 → 4076.

Each recursive summary is larger than the last because it carries the weight of all prior summaries. This means that after enough cycles, the summary itself approaches the context limit. This is the main argument for additive summarization over recursive.

### Summary quality

| Summary | Turns summarized  | Quality | Notes                                     |
|---------|-------------------|---------|-------------------------------------------|
| 1       | 1-8               | Good    | Focused, accurate                         |
| 2       | Summary 1 + 9-18  | Good    | Broader, well-structured                  |
| 3       | Summary 2 + 19-26 | Good    | Comprehensive, covers all prior topics    |
| 4       | Summary 3 + 27-37 | Problem | Dominated by ArgoCD, lost broader context |

Summary 4's quality drop is likely because the LLM prioritized the detailed recent content over the already-compressed summary text.

Full evidence in `poc-results/`.

## PoC code

- `src/utils/compaction.py` — compaction logic (trigger, split, summarize, new conversation).
- `src/utils/responses.py` — 8-line insertion calling `compact_conversation_if_needed()`.
- `tests/unit/utils/test_compaction.py` — 19 unit tests.

All linters pass (black, pylint, pyright, ruff, pydocstyle, mypy).

# How conversations work today

## Request flow

```
User Query → lightspeed-stack
  1. Resolve model, system prompt, tools
  2. Build input (query + inline RAG + attachments)
  3. Pass =conversation_id= to Llama Stack
  ↓
Llama Stack Responses API
  4. Retrieve full conversation history from storage
  5. Build prompt: [system] + [full history] + [user query]
  6. Call LLM inference provider
  7. If context exceeded → error bubbles up → HTTP 413
  8. Store response in conversation
  ↓
lightspeed-stack
  9. Extract LLM text, tool calls, documents, token usage
  10. Cache in conversation cache
  11. Return QueryResponse (truncated=False, always)
```

## Key components

| Component               | Role                                | Code                                                  |
|-------------------------|-------------------------------------|-------------------------------------------------------|
| lightspeed-stack        | FastAPI wrapper; delegates to Llama | `src/utils/responses.py:322-331`                      |
| Llama Stack             | Conversation storage + LLM calls    | `openai_responses.py:206-278`, `streaming.py:399-413` |
| `conversation_items`    | Rich items (tool calls, MCP) for UI | `conversations.py:81-98`                              |
| `conversation_messages` | Chat messages for LLM context       | `responses_store.py:71-77`                            |

## What happens when context is exceeded

1.  Llama Stack sends the full prompt to the inference provider.
2.  Provider rejects (HTTP 400/413 with "`context_length`" in error message).
3.  lightspeed-stack catches `RuntimeError` (library mode) or `APIStatusError`.
4.  Returns `PromptTooLongResponse` (HTTP 413) to the user.
5.  No recovery. No truncation. No summarization. Conversation is stuck.

Evidence: `query.py:321-325`, `streaming_query.py:312-317`.

## The `truncated` field

The `truncated` field exists in `QueryResponse` but is:

- Marked "Deprecated" in the field description (`responses.py:412`).
- Hardcoded to `False` in `query.py:265` and `transcripts.py:157`.
- Set to `None` in streaming responses (`streaming_query.py:886`).

It was added anticipating future truncation support, then deprecated when that work didn't happen.

## Llama Stack's truncation support

The `truncation` parameter exists in the Responses API:

- `"disabled"` (default): Pass through; let provider reject.
- `"auto"`: Explicitly rejects with error — not implemented.

The TODO at `streaming.py:400` says: *"Implement actual truncation logic when 'auto' mode is supported."* Dormant since Feb 2026 (Issue \#4890: zero comments, no assignee, no milestone).

## Token estimation

| Capability               | lightspeed-stack | Llama Stack    |
|--------------------------|------------------|----------------|
| Pre-inference estimation | None             | None           |
| Post-inference (`usage`) | Yes              | Yes            |
| Tokenizer dependency     | None             | tiktoken (RAG) |
| Context window registry  | None             | Partial        |

There is no way to estimate token count before sending to the LLM. Adding `tiktoken` to lightspeed-stack is a prerequisite for any token-based trigger.

tiktoken runs on CPU only — no API calls, no GPU. Cost is ~1-5ms for a 10K token conversation, negligible compared to the LLM call.

# How other APIs handle compaction

## OpenAI Responses API

**Approach**: Server-side stateful with opaque compaction.

- `truncation` parameter: `"auto"` drops oldest items; `"disabled"` fails on overflow.
- `POST /v1/responses/compact`: Manual compaction endpoint. Returns encrypted/opaque compaction items.
- Automatic compaction via `context_management` with `compact_threshold`.
- Compaction items are not human-readable — encrypted blobs.

| Pros                               | Cons                                   |
|------------------------------------|----------------------------------------|
| Zero developer intervention needed | Opaque: can't inspect what's preserved |
| Server manages all state           | Vendor lock-in (encrypted blobs)       |
| Manual `compact` for control       | All input tokens re-billed each turn   |

## Anthropic Messages API

**Approach**: Stateless with transparent compaction.

- Header: `compact_20260112`.
- Token-based trigger (default 150K, min 50K).
- Produces human-readable summaries as `compaction` content blocks.
- `pause_after_compaction`: Client can inject content after summary.
- `instructions`: Custom summarization prompt (replaces default entirely).
- Context editing strategies: `clear_tool_uses`, `clear_thinking` — composable.

Default summarization prompt:

> "You have written a partial transcript for the initial task above. Please write a summary of the transcript. The purpose of this summary is to provide continuity so you can continue to make progress towards solving the task in a future context, where the raw history above may not be accessible and will be replaced with this summary."

| Pros                                  | Cons                                  |
|---------------------------------------|---------------------------------------|
| Transparent, readable summaries       | Custom instructions replace default   |
| Custom summarization prompts          | Client must handle compaction blocks  |
| `pause_after_compaction` for control  | Stateless: client manages all history |
| Context editing strategies composable |                                       |

## AWS Bedrock Converse API

**Approach**: Stateless with zero built-in context management.

- No truncation, no compaction, no summarization.
- `stopReason: "model_context_window_exceeded"` is the only signal.
- Developer must implement everything client-side.

| Pros                            | Cons                                       |
|---------------------------------|--------------------------------------------|
| Model-agnostic (Claude, Llama…) | Zero built-in context management           |
| No data retention (privacy)     | Full burden on developer                   |
| Simple, predictable             | Cost grows linearly (full history re-sent) |

## Comparison

| Feature              | OpenAI      | Anthropic   | Bedrock     |
|----------------------|-------------|-------------|-------------|
| State management     | Server-side | Client-side | Client-side |
| Auto compaction      | Yes         | Yes         | No          |
| Manual compaction    | Yes         | Via trigger | No          |
| Summary transparency | Opaque      | Transparent | N/A         |
| Custom prompts       | No          | Yes         | N/A         |
| Pause after compact  | No          | Yes         | N/A         |
| Context editing      | No          | Yes         | N/A         |

# How other tools handle compaction

## ChatGPT (Consumer)

- **Approach**: FIFO sliding window — oldest messages silently dropped.
- **Trigger**: Automatic when token limit approached.
- **Preserved**: Recent messages + system instructions.
- **Lost**: All older messages — no summarization. User has no visibility.
- **Notable**: Separate "Memory" feature for cross-conversation persistent facts.

## Claude (Consumer and Claude Code)

- **Claude.ai**: Uses LLM compaction (summarization) for conversations approaching context limits.
- **Claude Code CLI**: LLM summarization with `CLAUDE.md` re-injection.
  - Automatic (auto-compact) or manual (`/compact`).
  - `CLAUDE.md` is re-read from disk after compaction — it always survives.
  - Instructions given only in conversation are lost during compaction.
  - Subagent delegation for context isolation (heavy work done in a separate context window, only the result returned to the main conversation).

## MemGPT / Letta

- **Approach**: 3-tier hierarchical memory (inspired by OS virtual memory).
  - Main Context: Active conversation in context window.
  - Recall Storage: Complete history, searchable by recency or semantics.
  - Archival Storage: Long-term facts, knowledge base.
- **Trigger**: Automatic eviction. The LLM itself decides what to page in/out via function calls (`archival_memory_search`, `conversation_search`, etc.).
- **Preserved**: Everything — raw messages go to recall, nothing truly deleted.
- **Lost**: Summarization compresses detail; retrieval depends on search quality.

## LangChain

| Strategy            | Trigger         | Preserves        | LLM cost       |
|---------------------|-----------------|------------------|----------------|
| BufferMemory        | None            | Everything       | 0 extra        |
| WindowMemory        | Message count   | Last k messages  | 0 extra        |
| SummaryMemory       | Every turn      | Rolling summary  | 1 call/turn    |
| SummaryBufferMemory | Token threshold | Recent + summary | 1 call/trigger |
| TokenBufferMemory   | Token threshold | Recent by tokens | 0 extra        |

`SummaryBufferMemory` is the proven hybrid: keep recent messages verbatim, summarize older ones. Trigger is token-threshold-based.

# Existing approaches

There are four approaches to handling long conversation history (excluding simple FIFO truncation, which loses all older context and is not considered here):

| \#  | Approach              | Examples                          | Complexity  | Context quality |
|-----|-----------------------|-----------------------------------|-------------|-----------------|
| 1   | No management         | Bedrock, raw Anthropic            | Trivial     | Full until fail |
| 2   | LLM summarization     | Anthropic compact, OpenAI compact | Medium      | Good            |
| 3   | Hybrid buffer+summary | LangChain SummaryBuffer, Claude   | Medium-High | Very good       |
| 4   | Tiered hierarchical   | MemGPT/Letta                      | High        | Excellent       |

# Design alternatives for lightspeed-stack

Given our architecture (lightspeed-stack wraps Llama Stack) and the constraint that we implement in lightspeed-stack (see [Appendix A](#llama-stack-upstream) for why not upstream):

## Alternative A: LLM-based summarization (recommended)

When approaching the context limit, use the LLM to summarize older turns. Recent turns kept verbatim.

**Implementation**:

1.  Add token estimation to lightspeed-stack.
2.  When estimated tokens exceed threshold (e.g., 70% of context window):
    1.  Split conversation into "old" (summarize) and "recent" (keep).
    2.  Send old turns to LLM with a summarization prompt.
    3.  Store the summary.
    4.  Build context as: \[system\] + \[summary\] + \[recent turns\] + \[user query\].
3.  Additive: when threshold hit again, generate a new summary for the new chunk and append it to the existing summaries.

| Pros                                         | Cons                                   |
|----------------------------------------------|----------------------------------------|
| Preserves semantic context from older turns  | Extra LLM call for summarization       |
| Well-proven pattern (Anthropic, LangChain)   | Summarization quality depends on model |
| Additive — each chunk summarized once        | Latency: adds 1 LLM call at trigger    |
| Can use domain-specific summarization prompt | Must handle summary storage            |

### Trigger mechanism

Token-based, not turn-based:

- Turn sizes vary wildly (a turn with tool results can be 10x a simple Q&A).
- Token threshold is directly tied to the actual constraint (context window).

`trigger_when(estimated_tokens > context_window * threshold_ratio)`

`threshold_ratio` configurable, defaulting to 0.7 (trigger at 70% of context window, leaving 30% for the new query + response).

### Conversation partitioning

Split conversation into:

- **Summary zone**: Oldest turns that will be summarized.
- **Buffer zone**: Most recent turns kept verbatim.

Buffer zone: degrading guard — start with N turns (default 4). If their token count exceeds the available budget, degrade to N-1, then N-2, down to 0.

### Summarization prompt

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

### Summary storage

Extend lightspeed's conversation cache. See [Decision 8](#decisions-technical).

### Changed request flow

```
User Query → lightspeed-stack
  1. Resolve model, system prompt, tools
  2. Build input (query + RAG + attachments)
  3. Acquire per-conversation lock
  4. Estimate total tokens: system + history + new query
  5. If over threshold:
     a. Emit compaction event (streaming)
     b. Summarize old turns
     c. Inject summary as marked item into Llama Stack conversation
     d. Store summary chunk in cache
  6. Build context: select items from last summary marker onward
  7. Call Llama Stack with conversation parameter (marker-based selection)
  ↓
Llama Stack
  8. Processes conversation (marker + recent turns + new query)
  ↓
lightspeed-stack
  9. Response stored in same conversation (continuous history)
  10. Release per-conversation lock
  11. Return QueryResponse (context_status="summarized" if summary was used)
```

After compaction, the summary is a marked item in the existing conversation. lightspeed-stack controls what the LLM sees by selecting from the marker onward. The conversation identity is preserved.

## Alternative B: Hybrid with compaction-proof instructions

Alternative A + a "compaction-proof" instruction layer (inspired by Claude Code's `CLAUDE.md` pattern).

Additional features over A:

- Certain instructions/context always survive compaction (re-injected fresh).
- System prompt is already compaction-proof (always re-sent).
- Extend to support "pinned" messages that the user marks as important.

| Pros                                | Cons                       |
|-------------------------------------|----------------------------|
| All benefits of A                   | All costs of A             |
| Critical instructions never lost    | Pinning adds UX complexity |
| Users can protect important context | More state to manage       |

**Verdict**: Good enhancement for later. Not essential for v1.

## Alternative C: Tiered memory (MemGPT-inspired)

Three-tier memory: working context, recall storage (searchable conversation history), archival storage (extracted facts).

| Pros                                   | Cons                             |
|----------------------------------------|----------------------------------|
| Nothing truly lost                     | High complexity                  |
| LLM can retrieve old context on demand | Requires vector DB for recall    |
| Best long-term context quality         | Multiple LLM calls per turn      |
| Cross-conversation memory              | Significant architecture changes |

**Verdict**: Too complex for v1.

## Alternative D: Delegate to provider-native compaction

Use OpenAI's or Anthropic's native compaction APIs. Implement client-side only for providers without native support.

| Pros                                | Cons                                 |
|-------------------------------------|--------------------------------------|
| Leverages best-in-class compaction  | Divergent behavior across providers  |
| Less code to maintain               | Opaque compaction for OpenAI         |
| Provider handles edge cases         | Can't customize for Red Hat domain   |
| Free quality improvements over time | Vendor lock-in for compaction format |

**Verdict**: Breaks the provider-agnostic principle. Not recommended as primary approach, but could be offered as an opt-in optimization.

# Cost and latency

## Summarization cost

Each summarization call consumes tokens:

- **Input**: The conversation turns being summarized (50-90% of context window).
- **Output**: The summary (target: 2,000-4,000 tokens).

Example for a 128K context window at 70% threshold:

- Trigger at 89,600 tokens.
- Summarize ~70,000 tokens of old turns.
- Summary output: ~2,000-4,000 tokens.
- Cost: 1 additional LLM call of ~74,000 total tokens.

## Latency impact

| Scenario          | Current             | With compaction                   |
|-------------------|---------------------|-----------------------------------|
| Normal turn       | 1 LLM call          | 1 LLM call (no change)            |
| Trigger turn      | 1 LLM call (or 413) | 2 LLM calls (summarize + respond) |
| Post-trigger turn | 1 LLM call          | 1 LLM call (no change)            |

Summarization adds latency only on the trigger turn. In our PoC, compaction turns took 14-40 seconds (vs 9-20 for normal turns).

## What's required

| Requirement                            | Status        | Effort |
|----------------------------------------|---------------|--------|
| Token estimation (tiktoken)            | Not present   | Small  |
| Context window registry (per model)    | Not present   | Small  |
| Summary storage in conversation cache  | Schema change | Medium |
| Summarization prompt design            | New           | Medium |
| Context building logic change          | Core change   | Large  |
| Configuration (threshold, buffer size) | New config    | Small  |

## Dependencies

| Dependency                   | Type           | Blocker? |
|------------------------------|----------------|----------|
| tiktoken library             | New dependency | No       |
| Model context window sizes   | Configuration  | No       |
| Llama Stack conversation API | Already exists | No       |
| Conversation cache schema    | Schema change  | No       |
| Upstream Llama Stack changes | None needed    | No       |

No external dependencies or cross-team coordination needed. The feature is fully self-contained within lightspeed-stack (except the UI indicator).

# Appendix A: Llama Stack upstream status

As of 2026-03-16:

- PR \#4813 (merged 2026-02-12): Added `truncation` parameter, `disabled` mode only.
- Issue \#4890 (open): "Support auto truncation" — zero comments, no assignee, no milestone.
- PR \#5084 (merged 2026-03-10): Integration test confirming `auto` mode rejects.
- No work on compaction or summarization.
- No context window registry in model info.
- Key reviewer mattf: *"this is a deep topic and will require some serious thought."*

The truncation work upstream is about OpenAI API conformance, not about building context management algorithms. Implementing in lightspeed-stack is the right approach.

# Appendix B: Anxhela Coba's SVD suggestion

Anxhela suggested using SVD (Singular Value Decomposition) on conversation embeddings as an alternative to LLM-based summarization.

**Assessment**: Not practical for this use case. SVD on embeddings produces compressed vector representations that an LLM cannot consume as text context. The LLM needs natural language in its context window, not a compressed matrix. Information loss is uncontrollable — you can't guarantee it preserves specific facts or decisions.

LLM-generated summaries produce natural language the model can directly read, and the summarization prompt can control what gets preserved.

Acknowledged as considered; not pursued.

# Appendix C: Ondrej Metelka's provider lock-in concern

Ondrej noted: *"if it is implemented on the provider/openai API level — then this feature is locked for providers conforming to these particular endpoints."*

Valid concern. This is why Alternative A (LLM-based summarization in lightspeed-stack) is recommended over Alternative D (delegate to provider-native compaction).

By implementing in lightspeed-stack:

- Consistent behavior across all providers (OpenAI, Anthropic, Bedrock, local).
- Domain-specific summarization prompts for Red Hat support context.
- No dependency on any provider's compaction API format.
- Freedom to use provider-native compaction as an opt-in optimization later.

# Appendix D: Reference sources

- Anthropic Compaction: <https://platform.claude.com/docs/en/docs/build-with-claude/compaction>
- Anthropic Context Windows: <https://platform.claude.com/docs/en/docs/build-with-claude/context-windows>
- OpenAI Conversation State: <https://developers.openai.com/docs/guides/conversation-state>
- OpenAI Compaction: <https://developers.openai.com/docs/guides/compaction>
- AWS Bedrock Converse: <https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html>
- MemGPT Paper: <https://arxiv.org/abs/2310.08560>
- LangChain Conversational Memory: <https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/>
