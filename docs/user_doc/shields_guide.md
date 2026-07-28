# Safety Shields Guide

This guide covers LCORE-owned safety shields: how to configure them in
`lightspeed-stack.yaml`, which shield types are supported, how they apply on
request endpoints, how to list them via `/v1/shields`, and how `shield_ids`
request overrides work.

> [!IMPORTANT]
> Shields used by `/query`, `/streaming_query`, `/responses`, and `/rlsapi` are
> **owned and configured by Lightspeed Core Stack**, not by the Llama Stack /
> OGX Safety or Moderations APIs anymore. Do not configure LCORE request guardrails
> under `providers.safety` / `registered_resources.shields` in the stack
> `run.yaml`.

---

- [Introduction](#introduction)
- [Configuration](#configuration)
  - [Supported shield types](#supported-shield-types)
  - [question_validity](#question_validity)
  - [redaction](#redaction)
- [How shields apply at runtime](#how-shields-apply-at-runtime)
  - [Agent-based endpoints](#agent-based-endpoints)
  - [Responses-based endpoints](#responses-based-endpoints)
  - [Per-endpoint behavior](#per-endpoint-behavior)
- [Listing shields (`GET /v1/shields`)](#listing-shields-get-v1shields)
- [Request overrides (`shield_ids`)](#request-overrides-shield_ids)
- [Disabling overrides](#disabling-overrides)
- [References](#references)

---

# Introduction

LCORE shields are guardrails declared in the Lightspeed Core Stack
configuration. Each entry has:

| Field | Meaning |
|-------|---------|
| `name` | Unique shield name used in `/v1/shields` and in `shield_ids` overrides |
| `provider_id` | Shield type discriminator (`question_validity` or `redaction`) |
| `config` | Type-specific settings |

Names must be unique across the `shields` list.

# Configuration

Add a `shields` list to `lightspeed-stack.yaml`:

```yaml
shields:
  - name: topic-guard
    provider_id: question_validity
    config:
      model_id: openai/gpt-4o-mini
      # optional:
      # model_prompt: "..."
      # invalid_question_response: "..."

  - name: pii-redaction
    provider_id: redaction
    config:
      rules:
        - pattern: '\b\d{3}-\d{2}-\d{4}\b'
          replacement: '[REDACTED]'
      case_sensitive: false
```

See [examples/lightspeed-stack-shields.yaml](../../examples/lightspeed-stack-shields.yaml)
for a complete example.

## Supported shield types

| `provider_id` | Purpose | Typical application |
|---------------|---------|---------------------|
| `question_validity` | Classify whether the user question is in-topic; reject off-topic input with a fixed reply | Agent capability on agent-based endpoints; also considered by direct-run input moderation |
| `redaction` | Regex-based PII / sensitive-data redaction of model messages | Agent capability on agent-based endpoints |

## question_validity

| Config field | Required | Description |
|--------------|----------|-------------|
| `model_id` | Yes | Model used for the validity check (for example `openai/gpt-4o-mini`) |
| `model_prompt` | No | Classifier prompt (has a built-in default) |
| `invalid_question_response` | No | Reply returned when the question is rejected |

## redaction

| Config field | Required | Description |
|--------------|----------|-------------|
| `rules` | No (default `[]`) | Ordered list of `{pattern, replacement, case_sensitive?}` rules |
| `case_sensitive` | No (default `false`) | Global case sensitivity when a rule does not override it |

Invalid regex patterns are rejected at configuration load time.

# How shields apply at runtime

The same shield logic (`question_validity` and `redaction`) is used on both
agent-based and responses-based endpoints; only the integration point differs.

## Agent-based endpoints

On agent-based endpoints (for example `/v1/query` and `/v1/streaming_query`),
shields run as **pydantic-ai capabilities** attached when the agent is built.
Those capabilities wrap the agent pipeline — for example rejecting off-topic
questions or redacting PII from model messages — using the configured shields.

## Responses-based endpoints

On pure responses-based endpoints (for example `/v1/responses` and `/v1/infer`),
there is no agent capability layer. Instead, LCORE runs the **same core shield
functionality directly** through a custom API (`run_shield_moderation`) before
each request. When moderation blocks the input, the endpoint returns a refusal
(and may persist the blocked turn) without calling the model.

## Per-endpoint behavior

| Endpoint | How shields run | `shield_ids` |
|----------|-----------------|--------------|
| `POST /v1/query` | Agent capabilities (via `build_agent`) | Yes; subject to `disable_shield_ids_override` |
| `POST /v1/streaming_query` | Agent capabilities (via `build_agent`) | Yes; subject to `disable_shield_ids_override` |
| `POST /v1/responses` | Direct custom API before the request; agent capabilities when the request uses the agent path | Yes (`shield_ids` is an LCORE extension). Override disable gate is not applied on this endpoint today |
| `POST /v1/infer` (rlsapi v1) | Direct custom API before the request | No `shield_ids` field — always uses all configured shields |

# Listing shields (`GET /v1/shields`)

`GET /v1/shields` returns shields from **LCORE configuration only**. It does
not call Llama Stack / OGX to list Safety or Moderations resources.

Each catalog entry has this shape:

| Field | Description |
|-------|-------------|
| `name` | Configured shield name |
| `provider_id` | `question_validity` or `redaction` |
| `type` | Always `"shield"` |
| `config` | Type-specific shield configuration |

Example response body:

```json
{
  "shields": [
    {
      "name": "pii-redaction",
      "provider_id": "redaction",
      "type": "shield",
      "config": {
        "rules": [
          {
            "pattern": "\\d+",
            "replacement": "[NUM]",
            "case_sensitive": null
          }
        ],
        "case_sensitive": false
      }
    }
  ]
}
```

# Request overrides (`shield_ids`)

Optional request field on `/v1/query`, `/v1/streaming_query`, and
`/v1/responses`:

| `shield_ids` value | Behavior |
|--------------------|----------|
| omitted / `null` | Apply **all** configured shields |
| `[]` | Apply **no** shields |
| `["topic-guard", ...]` | Apply only those names; unknown IDs yield HTTP **404** |

Values must match configured `name` strings (as returned by
`GET /v1/shields`), not Llama Stack shield resource names.

Example:

```json
{
  "query": "How do I scale a Deployment?",
  "shield_ids": ["topic-guard"]
}
```

# Disabling overrides

To ignore client-provided `shield_ids` on `/v1/query` and
`/v1/streaming_query` (always use the configured set), set:

```yaml
customization:
  disable_shield_ids_override: true
```

When this flag is set and the client still sends `shield_ids` (including an
empty list), the endpoint returns HTTP **422**.

# References

- [Configuration options](config.md) — schema tables for shield-related models
- [OpenResponses /responses](../devel_doc/responses.md) — `shield_ids` LCORE extension
- [Example configuration](../../examples/lightspeed-stack-shields.yaml)
