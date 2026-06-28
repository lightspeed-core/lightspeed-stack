# Lightspeed Core Stack




---

# 📋 Schemas for common models



## Attachment


Model representing an attachment that can be sent from the UI as part of query.

A list of attachments can be an optional part of 'query' request.

Attributes:
    attachment_type: The attachment type, like "log", "configuration" etc.
    content_type: The content type as defined in MIME standard
    content: The actual attachment content


| Field | Type | Description |
|-------|------|-------------|
| attachment_type | string | The attachment type, like 'log', 'configuration' etc. |
| content_type | string | The content type as defined in MIME standard |
| content | string | The actual attachment content |


## ConversationData


Model representing conversation data returned by cache list operations.

Attributes:
    conversation_id: The conversation ID
    topic_summary: The topic summary for the conversation (can be None)
    last_message_timestamp: The timestamp of the last message in the conversation


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| topic_summary | string |  |
| last_message_timestamp | number |  |


## ConversationDetails


Model representing the details of a user conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    created_at: When the conversation was created.
    last_message_at: When the last message was sent.
    message_count: Number of user messages in the conversation.
    last_used_model: The last model used for the conversation.
    last_used_provider: The provider of the last used model.
    topic_summary: The topic summary for the conversation.

Example:
    ```python
    conversation = ConversationDetails(
        conversation_id="123e4567-e89b-12d3-a456-426614174000",
        created_at="2024-01-01T00:00:00Z",
        last_message_at="2024-01-01T00:05:00Z",
        message_count=5,
        last_used_model="gemini/gemini-2.0-flash",
        last_used_provider="gemini",
        topic_summary="Openshift Microservices Deployment Strategies",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | Conversation ID (UUID) |
| created_at | string | When the conversation was created |
| last_message_at | string | When the last message was sent |
| message_count | integer | Number of user messages in the conversation |
| last_used_model | string | Identification of the last model used for the conversation |
| last_used_provider | string | Identification of the last provider used for the conversation |
| topic_summary | string | Topic summary for the conversation |


## ConversationTurn


Model representing a single conversation turn.

Attributes:
    messages: List of messages in this turn.
    tool_calls: List of tool calls made in this turn.
    tool_results: List of tool results from this turn.
    provider: Provider identifier used for this turn.
    model: Model identifier used for this turn.
    started_at: ISO 8601 timestamp when the turn started.
    completed_at: ISO 8601 timestamp when the turn completed.


| Field | Type | Description |
|-------|------|-------------|
| messages | array | List of messages in this turn |
| tool_calls | array | List of tool calls made in this turn |
| tool_results | array | List of tool results from this turn |
| provider | string | Provider identifier used for this turn |
| model | string | Model identifier used for this turn |
| started_at | string | ISO 8601 timestamp when the turn started |
| completed_at | string | ISO 8601 timestamp when the turn completed |


## MCPListToolsSummary


Model representing MCP list tools payload serialized into tool results.


| Field | Type | Description |
|-------|------|-------------|
| server_label | string | MCP server label associated with the tool list |
| tools | array | Tools exposed by the MCP server |


## MCPListToolsTool


Tool definition returned by MCP list tools operation.

:param input_schema: JSON schema defining the tool's input parameters
:param name: Name of the tool
:param description: (Optional) Description of what the tool does


| Field | Type | Description |
|-------|------|-------------|
| input_schema | object |  |
| name | string |  |
| description | string |  |


## MCPServerAuthInfo


Information about MCP server client authentication options.


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name |
| client_auth_headers | array | List of authentication header names for client-provided tokens |


## MCPServerInfo


Information about a registered MCP server.

Attributes:
    name: Unique name of the MCP server.
    url: URL of the MCP server endpoint.
    provider_id: MCP provider identification.
    source: Whether the server was registered statically (config) or dynamically (api).


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name |
| url | string | MCP server URL |
| provider_id | string | MCP provider identification |
| source | string | How the server was registered: 'config' (static) or 'api' (dynamic) |


## Message


Model representing a message in a conversation turn.

Attributes:
    content: The message content.
    type: The type of message.
    referenced_documents: Optional list of documents referenced in an assistant response.


| Field | Type | Description |
|-------|------|-------------|
| content | string | The message content |
| type | string | The type of message |
| referenced_documents | array | List of documents referenced in the response (assistant messages only) |


## OpenAIResponseAnnotationCitation


URL citation annotation for referencing external web resources.

:param type: Annotation type identifier, always "url_citation"
:param end_index: End position of the citation span in the content
:param start_index: Start position of the citation span in the content
:param title: Title of the referenced web resource
:param url: URL of the referenced web resource


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| end_index | integer |  |
| start_index | integer |  |
| title | string |  |
| url | string |  |


## OpenAIResponseAnnotationContainerFileCitation



| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| container_id | string |  |
| end_index | integer |  |
| file_id | string |  |
| filename | string |  |
| start_index | integer |  |


## OpenAIResponseAnnotationFileCitation


File citation annotation for referencing specific files in response content.

:param type: Annotation type identifier, always "file_citation"
:param file_id: Unique identifier of the referenced file
:param filename: Name of the referenced file
:param index: Position index of the citation within the content


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| file_id | string |  |
| filename | string |  |
| index | integer |  |


## OpenAIResponseAnnotationFilePath



| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| file_id | string |  |
| index | integer |  |


## OpenAIResponseContentPartRefusal


Refusal content within a streamed response part.

:param type: Content part type identifier, always "refusal"
:param refusal: Refusal text supplied by the model


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| refusal | string |  |


## OpenAIResponseInputMessageContentFile


File content for input messages in OpenAI response format.

:param type: The type of the input item. Always `input_file`.
:param file_data: The data of the file to be sent to the model.
:param file_id: (Optional) The ID of the file to be sent to the model.
:param file_url: The URL of the file to be sent to the model.
:param filename: The name of the file to be sent to the model.


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| file_data | string |  |
| file_id | string |  |
| file_url | string |  |
| filename | string |  |


## OpenAIResponseInputMessageContentImage


Image content for input messages in OpenAI response format.

:param detail: Level of detail for image processing, can be "low", "high", or "auto"
:param type: Content type identifier, always "input_image"
:param file_id: (Optional) The ID of the file to be sent to the model.
:param image_url: (Optional) URL of the image content


| Field | Type | Description |
|-------|------|-------------|
| detail |  |  |
| type | string |  |
| file_id | string |  |
| image_url | string |  |


## OpenAIResponseInputMessageContentText


Text content for input messages in OpenAI response format.

:param text: The text content of the input message
:param type: Content type identifier, always "input_text"


| Field | Type | Description |
|-------|------|-------------|
| text | string |  |
| type | string |  |


## OpenAIResponseMCPApprovalRequest


A request for human approval of a tool invocation.


| Field | Type | Description |
|-------|------|-------------|
| arguments | string |  |
| id | string |  |
| name | string |  |
| server_label | string |  |
| type | string |  |


## OpenAIResponseMessage


Corresponds to the various Message types in the Responses API.
They are all under one type because the Responses API gives them all
the same "type" value, and there is no way to tell them apart in certain
scenarios.


| Field | Type | Description |
|-------|------|-------------|
| content |  |  |
| role |  |  |
| type | string |  |
| id | string |  |
| status | string |  |


## OpenAIResponseOutputMessageContentOutputText



| Field | Type | Description |
|-------|------|-------------|
| text | string |  |
| type | string |  |
| annotations | array |  |
| logprobs | array |  |


## OpenAIResponseOutputMessageFileSearchToolCall


File search tool call output message for OpenAI responses.

:param id: Unique identifier for this tool call
:param queries: List of search queries executed
:param status: Current status of the file search operation
:param type: Tool call type identifier, always "file_search_call"
:param results: (Optional) Search results returned by the file search operation


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| queries | array |  |
| status | string |  |
| type | string |  |
| results | array |  |


## OpenAIResponseOutputMessageFileSearchToolCallResults


Search results returned by the file search operation.

:param attributes: (Optional) Key-value attributes associated with the file
:param file_id: Unique identifier of the file containing the result
:param filename: Name of the file containing the result
:param score: Relevance score for this search result (between 0 and 1)
:param text: Text content of the search result


| Field | Type | Description |
|-------|------|-------------|
| attributes | object |  |
| file_id | string |  |
| filename | string |  |
| score | number |  |
| text | string |  |


## OpenAIResponseOutputMessageFunctionToolCall


Function tool call output message for OpenAI responses.

:param call_id: Unique identifier for the function call
:param name: Name of the function being called
:param arguments: JSON string containing the function arguments
:param type: Tool call type identifier, always "function_call"
:param id: (Optional) Additional identifier for the tool call
:param status: (Optional) Current status of the function call execution


| Field | Type | Description |
|-------|------|-------------|
| call_id | string |  |
| name | string |  |
| arguments | string |  |
| type | string |  |
| id | string |  |
| status | string |  |


## OpenAIResponseOutputMessageMCPCall


Model Context Protocol (MCP) call output message for OpenAI responses.

:param id: Unique identifier for this MCP call
:param type: Tool call type identifier, always "mcp_call"
:param arguments: JSON string containing the MCP call arguments
:param name: Name of the MCP method being called
:param server_label: Label identifying the MCP server handling the call
:param error: (Optional) Error message if the MCP call failed
:param output: (Optional) Output result from the successful MCP call


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| type | string |  |
| arguments | string |  |
| name | string |  |
| server_label | string |  |
| error | string |  |
| output | string |  |


## OpenAIResponseOutputMessageMCPListTools


MCP list tools output message containing available tools from an MCP server.

:param id: Unique identifier for this MCP list tools operation
:param type: Tool call type identifier, always "mcp_list_tools"
:param server_label: Label identifying the MCP server providing the tools
:param tools: List of available tools provided by the MCP server


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| type | string |  |
| server_label | string |  |
| tools | array |  |


## OpenAIResponseOutputMessageWebSearchToolCall


Web search tool call output message for OpenAI responses.

:param id: Unique identifier for this tool call
:param status: Current status of the web search operation
:param type: Tool call type identifier, always "web_search_call"


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| status | string |  |
| type | string |  |


## OpenAITokenLogProb


The log probability for a token from an OpenAI-compatible chat completion response.


| Field | Type | Description |
|-------|------|-------------|
| token | string | The token. |
| bytes | array | The bytes for the token. |
| logprob | number | The log probability of the token. |
| top_logprobs | array | The top log probabilities for the token. |


## OpenAITopLogProb


The top log probability for a token from an OpenAI-compatible chat completion response.


| Field | Type | Description |
|-------|------|-------------|
| token | string | The token. |
| bytes | array | The bytes for the token. |
| logprob | number | The log probability of the token. |


## ProviderHealthStatus


Model representing the health status of a provider.

Attributes:
    provider_id: The ID of the provider.
    status: The health status ('ok', 'unhealthy', 'not_implemented').
    message: Optional message about the health status.


| Field | Type | Description |
|-------|------|-------------|
| provider_id | string | The ID of the provider |
| status | string | The health status |
| message | string | Optional message about the health status |


## RAGChunk


Model representing a RAG chunk used in the response.


| Field | Type | Description |
|-------|------|-------------|
| content | string | The content of the chunk |
| source | string | Index name identifying the knowledge source from configuration |
| score | number | Relevance score |
| attributes | object | Document metadata from the RAG provider (e.g., url, title, author) |


## RAGContext


Result of building RAG context from all enabled pre-query RAG sources.

Attributes:
    context_text: Formatted RAG context string for injection into the query.
    rag_chunks: RAG chunks from pre-query sources (BYOK + Solr).
    referenced_documents: Referenced documents from pre-query sources.


| Field | Type | Description |
|-------|------|-------------|
| context_text | string | Formatted context for injection |
| rag_chunks | array | RAG chunks from pre-query sources |
| referenced_documents | array | Documents from pre-query sources |


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


## ShieldModerationBlocked


Shield moderation blocked the content; refusal details are present.


| Field | Type | Description |
|-------|------|-------------|
| decision | string |  |
| message | string |  |
| moderation_id | string |  |
| refusal_response |  |  |


## ShieldModerationPassed


Shield moderation passed; no refusal.


| Field | Type | Description |
|-------|------|-------------|
| decision | string |  |


## SolrVectorSearchRequest


LCORE Solr inline RAG options for vector_io.query (mode and provider filters).

Attributes:
    mode: Solr vector_io search mode. When omitted, the server default (hybrid) is used.
    filters: Solr provider filter payload passed through as params['solr'].

Legacy clients may send a plain JSON object with filter keys only;
that object is accepted as filters with mode unset (server default applies).


| Field | Type | Description |
|-------|------|-------------|
| mode | string | Solr vector_io search mode. When omitted, the server default ('hybrid') is used. |
| filters | object | Solr provider filter payload passed through as params['solr']. Supports structured metadata filters (eq, ne, in, nin comparison operators). Legacy filter-only objects (e.g. fq) are still accepted. |


## TokenCounter


Model representing token counter.

Attributes:
    input_tokens: number of tokens sent to LLM
    output_tokens: number of tokens received from LLM
    input_tokens_counted: number of input tokens counted by the handler
    llm_calls: number of LLM calls


| Field | Type | Description |
|-------|------|-------------|
| input_tokens | integer |  |
| output_tokens | integer |  |
| input_tokens_counted | integer |  |
| llm_calls | integer |  |


## ToolCallSummary


Model representing a tool call made during response generation (for tool_calls list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call |
| name | string | Name of the tool called |
| args | object | Arguments passed to the tool |
| type | string | Type indicator for tool call |


## ToolInfoSummary


Model representing metadata for a single tool exposed by MCP list tools.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Tool name |
| description | string | Human-readable tool description |
| input_schema | object | JSON schema for the tool input |


## ToolResultSummary


Model representing a result from a tool call (for tool_results list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call/result, matches the corresponding tool call 'id' |
| status | string | Status of the tool execution (e.g., 'success') |
| content | string | Content/result returned from the tool |
| type | string | Type indicator for tool result |
| round | integer | Round number or step of tool execution |


## Transcript


Model representing a transcript entry to be stored.


| Field | Type | Description |
|-------|------|-------------|
| metadata |  |  |
| redacted_query | string |  |
| query_is_valid | boolean |  |
| llm_response | string |  |
| rag_chunks | array |  |
| truncated | boolean |  |
| attachments | array |  |
| tool_calls | array |  |
| tool_results | array |  |


## TranscriptMetadata


Metadata for a transcript entry.


| Field | Type | Description |
|-------|------|-------------|
| provider | string |  |
| model | string |  |
| query_provider | string |  |
| query_model | string |  |
| user_id | string |  |
| conversation_id | string |  |
| timestamp | string |  |


## TurnSummary


Summary of a turn in llama stack.


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the response |
| llm_response | string |  |
| tool_calls | array |  |
| tool_results | array |  |
| rag_chunks | array |  |
| referenced_documents | array |  |
| token_usage |  |  |
| output_items | array | Structured response output items, captured for compacted-mode turn persistence (LCORE-1572). Empty on the non-compacted path. |
