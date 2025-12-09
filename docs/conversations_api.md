# Conversations API Guide

This document explains how the Conversations API works with the Responses API in Lightspeed Core Stack (LCS). You will learn:

* How conversation management works with the Responses API
* Conversation ID formats and normalization
* How to interact with conversations via REST API and CLI
* Database storage and retrieval of conversations

---

## Table of Contents

* [Introduction](#introduction)
* [Conversation ID Formats](#conversation-id-formats)
   * [Llama Stack Format](#llama-stack-format)
   * [Normalized Format](#normalized-format)
   * [ID Conversion Utilities](#id-conversion-utilities)
* [How Conversations Work](#how-conversations-work)
   * [Creating New Conversations](#creating-new-conversations)
   * [Continuing Existing Conversations](#continuing-existing-conversations)
   * [Conversation Storage](#conversation-storage)
* [API Endpoints](#api-endpoints)
   * [Query Endpoint (v1)](#query-endpoint-v1)
   * [Streaming Query Endpoint (v1)](#streaming-query-endpoint-v1)
   * [Conversations List Endpoint (v1)](#conversations-list-endpoint-v1)
   * [Conversation Detail Endpoint (v1)](#conversation-detail-endpoint-v1)
* [Testing with curl](#testing-with-curl)
* [Database Schema](#database-schema)
* [Troubleshooting](#troubleshooting)

---

## Introduction

Lightspeed Core Stack uses the **OpenAI Responses API** (`client.responses.create()`) for generating chat completions with conversation persistence. The Responses API provides:

* Automatic conversation management with `store=True`
* Multi-turn conversation support
* Tool integration (RAG, MCP, function calls)
* Shield/guardrails support

Conversations are stored in two locations:
1. **Llama Stack database** (`openai_conversations` and `conversation_items` tables in `public` schema)
2. **Lightspeed Stack database** (`user_conversation` table in `lightspeed-stack` schema)

> [!NOTE]
> The Responses API replaced the older Agent API (`client.agents.create_turn()`) for better OpenAI compatibility and improved conversation management.

---

## Conversation ID Formats

### Llama Stack Format

When Llama Stack creates a conversation, it generates an ID in the format:

```
conv_<48-character-hex-string>
```

**Example:**
```
conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e
```

This is the format used internally by Llama Stack and must be used when calling Llama Stack APIs.

### Normalized Format

Lightspeed Stack normalizes conversation IDs by removing the `conv_` prefix before:
* Storing in the database
* Returning to API clients
* Displaying in CLI tools

**Example normalized ID:**
```
0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e
```

This 48-character format is what users see and work with.

### ID Conversion Utilities

LCS provides utilities in `src/utils/suid.py` for ID conversion:

```python
from utils.suid import normalize_conversation_id, to_llama_stack_conversation_id

# Convert from Llama Stack format to normalized format
normalized_id = normalize_conversation_id("conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e")
# Returns: "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"

# Convert from normalized format to Llama Stack format
llama_stack_id = to_llama_stack_conversation_id("0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e")
# Returns: "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"
```

---

## How Conversations Work

### Creating New Conversations

When a user makes a query **without** providing a `conversation_id`:

1. LCS creates a new conversation using `client.conversations.create(metadata={})`
2. Llama Stack returns a conversation ID (e.g., `conv_abc123...`)
3. LCS normalizes the ID and stores it in the database
4. The query is sent to `client.responses.create()` with the conversation ID
5. The normalized ID is returned to the client

**Code flow (from `src/app/endpoints/query_v2.py`):**

```python
# No conversation_id provided - create a new conversation first
conversation = await client.conversations.create(metadata={})
llama_stack_conv_id = conversation.id
# Store the normalized version
conversation_id = normalize_conversation_id(llama_stack_conv_id)

# Use the conversation in responses.create()
response = await client.responses.create(
    input=input_text,
    model=model_id,
    instructions=system_prompt,
    store=True,
    conversation=llama_stack_conv_id,  # Use Llama Stack format
    # ... other parameters
)
```

### Continuing Existing Conversations

When a user provides an existing `conversation_id`:

1. LCS receives the normalized ID (e.g., `0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e`)
2. Converts it to Llama Stack format (adds `conv_` prefix)
3. Sends the query to `client.responses.create()` with the existing conversation ID
4. Llama Stack retrieves the conversation history and continues the conversation
5. The conversation history is automatically included in the LLM context

**Code flow:**

```python
# Conversation ID was provided - convert to llama-stack format
conversation_id = query_request.conversation_id
llama_stack_conv_id = to_llama_stack_conversation_id(conversation_id)

# Use the existing conversation
response = await client.responses.create(
    input=input_text,
    model=model_id,
    conversation=llama_stack_conv_id,  # Existing conversation
    # ... other parameters
)
```

### Conversation Storage

Conversations are stored in **two databases**:

#### 1. Llama Stack Database (PostgreSQL `public` schema)

**Tables:**
- `openai_conversations`: Stores conversation metadata
- `conversation_items`: Stores individual messages/turns in conversations

**Configuration (in `config/llama_stack_client_config.yaml`):**
```yaml
storage:
  stores:
    conversations:
      table_name: openai_conversations
      backend: sql_default
```

#### 2. Lightspeed Stack Database (PostgreSQL `lightspeed-stack` schema)

**Table:** `user_conversation`

Stores user-specific metadata:
- Conversation ID (normalized, without `conv_` prefix)
- User ID
- Last used model and provider
- Creation and last message timestamps
- Message count
- Topic summary

---

## API Endpoints

### Query Endpoint (v1)

**Endpoint:** `POST /v1/query`

**Request:**
```json
{
  "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
  "query": "What is the OpenShift Assisted Installer?",
  "model": "models/gemini-2.0-flash",
  "provider": "gemini"
}
```

**Response:**
```json
{
  "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
  "response": "The OpenShift Assisted Installer is...",
  "rag_chunks": [],
  "tool_calls": [],
  "referenced_documents": [],
  "truncated": false,
  "input_tokens": 150,
  "output_tokens": 200,
  "available_quotas": {}
}
```

> [!NOTE]
> If `conversation_id` is omitted, a new conversation is automatically created and the new ID is returned in the response.

### Streaming Query Endpoint (v1)

**Endpoint:** `POST /v1/streaming_query`

**Request:** Same as `/v1/query`

**Response:** Server-Sent Events (SSE) stream

```
data: {"event": "start", "data": {"conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"}}

data: {"event": "token", "data": {"id": 0, "token": "The "}}

data: {"event": "token", "data": {"id": 1, "token": "OpenShift "}}

data: {"event": "turn_complete", "data": {"id": 10, "token": "The OpenShift Assisted Installer is..."}}

data: {"event": "end", "data": {"referenced_documents": [], "input_tokens": 150, "output_tokens": 200}}
```

### Conversations List Endpoint (v1)

**Endpoint:** `GET /v1/conversations`

**Response:**
```json
{
  "conversations": [
    {
      "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
      "created_at": "2025-11-24T10:30:00Z",
      "last_message_at": "2025-11-24T10:35:00Z",
      "message_count": 5,
      "last_used_model": "gemini-2.0-flash-exp",
      "last_used_provider": "google",
      "topic_summary": "OpenShift Assisted Installer discussion"
    }
  ]
}
```

### Conversation Detail Endpoint (v1)

**Endpoint:** `GET /v1/conversations/{conversation_id}`

**Response:**
```json
{
  "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
  "created_at": "2025-11-24T10:30:00Z",
  "chat_history": [
    {
      "started_at": "2025-11-24T10:30:00Z",
      "messages": [
        {
          "type": "user",
          "content": "What is the OpenShift Assisted Installer?"
        },
        {
          "type": "assistant",
          "content": "The OpenShift Assisted Installer is..."
        }
      ]
    }
  ]
}
```

---

## Testing with curl

You can test the Conversations API endpoints using `curl`. The examples below assume the server is running on `localhost:8090`.

First, set your authorization token:

```bash
export TOKEN="<your-token>"
```

### Non-Streaming Query (New Conversation)

To start a new conversation, omit the `conversation_id` field:

```bash
curl -X POST http://localhost:8090/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "What is the OpenShift Assisted Installer?",
    "model": "models/gemini-2.0-flash",
    "provider": "gemini"
  }'
```

**Response:**
```json
{
  "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
  "response": "The OpenShift Assisted Installer is...",
  "rag_chunks": [],
  "tool_calls": [],
  "referenced_documents": [],
  "truncated": false,
  "input_tokens": 150,
  "output_tokens": 200,
  "available_quotas": {}
}
```

### Non-Streaming Query (Continue Conversation)

To continue an existing conversation, include the `conversation_id` from a previous response:

```bash
curl -X POST http://localhost:8090/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
    "query": "How do I install it?",
    "model": "models/gemini-2.0-flash",
    "provider": "gemini"
  }'
```

### Streaming Query (New Conversation)

For streaming responses, use the `/v1/streaming_query` endpoint. The response is returned as Server-Sent Events (SSE):

```bash
curl -X POST http://localhost:8090/v1/streaming_query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -d '{
    "query": "What is the OpenShift Assisted Installer?",
    "model": "models/gemini-2.0-flash",
    "provider": "gemini"
  }'
```

**Response (SSE stream):**
```
data: {"event": "start", "data": {"conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"}}

data: {"event": "token", "data": {"id": 0, "token": "The "}}

data: {"event": "token", "data": {"id": 1, "token": "OpenShift "}}

data: {"event": "turn_complete", "data": {"id": 10, "token": "The OpenShift Assisted Installer is..."}}

data: {"event": "end", "data": {"referenced_documents": [], "input_tokens": 150, "output_tokens": 200}}
```

### Streaming Query (Continue Conversation)

```bash
curl -X POST http://localhost:8090/v1/streaming_query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -d '{
    "conversation_id": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
    "query": "Can you explain the prerequisites?",
    "model": "models/gemini-2.0-flash",
    "provider": "gemini"
  }'
```

### List Conversations

```bash
curl -X GET http://localhost:8090/v1/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### Get Conversation Details

```bash
curl -X GET http://localhost:8090/v1/conversations/0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Database Schema

### Lightspeed Stack Schema

**Table:** `lightspeed-stack.user_conversation`

```sql
CREATE TABLE "lightspeed-stack".user_conversation (
    id VARCHAR PRIMARY KEY,              -- Normalized conversation ID (48 chars)
    user_id VARCHAR NOT NULL,            -- User identifier
    last_used_model VARCHAR NOT NULL,    -- Model name (e.g., "gemini-2.0-flash-exp")
    last_used_provider VARCHAR NOT NULL, -- Provider (e.g., "google")
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    topic_summary VARCHAR DEFAULT ''
);

CREATE INDEX idx_user_conversation_user_id ON "lightspeed-stack".user_conversation(user_id);
```

> [!NOTE]
> The `id` column uses `VARCHAR` without a length limit, which PostgreSQL treats similarly to `TEXT`. This accommodates the 48-character normalized conversation IDs.

### Llama Stack Schema

**Table:** `public.openai_conversations`

```sql
CREATE TABLE public.openai_conversations (
    id VARCHAR(64) PRIMARY KEY,          -- Full ID with conv_ prefix (53 chars)
    created_at TIMESTAMP,
    metadata JSONB
);
```

**Table:** `public.conversation_items`

```sql
CREATE TABLE public.conversation_items (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) REFERENCES openai_conversations(id),
    turn_number INTEGER,
    content JSONB,
    created_at TIMESTAMP
);
```

---

## Troubleshooting

### Conversation Not Found Error

**Symptom:**
```
Error: Conversation not found (HTTP 404)
```

**Possible Causes:**
1. Conversation ID was truncated (should be 48 characters, not 41)
2. Conversation ID has incorrect prefix (should NOT include `conv_` when calling LCS API)
3. Conversation was deleted
4. Database connection issue

**Solution:**
- Verify the conversation ID is exactly 48 characters
- Ensure you're using the normalized ID format (without `conv_` prefix) when calling LCS endpoints
- Check database connectivity

### Model/Provider Changes Not Persisting

**Symptom:**
The `last_used_model` and `last_used_provider` fields don't update when using a different model.

**Explanation:**
This is expected behavior. The Responses API v2 allows you to change the model/provider for each query within the same conversation. The `last_used_model` field only tracks the most recently used model for display purposes in the conversation list.

### Empty Conversation History

**Symptom:**
Calling `/v1/conversations/{conversation_id}` returns empty `chat_history`.

**Possible Causes:**
1. The conversation was just created and has no messages yet
2. The conversation exists in Lightspeed DB but not in Llama Stack DB (data inconsistency)
3. Database connection to Llama Stack is failing

**Solution:**
- Verify the conversation has messages by checking `message_count`
- Check Llama Stack database connectivity
- Verify `openai_conversations` and `conversation_items` tables exist and are accessible

---

## References

- [OpenAI Responses API Documentation](https://platform.openai.com/docs/api-reference/responses)
- [Llama Stack Documentation](https://github.com/meta-llama/llama-stack)
- [LCS Configuration Guide](./config.md)
- [LCS Getting Started Guide](./getting_started.md)
