# Lightspeed Core Stack


---

# 📋 Schemas for requests models

## AllowedToolsFilter


Filter configuration for restricting which MCP tools can be used.

:param tool_names: (Optional) List of specific tool names that are allowed


| Field | Type | Description |
|-------|------|-------------|
| tool_names | array |  |


## ApprovalFilter


Filter configuration for MCP tool approval requirements.

:param always: (Optional) List of tool names that always require approval
:param never: (Optional) List of tool names that never require approval


| Field | Type | Description |
|-------|------|-------------|
| always | array |  |
| never | array |  |


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


## ConversationUpdateRequest


Model representing a request to update a conversation topic summary.

Attributes:
    topic_summary: The new topic summary for the conversation.


| Field | Type | Description |
|-------|------|-------------|
| topic_summary | string | The new topic summary for the conversation |


## FeedbackCategory


Enum representing predefined feedback categories for AI responses.

These categories help provide structured feedback about AI inference quality
when users provide negative feedback (thumbs down). Multiple categories can
be selected to provide comprehensive feedback about response issues.




## FeedbackRequest


Model representing a feedback request.

Attributes:
    conversation_id: The required conversation ID (UUID).
    user_question: The required user question.
    llm_response: The required LLM response.
    sentiment: The optional sentiment.
    user_feedback: The optional user feedback.
    categories: The optional list of feedback categories (multi-select for negative feedback).


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | The required conversation ID (UUID) |
| user_question | string | User question (the query string) |
| llm_response | string | Response from LLM |
| sentiment | integer | User sentiment, if provided must be -1 or 1 |
| user_feedback | string | Feedback on the LLM response. |
| categories | array | List of feedback categories that describe issues with the LLM response (for negative feedback). |


## FeedbackStatusUpdateRequest


Model representing a feedback status update request.

Attributes:
    status: Value of the desired feedback enabled state.


| Field | Type | Description |
|-------|------|-------------|
| status | boolean | Desired state of feedback enablement, must be False or True |


## IncludeParameter





## InputToolMCP


MCP input tool with authorization included when serializing request bodies.


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| server_label | string |  |
| connector_id | string |  |
| server_url | string |  |
| headers | object |  |
| authorization | string |  |
| require_approval |  |  |
| allowed_tools |  |  |


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


## MCPServerRegistrationRequest


Request model for dynamically registering an MCP server.

Attributes:
    name: Unique name for the MCP server.
    url: URL of the MCP server endpoint.
    provider_id: MCP provider identification (defaults to "model-context-protocol").
    authorization_headers: Optional headers to send to the MCP server.
    headers: Optional list of HTTP header names to forward from incoming requests.
    timeout: Optional request timeout in seconds.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Unique name for the MCP server |
| url | string | URL of the MCP server endpoint |
| provider_id | string | MCP provider identification |
| authorization_headers | object | Headers to send to the MCP server. Values must be one of the supported token resolution keywords: 'client' - forward the caller's token provided via MCP-HEADERS, 'kubernetes' - use the authenticated user's Kubernetes token, 'oauth' - use an OAuth token provided via MCP-HEADERS. File-path based secrets (used in static YAML config) are not supported for dynamically registered servers. |
| headers | array | List of HTTP header names to forward from incoming requests |
| timeout | integer | Request timeout in seconds for the MCP server |


## ModelFilter


Model representing a query parameter to select models by its type.

Attributes:
    model_type: Required model type, such as 'llm', 'embeddings' etc.


| Field | Type | Description |
|-------|------|-------------|
| model_type | string | Optional filter to return only models matching this type |


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


## OpenAIResponseInputFunctionToolCallOutput


This represents the output of a function call that gets passed back to the model.


| Field | Type | Description |
|-------|------|-------------|
| call_id | string |  |
| output |  |  |
| type | string |  |
| id | string |  |
| status | string |  |


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


## OpenAIResponseInputToolChoiceAllowedTools


Constrains the tools available to the model to a pre-defined set.

:param mode: Constrains the tools available to the model to a pre-defined set
:param tools: A list of tool definitions that the model should be allowed to call
:param type: Tool choice type identifier, always "allowed_tools"


| Field | Type | Description |
|-------|------|-------------|
| mode | string |  |
| tools | array |  |
| type | string |  |


