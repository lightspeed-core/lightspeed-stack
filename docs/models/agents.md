# Lightspeed Core Stack



## 🌍 Base URL


| URL | Description |
|-----|-------------|


# 🛠️ APIs

---

# 📋 Components



## EndEventData


Nested data for event: "end".


| Field | Type | Description |
|-------|------|-------------|
| referenced_documents | array |  |
| truncated | boolean |  |
| input_tokens | integer |  |
| output_tokens | integer |  |


## EndStreamPayload


SSE end-of-stream body (includes available_quotas beside data).


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |
| available_quotas | object |  |


## ErrorEventData


Payload for event: "error".


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| response | string |  |
| cause | string |  |


## ErrorStreamPayload


SSE error event body (event + typed data).


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |


## InterruptedEventData


Payload for event: "interrupted".


| Field | Type | Description |
|-------|------|-------------|
| request_id | string |  |


## InterruptedStreamPayload


SSE interrupted stream body.


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |


## ReferencedDocument


Model representing a document referenced in generating a response.

Attributes:
    doc_url: Url to the referenced doc.
    doc_title: Title of the referenced doc.
    document_id: Document ID for preserving identity during deduplication.


| Field | Type | Description |
|-------|------|-------------|
| doc_url | string | URL of the referenced document |
| doc_title | string | Title of the referenced document |
| source | string | Index name identifying the knowledge source from configuration |
| document_id | string | Document ID for preserving identity during deduplication |


## StartEventData


Payload for event: "start".


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| request_id | string |  |


## StartStreamPayload


SSE stream start body.


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |


## StreamPayloadBase


Base for streaming SSE JSON payloads.




## TokenChunkData


Structured data for token and turn-complete stream lines.


| Field | Type | Description |
|-------|------|-------------|
| id | integer |  |
| token | string |  |


## TokenStreamPayload


SSE token delta (event: "token").


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |


## ToolCallStreamPayload


SSE tool call summary.


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |


## ToolCallSummary


Model representing a tool call made during response generation (for tool_calls list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call |
| name | string | Name of the tool called |
| args | object | Arguments passed to the tool |
| type | string | Type indicator for tool call |


## ToolResultStreamPayload


SSE tool result summary.


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |


## ToolResultSummary


Model representing a result from a tool call (for tool_results list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call/result, matches the corresponding tool call 'id' |
| status | string | Status of the tool execution (e.g., 'success') |
| content | string | Content/result returned from the tool |
| type | string | Type indicator for tool result |
| round | integer | Round number or step of tool execution |


## TurnCompleteStreamPayload


SSE turn completion (same data shape as token).


| Field | Type | Description |
|-------|------|-------------|
| event | string |  |
| data |  |  |
