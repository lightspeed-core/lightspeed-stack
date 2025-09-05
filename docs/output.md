# Lightspeed Core Service (LCS) service - OpenAPI

Lightspeed Core Service (LCS) service API specification.

## 🌍 Base URL


| URL | Description |
|-----|-------------|
| http://localhost:8080/ | Locally running service |


# 🛠️ APIs

## GET `/`

> **Root Endpoint Handler**

Handle request to the / endpoint.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | string |
## GET `/v1/info`

> **Info Endpoint Handler**

Handle request to the /info endpoint.

Process GET requests to the /info endpoint, returning the
service name and version.

Returns:
    InfoResponse: An object containing the service's name and version.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [InfoResponse](#inforesponse) |
| 500 | Internal Server Error |  |
## GET `/v1/models`

> **Models Endpoint Handler**

Handle requests to the /models endpoint.

Process GET requests to the /models endpoint, returning a list of available
models from the Llama Stack service.

Raises:
    HTTPException: If unable to connect to the Llama Stack server or if
    model retrieval fails for any reason.

Returns:
    ModelsResponse: An object containing the list of available models.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ModelsResponse](#modelsresponse) |
| 503 | Connection to Llama Stack is broken |  |
## POST `/v1/query`

> **Query Endpoint Handler**

Handle request to the /query endpoint.

Processes a POST request to the /query endpoint, forwarding the
user's query to a selected Llama Stack LLM or agent and
returning the generated response.

Validates configuration and authentication, selects the appropriate model
and provider, retrieves the LLM response, updates metrics, and optionally
stores a transcript of the interaction. Handles connection errors to the
Llama Stack service by returning an HTTP 500 error.

Returns:
    QueryResponse: Contains the conversation ID and the LLM-generated response.





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [QueryResponse](#queryresponse) |
| 400 | Missing or invalid credentials provided by client | [UnauthorizedResponse](#unauthorizedresponse) |
| 403 | User is not authorized | [ForbiddenResponse](#forbiddenresponse) |
| 503 | Service Unavailable |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## POST `/v1/streaming_query`

> **Streaming Query Endpoint Handler**

Handle request to the /streaming_query endpoint.

This endpoint receives a query request, authenticates the user,
selects the appropriate model and provider, and streams
incremental response events from the Llama Stack backend to the
client. Events include start, token updates, tool calls, turn
completions, errors, and end-of-stream metadata. Optionally
stores the conversation transcript if enabled in configuration.

Returns:
    StreamingResponse: An HTTP streaming response yielding
    SSE-formatted events for the query lifecycle.

Raises:
    HTTPException: Returns HTTP 500 if unable to connect to the
    Llama Stack server.





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | ... |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/v1/config`

> **Config Endpoint Handler**

Handle requests to the /config endpoint.

Process GET requests to the /config endpoint and returns the
current service configuration.

Returns:
    Configuration: The loaded service configuration object.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [Configuration](#configuration) |
| 503 | Service Unavailable |  |
## POST `/v1/feedback`

> **Feedback Endpoint Handler**

Handle feedback requests.

Processes a user feedback submission, storing the feedback and
returning a confirmation response.

Args:
    feedback_request: The request containing feedback information.
    ensure_feedback_enabled: The feedback handler (FastAPI Depends) that
        will handle feedback status checks.
    auth: The Authentication handler (FastAPI Depends) that will
        handle authentication Logic.

Returns:
    Response indicating the status of the feedback storage request.

Raises:
    HTTPException: Returns HTTP 500 if feedback storage fails.





### 📦 Request Body 

[FeedbackRequest](#feedbackrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Feedback received and stored | [FeedbackResponse](#feedbackresponse) |
| 401 | Missing or invalid credentials provided by client | [UnauthorizedResponse](#unauthorizedresponse) |
| 403 | Client does not have permission to access resource | [ForbiddenResponse](#forbiddenresponse) |
| 500 | User feedback can not be stored | [ErrorResponse](#errorresponse) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/v1/feedback/status`

> **Feedback Status**

Handle feedback status requests.

Return the current enabled status of the feedback
functionality.

Returns:
    StatusResponse: Indicates whether feedback collection is enabled.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [StatusResponse](#statusresponse) |
## PUT `/v1/feedback/status`

> **Update Feedback Status**

Handle feedback status update requests.

Takes a request with the desired state of the feedback status.
Returns the updated state of the feedback status based on the request's value.
These changes are for the life of the service and are on a per-worker basis.

Returns:
    FeedbackStatusUpdateResponse: Indicates whether feedback is enabled.





### 📦 Request Body 

[FeedbackStatusUpdateRequest](#feedbackstatusupdaterequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [FeedbackStatusUpdateResponse](#feedbackstatusupdateresponse) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/v1/conversations`

> **Get Conversations List Endpoint Handler**

Handle request to retrieve all conversations for the authenticated user.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ConversationsListResponse](#conversationslistresponse) |
| 503 | Service Unavailable |  |
## GET `/v1/conversations/{conversation_id}`

> **Get Conversation Endpoint Handler**

Handle request to retrieve a conversation by ID.

Retrieve a conversation's chat history by its ID. Then fetches
the conversation session from the Llama Stack backend,
simplifies the session data to essential chat history, and
returns it in a structured response. Raises HTTP 400 for
invalid IDs, 404 if not found, 503 if the backend is
unavailable, and 500 for unexpected errors.

Parameters:
    conversation_id (str): Unique identifier of the conversation to retrieve.

Returns:
    ConversationResponse: Structured response containing the conversation
    ID and simplified chat history.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ConversationResponse](#conversationresponse) |
| 404 | Not Found |  |
| 503 | Service Unavailable |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## DELETE `/v1/conversations/{conversation_id}`

> **Delete Conversation Endpoint Handler**

Handle request to delete a conversation by ID.

Validates the conversation ID format and attempts to delete the
corresponding session from the Llama Stack backend. Raises HTTP
errors for invalid IDs, not found conversations, connection
issues, or unexpected failures.

Returns:
    ConversationDeleteResponse: Response indicating the result of the deletion operation.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ConversationDeleteResponse](#conversationdeleteresponse) |
| 404 | Not Found |  |
| 503 | Service Unavailable |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/readiness`

> **Readiness Probe Get Method**

Handle the readiness probe endpoint, returning service readiness.

If any provider reports an error status, responds with HTTP 503
and details of unhealthy providers; otherwise, indicates the
service is ready.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Service is ready | [ReadinessResponse](#readinessresponse) |
| 503 | Service is not ready | [ReadinessResponse](#readinessresponse) |
## GET `/liveness`

> **Liveness Probe Get Method**

Return the liveness status of the service.

Returns:
    LivenessResponse: Indicates that the service is alive.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Service is alive | [LivenessResponse](#livenessresponse) |
## POST `/authorized`

> **Authorized Endpoint Handler**

Handle request to the /authorized endpoint.

Process POST requests to the /authorized endpoint, returning
the authenticated user's ID and username.

Returns:
    AuthorizedResponse: Contains the user ID and username of the authenticated user.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | The user is logged-in and authorized to access OLS | [AuthorizedResponse](#authorizedresponse) |
| 400 | Missing or invalid credentials provided by client for noop and noop-with-token | [UnauthorizedResponse](#unauthorizedresponse) |
| 401 | Missing or invalid credentials provided by client for k8s | [UnauthorizedResponse](#unauthorizedresponse) |
| 403 | User is not authorized | [ForbiddenResponse](#forbiddenresponse) |
## GET `/metrics`

> **Metrics Endpoint Handler**

Handle request to the /metrics endpoint.

Process GET requests to the /metrics endpoint, returning the
latest Prometheus metrics in form of a plain text.

Initializes model metrics on the first request if not already
set up, then responds with the current metrics snapshot in
Prometheus format.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | string |
---

# 📋 Components



## AccessRule


Rule defining what actions a role can perform.


| Field | Type | Description |
|-------|------|-------------|
| role | string |  |
| actions | array |  |


## Action


Available actions in the system.




## Attachment


Model representing an attachment that can be send from the UI as part of query.

A list of attachments can be an optional part of 'query' request.

Attributes:
    attachment_type: The attachment type, like "log", "configuration" etc.
    content_type: The content type as defined in MIME standard
    content: The actual attachment content

YAML attachments with **kind** and **metadata/name** attributes will
be handled as resources with the specified name:
```
kind: Pod
metadata:
    name: private-reg
```


| Field | Type | Description |
|-------|------|-------------|
| attachment_type | string | The attachment type, like 'log', 'configuration' etc. |
| content_type | string | The content type as defined in MIME standard |
| content | string | The actual attachment content |


## AuthenticationConfiguration


Authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| module | string |  |
| skip_tls_verification | boolean |  |
| k8s_cluster_api |  |  |
| k8s_ca_cert_path |  |  |
| jwk_config |  |  |


## AuthorizationConfiguration


Authorization configuration.


| Field | Type | Description |
|-------|------|-------------|
| access_rules | array |  |


## AuthorizedResponse


Model representing a response to an authorization request.

Attributes:
    user_id: The ID of the logged in user.
    username: The name of the logged in user.
    skip_userid_check: Whether to skip user_id check


| Field | Type | Description |
|-------|------|-------------|
| user_id | string | User ID, for example UUID |
| username | string | User name |
| skip_userid_check | bool | skip user_id check |


## CORSConfiguration


CORS configuration.


| Field | Type | Description |
|-------|------|-------------|
| allow_origins | array |  |
| allow_credentials | boolean |  |
| allow_methods | array |  |
| allow_headers | array |  |


## Configuration


Global service configuration.


| Field | Type | Description |
|-------|------|-------------|
| name | string |  |
| service |  |  |
| llama_stack |  |  |
| user_data_collection |  |  |
| database |  |  |
| mcp_servers | array |  |
| authentication |  |  |
| authorization |  |  |
| customization |  |  |
| inference |  |  |


## ConversationDeleteResponse


Model representing a response for deleting a conversation.

Attributes:
    conversation_id: The conversation ID (UUID) that was deleted.
    success: Whether the deletion was successful.
    response: A message about the deletion result.

Example:
    ```python
    delete_response = ConversationDeleteResponse(
        conversation_id="123e4567-e89b-12d3-a456-426614174000",
        success=True,
        response="Conversation deleted successfully"
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| success | boolean |  |
| response | string |  |


## ConversationDetails


Model representing the details of a user conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    created_at: When the conversation was created.
    last_message_at: When the last message was sent.
    message_count: Number of user messages in the conversation.
    last_used_model: The last model used for the conversation.
    last_used_provider: The provider of the last used model.

Example:
    ```python
    conversation = ConversationDetails(
        conversation_id="123e4567-e89b-12d3-a456-426614174000"
        created_at="2024-01-01T00:00:00Z",
        last_message_at="2024-01-01T00:05:00Z",
        message_count=5,
        last_used_model="gemini/gemini-2.0-flash",
        last_used_provider="gemini",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| created_at |  |  |
| last_message_at |  |  |
| message_count |  |  |
| last_used_model |  |  |
| last_used_provider |  |  |


## ConversationResponse


Model representing a response for retrieving a conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    chat_history: The simplified chat history as a list of conversation turns.

Example:
    ```python
    conversation_response = ConversationResponse(
        conversation_id="123e4567-e89b-12d3-a456-426614174000",
        chat_history=[
            {
                "messages": [
                    {"content": "Hello", "type": "user"},
                    {"content": "Hi there!", "type": "assistant"}
                ],
                "started_at": "2024-01-01T00:01:00Z",
                "completed_at": "2024-01-01T00:01:05Z"
            }
        ]
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| chat_history | array |  |


## ConversationsListResponse


Model representing a response for listing conversations of a user.

Attributes:
    conversations: List of conversation details associated with the user.

Example:
    ```python
    conversations_list = ConversationsListResponse(
        conversations=[
            ConversationDetails(
                conversation_id="123e4567-e89b-12d3-a456-426614174000",
                created_at="2024-01-01T00:00:00Z",
                last_message_at="2024-01-01T00:05:00Z",
                message_count=5,
                last_used_model="gemini/gemini-2.0-flash",
                last_used_provider="gemini",
            ),
            ConversationDetails(
                conversation_id="456e7890-e12b-34d5-a678-901234567890"
                created_at="2024-01-01T01:00:00Z",
                message_count=2,
                last_used_model="gemini/gemini-2.0-flash",
                last_used_provider="gemini",
            )
        ]
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversations | array |  |


## Customization


Service customization.


| Field | Type | Description |
|-------|------|-------------|
| disable_query_system_prompt | boolean |  |
| system_prompt_path |  |  |
| system_prompt |  |  |


## DatabaseConfiguration


Database configuration.


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  |  |
| postgres |  |  |


## ErrorResponse


Model representing error response for query endpoint.


| Field | Type | Description |
|-------|------|-------------|
| detail | object | Error details |


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

Example:
    ```python
    feedback_request = FeedbackRequest(
        conversation_id="12345678-abcd-0000-0123-456789abcdef",
        user_question="what are you doing?",
        user_feedback="This response is not helpful",
        llm_response="I don't know",
        sentiment=-1,
        categories=[FeedbackCategory.INCORRECT, FeedbackCategory.INCOMPLETE]
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | The required conversation ID (UUID) |
| user_question | string | User question (the query string) |
| llm_response | string | Response from LLM |
| sentiment |  | User sentiment, if provided must be -1 or 1 |
| user_feedback |  | Feedback on the LLM response. |
| categories |  | List of feedback categories that describe issues with the LLM response (for negative feedback). |


## FeedbackResponse


Model representing a response to a feedback request.

Attributes:
    response: The response of the feedback request.

Example:
    ```python
    feedback_response = FeedbackResponse(response="feedback received")
    ```


| Field | Type | Description |
|-------|------|-------------|
| response | string |  |


## FeedbackStatusUpdateRequest


Model representing a feedback status update request.

Attributes:
    status: Value of the desired feedback enabled state.

Example:
    ```python
    feedback_request = FeedbackRequest(
        status=false
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| status | boolean | Desired state of feedback enablement, must be False or True |


## FeedbackStatusUpdateResponse


Model representing a response to a feedback status update request.

Attributes:
    status: The previous and current status of the service and who updated it.

Example:
    ```python
    status_response = StatusResponse(
        status={
            "previous_status": true,
            "updated_status": false,
            "updated_by": "user/test",
            "timestamp": "2023-03-15 12:34:56"
        },
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| status | object |  |


## ForbiddenResponse


Model representing response for forbidden access.


| Field | Type | Description |
|-------|------|-------------|
| detail | string |  |


## HTTPValidationError



| Field | Type | Description |
|-------|------|-------------|
| detail | array |  |


## InferenceConfiguration


Inference configuration.


| Field | Type | Description |
|-------|------|-------------|
| default_model |  |  |
| default_provider |  |  |


## InfoResponse


Model representing a response to an info request.

Attributes:
    name: Service name.
    service_version: Service version.
    llama_stack_version: Llama Stack version.

Example:
    ```python
    info_response = InfoResponse(
        name="Lightspeed Stack",
        service_version="1.0.0",
        llama_stack_version="0.2.18",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| name | string | Service name |
| service_version | string | Service version |
| llama_stack_version | string | Llama Stack version |


## JsonPathOperator


Supported operators for JSONPath evaluation.




## JwkConfiguration


JWK configuration.


| Field | Type | Description |
|-------|------|-------------|
| url | string |  |
| jwt_configuration |  |  |


## JwtConfiguration


JWT configuration.


| Field | Type | Description |
|-------|------|-------------|
| user_id_claim | string |  |
| username_claim | string |  |
| role_rules | array |  |


## JwtRoleRule


Rule for extracting roles from JWT claims.


| Field | Type | Description |
|-------|------|-------------|
| jsonpath | string |  |
| operator |  |  |
| negate | boolean |  |
| value |  |  |
| roles | array |  |


## LivenessResponse


Model representing a response to a liveness request.

Attributes:
    alive: If app is alive.

Example:
    ```python
    liveness_response = LivenessResponse(alive=True)
    ```


| Field | Type | Description |
|-------|------|-------------|
| alive | boolean |  |


## LlamaStackConfiguration


Llama stack configuration.


| Field | Type | Description |
|-------|------|-------------|
| url |  |  |
| api_key |  |  |
| use_as_library_client |  |  |
| library_client_config_path |  |  |


## ModelContextProtocolServer


model context protocol server configuration.


| Field | Type | Description |
|-------|------|-------------|
| name | string |  |
| provider_id | string |  |
| url | string |  |


## ModelsResponse


Model representing a response to models request.


| Field | Type | Description |
|-------|------|-------------|
| models | array | List of models available |


## PostgreSQLDatabaseConfiguration


PostgreSQL database configuration.


| Field | Type | Description |
|-------|------|-------------|
| host | string |  |
| port | integer |  |
| db | string |  |
| user | string |  |
| password | string |  |
| namespace |  |  |
| ssl_mode | string |  |
| gss_encmode | string |  |
| ca_cert_path |  |  |


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
| message |  | Optional message about the health status |


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

Example:
    ```python
    query_request = QueryRequest(query="Tell me about Kubernetes")
    ```


| Field | Type | Description |
|-------|------|-------------|
| query | string | The query string |
| conversation_id |  | The optional conversation ID (UUID) |
| provider |  | The optional provider |
| model |  | The optional model |
| system_prompt |  | The optional system prompt. |
| attachments |  | The optional list of attachments. |
| no_tools |  | Whether to bypass all tools and MCP servers |
| media_type |  | Media type (used just to enable compatibility) |


## QueryResponse


Model representing LLM response to a query.

Attributes:
    conversation_id: The optional conversation ID (UUID).
    response: The response.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id |  | The optional conversation ID (UUID) |
| response | string | Response from LLM |


## ReadinessResponse


Model representing response to a readiness request.

Attributes:
    ready: If service is ready.
    reason: The reason for the readiness.
    providers: List of unhealthy providers in case of readiness failure.

Example:
    ```python
    readiness_response = ReadinessResponse(
        ready=False,
        reason="Service is not ready",
        providers=[
            ProviderHealthStatus(
                provider_id="ollama",
                status="unhealthy",
                message="Server is unavailable"
            )
        ]
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| ready | boolean |  |
| reason | string |  |
| providers | array |  |


## SQLiteDatabaseConfiguration


SQLite database configuration.


| Field | Type | Description |
|-------|------|-------------|
| db_path | string |  |


## ServiceConfiguration


Service configuration.


| Field | Type | Description |
|-------|------|-------------|
| host | string |  |
| port | integer |  |
| auth_enabled | boolean |  |
| workers | integer |  |
| color_log | boolean |  |
| access_log | boolean |  |
| tls_config |  |  |
| cors |  |  |


## StatusResponse


Model representing a response to a status request.

Attributes:
    functionality: The functionality of the service.
    status: The status of the service.

Example:
    ```python
    status_response = StatusResponse(
        functionality="feedback",
        status={"enabled": True},
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| functionality | string |  |
| status | object |  |


## TLSConfiguration


TLS configuration.


| Field | Type | Description |
|-------|------|-------------|
| tls_certificate_path |  |  |
| tls_key_path |  |  |
| tls_key_password |  |  |


## UnauthorizedResponse


Model representing response for missing or invalid credentials.


| Field | Type | Description |
|-------|------|-------------|
| detail | string |  |


## UserDataCollection


User data collection configuration.


| Field | Type | Description |
|-------|------|-------------|
| feedback_enabled | boolean |  |
| feedback_storage |  |  |
| transcripts_enabled | boolean |  |
| transcripts_storage |  |  |


## ValidationError



| Field | Type | Description |
|-------|------|-------------|
| loc | array |  |
| msg | string |  |
| type | string |  |