## OpenAIResponseInputToolChoiceCustomTool


Forces the model to call a custom tool.

:param type: Tool choice type identifier, always "custom"
:param name: The name of the custom tool to call.


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| name | string |  |


## OpenAIResponseInputToolChoiceFileSearch


Indicates that the model should use file search to generate a response.

:param type: Tool choice type identifier, always "file_search"


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |


## OpenAIResponseInputToolChoiceFunctionTool


Forces the model to call a specific function.

:param name: The name of the function to call
:param type: Tool choice type identifier, always "function"


| Field | Type | Description |
|-------|------|-------------|
| name | string |  |
| type | string |  |


## OpenAIResponseInputToolChoiceMCPTool


Forces the model to call a specific tool on a remote MCP server

:param server_label: The label of the MCP server to use.
:param type: Tool choice type identifier, always "mcp"
:param name: (Optional) The name of the tool to call on the server.


| Field | Type | Description |
|-------|------|-------------|
| server_label | string |  |
| type | string |  |
| name | string |  |


## OpenAIResponseInputToolChoiceMode





## OpenAIResponseInputToolChoiceWebSearch


Indicates that the model should use web search to generate a response

:param type: Web search tool type variant to use


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |


## OpenAIResponseInputToolFileSearch


File search tool configuration for OpenAI response inputs.

:param type: Tool type identifier, always "file_search"
:param vector_store_ids: List of vector store identifiers to search within
:param filters: (Optional) Additional filters to apply to the search
:param max_num_results: (Optional) Maximum number of search results to return (1-50)
:param ranking_options: (Optional) Options for ranking and scoring search results


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| vector_store_ids | array |  |
| filters | object |  |
| max_num_results | integer |  |
| ranking_options |  |  |


## OpenAIResponseInputToolFunction


Function tool configuration for OpenAI response inputs.

:param type: Tool type identifier, always "function"
:param name: Name of the function that can be called
:param description: (Optional) Description of what the function does
:param parameters: (Optional) JSON schema defining the function's parameters
:param strict: (Optional) Whether to enforce strict parameter validation


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| name | string |  |
| description | string |  |
| parameters | object |  |
| strict | boolean |  |


## OpenAIResponseInputToolWebSearch


Web search tool configuration for OpenAI response inputs.

:param type: Web search tool type variant to use
:param search_context_size: (Optional) Size of search context, must be "low", "medium", or "high"


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |
| search_context_size | string |  |


## OpenAIResponseMCPApprovalRequest


A request for human approval of a tool invocation.


| Field | Type | Description |
|-------|------|-------------|
| arguments | string |  |
| id | string |  |
| name | string |  |
| server_label | string |  |
| type | string |  |


## OpenAIResponseMCPApprovalResponse


A response to an MCP approval request.


| Field | Type | Description |
|-------|------|-------------|
| approval_request_id | string |  |
| approve | boolean |  |
| type | string |  |
| id | string |  |
| reason | string |  |


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


## OpenAIResponsePrompt


OpenAI compatible Prompt object that is used in OpenAI responses.

:param id: Unique identifier of the prompt template
:param variables: Dictionary of variable names to OpenAIResponseInputMessageContent structure for template substitution. The substitution values can either be strings, or other Response input types
like images or files.
:param version: Version number of the prompt to use (defaults to latest if not specified)


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| variables | object |  |
| version | string |  |


## OpenAIResponseReasoning


Configuration for reasoning effort in OpenAI responses.

Controls how much reasoning the model performs before generating a response.

:param effort: The effort level for reasoning. "low" favors speed and economical token usage,
               "high" favors more complete reasoning, "medium" is a balance between the two.


| Field | Type | Description |
|-------|------|-------------|
| effort | string |  |


## OpenAIResponseText


Text response configuration for OpenAI responses.

:param format: (Optional) Text format configuration specifying output format requirements


| Field | Type | Description |
|-------|------|-------------|
| format |  |  |


## OpenAIResponseTextFormat


Configuration for Responses API text format.

