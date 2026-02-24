# LCORE OpenResponses API Specification

This document describes the LCORE implementation of the OpenResponses API, exposed via the `POST /v1/responses` endpoint. This endpoint follows the OpenResponses specification and is built on top of the Llama Stack Responses API. Since the underlying Llama Stack Responses API is still evolving, the LCORE endpoint provides a standards-aligned interface while documenting a supported subset of OpenResponses fields. In addition, it introduces LCORE-specific extensions to preserve feature parity and defines explicit field mappings to reproduce the functionality of existing `/v1/query` and `/v1/streaming_query` endpoints.

---

## Table of Contents

* [Introduction](#introduction)
* [Endpoint Overview](#endpoint-overview)
* [Request Specification](#request-specification)
  * [Inherited LLS OpenAPI Fields](#inherited-lls-openapi-fields)
  * [LCORE-Specific Extensions](#lcore-specific-extensions)
  * [Field Mappings](#field-mappings)
  * [Structured request attributes: variants and usage](#structured-request-attributes-variants-and-usage)
* [Response Specification](#response-specification)
  * [Inherited LLS OpenAPI Fields](#inherited-lls-openapi-fields-1)
  * [Structured response output: object types and examples](#structured-response-output-object-types-and-examples)
  * [LCORE-Specific Extensions](#lcore-specific-extensions-1)
  * [Field Mappings](#field-mappings-1)
* [Streaming Support](#streaming-support)
* [Known Limitations and Behavioral Differences](#known-limitations-and-behavioral-differences)
  * [Conversation Handling](#conversation-handling)
  * [Output Representation](#output-representation)
  * [Tool Configuration Differences](#tool-configuration-differences)
  * [LCORE-Specific Extensions](#lcore-specific-extensions-2)
  * [Streaming Differences](#streaming-differences)
* [Examples](#examples)
  * [Basic Request (Non-Streaming)](#basic-request-non-streaming)
  * [Request with Conversation Continuation](#request-with-conversation-continuation)
  * [Request with restricted Tools (RAG)](#request-with-restricted-tools-rag)
  * [Request with LCORE Extensions](#request-with-lcore-extensions)
  * [Streaming Request](#streaming-request)
* [Error Handling](#error-handling)
* [Available OpenResponses items](#available-openresponses-items)
  * [message](#message)
  * [web_search_call](#web_search_call)
  * [file_search_call](#file_search_call)
  * [function_call](#function_call)
  * [function_call_output](#function_call_output)
  * [mcp_call](#mcp_call)
  * [mcp_list_tools](#mcp_list_tools)
  * [mcp_approval_request](#mcp_approval_request)
  * [mcp_approval_response](#mcp_approval_response)

---

## Introduction

The LCORE OpenResponses API provides a standards-aligned interface for AI response generation while preserving feature compatibility with existing LCORE workflows. In particular, the endpoint enriches requests and responses with LCORE-specific attributes, adjusts the semantics of some fields for compatibility, and enriches streaming events.

The endpoint is designed to provide feature parity with existing streaming endpoints while offering a more direct interface to the underlying Responses API.

---

## Endpoint Overview

**Endpoint:** `POST /v1/responses`

**Request format:** **JSON** — send the request payload following the [Request Specification](#request-specification) as a single JSON object in the request body.

**Content-Type:** `application/json`

**Response format:**
* **JSON** — when `stream` is `false` or omitted; the response is a single JSON object.
* **Server-Sent Events (SSE)** — when `stream` is `true`; the response is a stream of SSE-formatted events.

---

## Request Specification

### Inherited LLS OpenAPI Fields

The following request attributes are supported as defined by the underlying Llama Stack Responses API and retain their original OpenResponses semantics unless otherwise stated:

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `input` | string or array[object] | Query text or structured input items | Yes |
| `model` | string | Model ID (`provider/model`). Auto-selected if omitted | No |
| `conversation` | string | Conversation ID (OpenAI or LCORE format). Mutually exclusive with `previous_response_id` | No |
| `include` | array[string] | Extra output item types to include | No |
| `instructions` | string | System prompt | No |
| `max_infer_iters` | integer | Max inference iterations | No |
| `max_tool_calls` | integer | Max tool calls per response | No |
| `metadata` | dictionary | Custom metadata (tracking/logging) | No |
| `parallel_tool_calls` | boolean | Allow parallel tool calls | No |
| `previous_response_id` | string | Previous response ID for context. Mutually exclusive with `conversation` | No |
| `prompt` | object | Prompt substitution template | No |
| `store` | boolean | Store in conversation history (default: true) | No |
| `stream` | boolean | Stream response (default: false) | No |
| `temperature` | float | Sampling temperature (0.0–2.0) | No |
| `text` | object | Output format specification (JSON schema, JSON object, or text) | No |
| `tool_choice` | string or object | Tool selection strategy (auto, required, none, or specific rules). Default: auto | No |
| `tools` | array[object] | Tools available for request (file search, web search, functions, MCP). Default: all | No |

**Note:** Only the fields listed above are currently supported. Additional OpenResponses fields may not yet be available due to LLS API incompleteness.

### LCORE-Specific Extensions

The following fields are LCORE-specific request extensions and are not part of the standard LLS OpenAPI specification:

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `generate_topic_summary` | boolean | Generate topic summary for new conversations | No |
| `solr` | dictionary | Solr vector_io provider query parameters | No |


### Field Mappings

The following table maps LCORE query request fields to the OpenResponses request fields used by `POST /v1/responses`.

| Original LCORE Field | LCORE OpenAPI Field | Notes |
|-------------------|-------------------|-------|
| `query` | `input` | The attribute allows to pass string-like input and also structured input of list of input items |
| `conversation_id` | `conversation` | Supports OpenAI `conv_*` format or LCORE hex UUID |
| `provider` + `model` | `model` | Concatenated as `provider/model` |
| `system_prompt` | `instructions` | Only change in attribute's name |
| `attachments` | `input` items | Attachments can be passed as input messages with content of type `input_file` |
| `no_tools` | `tool_choice` | `no_tools=true` mapped to `tool_choice="none"` |
| `vector_store_ids` | `tools` + `tool_choice` | Vector stores can be explicitly specified and restricted by `file_search` tool type's `vector_store_ids` attribute |
| `generate_topic_summary` | N/A | Exposed directly (LCORE-specific) |
| `solr` | N/A | Exposed directly (LCORE-specific) |

**Note:** The `media_type` attribute is not present in the LCORE specification, as downstream logic determines which format to process (structured `output` or textual `output_text` response attributes).

### Structured request attributes: variants and usage

This section examines some of the more complex request attributes with explanation and example usage.

#### `input`

Required. Either a **string** or a list of input items. Each **item** is one of:

- [message](#message) — one turn with `role` and `content` (string or list of content parts)
- [web_search_call](#web_search_call) — completed web search
- [file_search_call](#file_search_call) — completed file search
- [function_call](#function_call) — completed function call
- [function_call_output](#function_call_output) — result of a function call passed back to the model
- [mcp_call](#mcp_call) — completed MCP tool call
- [mcp_list_tools](#mcp_list_tools) — MCP list-tools result
- [mcp_approval_request](#mcp_approval_request) — request for human approval of an MCP call
- [mcp_approval_response](#mcp_approval_response) — human approval or denial

All input item objects have a common `type` attribute that determines their structure. See [Available OpenResponses items](#available-openresponses-items) for detailed descriptions and examples of each item type.

#### `include`

Optional. List of output item types to include in the response that are excluded by default.

Allowed values (literal strings): `web_search_call.action.sources`, `code_interpreter_call.outputs`, `computer_call_output.output.image_url`, `file_search_call.results`, `message.input_image.image_url`, `message.output_text.logprobs`, `reasoning.encrypted_content`.

**Examples:**

```json
{ "include": ["message.output_text.logprobs"] }
```

```json
{ "include": ["message.output_text.logprobs", "file_search_call.results"] }
```

#### `prompt`

Optional. References a **prompt template** with variables for dynamic substitution.

The template can contain placeholders (variables) that are replaced at request time with the values you send in `variables`. Typical use cases: reusable system prompts (e.g. “You are an expert on {{topic}}”), report generators that plug in a title and attachments, or standardized workflows that accept a few inputs.

When provided, the object must have an `id` (required); `variables` and `version` are optional.

- `id` (required): Unique identifier of the prompt template.
- `variables` (optional): Map of variable names to substitution values. Each value must be a content-part object of type `input_text`, `input_image`, or `input_file` (same shapes as in [input](#input) content parts). Omit or pass `null` if the template has no variables.
- `version` (optional): Version of the prompt template to use; defaults to the latest if omitted.

**Examples:**

Template with multiple variable types (text, image, file):
```json
{
  "prompt": {
    "id": "report_template",
    "variables": {
      "title": { "type": "input_text", "text": "Weekly summary" },
      "chart": { "type": "input_image", "image_url": "https://example.com/chart.png", "detail": "high" },
      "data": { "type": "input_file", "file_id": "file_xyz", "filename": "data.csv" }
    },
    "version": "2.0"
  }
}
```

Here the template `report_template` (version `2.0`) might define placeholders such as `{{title}}`, `{{chart}}`, and `{{data}}`; the backend substitutes them with the provided text, image, and file respectively.

#### `text`

Optional. Text response configuration that tells the model how to format its main text output.

The `text` object constrains the model’s reply so it fits your downstream use. Without it, the backend uses a default (typically plain text). With it, you can request **plain text** (`type: "text"`), **free-form JSON** (`type: "json_object"`), or **JSON that conforms to a schema** (`type: "json_schema"`). For `json_schema`, you supply a JSON Schema; the model then fills in the structure (e.g. a form, a list of items, or a single field like `answer`).

When provided, the object has a single optional key `format` which has the following attributes:

- `type` (required): One of `"text"`, `"json_object"`, or `"json_schema"`.
- `name` (optional): Name of the format; used with `json_schema`.
- `schema` (optional): JSON Schema object the response must conform to; used with `json_schema`.
- `description` (optional): Description of the response format; used with `json_schema`.
- `strict` (optional): If `true`, the response must match the schema exactly; used with `json_schema`.

**Examples:**

Plain text (explicit):

```json
{ "text": { "format": { "type": "text" } } }
```

Free-form JSON (any valid JSON object):

```json
{ "text": { "format": { "type": "json_object" } } }
```

JSON schema with optional name, description, and strict mode:

```json
{
  "text": {
    "format": {
      "type": "json_schema",
      "name": "survey_response",
      "description": "User survey answers",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "rating": { "type": "integer", "minimum": 1, "maximum": 5 },
          "comment": { "type": "string" }
        },
        "required": ["rating"]
      }
    }
  }
}
```

#### `tool_choice`

Optional. **Tool selection strategy** that controls whether and how the model uses tools.

**What it does:** When tools are supplied by `tools` attribute, `tool_choice` decides if the model may call them, must call at least one, or must not use any. You can pass a **simple mode string** or a **specific tool-config object** to force a particular tool (e.g. always use file search or a given function). Omitted or `null` behaves like `"auto"`. Typical use: disable tools for a plain-Q&A turn (`"none"`), force RAG-only (`file_search`), or constrain to a subset of tools (`allowed_tools`).

**Simple modes (string):**

- `"auto"`: Model may use any of the available tools (default when omitted).
- `"required"`: Model must use at least one tool.
- `"none"`: No tools; model must not call any. Use when LCORE maps `no_tools` to this.

**Specific tool objects (object with `type`):**

- `allowed_tools`: Restrict to a list of tool definitions; `mode` is `"auto"` or `"required"`, `tools` is a list of tool objects (same shapes as in [tools](#tools)).
- `file_search`: Force the model to use file search.
- `web_search`: Force the model to use web search (optionally with a variant such as `web_search_preview`).
- `function`: Force a specific function; `name` (required) is the function name.
- `mcp`: Force a tool on an MCP server; `server_label` (required), `name` (optional) tool name.
- `custom`: Force a custom tool; `name` (required).

**Examples:**

Simple modes (string): use one of `"auto"`, `"required"`, or `"none"`.

```json
{ "tool_choice": "auto" }
{ "tool_choice": "required" }
{ "tool_choice": "none" }
```

Restrict to specific tools with `allowed_tools` (mode `"auto"` or `"required"`, plus `tools` array):

```json
{
  "tool_choice": {
    "type": "allowed_tools",
    "mode": "required",
    "tools": [
      { "type": "file_search", "vector_store_ids": ["vs_123"] },
      { "type": "web_search" }
    ]
  }
}
```

Force a single tool type: `file_search`, `web_search`, `function`, `mcp`, or `custom`.

```json
{ "tool_choice": { "type": "file_search" } }
{ "tool_choice": { "type": "web_search" } }
{ "tool_choice": { "type": "function", "name": "get_weather" } }
{ "tool_choice": { "type": "mcp", "server_label": "my_server", "name": "fetch_data" } }
{ "tool_choice": { "type": "custom", "name": "my_tool" } }
```

---

#### `tools`

Optional. **List of tools** the model is allowed to use for this request (file search, web search, function, MCP).

Each item in `tools` declares one capability: search a set of vector stores (**file_search**), use web search (**web_search**), call a function (**function**), or use tools from an MCP server (**mcp**). The model may then call these tools during the response (subject to [tool_choice](#tool_choice)). **If `tools` is `null` or omitted, LCORE automatically uses all tools from the LCORE configuration.** Send `tools` only when you want to restrict the request to a specific subset of tools or vector stores (e.g. a single RAG index or only web search).

**Tool types (each object has a required `type`):**

- `file_search`: Search within given vector stores. `vector_store_ids` (required): list of vector store IDs. Optional: `max_num_results` (1–50, default 10), `filters`, `ranking_options`.
- `web_search`: Web search. `type` can be `"web_search"`, `"web_search_preview"`, or other variants. Optional: `search_context_size` (`"low"`, `"medium"`, `"high"`).
- `function`: Call a named function. `name` (required). Optional: `description`, `parameters` (JSON schema), `strict`.
- `mcp`: Use tools from an MCP server. `server_label` (required), `server_url` (required). Optional: `headers`, `require_approval`, `allowed_tools`.

**Examples:**

Omitted or null (use all tools configured in LCORE):

```json
{ "tools": null }
```
Restrict to file search on two vector stores and web search:

```json
{
  "tools": [
    { "type": "file_search", "vector_store_ids": ["vs_1", "vs_2"] },
    { "type": "web_search" }
  ]
}
```

All tool types in one request (file_search with optional params, web_search with context size, function with schema, mcp):

```json
{
  "tools": [
    { "type": "file_search", "vector_store_ids": ["vs_docs"], "max_num_results": 5 },
    { "type": "web_search", "search_context_size": "high" },
    {
      "type": "function",
      "name": "get_weather",
      "description": "Get weather for a city",
      "parameters": { "type": "object", "properties": { "city": { "type": "string" } }, "required": ["city"] }
    },
    { "type": "mcp", "server_label": "my_mcp", "server_url": "https://mcp.example.com" }
  ]
}
```
---

## Response Specification

### Inherited LLS OpenAPI Fields

The following response attributes are inherited directly from the LLS OpenAPI specification:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique response ID |
| `object` | string | Always `"response"` |
| `created_at` | integer | Creation time (Unix) |
| `status` | string | Status (e.g. completed, blocked, in_progress) |
| `completed_at` | integer | Completion time (Unix), if set |
| `model` | string | Model ID (provider/model) used |
| `output` | array[object] | Structured output (messages, tool calls, etc.) |
| `error` | object | Error details if failed or blocked |
| `instructions` | string | System instructions used |
| `max_tool_calls` | integer | Max tool calls allowed |
| `metadata` | dictionary | Custom metadata |
| `parallel_tool_calls` | boolean | Parallel tool calls allowed |
| `previous_response_id` | string | Previous response ID (multi-turn) |
| `prompt` | object | Prompt echoed (id, variables, version) |
| `temperature` | float | Temperature used |
| `text` | object | Text config (format key) |
| `tool_choice` | string or object | Tool selection used |
| `tools` | array[object] | Tools available during generation |
| `top_p` | float | Top-p sampling used |
| `truncation` | string | Truncation strategy applied (`"auto"` or `"disabled"`) |
| `usage` | object | Token usage (input_tokens, output_tokens, total_tokens) |
| `output_text` | string | Aggregated text from output items |

### Structured response output: object types and examples

The `output` array contains structured items. Each item has a `type`. Each list item is one of:

- [message](#message) — assistant (or other) message; `content` is a string or a list of content parts
- [web_search_call](#web_search_call) — web search tool call
- [file_search_call](#file_search_call) — file search tool call
- [function_call](#function_call) — function tool call
- [mcp_call](#mcp_call) — MCP tool call
- [mcp_list_tools](#mcp_list_tools) — MCP server tool list
- [mcp_approval_request](#mcp_approval_request) — request for human approval of an MCP call

**Note:** No `mcp_approval_response` nor `function_call_output` here as they can serve only as input items.

All response item objects have a common `type` attribute that determines their structure. See [Available OpenResponses items](#available-openresponses-items) for detailed descriptions and examples of each item type.

### LCORE-Specific Extensions

The following fields are LCORE-specific and enrich the standard LLS OpenAPI specification to achieve feature parity:

| Field | Type | Description |
|-------|------|-------------|
| `conversation` | string | Conversation ID (exposed as `conversation`, linked internally to request conversation attribute) |
| `available_quotas` | object | Available quotas as measured by all configured quota limiters (LCORE-specific) |

### Field Mappings

The following mappings are applied when converting from LLS OpenAPI format to LCORE format:

| Original LCORE Field | LCORE OpenAPI Field | Notes |
|-------------------|-------------|-------|
| `conversation_id` | `conversation` | Exposed as `conversation` in the LLS response; linked internally to request conversation attribute |
| `response` | `output` and `output_text` | Mapped to both `output` (structured) or `output_text` (string) |
| `input_tokens` | `usage.input_tokens` | Token usage fields mapped to usage object |
| `output_tokens` | `usage.output_tokens` | Token usage fields mapped to usage object |
| `tool_calls` | `output` items | Tool activity represented via dedicated `output` items |
| `tool_results` | `output` items | Tool results represented via dedicated `output` items |

**Deprecated Fields:** The following fields are not exposed in the LCORE OpenResponses specification:
* `rag_chunks` - Part of `output` items of `file_search_call` type
* `referenced_documents` - Part of `output` items
* `truncated` - Deprecated; `truncation` field indicates used strategy, not whether the truncation was applied.

---

## Streaming Support

The LCORE OpenResponses API supports streaming responses when the `stream` parameter is set to `true`. When streaming is enabled:

* The response is delivered using Server-Sent Events (SSE) format
* Events are streamed in real-time as they are generated
* The `conversation` attribute is added to all chunks that contain a `response` attribute in their data payload
* The `available_quotas` attribute is added to the final chunk events: `response.completed`, `response.incomplete`, or `response.failed` containing the information and also to intermediate `response.in_progress` chunk containing empty object.

**SSE Format:**
Each streaming event follows the Server-Sent Events (SSE) format:
* `event: <event_type>` - Specifies the type of event (e.g., `response.created`, `response.output_text.delta`)
* `data: <json_data>` - Contains the event data as a JSON string
* Events are separated by double newlines (`\n\n`)
* The stream ends with `data: [DONE]\n\n` to signal completion

**Note:** Streaming support maintains feature parity with the existing `/v1/streaming_query` endpoint, with the addition of LCORE-specific fields (`conversation` and `available_quotas`) in streaming events.

**Metadata Extraction:** Response metadata (referenced documents, rag_chunks, tool calls, tool results) is consistently extracted from the final response object after streaming completes internally, ensuring identical persistence models as in query endpoints.

---

## Known Limitations and Behavioral Differences

The `/v1/responses` endpoint follows the OpenResponses structure but is currently constrained by the capabilities of the underlying Llama Stack Responses API. As a result, only the documented subset of request and response fields is supported.

Several behavioral differences and implementation details should be noted:

### Conversation Handling

The `conversation` field in responses is a LCORE-managed extension. While not natively defined by the Llama Stack specification, it is internally resolved and linked to the request conversation to preserve multi-turn behavior.

The endpoint accepts two conversation ID formats:

- **OpenAI format**: `conv_<48-character-hex>`
- **LCORE format**: `<48-character-hex>`

Both formats are automatically normalized internally before being forwarded to the underlying API.

### Model Selection

In OpenResponses the `model` field is required; in LCORE it is optional. If you omit `model` from the request, one is chosen for you in this order:

1. **Conversation** — For an existing conversation, the same model used last in that conversation is reused if still available.
2. **Default model** — If a default model is configured, that model is used.
3. **First available** — Otherwise, the first available LLM model is used.
4. If no model can be selected (e.g. no default and no LLM models), the request fails with 404 (model not found).

### Output Representation

Responses expose both:

- `output` — structured response items  
- `output_text` — aggregated plain-text output  

Fields such as `media_type`, `tool_calls`, `tool_results`, `rag_chunks`, and `referenced_documents` are not exposed directly. Instead, tool activity and retrieval results are represented as structured items within the `output` array.

### Tool Configuration Differences

Vector store IDs are configured within the `tools` array (e.g., as `file_search` tools) rather than through separate parameters. By default all tools that are configured in LCORE are used to support the response. The set of available tools can be maintained per-request by `tool_choice` or `tools` attributes.

### LCORE-Specific Extensions

The API introduces extensions that are not part of the OpenResponses specification:

- `generate_topic_summary` (request) — When set to `true` and a new conversation is created, a topic summary is automatically generated and stored in conversation metadata.
- `solr` (request) — Solr vector_io provider query parameters (e.g. filter queries).
- `available_quotas` (response) — Provides real-time quota information from all configured quota limiters.

### Streaming Differences

Streaming responses use Server-Sent Events (SSE) and are enriched with LCORE-specific metadata:

- The `conversation` attribute is included in streamed response payloads.
- The `available_quotas` attribute is added to final completion events (`response.completed`, `response.incomplete`, or `response.failed`) and also to the intermediate `response.in_progress` with empty object.

This enrichment may differ slightly from standard OpenAI streaming behavior but preserves compatibility with existing LCORE streaming workflows.

## Examples

### Basic Request (Non-Streaming)

```bash
curl -X POST http://localhost:8090/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input": "What is Kubernetes?",
    "model": "openai/gpt-4-turbo",
    "store": true,
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "resp_abc123",
  "object": "response",
  "created_at": 1704067200,
  "completed_at": 1704067250,
  "model": "openai/gpt-4-turbo",
  "status": "completed",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "Kubernetes is an open-source container orchestration system..."
        }
      ]
    }
  ],
  "usage": {
    "input_tokens": 100,
    "output_tokens": 50,
    "total_tokens": 150
  },
  "conversation": "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
  "available_quotas": {
    "daily": 1000,
    "monthly": 50000
  },
  "output_text": "Kubernetes is an open-source container orchestration system..."
}
```

### Request with Conversation Continuation

```bash
curl -X POST http://localhost:8090/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input": "Tell me more about it",
    "model": "openai/gpt-4-turbo",
    "conversation": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
    "store": true,
    "stream": false
  }'
```

### Request with restricted Tools (RAG)

```bash
curl -X POST http://localhost:8090/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input": "How do I deploy an application?",
    "model": "openai/gpt-4-turbo",
    "tools": [
      {
        "type": "file_search",
        "vector_store_ids": ["vs_abc123", "vs_def456"]
      }
    ],
    "store": true,
    "stream": false
  }'
```

### Request with LCORE Extensions

```bash
curl -X POST http://localhost:8090/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input": "What is machine learning?",
    "model": "openai/gpt-4-turbo",
    "generate_topic_summary": true,
    "store": true,
    "stream": false
  }'
```

### Streaming Request

```bash
curl -X POST http://localhost:8090/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input": "Explain Kubernetes architecture",
    "model": "openai/gpt-4-turbo",
    "stream": true,
    "store": true
  }'
```

**Streaming Response (SSE format):**
```text
event: response.created
data: {"type":"response.created","response":{"id":"resp_abc123","conversation":"conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"}}

event: response.output_text.delta
data: {"delta":"Kubernetes"}

event: response.output_text.delta
data: {"delta":" is"}

event: response.output_text.delta
data: {"delta":" an"}

...

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_abc123","conversation":"conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e","usage":{"input_tokens":100,"output_tokens":50,"total_tokens":150},"available_quotas":{"daily":1000,"monthly":50000}}}

data: [DONE]

```

---

## Error Handling

The endpoint returns standard HTTP status codes and error responses:

| Status Code | Description | Example |
|-------------|-------------|---------|
| 200 | Success | Valid request processed successfully |
| 401 | Unauthorized | Missing or invalid credentials |
| 403 | Forbidden | Insufficient permissions or model override not allowed |
| 404 | Not Found | Conversation, model, or provider not found |
| 413 | Payload Too Large | Prompt exceeded model's context window size |
| 422 | Unprocessable Entity | Request validation failed |
| 429 | Too Many Requests | Token quota exceeded |
| 500 | Internal Server Error | Configuration not loaded or other server errors |
| 503 | Service Unavailable | Unable to connect to Llama Stack backend |

---

## Available OpenResponses items

This section lists all available OpenResponses item types. All items have common attribute `type` that can be used to distinguish between them and infer their subsequent structure.

### message

One turn with `role` and `content` (string or list of content parts).

Message with simple string content:
```json
{ "input": [{ "type": "message", "role": "user", "content": "Hello" }] }
```

Message with complex input content (text/image/file).

```json
{
  "input": [{
    "type": "message",
    "role": "user",
    "content": [
      { "type": "input_text", "text": "Summarize this" },
      { "type": "input_image", "image_url": "https://example.com/img.png", "detail": "auto" },
      { "type": "input_file", "file_id": "file_abc", "filename": "doc.pdf" }
    ]
  }]
}
```
Message with complex output content (text/refusal).
```json
{
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "output_text", "text": "Here is a brief overview." },
    { "type": "refusal", "refusal": "I can't provide details on that part." }
  ]
}
```

### web_search_call

Completed web search (multi-turn).

```json
{ "input": [{ "type": "web_search_call", "id": "ws_1", "status": "completed" }] }
```

### file_search_call

Result of a file (vector) search tool call from a previous turn. Include this in the input when continuing a multi-turn conversation so the model sees the search queries, status, and optional result snippets that were returned.

```json
{
  "input": [{
    "type": "file_search_call",
    "id": "fs_1",
    "queries": ["error patterns"],
    "status": "completed",
    "results": [{ "file_id": "f_1", "filename": "app.log", "text": "Error at 42", "score": 0.95, "attributes": {} }]
  }]
}
```

### function_call

Function tool call from a previous turn. Include this in the input when continuing a multi-turn conversation so the model sees the function name, call ID, and arguments that were invoked.

```json
{ "input": [{ "type": "function_call", "call_id": "fc_1", "name": "get_weather", "arguments": "{\"city\": \"Boston\"}" }] }
```

### function_call_output

Output of a function call passed back to the model. Include this in the input when continuing a multi-turn conversation after the model issued a [function_call](#function_call) and the client has executed it; the model then sees the `call_id` and the tool’s `output` (and optional `id`, `status`).

```json
{ "input": [{ "type": "function_call_output", "call_id": "fc_1", "output": "72°F, partly cloudy" }] }
```

### mcp_call

Result of a Model Context Protocol (MCP) tool call from a previous turn. Include this in the input when continuing a multi-turn conversation so the model sees the server label, tool name, arguments, and optional output or error from the MCP server.

```json
{ "input": [{ "type": "mcp_call", "id": "mcp_1", "server_label": "my_server", "name": "fetch_data", "arguments": "{}", "output": "result" }] }
```

### mcp_list_tools

Result of listing tools from an MCP server in a previous turn. Include this in the input when continuing a multi-turn conversation so the model sees the server label and the list of available tools (names and input schemas) returned by the server.

```json
{ "input": [{ "type": "mcp_list_tools", "id": "mlt_1", "server_label": "my_server", "tools": [{ "name": "tool_a", "input_schema": {} }] }] }
```

### mcp_approval_request

A pending request for human approval of an MCP tool call. The model has asked to run a tool that requires approval; this item describes the tool name, server, and arguments so the client can prompt the user and then send an [mcp_approval_response](#mcp_approval_response).

```json
{ "input": [{ "type": "mcp_approval_request", "id": "mar_1", "name": "run_script", "server_label": "my_server", "arguments": "{}" }] }
```

### mcp_approval_response

User’s decision on an [mcp_approval_request](#mcp_approval_request): approve or deny the requested MCP tool call. Include this in the input for the next request so the model can continue or adjust its behavior based on the approval or denial (and optional reason).

```json
{ "input": [{ "type": "mcp_approval_response", "approval_request_id": "mar_1", "approve": true }] }
```
