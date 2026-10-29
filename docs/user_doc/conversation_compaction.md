# Conversation Compaction Guide

## Overview

Conversation compaction is a feature that automatically summarizes older conversation turns when the conversation history approaches the LLM's context window limit. Instead of failing with an HTTP 413 error when the input becomes too long, compaction condenses earlier parts of the conversation into a summary while preserving recent turns verbatim. This allows long-running conversations to continue seamlessly.

## How it works

When a user sends a query, the system estimates the total token count of the entire input — system prompt (instructions), any existing compaction summaries, recent conversation items, and the new user query. If the estimated tokens exceed a configurable fraction of the model's context window (the *threshold ratio*), compaction is triggered:

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

Compaction is disabled by default. To enable it, add a `compaction` section to your `lightspeed-stack.yaml` configuration file. See [Context window](#context-window) for how the service finds the context window of each model.

### Minimal configuration

```yaml
inference:
  default_provider: openai
  default_model: gpt-5.6-luna
  providers:
    - type: openai
      api_key_env: OPENAI_API_KEY
      allowed_models:
        - provider_model_id: gpt-5.6-luna
          metadata:
            context_window: 128000

compaction:
  enabled: true
```

### Full configuration

```yaml
inference:
  default_provider: openai
  default_model: gpt-5.6-luna
  providers:
    - type: openai
      api_key_env: OPENAI_API_KEY
      allowed_models:
        - provider_model_id: gpt-5.6-luna
          metadata:
            context_window: 128000

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

- **Set the context window of models the service cannot look up.** Self-hosted models (vLLM, WatsonX and similar) get a default of 128,000 tokens unless their `allowed_models` entry sets `metadata.context_window`. See [Context window](#context-window).
- **A conversation cache is recommended.** While compaction works without a cache (using marker-only mode), enabling a conversation cache (PostgreSQL, SQLite, or in-memory) improves performance by caching summaries across requests and enabling recursive fold-up of accumulated summaries.

## Context window

The compaction threshold and the recent-buffer budget are fractions of the model's context window. For the model a request uses, the service takes the first of:

1. `metadata.context_window` on the model's entry in `inference.providers[].allowed_models`.
2. The deprecated `inference.context_windows` map (see below).
3. The window listed for the model in the model data bundled with the service (the `genai-prices` package). It covers hosted models of providers such as OpenAI, Azure OpenAI, Vertex AI and Bedrock, but not self-hosted backends such as vLLM or WatsonX.
4. A default of 128,000 tokens.

Set `metadata.context_window` for every model whose window is not listed and is not 128,000 tokens. A model with a smaller window can otherwise fail with HTTP 413 before compaction triggers. A configured value also takes precedence over the listed one, which helps when a deployment limits the window below the vendor's maximum.

Requests identify the model as `<provider id>/<model name>`. The entry that matches has the provider `id` (which defaults to `type`) and the model `name` (which defaults to `provider_model_id`), or else that `provider_model_id`:

```yaml
inference:
  providers:
    - type: vllm
      id: rhaiis
      allowed_models:
        - name: granite-3.3-8b-instruct
          provider_model_id: granite-3.3-8b-instruct
          metadata:
            context_window: 131072
```

Before adding an `inference.providers` entry only to set a window, read [Migrating to v0.8.0](../migrations/v0.8.0.md#context-windows-for-conversation-compaction): in some deployments the entry changes the generated OGX configuration.

### Deprecated: `inference.context_windows`

The top-level `inference.context_windows` map is deprecated: it still applies to a model whose entry sets no `metadata.context_window`, and the service logs a warning at startup while it is set. [Migrating to v0.8.0](../migrations/v0.8.0.md#context-windows-for-conversation-compaction) says how to move its entries and when to keep them for now.

## Behavior details

### Compaction trigger

Compaction triggers when **all** of the following are true:

1. `compaction.enabled` is `true`
2. The estimated token count of the conversation exceeds `threshold_ratio × context_window` (see [Context window](#context-window))
3. The estimated token count is at least `token_floor`

### Image attachments

A query with image attachments on `/v1/query` or `/v1/streaming_query` is answered in a compacted conversation as well:

- The images attached to the current query are sent to the LLM, together with the summary and the recent turns.
- Images from earlier turns are not sent again once the conversation is compacted. The LLM gets the text of those turns, or their summary.
- Images are not counted in the token estimate that triggers compaction. Only text is counted.
- The turn that the service stores in the conversation holds the text of the query, without the image.

### Degrading guard

The `buffer_turns` setting specifies a target number of recent turns to preserve. If the selected buffer turns exceed the available budget (`buffer_max_ratio × context_window`), the system reduces the buffer by one turn pair at a time until the budget fits. In extreme cases, the buffer can shrink to zero turns, meaning only the summary and the current query are sent to the LLM.

### Marker persistence

When compaction occurs, a marker message (prefixed with `[lightspeed:compaction-summary]`) is appended to the conversation in OGX. This marker serves as a fallback for reconstructing the compacted state in cache-less deployments or after cache eviction.

The marker is internal bookkeeping, not something the user said. It stays in storage, but `GET /v1/conversations/{conversation_id}` leaves it out of the returned chat history, so clients see only the turns the user and the assistant exchanged. `GET /v2/conversations/{conversation_id}` reads the conversation cache, which never holds markers.

The prefix is reserved. A user message that begins with `[lightspeed:compaction-summary]` cannot be told apart from a marker, so `GET /v1/conversations/{conversation_id}` leaves it out as well, whether or not compaction is enabled.

### Per-conversation locking

Compaction acquires a per-conversation lock to prevent concurrent requests on the same conversation from racing during summarization. If multiple requests arrive simultaneously, they are serialized. The lock is automatically released after processing.

### Recursive re-summarization

Over very long conversations, multiple compaction summaries may accumulate. When the total size of cached summaries approaches the context window threshold, they are recursively folded into a single summary using a dedicated re-summarization prompt. This prevents summaries from themselves exceeding the context window.

## When compaction is disabled

When compaction is disabled (the default), requests that cause the conversation history to exceed the model's context window will fail with HTTP 413 (Prompt Too Long). Clients must manage conversation length themselves, for example by starting new conversations or deleting old ones.

> **Warning:** Disabling compaction after a conversation has already been compacted is unsupported. Turning off compaction reverts the conversation to full-history replay, which can re-trigger the HTTP 413 error and send marker text through the model. Leave compaction enabled for the lifetime of any conversation that has already been compacted.

## Frequently asked questions

**Does compaction lose information?**

Compaction summarizes older turns, so fine-grained details from early in the conversation may be condensed. The full original conversation history remains stored in OGX and is retrievable via the conversations API; the summaries themselves are not part of that history and are not returned. The LLM simply receives a summary instead of the full transcript for inference.

**Does compaction use extra tokens?**

Yes. The summarization step requires an additional LLM call, which consumes tokens. These tokens are counted against the user's quota. The trade-off is that the conversation can continue instead of failing with HTTP 413.

**Can I use compaction with all LLM providers?**

Compaction works with any provider supported by OGX. For a model whose context window the service cannot look up, set `metadata.context_window` on its `allowed_models` entry; see [Context window](#context-window).

**How does compaction interact with RAG?**

RAG context (retrieved documents) is injected at query time and is not affected by compaction. Compaction only summarizes conversation history turns, not RAG-injected content.

**Why don't `/v1/responses` and `/a2a` return `context_status`?**

The `/v1/responses` endpoint follows the OpenAI Responses API specification and must not include custom fields to remain compatible. The `/a2a` endpoint uses the A2A protocol specification, which does not define UI indicator fields. Compaction still runs on both endpoints — the status is simply not surfaced in the response.