:param type: Must be "text", "json_schema", or "json_object" to identify the format type
:param name: The name of the response format. Only used for json_schema.
:param schema: The JSON schema the response should conform to. In a Python SDK, this is often a `pydantic` model. Only used for json_schema.
:param description: (Optional) A description of the response format. Only used for json_schema.
:param strict: (Optional) Whether to strictly enforce the JSON schema. If true, the response must match the schema exactly. Only used for json_schema.


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |
| name | string |  |
| schema | object |  |
| description | string |  |
| strict | boolean |  |


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


## PromptCreateRequest


Request body to create a stored prompt template in Llama Stack.

Attributes:
    prompt: Prompt text with variable placeholders.
    variables: Variable names allowed in the template.


| Field | Type | Description |
|-------|------|-------------|
| prompt | string | Prompt text with variable placeholders |
| variables | array | Variable names allowed in the template |


## PromptUpdateRequest


Request body to update a stored prompt (creates a new version).

Attributes:
    prompt: Updated prompt text.
    version: Current version being updated.
    set_as_default: Whether the new version becomes the default.
    variables: Updated allowed variable names.


| Field | Type | Description |
|-------|------|-------------|
| prompt | string | Updated prompt text |
| version | integer | Current version being updated |
| set_as_default | boolean | Whether the new version becomes the default |
| variables | array | Updated allowed variable names |


## QueryRequest


Model representing a request for the LLM (Language Model).

Attributes:
    query: The query string.
    conversation_id: The optional conversation ID (UUID).
    provider: The optional provider.
    model: The optional model.
    system_prompt: The optional system prompt.
    attachments: The optional attachments.
    no_tools: Whether to bypass all tools and MCP servers (default: False).
    generate_topic_summary: Whether to generate topic summary for new conversations.
    media_type: The optional media type for response format (application/json or text/plain).
    vector_store_ids: The optional list of specific vector store IDs to query for RAG.
    shield_ids: The optional list of safety shield IDs to apply.
    solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.


| Field | Type | Description |
|-------|------|-------------|
| query | string | The query string |
| conversation_id | string | The optional conversation ID (UUID) |
| provider | string | The optional provider |
| model | string | The optional model |
| system_prompt | string | The optional system prompt. |
| attachments | array | The optional list of attachments. |
| no_tools | boolean | Whether to bypass all tools and MCP servers |
| generate_topic_summary | boolean | Whether to generate topic summary for new conversations |
| media_type | string | Media type for the response format |
| vector_store_ids | array | Optional list of specific vector store IDs to query for RAG. If not provided, all available vector stores will be queried. |
| shield_ids | array | Optional list of safety shield IDs to apply. If None, all configured shields are used.  |
| solr |  | Solr inline RAG config: mode (semantic, hybrid, lexical) and filters; a legacy filter-only object (e.g. fq) is still accepted. |


## ResponseInput





## ResponseItem





## ResponsesRequest


Model representing a request for the Responses API following LCORE specification.

Attributes:
    input: Input text or structured input items containing the query.
    model: Model identifier in format "provider/model". Auto-selected if not provided.
    conversation: Conversation ID linking to an existing conversation. Accepts both
        OpenAI and LCORE formats. Mutually exclusive with previous_response_id.
    include: Explicitly specify output item types that are excluded by default but
        should be included in the response.
    instructions: System instructions or guidelines provided to the model (acts as
        the system prompt).
    max_infer_iters: Maximum number of inference iterations the model can perform.
    max_output_tokens: Maximum number of tokens allowed in the response.
    max_tool_calls: Maximum number of tool calls allowed in a single response.
    metadata: Custom metadata dictionary with key-value pairs for tracking or logging.
    parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
    previous_response_id: Identifier of the previous response in a multi-turn
        conversation. Mutually exclusive with conversation.
    prompt: Prompt object containing a template with variables for dynamic
        substitution.
    reasoning: Reasoning configuration for the response.
    safety_identifier: Safety identifier for the response.
    store: Whether to store the response in conversation history. Defaults to True.
    stream: Whether to stream the response as it is generated. Defaults to False.
    temperature: Sampling temperature controlling randomness (typically 0.0–2.0).
    text: Text response configuration specifying output format constraints (JSON
        schema, JSON object, or plain text).
    tool_choice: Tool selection strategy ("auto", "required", "none", or specific
        tool configuration).
    tools: List of tools available to the model (file search, web search, function
        calls, MCP tools). Defaults to all tools available to the model.
    generate_topic_summary: LCORE-specific flag indicating whether to generate a
        topic summary for new conversations. Defaults to True.
    shield_ids: LCORE-specific list of safety shield IDs to apply. If None, all
        configured shields are used.
    solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.


