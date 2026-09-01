# Safety Shields Guide

This guide covers LCORE-owned safety shields: how to configure them in
`lightspeed-stack.yaml`, which shield types are supported, how they apply on
request endpoints, how to list them via `/v1/shields`, and how `shield_ids`
request overrides work.

> [!IMPORTANT]
> Shields used by `/query`, `/streaming_query`, `/responses`, and `/rlsapi` are
> **owned and configured by Lightspeed Core Stack**, not by the OGX /
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
| `model_prompt` | No | Classifier prompt. When omitted: customization profile `system_prompts.validation`, then the LCORE default |
| `invalid_question_response` | No | Reply when rejected. When omitted: profile `query_responses.invalid_resp`, then the LCORE default |

### Profile fallback (resolved at startup)

When LCORE loads configuration, omitted `model_prompt` /
`invalid_question_response` on each `question_validity` shield are filled
once from the customization profile module (when `customization.profile_path`
points at a Python profile) or from LCORE defaults:

| Shield field | Profile module key | Runtime use |
|--------------|--------------------|-------------|
| `model_prompt` | `PROFILE_CONFIG["system_prompts"]["validation"]` | **Classifier template** — agent / `wrap_run` only |
| `invalid_question_response` | `PROFILE_CONFIG["query_responses"]["invalid_resp"]` | **Refusal text** — agent and responses / `run()` paths |

Those profile keys are read from the profile **Python module**
(`PROFILE_CONFIG`), not from fields under `customization:` in
`lightspeed-stack.yaml`.

Explicit values in `lightspeed-stack.yaml` always win. Missing profile keys
fall through silently to LCORE defaults. After load, `GET /v1/shields` returns
the **effective** prompt and refusal text.

**Omit vs empty string:** Only a missing / `null` field is filled. An explicit
empty string (`""`) in YAML **or** in the profile (`validation` /
`invalid_resp`) is kept as-is and is not replaced by LCORE defaults.

**Upgrade note:** If a deployment already uses a customization profile that
defines `validation` / `invalid_resp`, and a QV shield omits those YAML fields,
the effective values change after upgrade (no YAML edit required): classifier
text on the agent path, and refusal text on both agent and responses paths.
Set the fields explicitly in YAML to keep the previous LCORE defaults.

**Schema / OpenAPI note:** In the config model these fields are optional
(`null` when omitted in YAML). After configuration load they are always filled
with the effective string. Clients that read `GET /v1/shields` see the resolved
values, not `null`.

### `model_prompt` placeholders (agent / `wrap_run` only)

On the agent capability path, the classifier prompt is rendered with Python
`string.Template` before the validity model runs. Include `$message` or
`${message}` so the user question is substituted into the prompt. Without it,
the classifier still runs but does not see the user's question (same behavior
as before). The responses moderation path (`run()`) does not use this template;
it sends raw user input (see below).

Optional placeholders:

| Placeholder | Substituted value |
|-------------|-------------------|
| `${message}` / `$message` | User question text |
| `${allowed}` / `$allowed` | `ALLOWED` |
| `${rejected}` / `$rejected` | `REJECTED` |

## redaction

| Config field | Required | Description |
|--------------|----------|-------------|
| `rules` | No (default `[]`) | Ordered list of `{pattern, replacement, case_sensitive?}` rules |
| `case_sensitive` | No (default `false`) | Global case sensitivity when a rule does not override it |

Invalid regex patterns are rejected at configuration load time.

# How shields apply at runtime

Both agent-based and responses-based endpoints use the configured
`question_validity` and `redaction` shields; the integration point differs
(see below for how `question_validity` prompts are applied on each path).

## Agent-based endpoints

On agent-based endpoints (for example `/v1/query` and `/v1/streaming_query`),
shields run as **pydantic-ai capabilities** attached when the agent is built.
Those capabilities wrap the agent pipeline — for example rejecting off-topic
questions or redacting PII from model messages — using the configured shields.

## Responses-based endpoints

On pure responses-based endpoints (for example `/v1/responses` and `/v1/infer`),
there is no agent capability layer. Instead, LCORE runs shield moderation
directly through `run_shield_moderation_v2` before each request. When
moderation blocks the input, the endpoint returns a refusal (and may persist
the blocked turn) without calling the model.

For `question_validity`, that moderation path sends the **raw user input** to
the validity model. It does **not** render `model_prompt` with
`$message` / `${message}` the way the agent capability path (`wrap_run`) does.
Configured / profile-resolved `invalid_question_response` is still used for the
refusal text on this path. This matches pre-existing moderation behavior.

## Per-endpoint behavior

| Endpoint | How shields run | `shield_ids` |
|----------|-----------------|--------------|
| `POST /v1/query` | Agent capabilities (via `build_agent`) | Yes; subject to `disable_shield_ids_override` |
| `POST /v1/streaming_query` | Agent capabilities (via `build_agent`) | Yes; subject to `disable_shield_ids_override` |
| `POST /v1/responses` | Direct custom API before the request; agent capabilities when the request uses the agent path | Yes (`shield_ids` is an LCORE extension). Override disable gate is not applied on this endpoint today |
| `POST /v1/infer` (rlsapi v1) | Direct custom API before the request | No `shield_ids` field — always uses all configured shields |

# Listing shields (`GET /v1/shields`)

`GET /v1/shields` returns shields from **LCORE configuration only**. It does
not call OGX / OGX to list Safety or Moderations resources.

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
`GET /v1/shields`), not OGX shield resource names.

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
