# foo bar baz service - OpenAPI

foo bar baz service API specification.

## 🌍 Base URL


| URL | Description |
|-----|-------------|


# 🛠️ APIs

## GET `/`

> **Root Endpoint Handler**

Handle request to the / endpoint.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | string
 |
## GET `/v1/info`

> **Info Endpoint Handler**

Handle request to the /info endpoint.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [InfoResponse](#inforesponse)
 |
## GET `/v1/models`

> **Models Endpoint Handler**

Handle requests to the /models endpoint.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ModelsResponse](#modelsresponse)
 |
| 503 | Connection to Llama Stack is broken |  |
## POST `/v1/query`

> **Query Endpoint Handler**

Handle request to the /query endpoint.





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [QueryResponse](#queryresponse)
 |
| 400 | Missing or invalid credentials provided by client | [UnauthorizedResponse](#unauthorizedresponse)
 |
| 403 | User is not authorized | [ForbiddenResponse](#forbiddenresponse)
 |
| 503 | Service Unavailable |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror)
 |
## POST `/v1/streaming_query`

> **Streaming Query Endpoint Handler**

Handle request to the /streaming_query endpoint.





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | ... |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror)
 |
## GET `/v1/config`

> **Config Endpoint Handler**

Handle requests to the /config endpoint.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [Configuration](#configuration)
 |
| 503 | Service Unavailable |  |
## POST `/v1/feedback`

> **Feedback Endpoint Handler**

Handle feedback requests.

Args:
    feedback_request: The request containing feedback information.
    ensure_feedback_enabled: The feedback handler (FastAPI Depends) that
        will handle feedback status checks.
    auth: The Authentication handler (FastAPI Depends) that will
        handle authentication Logic.

Returns:
    Response indicating the status of the feedback storage request.





### 📦 Request Body 

[FeedbackRequest](#feedbackrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [FeedbackResponse](#feedbackresponse)
 |
| 400 | Missing or invalid credentials provided by client | [UnauthorizedResponse](#unauthorizedresponse)
 |
| 403 | User is not authorized | [ForbiddenResponse](#forbiddenresponse)
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror)
 |
## GET `/v1/feedback/status`

> **Feedback Status**

Handle feedback status requests.

Returns:
    Response indicating the status of the feedback.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [StatusResponse](#statusresponse)
 |
## GET `/v1/conversations/{conversation_id}`

> **Get Conversation Endpoint Handler**

Handle request to retrieve a conversation by ID.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ConversationResponse](#conversationresponse)
 |
| 404 | Not Found |  |
| 503 | Service Unavailable |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror)
 |
## DELETE `/v1/conversations/{conversation_id}`

> **Delete Conversation Endpoint Handler**

Handle request to delete a conversation by ID.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [ConversationDeleteResponse](#conversationdeleteresponse)
 |
| 404 | Not Found |  |
| 503 | Service Unavailable |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror)
 |
## GET `/readiness`

> **Readiness Probe Get Method**

Ready status of service with provider health details.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Service is ready | [ReadinessResponse](#readinessresponse)
 |
| 503 | Service is not ready | [ReadinessResponse](#readinessresponse)
 |
## GET `/liveness`

> **Liveness Probe Get Method**

Live status of service.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Service is alive | [LivenessResponse](#livenessresponse)
 |
| 503 | Service is not alive | [LivenessResponse](#livenessresponse)
 |
## POST `/authorized`

> **Authorized Endpoint Handler**

Handle request to the /authorized endpoint.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | The user is logged-in and authorized to access OLS | [AuthorizedResponse](#authorizedresponse)
 |
| 400 | Missing or invalid credentials provided by client | [UnauthorizedResponse](#unauthorizedresponse)
 |
| 403 | User is not authorized | [ForbiddenResponse](#forbiddenresponse)
 |
---

# 📋 Components



## Attachment


Model representing an attachment that can be send from UI as part of query.

List of attachments can be optional part of 'query' request.

Attributes:
    attachment_type: The attachment type, like "log", "configuration" etc.
    content_type: The content type as defined in MIME standard
    content: The actual attachment content

YAML attachments with **kind** and **metadata/name** attributes will
be handled as resources with specified name:
```
kind: Pod
metadata:
    name: private-reg
```


| Field | Type | Description |
|-------|------|-------------|
| attachment_type | string |  |
| content_type | string |  |
| content | string |  |


## AuthenticationConfiguration


Authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| module | string |  |
| skip_tls_verification | boolean |  |
| k8s_cluster_api |  |  |
| k8s_ca_cert_path |  |  |


## AuthorizedResponse


Model representing a response to an authorization request.

Attributes:
    user_id: The ID of the logged in user.
    username: The name of the logged in user.


| Field | Type | Description |
|-------|------|-------------|
| user_id | string |  |
| username | string |  |


## Configuration


Global service configuration.


| Field | Type | Description |
|-------|------|-------------|
| name | string |  |
| service |  |  |
| llama_stack |  |  |
| user_data_collection |  |  |
| mcp_servers | array |  |
| authentication |  |  |
| customization |  |  |


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


## Customization


Service customization.


| Field | Type | Description |
|-------|------|-------------|
| disable_query_system_prompt | boolean |  |
| system_prompt_path |  |  |
| system_prompt |  |  |


## DataCollectorConfiguration


Data collector configuration for sending data to ingress server.


| Field | Type | Description |
|-------|------|-------------|
| enabled | boolean |  |
| ingress_server_url |  |  |
| ingress_server_auth_token |  |  |
| ingress_content_service_name |  |  |
| collection_interval | integer |  |
| cleanup_after_send | boolean |  |
| connection_timeout | integer |  |


## FeedbackRequest


Model representing a feedback request.

Attributes:
    conversation_id: The required conversation ID (UUID).
    user_question: The required user question.
    llm_response: The required LLM response.
    sentiment: The optional sentiment.
    user_feedback: The optional user feedback.

Example:
    ```python
    feedback_request = FeedbackRequest(
        conversation_id="12345678-abcd-0000-0123-456789abcdef",
        user_question="what are you doing?",
        user_feedback="Great service!",
        llm_response="I don't know",
        sentiment=-1,
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| user_question | string |  |
| llm_response | string |  |
| sentiment |  |  |
| user_feedback |  | Feedback on the LLM response. |


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


## ForbiddenResponse


Model representing response for forbidden access.


| Field | Type | Description |
|-------|------|-------------|
| detail | string |  |


## HTTPValidationError



| Field | Type | Description |
|-------|------|-------------|
| detail | array |  |


## InfoResponse


Model representing a response to a info request.

Attributes:
    name: Service name.
    version: Service version.

Example:
    ```python
    info_response = InfoResponse(
        name="Lightspeed Stack",
        version="1.0.0",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| name | string |  |
| version | string |  |


## LLamaStackConfiguration


Llama stack configuration.


| Field | Type | Description |
|-------|------|-------------|
| url |  |  |
| api_key |  |  |
| use_as_library_client |  |  |
| library_client_config_path |  |  |


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
| models | array |  |


## ProviderHealthStatus


Model representing the health status of a provider.

Attributes:
    provider_id: The ID of the provider.
    status: The health status ('ok', 'unhealthy', 'not_implemented').
    message: Optional message about the health status.


| Field | Type | Description |
|-------|------|-------------|
| provider_id | string |  |
| status | string |  |
| message |  |  |


## QueryRequest


Model representing a request for the LLM (Language Model).

Attributes:
    query: The query string.
    conversation_id: The optional conversation ID (UUID).
    provider: The optional provider.
    model: The optional model.
    system_prompt: The optional system prompt.
    attachments: The optional attachments.

Example:
    ```python
    query_request = QueryRequest(query="Tell me about Kubernetes")
    ```


| Field | Type | Description |
|-------|------|-------------|
| query | string |  |
| conversation_id |  |  |
| provider |  |  |
| model |  |  |
| system_prompt |  |  |
| attachments |  |  |
| media_type |  |  |


## QueryResponse


Model representing LLM response to a query.

Attributes:
    conversation_id: The optional conversation ID (UUID).
    response: The response.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id |  |  |
| response | string |  |


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
                status="Error",
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
| data_collector |  |  |


## ValidationError



| Field | Type | Description |
|-------|------|-------------|
| loc | array |  |
| msg | string |  |
| type | string |  |
