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

Raises:
    HTTPException: with status 500 and a detail object
    containing `response` and `cause` when unable to connect to
    Llama Stack. It can also return status 401 or 403 for
    unauthorized access.

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
## GET `/v1/mcp-auth/client-options`

> **Get Mcp Client Auth Options**

Get MCP servers that accept client-provided authorization.

Returns a list of MCP servers configured to accept client-provided
authorization tokens, along with the header names where clients
should provide these tokens.

This endpoint helps clients discover which MCP servers they can
authenticate with using their own tokens.

Args:
    request: The incoming HTTP request (used by middleware).
    auth: Authentication tuple from the auth dependency (used by middleware).

Returns:
    MCPClientAuthOptionsResponse: List of MCP servers and their
        accepted client authentication headers.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [MCPClientAuthOptionsResponse](#mcpclientauthoptionsresponse) |
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

> **Query Endpoint Handler V1**

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
## POST `/v1/streaming_query`

> **Streaming Query Endpoint Handler V1**

Handle request to the /streaming_query endpoint using Responses API.

Returns a streaming response using Server-Sent Events (SSE) format with
content type text/event-stream.

Returns:
    StreamingResponse: An HTTP streaming response yielding
    SSE-formatted events for the query lifecycle with content type
    text/event-stream.

Raises:
    HTTPException:
        - 401: Unauthorized - Missing or invalid credentials
        - 403: Forbidden - Insufficient permissions or model override not allowed
        - 404: Not Found - Conversation, model, or provider not found
        - 422: Unprocessable Entity - Request validation failed
        - 429: Too Many Requests - Quota limit exceeded
        - 500: Internal Server Error - Configuration not loaded or other server errors
        - 503: Service Unavailable - Unable to connect to Llama Stack backend





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | string |
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

Ensures the application configuration is loaded before returning it.

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
    HTTPException: Returns HTTP 404 if conversation does not exist.
    HTTPException: Returns HTTP 403 if conversation belongs to a different user.
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

> **Conversations List Endpoint Handler V1**

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
## GET `/v1/conversations/{conversation_id}`

> **Conversation Get Endpoint Handler V1**

Handle request to retrieve a conversation by ID using Conversations API.

Retrieve a conversation's chat history by its ID using the LlamaStack
Conversations API. This endpoint fetches the conversation items from
the backend, simplifies them to essential chat history, and returns
them in a structured response. Raises HTTP 400 for invalid IDs, 404
if not found, 503 if the backend is unavailable, and 500 for
unexpected errors.

Args:
    request: The FastAPI request object
    conversation_id: Unique identifier of the conversation to retrieve
    auth: Authentication tuple from dependency

Returns:
    ConversationResponse: Structured response containing the conversation
    ID and simplified chat history



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

> **Conversation Delete Endpoint Handler V1**

Handle request to delete a conversation by ID using Conversations API.

Validates the conversation ID format and attempts to delete the
conversation from the Llama Stack backend using the Conversations API.
Raises HTTP errors for invalid IDs, not found conversations, connection
issues, or unexpected failures.

Args:
    request: The FastAPI request object
    conversation_id: Unique identifier of the conversation to delete
    auth: Authentication tuple from dependency

Returns:
    ConversationDeleteResponse: Response indicating the result of the deletion operation



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
## PUT `/v1/conversations/{conversation_id}`

> **Conversation Update Endpoint Handler V1**

Handle request to update a conversation metadata using Conversations API.

Updates the conversation metadata (including topic summary) in both the
LlamaStack backend using the Conversations API and the local database.

Args:
    request: The FastAPI request object
    conversation_id: Unique identifier of the conversation to update
    update_request: Request containing the topic summary to update
    auth: Authentication tuple from dependency

Returns:
    ConversationUpdateResponse: Response indicating the result of the update operation



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
## POST `/v1/infer`

> **Infer Endpoint**

Handle rlsapi v1 /infer requests for stateless inference.

This endpoint serves requests from the RHEL Lightspeed Command Line Assistant (CLA).

Accepts a question with optional context (stdin, attachments, terminal output,
system info) and returns an LLM-generated response.

Args:
    infer_request: The inference request containing question and context.
    request: The FastAPI request object for accessing headers and state.
    background_tasks: FastAPI background tasks for async Splunk event sending.
    auth: Authentication tuple from the configured auth provider.

Returns:
    RlsapiV1InferResponse containing the generated response text and request ID.

Raises:
    HTTPException: 503 if the LLM service is unavailable.





### 📦 Request Body 

[RlsapiV1InferRequest](#rlsapiv1inferrequest)

### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful response | [RlsapiV1InferResponse](#rlsapiv1inferresponse) |
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
| 500 | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
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

Returns:
    ReadinessResponse: Object with `ready` indicating overall readiness,
    `reason` explaining the outcome, and `providers` containing the list of
    unhealthy ProviderHealthStatus entries (empty when ready).





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

The response intentionally omits any authentication token.

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

Returns:
    PlainTextResponse: Response body containing the Prometheus metrics text
    and the Prometheus content type.





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
## GET `/.well-known/agent-card.json`

> **Get Agent Card**

Serve the A2A Agent Card at the well-known location.

This endpoint provides the agent card that describes Lightspeed's
capabilities according to the A2A protocol specification.

Returns:
    AgentCard: The agent card describing this agent's capabilities.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [AgentCard](#agentcard) |
## GET `/.well-known/agent.json`

> **Get Agent Card**

Serve the A2A Agent Card at the well-known location.

This endpoint provides the agent card that describes Lightspeed's
capabilities according to the A2A protocol specification.

Returns:
    AgentCard: The agent card describing this agent's capabilities.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | [AgentCard](#agentcard) |
## GET `/a2a`

> **Handle A2A Jsonrpc**

Handle A2A JSON-RPC requests following the A2A protocol specification.

This endpoint uses the DefaultRequestHandler from the A2A SDK to handle
all JSON-RPC requests including message/send, message/stream, etc.

The A2A SDK application is created per-request to include authentication
context while still leveraging FastAPI's authorization middleware.

Automatically detects streaming requests (message/stream JSON-RPC method)
and returns a StreamingResponse to enable real-time chunk delivery.

Args:
    request: FastAPI request object
    auth: Authentication tuple
    mcp_headers: MCP headers for context propagation

Returns:
    JSON-RPC response or streaming response





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | ... |
## POST `/a2a`

> **Handle A2A Jsonrpc**

Handle A2A JSON-RPC requests following the A2A protocol specification.

This endpoint uses the DefaultRequestHandler from the A2A SDK to handle
all JSON-RPC requests including message/send, message/stream, etc.

The A2A SDK application is created per-request to include authentication
context while still leveraging FastAPI's authorization middleware.

Automatically detects streaming requests (message/stream JSON-RPC method)
and returns a StreamingResponse to enable real-time chunk delivery.

Args:
    request: FastAPI request object
    auth: Authentication tuple
    mcp_headers: MCP headers for context propagation

Returns:
    JSON-RPC response or streaming response





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | ... |
## GET `/a2a/health`

> **A2A Health Check**

Health check endpoint for A2A service.

Returns:
    Dict with health status information.





### ✅ Responses

| Status Code | Description | Component |
|-------------|-------------|-----------|
| 200 | Successful Response | object |
---

# 📋 Components



## A2AStateConfiguration


A2A protocol persistent state configuration.

Configures how A2A task state and context-to-conversation mappings are
stored. For multi-worker deployments, use SQLite or PostgreSQL to ensure
state is shared across all workers.

If no configuration is provided, in-memory storage is used (default).
This is suitable for single-worker deployments but state will be lost
on restarts and not shared across workers.

Attributes:
    sqlite: SQLite database configuration for A2A state storage.
    postgres: PostgreSQL database configuration for A2A state storage.


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  | SQLite database configuration for A2A state storage. |
| postgres |  | PostgreSQL database configuration for A2A state storage. |


## APIKeySecurityScheme


Defines a security scheme using an API key.


| Field | Type | Description |
|-------|------|-------------|
| description |  |  |
| in |  |  |
| name | string |  |
| type | string |  |


## APIKeyTokenConfiguration


API Key Token configuration.


| Field | Type | Description |
|-------|------|-------------|
| api_key | string |  |


## AccessRule


Rule defining what actions a role can perform.


| Field | Type | Description |
|-------|------|-------------|
| role | string | Name of the role |
| actions | array | Allowed actions for this role |


## Action


Available actions in the system.

Note: this is not a real model, just an enumeration of all action names.




## AgentCapabilities


Defines optional capabilities supported by an agent.


| Field | Type | Description |
|-------|------|-------------|
| extensions |  |  |
| pushNotifications |  |  |
| stateTransitionHistory |  |  |
| streaming |  |  |


## AgentCard


The AgentCard is a self-describing manifest for an agent. It provides essential
metadata including the agent's identity, capabilities, skills, supported
communication methods, and security requirements.


| Field | Type | Description |
|-------|------|-------------|
| additionalInterfaces |  |  |
| capabilities |  |  |
| defaultInputModes | array |  |
| defaultOutputModes | array |  |
| description | string |  |
| documentationUrl |  |  |
| iconUrl |  |  |
| name | string |  |
| preferredTransport |  |  |
| protocolVersion |  |  |
| provider |  |  |
| security |  |  |
| securitySchemes |  |  |
| signatures |  |  |
| skills | array |  |
| supportsAuthenticatedExtendedCard |  |  |
| url | string |  |
| version | string |  |


## AgentCardSignature


AgentCardSignature represents a JWS signature of an AgentCard.
This follows the JSON format of an RFC 7515 JSON Web Signature (JWS).


| Field | Type | Description |
|-------|------|-------------|
| header |  |  |
| protected | string |  |
| signature | string |  |


## AgentExtension


A declaration of a protocol extension supported by an Agent.


| Field | Type | Description |
|-------|------|-------------|
| description |  |  |
| params |  |  |
| required |  |  |
| uri | string |  |


## AgentInterface


Declares a combination of a target URL and a transport protocol for interacting with the agent.
This allows agents to expose the same functionality over multiple transport mechanisms.


| Field | Type | Description |
|-------|------|-------------|
| transport | string |  |
| url | string |  |


## AgentProvider


Represents the service provider of an agent.


| Field | Type | Description |
|-------|------|-------------|
| organization | string |  |
| url | string |  |


## AgentSkill


Represents a distinct capability or function that an agent can perform.


| Field | Type | Description |
|-------|------|-------------|
| description | string |  |
| examples |  |  |
| id | string |  |
| inputModes |  |  |
| name | string |  |
| outputModes |  |  |
| security |  |  |
| tags | array |  |


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
| skip_for_health_probes | boolean | Skip authorization for readiness and liveness probes |
| k8s_cluster_api |  |  |
| k8s_ca_cert_path |  |  |
| jwk_config |  |  |
| api_key_config |  |  |
| rh_identity_config |  |  |


## AuthorizationCodeOAuthFlow


Defines configuration details for the OAuth 2.0 Authorization Code flow.


| Field | Type | Description |
|-------|------|-------------|
| authorizationUrl | string |  |
| refreshUrl |  |  |
| scopes | object |  |
| tokenUrl | string |  |


## AuthorizationConfiguration


Authorization configuration.


| Field | Type | Description |
|-------|------|-------------|
| access_rules | array | Rules for role-based access control |


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


## AzureEntraIdConfiguration


Microsoft Entra ID authentication attributes for Azure.


| Field | Type | Description |
|-------|------|-------------|
| tenant_id | string |  |
| client_id | string |  |
| client_secret | string |  |
| scope | string | Azure Cognitive Services scope for token requests. Override only if using a different Azure service. |


## BadRequestResponse


400 Bad Request. Invalid resource identifier.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## ByokRag


BYOK (Bring Your Own Knowledge) RAG configuration.


| Field | Type | Description |
|-------|------|-------------|
| rag_id | string | Unique RAG ID |
| rag_type | string | Type of RAG database. |
| embedding_model | string | Embedding model identification |
| embedding_dimension | integer | Dimensionality of embedding vectors. |
| vector_db_id | string | Vector database identification. |
| db_path | string | Path to RAG database. |


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


## ClientCredentialsOAuthFlow


Defines configuration details for the OAuth 2.0 Client Credentials flow.


| Field | Type | Description |
|-------|------|-------------|
| refreshUrl |  |  |
| scopes | object |  |
| tokenUrl | string |  |


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
| a2a_state |  | Configuration for A2A protocol persistent state storage. |
| quota_handlers |  | Quota handlers configuration |
| azure_entra_id |  |  |
| splunk |  | Splunk HEC configuration for sending telemetry events. |
| deployment_environment | string | Deployment environment name (e.g., 'development', 'staging', 'production'). Used in telemetry events. |


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

Example:
    ```python
    conversation = ConversationDetails(
        conversation_id="123e4567-e89b-12d3-a456-426614174000"
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
| type |  | Type of database where the conversation history is to be stored. |
| memory |  | In-memory cache configuration |
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |


## ConversationResponse


Model representing a response for retrieving a conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    chat_history: The chat history as a list of conversation turns.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | Conversation ID (UUID) |
| chat_history | array | The simplified chat history as a list of conversation turns |


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

Example:
    ```python
    update_response = ConversationUpdateResponse(
        conversation_id="123e4567-e89b-12d3-a456-426614174000",
        success=True,
        message="Topic summary updated successfully",
    )
    ```


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
| path | string | Path to Python modules containing custom profile. |
| prompts | object | Dictionary containing map of system prompts |


## Customization


Service customization.


| Field | Type | Description |
|-------|------|-------------|
| profile_path |  |  |
| disable_query_system_prompt | boolean |  |
| system_prompt_path |  |  |
| system_prompt |  |  |
| agent_card_path |  |  |
| agent_card_config |  |  |
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

Example:
    ```python
    feedback_response = FeedbackResponse(response="feedback received")
    ```


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


403 Forbidden. Access denied.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## HTTPAuthSecurityScheme


Defines a security scheme using HTTP authentication.


| Field | Type | Description |
|-------|------|-------------|
| bearerFormat |  |  |
| description |  |  |
| scheme | string |  |
| type | string |  |


## HTTPValidationError



| Field | Type | Description |
|-------|------|-------------|
| detail | array |  |


## ImplicitOAuthFlow


Defines configuration details for the OAuth 2.0 Implicit flow.


| Field | Type | Description |
|-------|------|-------------|
| authorizationUrl | string |  |
| refreshUrl |  |  |
| scopes | object |  |


## In


The location of the API key.




## InMemoryCacheConfig


In-memory cache configuration.


| Field | Type | Description |
|-------|------|-------------|
| max_entries | integer | Maximum number of entries stored in the in-memory cache |


## InferenceConfiguration


Inference configuration.


| Field | Type | Description |
|-------|------|-------------|
| default_model |  | Identification of default model used when no other model is specified. |
| default_provider |  | Identification of default provider used when no other model is specified. |


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
        llama_stack_version="0.2.22",
    )
    ```


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

Note: this is not a real model, just an enumeration of all supported JSONPath operators.




## JwkConfiguration


JWK (JSON Web Key) configuration.

A JSON Web Key (JWK) is a JavaScript Object Notation (JSON) data structure
that represents a cryptographic key.

Useful resources:

  - [JSON Web Key](https://openid.net/specs/draft-jones-json-web-key-03.html)
  - [RFC 7517](https://www.rfc-editor.org/rfc/rfc7517)


| Field | Type | Description |
|-------|------|-------------|
| url | string | HTTPS URL of the JWK (JSON Web Key) set used to validate JWTs. |
| jwt_configuration |  | JWT (JSON Web Token) configuration |


## JwtConfiguration


JWT (JSON Web Token) configuration.

JSON Web Token (JWT) is a compact, URL-safe means of representing
claims to be transferred between two parties.  The claims in a JWT
are encoded as a JSON object that is used as the payload of a JSON
Web Signature (JWS) structure or as the plaintext of a JSON Web
Encryption (JWE) structure, enabling the claims to be digitally
signed or integrity protected with a Message Authentication Code
(MAC) and/or encrypted.

Useful resources:

  - [JSON Web Token](https://en.wikipedia.org/wiki/JSON_Web_Token)
  - [RFC 7519](https://datatracker.ietf.org/doc/html/rfc7519)
  - [JSON Web Tokens](https://auth0.com/docs/secure/tokens/json-web-tokens)


| Field | Type | Description |
|-------|------|-------------|
| user_id_claim | string | JWT claim name that uniquely identifies the user (subject ID). |
| username_claim | string | JWT claim name that provides the human-readable username. |
| role_rules | array | Rules for extracting roles from JWT claims |


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

Example:
    ```python
    liveness_response = LivenessResponse(alive=True)
    ```


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
| url |  | URL to Llama Stack service; used when library mode is disabled. Must be a valid HTTP or HTTPS URL. |
| api_key |  | API key to access Llama Stack service |
| use_as_library_client |  | When set to true Llama Stack will be used in library mode, not in server mode (default) |
| library_client_config_path |  | Path to configuration file used when Llama Stack is run in library mode |
| timeout | integer | Timeout in seconds for requests to Llama Stack service. Default is 180 seconds (3 minutes) to accommodate long-running RAG queries. |


## MCPClientAuthOptionsResponse


Response containing MCP servers that accept client-provided authorization.


| Field | Type | Description |
|-------|------|-------------|
| servers | array | List of MCP servers that accept client-provided authorization |


## MCPServerAuthInfo


Information about MCP server client authentication options.


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name |
| client_auth_headers | array | List of authentication header names for client-provided tokens |


## Message


Model representing a message in a conversation turn.

Attributes:
    content: The message content.
    type: The type of message.


| Field | Type | Description |
|-------|------|-------------|
| content | string | The message content |
| type | string | The type of message |


## ModelContextProtocolServer


Model context protocol server configuration.

MCP (Model Context Protocol) servers provide tools and capabilities to the
AI agents. These are configured by this structure. Only MCP servers
defined in the lightspeed-stack.yaml configuration are available to the
agents. Tools configured in the llama-stack run.yaml are not accessible to
lightspeed-core agents.

Useful resources:

- [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)
- [MCP FAQs](https://modelcontextprotocol.io/faqs)
- [Wikipedia article](https://en.wikipedia.org/wiki/Model_Context_Protocol)


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name that must be unique |
| provider_id | string | MCP provider identification |
| url | string | URL of the MCP server |
| authorization_headers | object | Headers to send to the MCP server. The map contains the header name and the path to a file containing the header value (secret). There are 2 special cases: 1. Usage of the kubernetes token in the header. To specify this use a string 'kubernetes' instead of the file path. 2. Usage of the client provided token in the header. To specify this use a string 'client' instead of the file path. |
| timeout |  | Timeout in seconds for requests to the MCP server. If not specified, the default timeout from Llama Stack will be used. Note: This field is reserved for future use when Llama Stack adds timeout support. |


## ModelsResponse


Model representing a response to models request.


| Field | Type | Description |
|-------|------|-------------|
| models | array | List of models available |


## MutualTLSSecurityScheme


Defines a security scheme using mTLS authentication.


| Field | Type | Description |
|-------|------|-------------|
| description |  |  |
| type | string |  |


## NotFoundResponse


404 Not Found - Resource does not exist.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


## OAuth2SecurityScheme


Defines a security scheme using OAuth 2.0.


| Field | Type | Description |
|-------|------|-------------|
| description |  |  |
| flows |  |  |
| oauth2MetadataUrl |  |  |
| type | string |  |


## OAuthFlows


Defines the configuration for the supported OAuth 2.0 flows.


| Field | Type | Description |
|-------|------|-------------|
| authorizationCode |  |  |
| clientCredentials |  |  |
| implicit |  |  |
| password |  |  |


## OpenIdConnectSecurityScheme


Defines a security scheme using OpenID Connect.


| Field | Type | Description |
|-------|------|-------------|
| description |  |  |
| openIdConnectUrl | string |  |
| type | string |  |


## PasswordOAuthFlow


Defines configuration details for the OAuth 2.0 Resource Owner Password flow.


| Field | Type | Description |
|-------|------|-------------|
| refreshUrl |  |  |
| scopes | object |  |
| tokenUrl | string |  |


## PostgreSQLDatabaseConfiguration


PostgreSQL database configuration.

PostgreSQL database is used by Lightspeed Core Stack service for storing
information about conversation IDs. It can also be leveraged to store
conversation history and information about quota usage.

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
    vector_store_ids: The optional list of specific vector store IDs to query for RAG.

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
| vector_store_ids |  | Optional list of specific vector store IDs to query for RAG. If not provided, all available vector stores will be queried. |


## QueryResponse


Model representing LLM response to a query.

Attributes:
    conversation_id: The optional conversation ID (UUID).
    response: The response.
    rag_chunks: Deprecated. List of RAG chunks used to generate the response.
        This information is now available in tool_results under file_search_call type.
    referenced_documents: The URLs and titles for the documents used to generate the response.
    tool_calls: List of tool calls made during response generation.
    tool_results: List of tool results.
    truncated: Whether conversation history was truncated.
    input_tokens: Number of tokens sent to LLM.
    output_tokens: Number of tokens received from LLM.
    available_quotas: Quota available as measured by all configured quota limiters.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id |  | The optional conversation ID (UUID) |
| response | string | Response from LLM |
| rag_chunks | array | Deprecated: List of RAG chunks used to generate the response. |
| referenced_documents | array | List of documents referenced in generating the response |
| truncated | boolean | Whether conversation history was truncated |
| input_tokens | integer | Number of tokens sent to LLM |
| output_tokens | integer | Number of tokens received from LLM |
| available_quotas | object | Quota available as measured by all configured quota limiters |
| tool_calls | array | List of tool calls made during response generation |
| tool_results | array | List of tool results |


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
| database_reconnection_count | integer | Database reconnection count on startup. When database for quota is not available on startup, the service tries to reconnect N times with specified delay. |
| database_reconnection_delay | integer | Database reconnection delay specified in seconds. When database for quota is not available on startup, the service tries to reconnect N times with specified delay. |


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
| required_entitlements |  | List of all required entitlements. |


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


## RlsapiV1InferData


Response data for rlsapi v1 /infer endpoint.

Attributes:
    text: The generated response text.
    request_id: Unique identifier for the request.


| Field | Type | Description |
|-------|------|-------------|
| text | string | Generated response text |
| request_id |  | Unique request identifier |


## RlsapiV1InferRequest


RHEL Lightspeed rlsapi v1 /infer request.

Attributes:
    question: User question string.
    context: Context with system info, terminal output, etc. (defaults provided).
    skip_rag: Reserved for future use. RAG retrieval is not yet implemented.

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


## RlsapiV1InferResponse


RHEL Lightspeed rlsapi v1 /infer response.

Attributes:
    data: Response data containing text and request_id.


| Field | Type | Description |
|-------|------|-------------|
| data |  | Response data containing text and request_id |


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


## SQLiteDatabaseConfiguration


SQLite database configuration.


| Field | Type | Description |
|-------|------|-------------|
| db_path | string | Path to file where SQLite database is stored |


## SecurityScheme





## ServiceConfiguration


Service configuration.

Lightspeed Core Stack is a REST API service that accepts requests on a
specified hostname and port. It is also possible to enable authentication
and specify the number of Uvicorn workers. When more workers are specified,
the service can handle requests concurrently.


| Field | Type | Description |
|-------|------|-------------|
| host | string | Service hostname |
| port | integer | Service port |
| base_url |  | Externally reachable base URL for the service; needed for A2A support. |
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


## SplunkConfiguration


Splunk HEC (HTTP Event Collector) configuration.

Splunk HEC allows sending events directly to Splunk over HTTP/HTTPS.
This configuration is used to send telemetry events for inference
requests to the corporate Splunk deployment.

Useful resources:

  - [Splunk HEC Docs](https://docs.splunk.com/Documentation/SplunkCloud)
  - [About HEC](https://docs.splunk.com/Documentation/Splunk/latest/Data)


| Field | Type | Description |
|-------|------|-------------|
| enabled | boolean | Enable or disable Splunk HEC integration. |
| url |  | Splunk HEC endpoint URL. |
| token_path |  | Path to file containing the Splunk HEC authentication token. |
| index |  | Target Splunk index for events. |
| source | string | Event source identifier. |
| timeout | integer | HTTP timeout in seconds for HEC requests. |
| verify_ssl | boolean | Whether to verify SSL certificates for HEC endpoint. |


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


## ToolCallSummary


Model representing a tool call made during response generation (for tool_calls list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call |
| name | string | Name of the tool called |
| args | object | Arguments passed to the tool |
| type | string | Type indicator for tool call |


## ToolResultSummary


Model representing a result from a tool call (for tool_results list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call/result, matches the corresponding tool call 'id' |
| status | string | Status of the tool execution (e.g., 'success') |
| content | string | Content/result returned from the tool |
| type | string | Type indicator for tool result |
| round | integer | Round number or step of tool execution |


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
| feedback_enabled | boolean | When set to true the user feedback is stored and later sent for analysis. |
| feedback_storage |  | Path to directory where feedback will be saved for further processing. |
| transcripts_enabled | boolean | When set to true the conversation history is stored and later sent for analysis. |
| transcripts_storage |  | Path to directory where conversation history will be saved for further processing. |


## ValidationError



| Field | Type | Description |
|-------|------|-------------|
| loc | array |  |
| msg | string |  |
| type | string |  |
| input |  |  |
| ctx | object |  |
