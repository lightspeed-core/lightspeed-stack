# LCORE OpenResponses API Specification

This document describes the LCORE OpenResponses API specification, which provides a standardized interface for interacting with the Llama Stack Responses API. The LCORE specification inherits a subset of request and response attributes directly from the LLS (Llama Stack) OpenAPI specification while adding LCORE-specific extensions.

---

## Table of Contents

* [Introduction](#introduction)
* [Endpoint Overview](#endpoint-overview)
* [Request Specification](#request-specification)
  * [Inherited LLS OpenAPI Fields](#inherited-lls-openapi-fields)
  * [LCORE-Specific Extensions](#lcore-specific-extensions)
  * [Field Mappings](#field-mappings)
* [Response Specification](#response-specification)
  * [Inherited LLS OpenAPI Fields](#inherited-lls-openapi-fields-1)
  * [LCORE-Specific Extensions](#lcore-specific-extensions-1)
  * [Field Mappings](#field-mappings-1)
* [Streaming Support](#streaming-support)
* [Feature Parity](#feature-parity)
* [Known Limitations](#known-limitations)
* [Examples](#examples)
* [Error Handling](#error-handling)

---

## Introduction

The LCORE OpenResponses API (`/v1/responses`) provides a standardized interface for generating AI responses using the Llama Stack Responses API. This endpoint follows the LCORE specification, which:

* Inherits a subset of request/response attributes directly from the LLS OpenAPI specification
* Adds LCORE-specific extensions for enhanced functionality
* Maintains compatibility with OpenAI Responses API patterns
* Supports both streaming and non-streaming modes

The endpoint is designed to provide feature parity with existing streaming endpoints while offering a more direct interface to the underlying Responses API.

---

## Endpoint Overview

**Endpoint:** `POST /v1/responses`

**Authentication:** Required (Bearer token or API key)

**Content-Type:** `application/json`

**Response Format:** JSON (non-streaming) or Server-Sent Events (SSE) for streaming

---

## Request Specification

### Inherited LLS OpenAPI Fields

The following request attributes are inherited directly from the LLS OpenAPI specification and retain their original semantics:

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `input` | string | The input text to process | No |
| `model` | string | Model identifier in format `provider/model` (e.g., `openai/gpt-4-turbo`) | No |
| `conversation` | string | Conversation ID (accepts OpenAI `conv_*` format or LCORE hex UUID) | No |
| `include` | array[string] | Include parameter for response filtering | No |
| `instructions` | string | System instructions (maps from `system_prompt` in legacy format) | No |
| `max_infer_iters` | integer | Maximum inference iterations | No |
| `max_tool_calls` | integer | Maximum tool calls allowed | No |
| `metadata` | object | Metadata dictionary for request tracking | No |
| `parallel_tool_calls` | boolean | Enable parallel tool call execution | No |
| `previous_response_id` | string | ID of previous response for context | No |
| `prompt` | string | Prompt parameter | No |
| `store` | boolean | Whether to store the response in conversation history (default: `true`) | No |
| `stream` | boolean | Whether to stream the response (default: `false`) | No |
| `temperature` | float | Temperature parameter for response generation | No |
| `text` | string | Text parameter | No |
| `tool_choice` | string | Tool choice parameter (`None` maps from `no_tools` in legacy format) | No |
| `tools` | array[object] | List of tool configurations (includes vector_store_ids for RAG) | No |

### LCORE-Specific Extensions

The following fields are LCORE-specific and not part of the standard LLS OpenAPI specification:

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `generate_topic_summary` | boolean | Generate topic summary for new conversations | No |

### Field Mappings

The following mappings are applied when converting from legacy LCORE format to LLS OpenAPI format:

| Legacy LCORE Field | LLS OpenAPI Field | Notes |
|-------------------|-------------------|-------|
| `query` | `input` | Specific type of input item |
| `conversation_id` | `conversation` | Supports OpenAI `conv_*` format or LCORE hex UUID |
| `provider` + `model` | `model` | Concatenated as `provider/model` |
| `system_prompt` | `instructions` | Injected into instructions attribute |
| `attachments` | `input` items | Included as part of the response input |
| `no_tools` | `tool_choice` | Mapped to `tool_choice=None` |
| `vector_store_ids` | `tools` | Included in tools attribute as file_search tools |
| `generate_topic_summary` | N/A | Exposed directly (LCORE-specific) |

**Note:** The `media_type` attribute is not present in the LCORE specification, as downstream logic determines which format to process (structured `output` or textual `text` response attributes).

---

## Response Specification

### Inherited LLS OpenAPI Fields

The following response attributes are inherited directly from the LLS OpenAPI specification:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Response ID |
| `created_at` | integer | Creation timestamp (Unix timestamp) |
| `model` | string | Model identifier used |
| `status` | string | Response status (e.g., `completed`, `blocked`) |
| `output` | array[object] | Structured output items |
| `text` | string | Text output (plain text representation) |
| `error` | object | Error information (if any) |
| `temperature` | float | Temperature used |
| `previous_response_id` | string | Previous response ID |
| `prompt` | string | Prompt used |
| `top_p` | float | Top-p parameter used |
| `tools` | array[object] | Tools used |
| `tool_choice` | string | Tool choice used |
| `truncation` | string | Truncation strategy |
| `usage` | object | Token usage information (`prompt_tokens`, `completion_tokens`) |
| `instructions` | string | Instructions used |
| `max_tool_calls` | integer | Maximum tool calls |
| `metadata` | object | Metadata dictionary |
| `parallel_tool_calls` | boolean | Parallel tool calls flag |

### LCORE-Specific Extensions

The following fields are LCORE-specific and not part of the standard LLS OpenAPI specification:

| Field | Type | Description |
|-------|------|-------------|
| `conversation` | string | Conversation ID (exposed as `conversation`, linked internally to request conversation attribute) |
| `available_quotas` | object | Available quotas as measured by all configured quota limiters (LCORE-specific) |

### Field Mappings

The following mappings are applied when converting from LLS OpenAPI format to LCORE format:

| LLS OpenAPI Field | LCORE Field | Notes |
|-------------------|-------------|-------|
| `conversation_id` | `conversation` | Exposed as `conversation` in the LLS response; linked internally to request conversation attribute |
| `response` | `output` or `text` | Mapped to `output` (structured) or `text` (string) |
| `input_tokens` | `usage.prompt_tokens` | Token usage fields mapped to usage object |
| `output_tokens` | `usage.completion_tokens` | Token usage fields mapped to usage object |
| `tool_calls` | `output` items | Tool activity represented via dedicated output items |
| `tool_results` | `output` items | Tool results represented via dedicated output items |

**Deprecated Fields:** The following legacy fields are not exposed in the LCORE specification:
* `rag_chunks` - Replaced by `tool_results` in output (file_search_call type)
* `referenced_documents` - Part of output items
* `truncated` - Deprecated; `truncation` field indicates strategy, not actual truncation

---

## Streaming Support

The LCORE OpenResponses API supports streaming responses when the `stream` parameter is set to `true`. When streaming is enabled:

* The response is delivered using Server-Sent Events (SSE) format
* Events are streamed in real-time as they are generated
* The `conversation` attribute is added to the `response.created` event's data payload
* The `available_quotas` attribute is added to the `response.completed` event's data payload

**Streaming Event Types:**
* `response.created` - Initial response creation event (includes `conversation` attribute)
* `response.output_item.added` - New output item added
* `response.output_item.done` - Output item completed
* `response.output_text.delta` - Text delta chunk
* `response.output_text.done` - Text output completed
* `response.completed` - Response completion event (includes `available_quotas` attribute)

**Note:** Streaming support maintains feature parity with the existing `/v1/streaming_query` endpoint, with the addition of LCORE-specific fields (`conversation` and `available_quotas`) in streaming events.

---

## Feature Parity

The LCORE OpenResponses API (`/v1/responses`) maintains **full feature parity** with the existing streaming endpoints (`/v1/streaming_query` and `/v1/query`). This includes:

### Core Features
* ✅ **Conversation Management** - Automatic conversation creation and continuation
* ✅ **Multi-turn Conversations** - Support for conversation history and context
* ✅ **Tool Integration** - RAG (file_search), MCP tools, and function calls
* ✅ **Shield/Guardrails** - Content moderation and safety checks
* ✅ **Token Management** - Token consumption tracking and quota enforcement
* ✅ **Error Handling** - Comprehensive error handling with appropriate HTTP status codes
* ✅ **Authentication & Authorization** - Same authentication and authorization mechanisms

### Streaming Features
* ✅ **Server-Sent Events (SSE)** - Real-time streaming support
* ✅ **Event Types** - All standard streaming event types supported
* ✅ **LCORE Extensions** - `conversation` and `available_quotas` fields in streaming events
* ✅ **Error Streaming** - Error events streamed appropriately

### Additional LCORE Features
* ✅ **Direct API Access** - More direct interface to Responses API
* ✅ **LCORE Extensions** - `generate_topic_summary` and `available_quotas` support
* ✅ **Flexible Conversation IDs** - Support for both OpenAI and LCORE conversation ID formats

**Migration Path:** Existing clients using `/v1/query` or `/v1/streaming_query` can migrate to `/v1/responses` with minimal changes, as the core functionality remains the same.

---

## Known Limitations

### LLS OpenAPI Constraints

The following limitations exist due to LLS OpenAPI constraints:

1. **Limited Field Support**: Not all OpenAI Responses API fields are supported. Only the fields listed in the [Inherited LLS OpenAPI Fields](#inherited-lls-openapi-fields) section are available.

2. **Conversation Attribute**: The `conversation` attribute in responses is LCORE-specific and not directly supported by LLS OpenAPI spec yet. It is internally linked to the request's resolved conversation for proper conversation management.

3. **Output Format**: The response format is determined by downstream logic. The `media_type` attribute from legacy LCORE is not present, as the format is automatically determined based on the response structure.

4. **Tool Representation**: Tool activity is represented via dedicated output items rather than legacy `tool_calls` or `tool_results` fields. This follows the LLS OpenAPI specification.

### OpenAI Responses API Differences

The following differences exist compared to the standard OpenAI Responses API:

1. **Conversation ID Format**: Supports both OpenAI format (`conv_*`) and LCORE hex UUID format, with automatic conversion.

2. **LCORE Extensions**: Includes LCORE-specific fields (`generate_topic_summary`, `available_quotas`) that are not part of the OpenAI specification.

3. **Tool Configuration**: Vector store IDs are included in the `tools` attribute as file_search tools, rather than as a separate parameter.

4. **Response Structure**: Some fields may be structured differently to accommodate LCORE-specific requirements.

### Streaming Limitations

1. **Event Enrichment**: Streaming SSEs are enriched with LCORE-specific fields (`conversation`, `available_quotas`) that may not be present in standard OpenAI streaming responses.

2. **Event Timing**: The `conversation` attribute is added to `response.created` event, and `available_quotas` is added to `response.completed` event, which may differ from standard OpenAI behavior.

---

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
  "created_at": 1704067200,
  "model": "openai/gpt-4-turbo",
  "status": "completed",
  "text": "Kubernetes is an open-source container orchestration system...",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": "Kubernetes is an open-source container orchestration system..."
    }
  ],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50
  },
  "conversation": "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
  "available_quotas": {
    "daily": 1000,
    "monthly": 50000
  }
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
    "conversation": "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
    "store": true,
    "stream": false
  }'
```

### Request with Tools (RAG)

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
        "vector_store_ids": ["vs_abc123", "vs_def456"],
        "max_num_results": 10
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
```
event: response.created
data: {"id":"resp_abc123","conversation":"conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"}

event: response.output_text.delta
data: {"delta":"Kubernetes"}

event: response.output_text.delta
data: {"delta":" is"}

event: response.output_text.delta
data: {"delta":" an"}

...

event: response.completed
data: {"usage":{"prompt_tokens":100,"completion_tokens":50},"available_quotas":{"daily":1000,"monthly":50000}}
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

**Error Response Format:**
```json
{
  "detail": {
    "response": "Error message summary",
    "cause": "Detailed error explanation"
  }
}
```

**Example Error Response:**
```json
{
  "detail": {
    "response": "Conversation not found",
    "cause": "Conversation with ID conv_abc123 does not exist"
  }
}
```

---

## Additional Notes

### Conversation ID Formats

The endpoint accepts conversation IDs in two formats:
1. **OpenAI Format**: `conv_<48-character-hex-string>` (e.g., `conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e`)
2. **LCORE Format**: `<48-character-hex-string>` (e.g., `0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e`)

Both formats are automatically converted internally to the Llama Stack format for API calls.

### Topic Summary Generation

When `generate_topic_summary` is set to `true` and a new conversation is created, the endpoint automatically generates a topic summary for the conversation. This summary is stored in the conversation metadata and can be retrieved via the conversations API.

### Quota Management

The `available_quotas` field in the response provides real-time quota information from all configured quota limiters. This allows clients to track remaining quota and adjust behavior accordingly.

---

## Related Documentation

* [Conversations API Guide](./conversations_api.md) - Detailed information about conversation management
* [Query Endpoint Documentation](./openapi.md) - Legacy query endpoint documentation
* [Streaming Query Endpoint](./streaming_query_endpoint.puml) - Streaming endpoint architecture
* [Architecture Documentation](./ARCHITECTURE.md) - Overall system architecture

---

## Version History

* **v1.0.0** (2026-02-09): Initial LCORE OpenResponses API specification
  * Support for non-streaming and streaming modes
  * LCORE-specific extensions (`generate_topic_summary`, `available_quotas`)
  * Full feature parity with existing query endpoints
