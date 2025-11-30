# Lightspeed Core Service (LCS) service - OpenAPI

Lightspeed Core Service (LCS) service API specification.

## 🌍 Base URL


| URL | Description |
|-----|-------------|
| http://localhost:8080/ | Locally running service |


# 🛠️ APIs

## GET `/`

> **Root Endpoint Handler**

Handle GET requests to the root ("/") endpoint and returns the static HTML index page.

Returns:
    HTMLResponse: The HTML content of the index page, including a heading,
    embedded image with the service icon, and links to the API documentation
    via Swagger UI and ReDoc.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | string |
| 401 | Unauthorized | ...
Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```

[UnauthorizedResponse](#unauthorizedresponse) |
| 403 | Permission denied | ...
Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

[ForbiddenResponse](#forbiddenresponse) |
## GET `/v1/info`

> **Info Endpoint Handler**

Handle request to the /info endpoint.

Process GET requests to the /info endpoint, returning the
service name, version and Llama-stack version.

Returns:
    InfoResponse: An object containing the service's name and version.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [InfoResponse](#inforesponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "Token has expired",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "Invalid token signature",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "Token signed by unknown key",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "Token missing claim: user_id",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "Invalid or expired Kubernetes token",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "Authentication key server returned invalid data",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
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
| 200 | Successful response | [ModelsResponse](#modelsresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/v1/tools`

> **Tools Endpoint Handler**

Handle requests to the /tools endpoint.

Process GET requests to the /tools endpoint, returning a consolidated list of
available tools from all configured MCP servers.

Raises:
    HTTPException: If unable to connect to the Llama Stack server or if
    tool retrieval fails for any reason.

