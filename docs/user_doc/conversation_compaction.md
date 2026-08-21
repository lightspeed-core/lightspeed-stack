# Conversation Compaction Guide

## Overview

Conversation compaction is a feature that automatically summarizes older conversation turns when the conversation history approaches the LLM's context window limit. Instead of failing with an HTTP 413 error when the input becomes too long, compaction condenses earlier parts of the conversation into a summary while preserving recent turns verbatim. This allows long-running conversations to continue seamlessly.

## How it works

When a user sends a query, the system estimates the total token count of the conversation history. If the estimated tokens exceed a configurable fraction of the model's context window (the *threshold ratio*), compaction is triggered:

1. **Partition** -- The conversation is split into two parts: older turns and a recent buffer of the most recent turns.
2. **Summarize** -- The older turns are sent to the LLM with a summarization prompt. The resulting summary is stored as a compaction marker in the conversation.
3. **Rebuild context** -- The LLM receives the summary plus the recent buffer plus the new user query, keeping the total input well within the context window.
4. **Recursive fold** -- If accumulated summaries themselves grow too large, they are recursively re-summarized into a single condensed summary.

After compaction, the service takes ownership of the context window. The full original conversation history remains stored in OGX for auditing and retrieval, but only the compacted view is sent to the LLM for inference.

### Affected endpoints

| Endpoint | Compaction behavior |
|---|---|
| `POST /v1/query` | Blocking compaction before inference. Response includes `context_status`. |
| `POST /v1/streaming_query` | Compaction runs inside the SSE stream. A `compaction` event is emitted before tokens begin. The `end` event includes `context_status`. |
| `POST /v1/responses` | Compaction runs silently (no `context_status` in response). The `/v1/responses` endpoint follows the OpenAI Responses API specification and does not add custom fields. |
| `POST /a2a` | Compaction runs in marker-only mode (no cache, no recursive fold). No `context_status` is surfaced. |

### The `context_status` field

The `/v1/query` and `/v1/streaming_query` endpoints include a `context_status` field in their responses:

| Value | Meaning |
|---|---|
| `"full"` | The complete conversation history was sent to the LLM without summarization. |
| `"summarized"` | Older conversation turns were summarized before sending to the LLM. |

**Synchronous response example (`/v1/query`):**

```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "response": "Here is the answer to your question...",
  "context_status": "summarized",
  "input_tokens": 1250,
  "output_tokens": 200,
  "available_quotas": {"UserQuotaLimiter": 998550}
}
```

**Streaming `end` event example (`/v1/streaming_query`):**

```json
{
  "event": "end",
  "data": {
    "referenced_documents": [],
    "input_tokens": 1250,
    "output_tokens": 200,
    "context_status": "summarized"
  },
  "available_quotas": {"UserQuotaLimiter": 998550}
}
```

**Streaming `compaction` event** (emitted before inference when compaction triggers):

```json
{"event": "compaction", "data": {"status": "started", "conversation_id": "123e4567-e89b-12d3-a456-426614174000"}}
```

## Configuration

Compaction is disabled by default. To enable it, add a `compaction` section to your `lightspeed-stack.yaml` configuration file and register context window sizes for your models.

### Minimal configuration

```yaml
inference:
  default_provider: openai
  default_model: gpt-4o-mini
  context_windows:
    openai/gpt-4o-mini: 128000

compaction:
  enabled: true
```

### Full configuration

```yaml
inference:
  default_provider: openai
  default_model: gpt-4o-mini
  context_windows:
    openai/gpt-4o-mini: 128000
    openai/gpt-4o: 128000

compaction:
  enabled: true
  threshold_ratio: 0.7
  token_floor: 4096
  buffer_turns: 4
  buffer_max_ratio: 0.3
```