| Field | Type | Description |
|-------|------|-------------|
| input |  |  |
| model | string |  |
| conversation | string |  |
| include | array |  |
| instructions | string |  |
| max_infer_iters | integer |  |
| max_output_tokens | integer |  |
| max_tool_calls | integer |  |
| metadata | object |  |
| parallel_tool_calls | boolean |  |
| previous_response_id | string |  |
| prompt |  |  |
| reasoning |  |  |
| safety_identifier | string |  |
| store | boolean |  |
| stream | boolean |  |
| temperature | number |  |
| text |  |  |
| tool_choice |  |  |
| tools | array |  |
| generate_topic_summary | boolean |  |
| shield_ids | array |  |
| solr |  |  |


## RlsapiV1Attachment


Attachment data from rlsapi v1 context.

Attributes:
    contents: The textual contents of the file read on the client machine.
    mimetype: The MIME type of the file.


| Field | Type | Description |
|-------|------|-------------|
| contents | string | File contents read on client |
| mimetype | string | MIME type of the file |


## RlsapiV1CLA


Command Line Assistant information from rlsapi v1 context.

Attributes:
    nevra: The NEVRA (Name-Epoch-Version-Release-Architecture) of the CLA.
    version: The version of the command line assistant.


| Field | Type | Description |
|-------|------|-------------|
| nevra | string | CLA NEVRA identifier |
| version | string | Command line assistant version |


## RlsapiV1Context


Context data for rlsapi v1 /infer request.

Attributes:
    stdin: Redirect input read by command-line-assistant.
    attachments: Attachment object received by the client.
    terminal: Terminal object received by the client.
    systeminfo: System information object received by the client.
    cla: Command Line Assistant information.


| Field | Type | Description |
|-------|------|-------------|
| stdin | string | Redirect input from stdin |
| attachments |  | File attachment data |
| terminal |  | Terminal output context |
| systeminfo |  | Client system information |
| cla |  | Command line assistant metadata |


## RlsapiV1InferRequest


RHEL Lightspeed rlsapi v1 /infer request.

Attributes:
    question: User question string.
    context: Context with system info, terminal output, etc. (defaults provided).
    skip_rag: Reserved for future use. RAG retrieval is not yet implemented.
    include_metadata: Request extended response with debugging metadata (dev/testing only).