Returns:
    ToolsResponse: An object containing the consolidated list of available tools
    with metadata including tool name, description, parameters, and server source.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ToolsResponse](#toolsresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/v1/shields`

> **Shields Endpoint Handler**

Handle requests to the /shields endpoint.

Process GET requests to the /shields endpoint, returning a list of available
shields from the Llama Stack service.

Raises:
    HTTPException: If unable to connect to the Llama Stack server or if
    shield retrieval fails for any reason.

Returns:
    ShieldsResponse: An object containing the list of available shields.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ShieldsResponse](#shieldsresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/v1/providers`

> **Providers Endpoint Handler**

List all available providers grouped by API type.

Returns:
    ProvidersListResponse: Mapping from API type to list of providers.

Raises:
    HTTPException:
        - 401: Authentication failed
        - 403: Authorization failed
        - 500: Lightspeed Stack configuration not loaded
        - 503: Unable to connect to Llama Stack





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ProvidersListResponse](#providerslistresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/v1/providers/{provider_id}`

> **Get Provider Endpoint Handler**

Retrieve a single provider by its unique ID.

Returns:
    ProviderResponse: Provider details.

Raises:
    HTTPException:
        - 401: Authentication failed
        - 403: Authorization failed
        - 404: Provider not found
        - 500: Lightspeed Stack configuration not loaded
        - 503: Unable to connect to Llama Stack



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| provider_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ProviderResponse](#providerresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Provider with ID openai does not exist",
    "response": "Provider not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/v1/rags`

> **Rags Endpoint Handler**

List all available RAGs.

Returns:
    RAGListResponse: List of RAG identifiers.

Raises:
    HTTPException:
        - 401: Authentication failed
        - 403: Authorization failed
        - 500: Lightspeed Stack configuration not loaded
        - 503: Unable to connect to Llama Stack





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [RAGListResponse](#raglistresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/v1/rags/{rag_id}`

> **Get Rag Endpoint Handler**

Retrieve a single RAG by its unique ID.

Returns:
    RAGInfoResponse: A single RAG's details.

Raises:
    HTTPException:
        - 401: Authentication failed
        - 403: Authorization failed
        - 404: RAG with the given ID not found
        - 500: Lightspeed Stack configuration not loaded
        - 503: Unable to connect to Llama Stack



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| rag_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [RAGInfoResponse](#raginforesponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Rag with ID vs_7b52a8cf-0fa3-489c-beab-27e061d102f3 does not exist",
    "response": "Rag not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## POST `/v1/query`

> **Query Endpoint Handler**

Handle request to the /query endpoint using Agent API.

This is a wrapper around query_endpoint_handler_base that provides
the Agent API specific retrieve_response and get_topic_summary functions.

Returns:
    QueryResponse: Contains the conversation ID and the LLM-generated response.





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [QueryResponse](#queryresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 does not have permission to read conversation with ID 123e4567-e89b-12d3-a456-426614174000",
    "response": "User does not have permission to perform this action"
  }
}
```




```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```




```json
{
  "detail": {
    "cause": "User lacks model_override permission required to override model/provider.",
    "response": "This instance does not permit overriding model/provider in the query request (missing permission: MODEL_OVERRIDE). Please remove the model and provider fields from your request."
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Provider with ID openai does not exist",
    "response": "Provider not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Model with ID gpt-4-turbo is not configured",
    "response": "Model not found"
  }
}
```
 |
| 422 | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse)

Examples





```json
{
  "detail": {
    "cause": "Invalid request format. The request body could not be parsed.",
    "response": "Invalid request format"
  }
}
```




```json
{
  "detail": {
    "cause": "Missing required attributes: ['query', 'model', 'provider']",
    "response": "Missing required attributes"
  }
}
```




```json
{
  "detail": {
    "cause": "Invalid attatchment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```
 |
| 429 | Quota limit exceeded | [QuotaExceededResponse](#quotaexceededresponse)

Examples





```json
{
  "detail": {
    "cause": "The token quota for model gpt-4-turbo has been exceeded.",
    "response": "The model quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has 5 tokens, but 10 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has 500 tokens, but 900 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## POST `/v1/streaming_query`

> **Streaming Query Endpoint Handler**

Handle request to the /streaming_query endpoint using Agent API.

This is a wrapper around streaming_query_endpoint_handler_base that provides
the Agent API specific retrieve_response and response generator functions.

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
| 200 | Streaming response (Server-Sent Events) | ...string |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 does not have permission to read conversation with ID 123e4567-e89b-12d3-a456-426614174000",
    "response": "User does not have permission to perform this action"
  }
}
```




```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```




```json
{
  "detail": {
    "cause": "User lacks model_override permission required to override model/provider.",
    "response": "This instance does not permit overriding model/provider in the query request (missing permission: MODEL_OVERRIDE). Please remove the model and provider fields from your request."
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Provider with ID openai does not exist",
    "response": "Provider not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Model with ID gpt-4-turbo is not configured",
    "response": "Model not found"
  }
}
```
 |
| 422 | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse)

Examples





```json
{
  "detail": {
    "cause": "Invalid request format. The request body could not be parsed.",
    "response": "Invalid request format"
  }
}
```




```json
{
  "detail": {
    "cause": "Missing required attributes: ['query', 'model', 'provider']",
    "response": "Missing required attributes"
  }
}
```




```json
{
  "detail": {
    "cause": "Invalid attatchment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```
 |
| 429 | Quota limit exceeded | [QuotaExceededResponse](#quotaexceededresponse)

Examples





```json
{
  "detail": {
    "cause": "The token quota for model gpt-4-turbo has been exceeded.",
    "response": "The model quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has 5 tokens, but 10 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has 500 tokens, but 900 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/v1/config`

> **Config Endpoint Handler**

Handle requests to the /config endpoint.

Process GET requests to the /config endpoint and returns the
current service configuration.

Returns:
    ConfigurationResponse: The loaded service configuration response.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ConfigurationResponse](#configurationresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
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
| 200 | Successful response | [FeedbackResponse](#feedbackresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```




```json
{
  "detail": {
    "cause": "Storing feedback is disabled.",
    "response": "Storing feedback is disabled"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Failed to store feedback at directory: /path/example",
    "response": "Failed to store feedback"
  }
}
```
 |
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
| 200 | Successful response | [StatusResponse](#statusresponse) |
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
| 200 | Successful response | [FeedbackStatusUpdateResponse](#feedbackstatusupdateresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/v1/conversations`

> **Get Conversations List Endpoint Handler**

Handle request to retrieve all conversations for the authenticated user.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ConversationsListResponse](#conversationslistresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Failed to query the database",
    "response": "Database query failed"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
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
| 200 | Successful response | [ConversationResponse](#conversationresponse) |
| 400 | Invalid request format | [BadRequestResponse](#badrequestresponse)

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```
 |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 does not have permission to read conversation with ID 123e4567-e89b-12d3-a456-426614174000",
    "response": "User does not have permission to perform this action"
  }
}
```




```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Failed to query the database",
    "response": "Database query failed"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
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
| 200 | Successful response | [ConversationDeleteResponse](#conversationdeleteresponse)

Examples





```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "response": "Conversation deleted successfully",
  "success": true
}
```




```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "response": "Conversation can not be deleted",
  "success": true
}
```
 |
| 400 | Invalid request format | [BadRequestResponse](#badrequestresponse)

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```
 |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 does not have permission to delete conversation with ID 123e4567-e89b-12d3-a456-426614174000",
    "response": "User does not have permission to perform this action"
  }
}
```




```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Failed to query the database",
    "response": "Database query failed"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## GET `/v2/conversations`

> **Get Conversations List Endpoint Handler**

Handle request to retrieve all conversations for the authenticated user.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ConversationsListResponseV2](#conversationslistresponsev2) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Conversation cache is not configured or unavailable.",
    "response": "Conversation cache not configured"
  }
}
```
 |
## GET `/v2/conversations/{conversation_id}`

> **Get Conversation Endpoint Handler**

Handle request to retrieve a conversation by ID.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ConversationResponse](#conversationresponse) |
| 400 | Invalid request format | [BadRequestResponse](#badrequestresponse)

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```
 |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Conversation cache is not configured or unavailable.",
    "response": "Conversation cache not configured"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## DELETE `/v2/conversations/{conversation_id}`

> **Delete Conversation Endpoint Handler**

Handle request to delete a conversation by ID.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ConversationDeleteResponse](#conversationdeleteresponse)

Examples





```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "response": "Conversation deleted successfully",
  "success": true
}
```




```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "response": "Conversation can not be deleted",
  "success": true
}
```
 |
| 400 | Invalid request format | [BadRequestResponse](#badrequestresponse)

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```
 |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Conversation cache is not configured or unavailable.",
    "response": "Conversation cache not configured"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## PUT `/v2/conversations/{conversation_id}`

> **Update Conversation Endpoint Handler**

Handle request to update a conversation topic summary by ID.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### 📦 Request Body 

[ConversationUpdateRequest](#conversationupdaterequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ConversationUpdateResponse](#conversationupdateresponse) |
| 400 | Invalid request format | [BadRequestResponse](#badrequestresponse)

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```
 |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```




```json
{
  "detail": {
    "cause": "Conversation cache is not configured or unavailable.",
    "response": "Conversation cache not configured"
  }
}
```
 |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |
## POST `/v2/query`

> **Query Endpoint Handler V2**

Handle request to the /query endpoint using Responses API.

This is a wrapper around query_endpoint_handler_base that provides
the Responses API specific retrieve_response and get_topic_summary functions.

Returns:
    QueryResponse: Contains the conversation ID and the LLM-generated response.





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [QueryResponse](#queryresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 does not have permission to read conversation with ID 123e4567-e89b-12d3-a456-426614174000",
    "response": "User does not have permission to perform this action"
  }
}
```




```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```




```json
{
  "detail": {
    "cause": "User lacks model_override permission required to override model/provider.",
    "response": "This instance does not permit overriding model/provider in the query request (missing permission: MODEL_OVERRIDE). Please remove the model and provider fields from your request."
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Provider with ID openai does not exist",
    "response": "Provider not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Model with ID gpt-4-turbo is not configured",
    "response": "Model not found"
  }
}
```
 |
| 422 | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse)

Examples





```json
{
  "detail": {
    "cause": "Invalid request format. The request body could not be parsed.",
    "response": "Invalid request format"
  }
}
```




```json
{
  "detail": {
    "cause": "Missing required attributes: ['query', 'model', 'provider']",
    "response": "Missing required attributes"
  }
}
```




```json
{
  "detail": {
    "cause": "Invalid attatchment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```
 |
| 429 | Quota limit exceeded | [QuotaExceededResponse](#quotaexceededresponse)

Examples





```json
{
  "detail": {
    "cause": "The token quota for model gpt-4-turbo has been exceeded.",
    "response": "The model quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has 5 tokens, but 10 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has 500 tokens, but 900 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## POST `/v2/streaming_query`

> **Streaming Query Endpoint Handler V2**

Handle request to the /streaming_query endpoint using Responses API.

This is a wrapper around streaming_query_endpoint_handler_base that provides
the Responses API specific retrieve_response and response generator functions.

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
| 200 | Streaming response with Server-Sent Events | string
string |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 does not have permission to read conversation with ID 123e4567-e89b-12d3-a456-426614174000",
    "response": "User does not have permission to perform this action"
  }
}
```




```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```




```json
{
  "detail": {
    "cause": "User lacks model_override permission required to override model/provider.",
    "response": "This instance does not permit overriding model/provider in the query request (missing permission: MODEL_OVERRIDE). Please remove the model and provider fields from your request."
  }
}
```
 |
| 404 | Resource not found | [NotFoundResponse](#notfoundresponse)

Examples





```json
{
  "detail": {
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Provider with ID openai does not exist",
    "response": "Provider not found"
  }
}
```




```json
{
  "detail": {
    "cause": "Model with ID gpt-4-turbo is not configured",
    "response": "Model not found"
  }
}
```
 |
| 422 | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse)

Examples





```json
{
  "detail": {
    "cause": "Invalid request format. The request body could not be parsed.",
    "response": "Invalid request format"
  }
}
```




```json
{
  "detail": {
    "cause": "Missing required attributes: ['query', 'model', 'provider']",
    "response": "Missing required attributes"
  }
}
```




```json
{
  "detail": {
    "cause": "Invalid attatchment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```
 |
| 429 | Quota limit exceeded | [QuotaExceededResponse](#quotaexceededresponse)

Examples





```json
{
  "detail": {
    "cause": "The token quota for model gpt-4-turbo has been exceeded.",
    "response": "The model quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has no available tokens.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "User 123 has 5 tokens, but 10 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Cluster has 500 tokens, but 900 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```




```json
{
  "detail": {
    "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed.",
    "response": "The quota has been exceeded"
  }
}
```
 |
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)

Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/readiness`

> **Readiness Probe Get Method**

Handle the readiness probe endpoint, returning service readiness.

If any provider reports an error status, responds with HTTP 503
and details of unhealthy providers; otherwise, indicates the
service is ready.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [ReadinessResponse](#readinessresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse)

Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
 |
## GET `/liveness`

> **Liveness Probe Get Method**

Return the liveness status of the service.

Returns:
    LivenessResponse: Indicates that the service is alive.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [LivenessResponse](#livenessresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
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
| 200 | Successful response | [AuthorizedResponse](#authorizedresponse) |
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse)

Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```
 |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse)

Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```
 |
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
| 401 | Unauthorized | ...
Examples





```json
{
  "detail": {
    "cause": "No Authorization header found",
    "response": "Missing or invalid credentials provided by client"
  }
}
```




```json
{
  "detail": {
    "cause": "No token found in Authorization header",
    "response": "Missing or invalid credentials provided by client"
  }
}
```

[UnauthorizedResponse](#unauthorizedresponse) |
| 403 | Permission denied | ...
Examples





```json
{
  "detail": {
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

[ForbiddenResponse](#forbiddenresponse) |
| 500 | Internal server error | ...
Examples





```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```

[InternalServerErrorResponse](#internalservererrorresponse) |
| 503 | Service unavailable | ...
Examples





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

[ServiceUnavailableResponse](#serviceunavailableresponse) |
---

# 📋 Components



## APIKeyTokenConfiguration


API Key Token configuration.


| Field | Type | Description |
|-------|------|-------------|
| api_key | string |  |


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
| api_key_config |  |  |
| rh_identity_config |  |  |


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
    skip_userid_check: Whether to skip the user ID check.


| Field | Type | Description |
|-------|------|-------------|
| user_id | string | User ID, for example UUID |
| username | string | User name |
| skip_userid_check | boolean | Whether to skip the user ID check |


## BadRequestResponse


400 Bad Request. Invalid resource identifier.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## ByokRag


BYOK RAG configuration.


| Field | Type | Description |
|-------|------|-------------|
| rag_id | string |  |
| rag_type | string |  |
| embedding_model | string |  |
| embedding_dimension | integer |  |
| vector_db_id | string |  |
| db_path | string |  |


## CORSConfiguration


CORS configuration.

CORS or 'Cross-Origin Resource Sharing' refers to the situations when a
frontend running in a browser has JavaScript code that communicates with a
backend, and the backend is in a different 'origin' than the frontend.

Useful resources:

  - [CORS in FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)
  - [Wikipedia article](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing)
  - [What is CORS?](https://dev.to/akshay_chauhan/what-is-cors-explained-8f1)


| Field | Type | Description |
|-------|------|-------------|
| allow_origins | array | A list of origins allowed for cross-origin requests. An origin is the combination of protocol (http, https), domain (myapp.com, localhost, localhost.tiangolo.com), and port (80, 443, 8080). Use ['*'] to allow all origins. |
| allow_credentials | boolean | Indicate that cookies should be supported for cross-origin requests |
| allow_methods | array | A list of HTTP methods that should be allowed for cross-origin requests. You can use ['*'] to allow all standard methods. |
| allow_headers | array | A list of HTTP request headers that should be supported for cross-origin requests. You can use ['*'] to allow all headers. The Accept, Accept-Language, Content-Language and Content-Type headers are always allowed for simple CORS requests. |


## Configuration


Global service configuration.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Name of the service. That value will be used in REST API endpoints. |
| service |  | This section contains Lightspeed Core Stack service configuration. |
| llama_stack |  | This section contains Llama Stack configuration. Lightspeed Core Stack service can call Llama Stack in library mode or in server mode. |
| user_data_collection |  | This section contains configuration for subsystem that collects user data(transcription history and feedbacks). |
| database |  | Configuration for database to store conversation IDs and other runtime data |
| mcp_servers | array | MCP (Model Context Protocol) servers provide tools and capabilities to the AI agents. These are configured in this section. Only MCP servers defined in the lightspeed-stack.yaml configuration are available to the agents. Tools configured in the llama-stack run.yaml are not accessible to lightspeed-core agents. |
| authentication |  | Authentication configuration |
| authorization |  | Lightspeed Core Stack implements a modular authentication and authorization system with multiple authentication methods. Authorization is configurable through role-based access control. Authentication is handled through selectable modules configured via the module field in the authentication configuration. |
| customization |  | It is possible to customize Lightspeed Core Stack via this section. System prompt can be customized and also different parts of the service can be replaced by custom Python modules. |
| inference |  | One LLM provider and one its model might be selected as default ones. When no provider+model pair is specified in REST API calls (query endpoints), the default provider and model are used. |
| conversation_cache |  |  |
| byok_rag | array | BYOK RAG configuration. This configuration can be used to reconfigure Llama Stack through its run.yaml configuration file |
| quota_handlers |  | Quota handlers configuration |


## ConfigurationResponse


Success response model for the config endpoint.


| Field | Type | Description |
|-------|------|-------------|
| configuration |  |  |


## ConversationData


Model representing conversation data returned by cache list operations.

Attributes:
    conversation_id: The conversation ID
    topic_summary: The topic summary for the conversation (can be None)
    last_message_timestamp: The timestamp of the last message in the conversation


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| topic_summary |  |  |
| last_message_timestamp | number |  |


## ConversationDeleteResponse


Model representing a response for deleting a conversation.

Attributes:
    conversation_id: The conversation ID (UUID) that was deleted.
    success: Whether the deletion was successful.
    response: A message about the deletion result.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | The conversation ID (UUID) that was deleted. |
| success | boolean | Whether the deletion was successful. |
| response | string | A message about the deletion result. |


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


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | Conversation ID (UUID) |
| created_at |  | When the conversation was created |
| last_message_at |  | When the last message was sent |
| message_count |  | Number of user messages in the conversation |
| last_used_model |  | Identification of the last model used for the conversation |
| last_used_provider |  | Identification of the last provider used for the conversation |
| topic_summary |  | Topic summary for the conversation |


## ConversationHistoryConfiguration


Conversation history configuration.


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |
| memory |  |  |
| sqlite |  |  |
| postgres |  |  |


## ConversationResponse


Model representing a response for retrieving a conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    chat_history: The simplified chat history as a list of conversation turns.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | Conversation ID (UUID) |
| chat_history | array | The simplified chat history as a list of conversation turns |


## ConversationUpdateRequest


Model representing a request to update a conversation topic summary.

Attributes:
    topic_summary: The new topic summary for the conversation.

Example:
    ```python
    update_request = ConversationUpdateRequest(
        topic_summary="Discussion about machine learning algorithms"
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| topic_summary | string | The new topic summary for the conversation |


## ConversationUpdateResponse


Model representing a response for updating a conversation topic summary.

Attributes:
    conversation_id: The conversation ID (UUID) that was updated.
    success: Whether the update was successful.
    message: A message about the update result.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | The conversation ID (UUID) that was updated |
| success | boolean | Whether the update was successful |
| message | string | A message about the update result |


## ConversationsListResponse


Model representing a response for listing conversations of a user.

Attributes:
    conversations: List of conversation details associated with the user.


| Field | Type | Description |
|-------|------|-------------|
| conversations | array |  |


## ConversationsListResponseV2


Model representing a response for listing conversations of a user.

Attributes:
    conversations: List of conversation data associated with the user.


| Field | Type | Description |
|-------|------|-------------|
| conversations | array |  |


## CustomProfile


Custom profile customization for prompts and validation.


| Field | Type | Description |
|-------|------|-------------|
| path | string |  |
| prompts | object |  |


## Customization


Service customization.


| Field | Type | Description |
|-------|------|-------------|
| profile_path |  |  |
| disable_query_system_prompt | boolean |  |
| system_prompt_path |  |  |
| system_prompt |  |  |
| custom_profile |  |  |


## DatabaseConfiguration


Database configuration.


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |


## DetailModel


Nested detail model for error responses.


| Field | Type | Description |
|-------|------|-------------|
| response | string | Short summary of the error |
| cause | string | Detailed explanation of what caused the error |


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


| Field | Type | Description |
|-------|------|-------------|
| response | string | The response of the feedback request. |


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


| Field | Type | Description |
|-------|------|-------------|
| status | object |  |


## ForbiddenResponse


403 Forbidden. Access denied.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## HTTPValidationError



| Field | Type | Description |
|-------|------|-------------|
| detail | array |  |


## InMemoryCacheConfig


In-memory cache configuration.


| Field | Type | Description |
|-------|------|-------------|
| max_entries | integer | Maximum number of entries stored in the in-memory cache |


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


| Field | Type | Description |
|-------|------|-------------|
| name | string | Service name |
| service_version | string | Service version |
| llama_stack_version | string | Llama Stack version |


## InternalServerErrorResponse


500 Internal Server Error.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


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
| jsonpath | string | JSONPath expression to evaluate against the JWT payload |
| operator |  | JSON path comparison operator |
| negate | boolean | If set to true, the meaning of the rule is negated |
| value |  | Value to compare against |
| roles | array | Roles to be assigned if the rule matches |


## LivenessResponse


Model representing a response to a liveness request.

Attributes:
    alive: If app is alive.


| Field | Type | Description |
|-------|------|-------------|
| alive | boolean | Flag indicating that the app is alive |


## LlamaStackConfiguration


Llama stack configuration.

Llama Stack is a comprehensive system that provides a uniform set of tools
for building, scaling, and deploying generative AI applications, enabling
developers to create, integrate, and orchestrate multiple AI services and
capabilities into an adaptable setup.

Useful resources:

  - [Llama Stack](https://www.llama.com/products/llama-stack/)
  - [Python Llama Stack client](https://github.com/llamastack/llama-stack-client-python)
  - [Build AI Applications with Llama Stack](https://llamastack.github.io/)


| Field | Type | Description |
|-------|------|-------------|
| url |  | URL to Llama Stack service; used when library mode is disabled |
| api_key |  | API key to access Llama Stack service |
| use_as_library_client |  | When set to true Llama Stack will be used in library mode, not in server mode (default) |
| library_client_config_path |  | Path to configuration file used when Llama Stack is run in library mode |


## ModelContextProtocolServer


Model context protocol server configuration.

MCP (Model Context Protocol) servers provide tools and
capabilities to the AI agents. These are configured by this structure.
Only MCP servers defined in the lightspeed-stack.yaml configuration are
available to the agents. Tools configured in the llama-stack run.yaml
are not accessible to lightspeed-core agents.

Useful resources:

- [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)
- [MCP FAQs](https://modelcontextprotocol.io/faqs)
- [Wikipedia article](https://en.wikipedia.org/wiki/Model_Context_Protocol)


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name that must be unique |
| provider_id | string | MCP provider identification |
| url | string | URL of the MCP server |


## ModelsResponse


Model representing a response to models request.


| Field | Type | Description |
|-------|------|-------------|
| models | array | List of models available |


## NotFoundResponse


404 Not Found - Resource does not exist.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## PostgreSQLDatabaseConfiguration


PostgreSQL database configuration.

PostgreSQL database is used by Lightspeed Core Stack service for storing information about
conversation IDs. It can also be leveraged to store conversation history and information
about quota usage.

Useful resources:

- [Psycopg: connection classes](https://www.psycopg.org/psycopg3/docs/api/connections.html)
- [PostgreSQL connection strings](https://www.connectionstrings.com/postgresql/)
- [How to Use PostgreSQL in Python](https://www.freecodecamp.org/news/postgresql-in-python/)


| Field | Type | Description |
|-------|------|-------------|
| host | string | Database server host or socket directory |
| port | integer | Database server port |
| db | string | Database name to connect to |
| user | string | Database user name used to authenticate |
| password | string | Password used to authenticate |
| namespace |  | Database namespace |
| ssl_mode | string | SSL mode |
| gss_encmode | string | This option determines whether or with what priority a secure GSS TCP/IP connection will be negotiated with the server. |
| ca_cert_path |  | Path to CA certificate |


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


## ProviderResponse


Model representing a response to get specific provider request.


| Field | Type | Description |
|-------|------|-------------|
| api | string | The API this provider implements |
| config | object | Provider configuration parameters |
| health | object | Current health status of the provider |
| provider_id | string | Unique provider identifier |
| provider_type | string | Provider implementation type |


## ProvidersListResponse


Model representing a response to providers request.


| Field | Type | Description |
|-------|------|-------------|
| providers | object | List of available API types and their corresponding providers |


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
| generate_topic_summary |  | Whether to generate topic summary for new conversations |
| media_type |  | Media type for the response format |


## QueryResponse


Model representing LLM response to a query.

Attributes:
    conversation_id: The optional conversation ID (UUID).
    response: The response.
    rag_chunks: List of RAG chunks used to generate the response.
    referenced_documents: The URLs and titles for the documents used to generate the response.
    tool_calls: List of tool calls made during response generation.
    truncated: Whether conversation history was truncated.
    input_tokens: Number of tokens sent to LLM.
    output_tokens: Number of tokens received from LLM.
    available_quotas: Quota available as measured by all configured quota limiters.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id |  | The optional conversation ID (UUID) |
| response | string | Response from LLM |
| rag_chunks | array | List of RAG chunks used to generate the response |
| tool_calls |  | List of tool calls made during response generation |
| referenced_documents | array | List of documents referenced in generating the response |
| truncated | boolean | Whether conversation history was truncated |
| input_tokens | integer | Number of tokens sent to LLM |
| output_tokens | integer | Number of tokens received from LLM |
| available_quotas | object | Quota available as measured by all configured quota limiters |


## QuotaExceededResponse


429 Too Many Requests - Quota limit exceeded.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## QuotaHandlersConfiguration


Quota limiter configuration.

It is possible to limit quota usage per user or per service or services
(that typically run in one cluster). Each limit is configured as a separate
_quota limiter_. It can be of type `user_limiter` or `cluster_limiter`
(which is name that makes sense in OpenShift deployment).


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |
| limiters | array | Quota limiters configuration |
| scheduler |  | Quota scheduler configuration |
| enable_token_history | boolean | Enables storing information about token usage history |


## QuotaLimiterConfiguration


Configuration for one quota limiter.

There are three configuration options for each limiter:

1. ``period`` is specified in a human-readable form, see
   https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-INTERVAL-INPUT
   for all possible options. When the end of the period is reached, the
   quota is reset or increased.
2. ``initial_quota`` is the value set at the beginning of the period.
3. ``quota_increase`` is the value (if specified) used to increase the
   quota when the period is reached.

There are two basic use cases:

1. When the quota needs to be reset to a specific value periodically (for
   example on a weekly or monthly basis), set ``initial_quota`` to the
   required value.
2. When the quota needs to be increased by a specific value periodically
   (for example on a daily basis), set ``quota_increase``.


| Field | Type | Description |
|-------|------|-------------|
| type | string | Quota limiter type, either user_limiter or cluster_limiter |
| name | string | Human readable quota limiter name |
| initial_quota | integer | Quota set at beginning of the period |
| quota_increase | integer | Delta value used to increase quota when period is reached |
| period | string | Period specified in human readable form |


## QuotaSchedulerConfiguration


Quota scheduler configuration.


| Field | Type | Description |
|-------|------|-------------|
| period | integer | Quota scheduler period specified in seconds |


## RAGChunk


Model representing a RAG chunk used in the response.


| Field | Type | Description |
|-------|------|-------------|
| content | string | The content of the chunk |
| source |  | Source document or URL |
| score |  | Relevance score |


## RAGInfoResponse


Model representing a response with information about RAG DB.


| Field | Type | Description |
|-------|------|-------------|
| id | string | Vector DB unique ID |
| name |  | Human readable vector DB name |
| created_at | integer | When the vector store was created, represented as Unix time |
| last_active_at |  | When the vector store was last active, represented as Unix time |
| usage_bytes | integer | Storage byte(s) used by this vector DB |
| expires_at |  | When the vector store expires, represented as Unix time |
| object | string | Object type |
| status | string | Vector DB status |


## RAGListResponse


Model representing a response to list RAGs request.


| Field | Type | Description |
|-------|------|-------------|
| rags | array | List of RAG identifiers |


## RHIdentityConfiguration


Red Hat Identity authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| required_entitlements |  |  |


## ReadinessResponse


Model representing response to a readiness request.

Attributes:
    ready: If service is ready.
    reason: The reason for the readiness.
    providers: List of unhealthy providers in case of readiness failure.


| Field | Type | Description |
|-------|------|-------------|
| ready | boolean | Flag indicating if service is ready |
| reason | string | The reason for the readiness |
| providers | array | List of unhealthy providers in case of readiness failure. |


## ReferencedDocument


Model representing a document referenced in generating a response.

Attributes:
    doc_url: Url to the referenced doc.
    doc_title: Title of the referenced doc.


| Field | Type | Description |
|-------|------|-------------|
| doc_url |  | URL of the referenced document |
| doc_title |  | Title of the referenced document |


## SQLiteDatabaseConfiguration


SQLite database configuration.


| Field | Type | Description |
|-------|------|-------------|
| db_path | string | Path to file where SQLite database is stored |


## ServiceConfiguration


Service configuration.

Lightspeed Core Stack is a REST API service that accepts requests
on a specified hostname and port. It is also possible to enable
authentication and specify the number of Uvicorn workers. When more
workers are specified, the service can handle requests concurrently.


| Field | Type | Description |
|-------|------|-------------|
| host | string | Service hostname |
| port | integer | Service port |
| auth_enabled | boolean | Enables the authentication subsystem |
| workers | integer | Number of Uvicorn worker processes to start |
| color_log | boolean | Enables colorized logging |
| access_log | boolean | Enables logging of all access information |
| tls_config |  | Transport Layer Security configuration for HTTPS support |
| cors |  | Cross-Origin Resource Sharing configuration for cross-domain requests |


## ServiceUnavailableResponse


503 Backend Unavailable.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## ShieldsResponse


Model representing a response to shields request.


| Field | Type | Description |
|-------|------|-------------|
| shields | array | List of shields available |


## StatusResponse


Model representing a response to a status request.

Attributes:
    functionality: The functionality of the service.
    status: The status of the service.


| Field | Type | Description |
|-------|------|-------------|
| functionality | string | The functionality of the service |
| status | object | The status of the service |


## TLSConfiguration


TLS configuration.

Transport Layer Security (TLS) is a cryptographic protocol designed to
provide communications security over a computer network, such as the
Internet. The protocol is widely used in applications such as email,
instant messaging, and voice over IP, but its use in securing HTTPS remains
the most publicly visible.

Useful resources:

  - [FastAPI HTTPS Deployment](https://fastapi.tiangolo.com/deployment/https/)
  - [Transport Layer Security Overview](https://en.wikipedia.org/wiki/Transport_Layer_Security)
  - [What is TLS](https://www.ssltrust.eu/learning/ssl/transport-layer-security-tls)


| Field | Type | Description |
|-------|------|-------------|
| tls_certificate_path |  | SSL/TLS certificate file path for HTTPS support. |
| tls_key_path |  | SSL/TLS private key file path for HTTPS support. |
| tls_key_password |  | Path to file containing the password to decrypt the SSL/TLS private key. |


## ToolCall


Model representing a tool call made during response generation.


| Field | Type | Description |
|-------|------|-------------|
| tool_name | string | Name of the tool called |
| arguments | object | Arguments passed to the tool |
| result |  | Result from the tool |


## ToolsResponse


Model representing a response to tools request.


| Field | Type | Description |
|-------|------|-------------|
| tools | array | List of tools available from all configured MCP servers and built-in toolgroups |


## UnauthorizedResponse


401 Unauthorized - Missing or invalid credentials.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## UnprocessableEntityResponse


422 Unprocessable Entity - Request validation failed.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


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