### Configuration fields

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | `false` | Master switch. When `false`, compaction never triggers and all other fields are inert. |
| `threshold_ratio` | float | `0.7` | Trigger compaction when estimated input tokens exceed this fraction of the model's context window. Valid range: 0.0 to 1.0. |
| `token_floor` | integer | `4096` | Minimum estimated token count before compaction can trigger, regardless of `threshold_ratio`. Prevents compaction on very short conversations. |
| `buffer_turns` | integer | `4` | Number of recent user/assistant turn pairs to keep verbatim (not summarized). The runtime applies a *degrading guard*: if these turns exceed the available budget, `buffer_turns` is reduced by one repeatedly until the budget fits, down to zero. |
| `buffer_max_ratio` | float | `0.3` | Hard cap on the fraction of the context window the recent buffer may occupy. Even if `buffer_turns` would fit, the buffer is trimmed if it exceeds this ratio. |

### Prerequisites

- **Context windows must be registered.** Add entries to `inference.context_windows` mapping each fully-qualified model identifier (e.g., `"openai/gpt-4o-mini"`) to its context window size in tokens. Models absent from this map have no registered window and compaction will not trigger for them.
- **A conversation cache is recommended.** While compaction works without a cache (using marker-only mode), enabling a conversation cache (PostgreSQL, SQLite, or in-memory) improves performance by caching summaries across requests and enabling recursive fold-up of accumulated summaries.

## Behavior details

### Compaction trigger

Compaction triggers when **all** of the following are true:

1. `compaction.enabled` is `true`
2. The model has a registered context window in `inference.context_windows`
3. The estimated token count of the conversation exceeds `threshold_ratio × context_window`
4. The estimated token count is at least `token_floor`

### Degrading guard

The `buffer_turns` setting specifies a target number of recent turns to preserve. If the selected buffer turns exceed the available budget (the context window minus the summary minus the new query), the system reduces the buffer by one turn pair at a time until the budget fits. In extreme cases, the buffer can shrink to zero turns, meaning only the summary and the current query are sent to the LLM.

### Marker persistence

When compaction occurs, a marker message (prefixed with `[lightspeed:compaction-summary]`) is appended to the conversation in OGX. This marker serves as a fallback for reconstructing the compacted state in cache-less deployments or after cache eviction.

### Per-conversation locking

Compaction acquires a per-conversation lock to prevent concurrent requests on the same conversation from racing during summarization. If multiple requests arrive simultaneously, they are serialized. The lock is automatically released after processing.

### Recursive re-summarization

Over very long conversations, multiple compaction summaries may accumulate. When the total size of cached summaries approaches the context window threshold, they are recursively folded into a single summary using a dedicated re-summarization prompt. This prevents summaries from themselves exceeding the context window.

## When compaction is disabled

When compaction is disabled (the default), requests that cause the conversation history to exceed the model's context window will fail with HTTP 413 (Prompt Too Long). Clients must manage conversation length themselves, for example by starting new conversations or deleting old ones.

## Frequently asked questions

**Does compaction lose information?**

Compaction summarizes older turns, so fine-grained details from early in the conversation may be condensed. The full original conversation history remains stored in OGX and is retrievable via the conversations API. The LLM simply receives a summary instead of the full transcript for inference.

**Does compaction use extra tokens?**

Yes. The summarization step requires an additional LLM call, which consumes tokens. These tokens are counted against the user's quota. The trade-off is that the conversation can continue instead of failing with HTTP 413.

**Can I use compaction with all LLM providers?**

Compaction works with any provider supported by OGX, as long as the model's context window is registered in `inference.context_windows`.

**How does compaction interact with RAG?**

RAG context (retrieved documents) is injected at query time and is not affected by compaction. Compaction only summarizes conversation history turns, not RAG-injected content.

**Why don't `/v1/responses` and `/a2a` return `context_status`?**

The `/v1/responses` endpoint follows the OpenAI Responses API specification and must not include custom fields to remain compatible. The `/a2a` endpoint uses the A2A protocol specification, which does not define UI indicator fields. Compaction still runs on both endpoints — the status is simply not surfaced in the response.