Example:
    ```python
    request = RlsapiV1InferRequest(
        question="How do I list files?",
        context=RlsapiV1Context(
            systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3"),
            terminal=RlsapiV1Terminal(output="bash: command not found"),
        ),
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| question | string | User question |
| context |  | Optional context (system info, terminal output, stdin, attachments) |
| skip_rag | boolean | Reserved for future use. RAG retrieval is not yet implemented. |
| include_metadata | boolean | [Development/Testing Only] Return extended response with debugging metadata (tool_calls, rag_chunks, tokens). Only honored when allow_verbose_infer is enabled. Not available in production. |


## RlsapiV1SystemInfo


System information from rlsapi v1 context.

Attributes:
    os: The operating system of the client machine.
    version: The version of the operating system.
    arch: The architecture of the client machine.
    system_id: The id of the client machine.


| Field | Type | Description |
|-------|------|-------------|
| os | string | Operating system name |
| version | string | Operating system version |
| arch | string | System architecture |
| id | string | Client machine ID |


## RlsapiV1Terminal


Terminal output from rlsapi v1 context.

Attributes:
    output: The textual contents of the terminal read on the client machine.


| Field | Type | Description |
|-------|------|-------------|
| output | string | Terminal output from client |


## SearchRankingOptions


Options for ranking and filtering search results.

This class configures how search results are ranked and filtered. You can use algorithm-based
rerankers (weighted, RRF) or neural rerankers. Defaults from VectorStoresConfig are
used when parameters are not provided.

Examples:
    # Weighted ranker with custom alpha
    SearchRankingOptions(ranker="weighted", alpha=0.7)

    # RRF ranker with custom impact factor
    SearchRankingOptions(ranker="rrf", impact_factor=50.0)

    # Use config defaults (just specify ranker type)
    SearchRankingOptions(ranker="weighted")  # Uses alpha from VectorStoresConfig

    # Score threshold filtering
    SearchRankingOptions(ranker="weighted", score_threshold=0.5)

:param ranker: (Optional) Name of the ranking algorithm to use. Supported values:
    - "weighted": Weighted combination of vector and keyword scores
    - "rrf": Reciprocal Rank Fusion algorithm
    - "neural": Neural reranking model (requires model parameter, Part II)
    Note: For OpenAI API compatibility, any string value is accepted, but only the above values are supported.
:param score_threshold: (Optional) Minimum relevance score threshold for results. Default: 0.0
:param alpha: (Optional) Weight factor for weighted ranker (0-1).
    - 0.0 = keyword only
    - 0.5 = equal weight (default)
    - 1.0 = vector only
    Only used when ranker="weighted" and weights is not provided.
    Falls back to VectorStoresConfig.chunk_retrieval_params.weighted_search_alpha if not provided.
:param impact_factor: (Optional) Impact factor (k) for RRF algorithm.
    Lower values emphasize higher-ranked results. Default: 60.0 (optimal from research).
    Only used when ranker="rrf".
    Falls back to VectorStoresConfig.chunk_retrieval_params.rrf_impact_factor if not provided.
:param weights: (Optional) Dictionary of weights for combining different signal types.
    Keys can be "vector", "keyword", "neural". Values should sum to 1.0.
    Used when combining algorithm-based reranking with neural reranking (Part II).
    Example: {"vector": 0.3, "keyword": 0.3, "neural": 0.4}
:param model: (Optional) Model identifier for neural reranker (e.g., "vllm/Qwen3-Reranker-0.6B").
    Required when ranker="neural" or when weights contains "neural" (Part II).


| Field | Type | Description |
|-------|------|-------------|
| ranker | string |  |
| score_threshold | number |  |
| alpha | number | Weight factor for weighted ranker |
| impact_factor | number | Impact factor for RRF algorithm |
| weights | object | Weights for combining vector, keyword, and neural scores. Keys: 'vector', 'keyword', 'neural' |
| model | string | Model identifier for neural reranker |


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


## StreamingInterruptRequest


Model representing a request to interrupt an active streaming query.

Attributes:
    request_id: Unique ID of the active streaming request to interrupt.


| Field | Type | Description |
|-------|------|-------------|
| request_id | string | The active streaming request ID to interrupt |


## VectorStoreCreateRequest


Model representing a request to create a vector store.

Attributes:
    name: Name of the vector store.
    embedding_model: Optional embedding model to use.
    embedding_dimension: Optional embedding dimension.
    chunking_strategy: Optional chunking strategy configuration.
    provider_id: Optional vector store provider identifier.
    metadata: Optional metadata dictionary for storing session information.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Name of the vector store |
| embedding_model | string | Embedding model to use for the vector store |
| embedding_dimension | integer | Dimension of the embedding vectors |
| chunking_strategy | object | Chunking strategy configuration |
| provider_id | string | Vector store provider identifier |
| metadata | object | Metadata dictionary for storing session information |


## VectorStoreFileCreateRequest


Model representing a request to add a file to a vector store.

Attributes:
    file_id: ID of the file to add to the vector store.
    attributes: Optional metadata key-value pairs (max 16 pairs).
    chunking_strategy: Optional chunking strategy configuration.


| Field | Type | Description |
|-------|------|-------------|
| file_id | string | ID of the file to add to the vector store |
| attributes | object | Set of up to 16 key-value pairs for storing additional information. Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers. |
| chunking_strategy | object | Chunking strategy configuration for this file |


## VectorStoreUpdateRequest


Model representing a request to update a vector store.

Attributes:
    name: New name for the vector store.
    expires_at: Optional expiration timestamp.
    metadata: Optional metadata dictionary for storing session information.


| Field | Type | Description |
|-------|------|-------------|
| name | string | New name for the vector store |
| expires_at | integer | Unix timestamp when the vector store should expire |
| metadata | object | Metadata dictionary for storing session information |
