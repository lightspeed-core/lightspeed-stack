# Lightspeed Core Service (LCS) service - OpenAPI

Lightspeed Core Service (LCS) service API specification.

## 🌍 Base URL


| URL | Description |
|-----|-------------|
| http://localhost:8080/ | Locally running service |


# 🛠️ APIs

## List of REST API endpoints

| Method | Path                                  | Description |
|--------|---------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| GET    | `/`                                   | Returns the static HTML index page                                                                                                                   |
| GET    | `/v1/info`                            | Returns the service name, version and Llama-stack version                                                                                            |
| GET    | `/v1/models`                          | List of available models                                                                                                                             |
| GET    | `/v1/tools`                           | Consolidated list of available tools from all configured MCP servers                                                                                 |
| GET    | `/v1/mcp-auth/client-options`         | List of MCP servers configured to accept client-provided authorization tokens, along with the header names where clients should provide these tokens |
| GET    | `/v1/mcp-servers`                     | List all registered MCP servers                                                                                                                      |
| POST   | `/v1/mcp-servers`                     | Register an MCP server dynamically at runtime                                                                                                        |
| DELETE | `/v1/mcp-servers/{name}`              | Unregister a dynamically registered MCP server                                                                                                       |
| GET    | `/v1/shields`                         | List of available shields from the Llama Stack service                                                                                               |
| GET    | `/v1/providers`                       | List all available providers grouped by API type                                                                                                     |
| GET    | `/v1/providers/{provider_id}`         | Retrieve a single provider identified by its unique ID                                                                                               |
| GET    | `/v1/rags`                            | List all available RAGs                                                                                                                              |
| GET    | `/v1/rags/{rag_id}`                   | Retrieve a single RAG identified by its unique ID                                                                                                    |
| POST   | `/v1/query`                           | Processes a POST request to a query endpoint, forwarding the user's query to a selected Llama Stack LLM and returning the generated response         |
| POST   | `/v1/streaming_query`                 | Streaming response using Server-Sent Events (SSE) format with content type text/event-stream                                                         |
| GET    | `/v1/config`                          | Returns the current service configuration                                                                                                            |
| POST   | `/v1/feedback`                        | Processes a user feedback submission, storing the feedback and returning a confirmation response                                                     |
| GET    | `/v1/feedback/status`                 | Return the current enabled status of the feedback functionality                                                                                      |
| PUT    | `/v1/feedback/status`                 | Change the feedback status: enables or disables it                                                                                                   |
| GET    | `/v1/conversations`                   | Retrieve all conversations for the authenticated user                                                                                                |
| GET    | `/v1/conversations/{conversation_id}` | Retrieve a conversation by ID using Conversations API                                                                                                |
| DELETE | `/v1/conversations/{conversation_id}` | Delete a conversation by ID using Conversations API                                                                                                  |
| PUT    | `/v1/conversations/{conversation_id}` | Update a conversation metadata using Conversations API                                                                                               |
| GET    | `/v2/conversations`                   | Retrieve all conversations for the authenticated user                                                                                                |
| GET    | `/v2/conversations/{conversation_id}` | Retrieve a conversation identified by its ID                                                                                                         |
| DELETE | `/v2/conversations/{conversation_id}` | Delete a conversation identified by its ID                                                                                                           |
| PUT    | `/v2/conversations/{conversation_id}` | Update a conversation topic summary by ID                                                                                                            |
| POST   | `/v1/infer`                           | Serves requests from the RHEL Lightspeed Command Line Assistant (CLA)                                                                                |
| POST   | `/v1/responses`                       | Handle request to the /responses endpoint using Responses API (LCORE specification)                                                                  |
| GET    | `/readiness`                          | Returns service readiness state                                                                                                                      |
| GET    | `/liveness`                           | Returns liveness status of the service                                                                                                               |
| POST   | `/authorized`                         | Returns the authenticated user's ID and username                                                                                                     |
| GET    | `/metrics`                            | Returns the latest Prometheus metrics in a form of plain text                                                                                        |
| GET    | `/.well-known/agent-card.json`        | Serve the A2A Agent Card at the well-known location                                                                                                  |
| GET    | `/.well-known/agent.json`             | Handle A2A JSON-RPC requests following the A2A protocol specification                                                                                |
| GET    | `/a2a`                                | Handle A2A JSON-RPC requests following the A2A protocol specification                                                                                |
| POST   | `/a2a`                                | Handle A2A JSON-RPC requests following the A2A protocol specification                                                                                |
| GET    | `/a2a/health`                         | Handle A2A JSON-RPC requests following the A2A protocol specification                                                                                |


## GET `/`

> **Root Endpoint Handler**

Handle GET requests to the root ("/") endpoint and returns the static HTML index page.

Returns:
    HTMLResponse: The HTML content of the index page, including a heading,
    embedded image with the service icon, and links to the API documentation
    via Swagger UI and ReDoc.





### ✅ Responses

| Status Code | Description         | Component                                     |
|-------------|---------------------|-----------------------------------------------|
| 200         | Successful Response | string                                        |
| 401         | Unauthorized        | [UnauthorizedResponse](#unauthorizedresponse) |
| 403         | Permission denied   | [ForbiddenResponse](#forbiddenresponse)       |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

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

| Status Code | Description         | Component                                                 |
|-------------|---------------------|-----------------------------------------------------------|
| 200         | Successful response | [InfoResponse](#inforesponse)                             |
| 401         | Unauthorized        | [UnauthorizedResponse](#unauthorizedresponse)             |
| 403         | Permission denied   | [ForbiddenResponse](#forbiddenresponse)                   |
| 503         | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse) |

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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## GET `/v1/models`

> **Models Endpoint Handler**

Handle requests to the /models endpoint.

Process GET requests to the /models endpoint, returning a list of available
models from the Llama Stack service. It is possible to specify "model_type"
query parameter that is used as a filter. For example, if model type is set
to "llm", only LLM models will be returned:

    curl http://localhost:8080/v1/models?model_type=llm

The "model_type" query parameter is optional. When not specified, all models
will be returned.

### Parameters:
    request: The incoming HTTP request.
    auth: Authentication tuple from the auth dependency.
    model_type: Optional filter to return only models matching this type.

### Raises:
    HTTPException: If unable to connect to the Llama Stack server or if
    model retrieval fails for any reason.

### Returns:
    ModelsResponse: An object containing the list of available models.



### 🔗 Parameters

| Name       | Type | Required | Description                                              |
|------------|------|----------|----------------------------------------------------------|
| model_type |      | False    | Optional filter to return only models matching this type |


### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ModelsResponse](#modelsresponse)                           |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error      | [HTTPValidationError](#httpvalidationerror)                 |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ToolsResponse](#toolsresponse)                             |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```


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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Status Code | Description           | Component                                                     |
|-------------|-----------------------|---------------------------------------------------------------|
| 200         | Successful response   | [MCPClientAuthOptionsResponse](#mcpclientauthoptionsresponse) |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)                 |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                       |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```


## GET `/v1/mcp-servers`

> **List Mcp Servers Handler**

List all registered MCP servers.

Returns both statically configured (from YAML) and dynamically
registered (via API) MCP servers.

Raises:
    HTTPException: If configuration is not loaded.

Returns:
    MCPServerListResponse: List of all registered MCP servers with source info.





### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [MCPServerListResponse](#mcpserverlistresponse)             |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```


```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```

## POST `/v1/mcp-servers`

> **Register Mcp Server Handler**

Register an MCP server dynamically at runtime.

Adds the MCP server to the runtime configuration and registers it
as a toolgroup with Llama Stack so it becomes available for queries.

Raises:
    HTTPException: On duplicate name, Llama Stack connection error,
        or registration failure.

Returns:
    MCPServerRegistrationResponse: Details of the newly registered server.





### 📦 Request Body 

[MCPServerRegistrationRequest](#mcpserverregistrationrequest)

### ✅ Responses

| Status Code | Description             | Component                                                       |
|-------------|-------------------------|-----------------------------------------------------------------|
| 201         | Successful response     | [MCPServerRegistrationResponse](#mcpserverregistrationresponse) |
| 401         | Unauthorized            | [UnauthorizedResponse](#unauthorizedresponse)                   |
| 403         | Permission denied       | [ForbiddenResponse](#forbiddenresponse)                         |
| 409         | Resource already exists | [ConflictResponse](#conflictresponse)                           |
| 500         | Internal server error   | [InternalServerErrorResponse](#internalservererrorresponse)     |
| 503         | Service unavailable     | [ServiceUnavailableResponse](#serviceunavailableresponse)       |
| 422         | Validation Error        | [HTTPValidationError](#httpvalidationerror)                     |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



```json
{
  "detail": {
    "cause": "Mcp Server with name 'test-mcp-server' is already registered",
    "response": "Mcp Server already exists"
  }
}
```



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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## DELETE `/v1/mcp-servers/{name}`

> **Delete Mcp Server Handler**

Unregister a dynamically registered MCP server.

Removes the MCP server from the runtime configuration and unregisters
its toolgroup from Llama Stack. Only servers registered via the API
can be deleted; statically configured servers cannot be removed.

Raises:
    HTTPException: If the server is not found, is statically configured,
        or Llama Stack unregistration fails.

Returns:
    MCPServerDeleteResponse: Confirmation of the deletion.



### 🔗 Parameters

| Name | Type   | Required | Description |
|------|--------|----------|-------------|
| name | string | True     |             |


### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [MCPServerDeleteResponse](#mcpserverdeleteresponse)         |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found    | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error      | [HTTPValidationError](#httpvalidationerror)                 |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```





```json
{
  "detail": {
    "cause": "Mcp Server with ID test-mcp-server does not exist",
    "response": "Mcp Server not found"
  }
}
```




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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ShieldsResponse](#shieldsresponse)                         |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ProvidersListResponse](#providerslistresponse)             |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```


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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## GET `/v1/providers/{provider_id}`

> **Get Provider Endpoint Handler**

Retrieve a single provider identified by its unique ID.

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

| Name        | Type   | Required | Description |
|-------------|--------|----------|-------------|
| provider_id | string | True     |             |


### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ProviderResponse](#providerresponse)                       |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found    | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error      | [HTTPValidationError](#httpvalidationerror)                 |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
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
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```

```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [RAGListResponse](#raglistresponse)                         |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## GET `/v1/rags/{rag_id}`

> **Get Rag Endpoint Handler**

Retrieve a single RAG identified by its unique ID.

Accepts both user-facing rag_id (from LCORE config) and llama-stack
vector_store_id. If a rag_id from config is provided, it is resolved
to the underlying vector_store_id for the llama-stack lookup.

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

| Name   | Type   | Required | Description |
|--------|--------|----------|-------------|
| rag_id | string | True     |             |


### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [RAGInfoResponse](#raginforesponse)                         |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found    | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable   | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error      | [HTTPValidationError](#httpvalidationerror)                 |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

```json
{
  "detail": {
    "cause": "Rag with ID vs_7b52a8cf-0fa3-489c-beab-27e061d102f3 does not exist",
    "response": "Rag not found"
  }
}
```


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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## POST `/v1/query`

> **Query Endpoint Handler**

Handle request to the /query endpoint using Responses API.

Processes a POST request to a query endpoint, forwarding the
user's query to a selected Llama Stack LLM and returning the generated response.

Returns:
    QueryResponse: Contains the conversation ID and the LLM-generated response.

Raises:
    HTTPException:
        - 401: Unauthorized - Missing or invalid credentials
        - 403: Forbidden - Insufficient permissions or model override not allowed
        - 404: Not Found - Conversation, model, or provider not found
        - 413: Prompt too long - Prompt exceeded model's context window size
        - 422: Unprocessable Entity - Request validation failed
        - 429: Quota limit exceeded - The token quota for model or user has been exceeded
        - 500: Internal Server Error - Configuration not loaded or other server errors
        - 503: Service Unavailable - Unable to connect to Llama Stack backend





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description               | Component                                                   |
|-------------|---------------------------|-------------------------------------------------------------|
| 200         | Successful response       | [QueryResponse](#queryresponse)                             |
| 401         | Unauthorized              | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied         | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found        | [NotFoundResponse](#notfoundresponse)                       |
| 422         | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse) |
| 429         | Quota limit exceeded      | [QuotaExceededResponse](#quotaexceededresponse)             |
| 500         | Internal server error     | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable       | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "Invalid attachment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```



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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## POST `/v1/streaming_query`

> **Streaming Query Endpoint Handler**

Handle request to the /streaming_query endpoint using Responses API.

Returns a streaming response using Server-Sent Events (SSE) format with
content type text/event-stream.

Returns:
    SSE-formatted events for the query lifecycle.

Raises:
    HTTPException:
        - 401: Unauthorized - Missing or invalid credentials
        - 403: Forbidden - Insufficient permissions or model override not allowed
        - 404: Not Found - Conversation, model, or provider not found
        - 413: Prompt too long - Prompt exceeded model's context window size
        - 422: Unprocessable Entity - Request validation failed
        - 429: Quota limit exceeded - The token quota for model or user has been exceeded
        - 500: Internal Server Error - Configuration not loaded or other server errors
        - 503: Service Unavailable - Unable to connect to Llama Stack backend





### 📦 Request Body 

[QueryRequest](#queryrequest)

### ✅ Responses

| Status Code | Description               | Component                                                   |
|-------------|---------------------------|-------------------------------------------------------------|
| 200         | Successful response       | string                                                      |
| 401         | Unauthorized              | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied         | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found        | [NotFoundResponse](#notfoundresponse)                       |
| 422         | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse) |
| 429         | Quota limit exceeded      | [QuotaExceededResponse](#quotaexceededresponse)             |
| 500         | Internal server error     | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable       | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "Invalid attachment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```


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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## POST `/v1/streaming_query/interrupt`

> **Streaming Query Interrupt Endpoint Handler**

Interrupt an in-progress streaming query by request identifier.

Parameters:
    interrupt_request: Request payload containing the stream request ID.
    auth: Auth context tuple resolved from the authentication dependency.
    registry: Stream interrupt registry dependency used to cancel streams.

Returns:
    StreamingInterruptResponse: Confirmation payload when interruption succeeds.

Raises:
    HTTPException: If no active stream for the given request ID can be interrupted.





### 📦 Request Body 

[StreamingInterruptRequest](#streaminginterruptrequest)

### ✅ Responses

| Status Code | Description         | Component                                                 |
|-------------|---------------------|-----------------------------------------------------------|
| 200         | Successful response | [StreamingInterruptResponse](#streaminginterruptresponse) |
| 401         | Unauthorized        | [UnauthorizedResponse](#unauthorizedresponse)             |
| 403         | Permission denied   | [ForbiddenResponse](#forbiddenresponse)                   |
| 404         | Resource not found  | [NotFoundResponse](#notfoundresponse)                     |
| 422         | Validation Error    | [HTTPValidationError](#httpvalidationerror)               |


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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



```json
{
  "detail": {
    "cause": "Streaming Request with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Streaming Request not found"
  }
}
```
## GET `/v1/config`

> **Config Endpoint Handler**

Handle requests to the /config endpoint.

Process GET requests to the /config endpoint and returns the
current service configuration.

Ensures the application configuration is loaded before returning it.

Returns:
    ConfigurationResponse: The loaded service configuration response.





### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ConfigurationResponse](#configurationresponse)             |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```

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

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [FeedbackResponse](#feedbackresponse)                       |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found    | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |
| 422         | Validation Error      | [HTTPValidationError](#httpvalidationerror)                 |

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

## GET `/v1/feedback/status`

> **Feedback Status**

Handle feedback status requests.

Return the current enabled status of the feedback
functionality.

Returns:
    StatusResponse: Indicates whether feedback collection is enabled.





### ✅ Responses

| Status Code | Description         | Component                         |
|-------------|---------------------|-----------------------------------|
| 200         | Successful response | [StatusResponse](#statusresponse) |

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

| Status Code | Description           | Component                                                     |
|-------------|-----------------------|---------------------------------------------------------------|
| 200         | Successful response   | [FeedbackStatusUpdateResponse](#feedbackstatusupdateresponse) |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)                 |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                       |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse)   |
| 422         | Validation Error      | [HTTPValidationError](#httpvalidationerror)                   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



```json
{
  "detail": {
    "cause": "Lightspeed Stack configuration has not been initialized.",
    "response": "Configuration is not loaded"
  }
}
```

## GET `/v1/conversations`

> **Conversations List Endpoint Handler V1**

Handle request to retrieve all conversations for the authenticated user.





### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ConversationsListResponse](#conversationslistresponse)     |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```


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

## GET `/v1/conversations/{conversation_id}`

> **Conversation Get Endpoint Handler V1**

Handle request to retrieve a conversation identified by ID using Conversations API.

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

| Name            | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| conversation_id | string | True     |             |


### ✅ Responses

| Status Code | Description            | Component                                                   |
|-------------|------------------------|-------------------------------------------------------------|
| 200         | Successful response    | [ConversationResponse](#conversationresponse)               |
| 400         | Invalid request format | [BadRequestResponse](#badrequestresponse)                   |
| 401         | Unauthorized           | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied      | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found     | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error  | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable    | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error       | [HTTPValidationError](#httpvalidationerror)                 |

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```



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
    "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
    "response": "Conversation not found"
  }
}
```



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



```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```
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

| Name            | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| conversation_id | string | True     |             |


### ✅ Responses

| Status Code | Description            | Component                                                   |
|-------------|------------------------|-------------------------------------------------------------|
| 200         | Successful response    | [ConversationDeleteResponse](#conversationdeleteresponse)   |
| 400         | Invalid request format | [BadRequestResponse](#badrequestresponse)                   |
| 401         | Unauthorized           | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied      | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error  | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable    | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error       | [HTTPValidationError](#httpvalidationerror)                 |

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


```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```


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

```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Name            | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| conversation_id | string | True     |             |


### 📦 Request Body 

[ConversationUpdateRequest](#conversationupdaterequest)

### ✅ Responses

| Status Code | Description            | Component                                                   |
|-------------|------------------------|-------------------------------------------------------------|
| 200         | Successful response    | [ConversationUpdateResponse](#conversationupdateresponse)   |
| 400         | Invalid request format | [BadRequestResponse](#badrequestresponse)                   |
| 401         | Unauthorized           | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied      | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found     | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error  | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable    | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 422         | Validation Error       | [HTTPValidationError](#httpvalidationerror)                 |

Examples



```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```


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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

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


```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

## GET `/v2/conversations`

> **Get Conversations List Endpoint Handler**

Handle request to retrieve all conversations for the authenticated user.





### ✅ Responses

| Status Code | Description           | Component                                                   |
|-------------|-----------------------|-------------------------------------------------------------|
| 200         | Successful response   | [ConversationsListResponseV2](#conversationslistresponsev2) |
| 401         | Unauthorized          | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied     | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error | [InternalServerErrorResponse](#internalservererrorresponse) |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



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

## GET `/v2/conversations/{conversation_id}`

> **Get Conversation Endpoint Handler**

Handle request to retrieve a conversation identified by its ID.



### 🔗 Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| conversation_id | string | True |  |


### ✅ Responses

| Status Code | Description            | Component                                                   |
|-------------|------------------------|-------------------------------------------------------------|
| 200         | Successful response    | [ConversationResponse](#conversationresponse)               |
| 400         | Invalid request format | [BadRequestResponse](#badrequestresponse)                   |
| 401         | Unauthorized           | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied      | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found     | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error  | [InternalServerErrorResponse](#internalservererrorresponse) |
| 422         | Validation Error       | [HTTPValidationError](#httpvalidationerror)                 |

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```




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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



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

## DELETE `/v2/conversations/{conversation_id}`

> **Delete Conversation Endpoint Handler**

Handle request to delete a conversation by ID.



### 🔗 Parameters

| Name            | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| conversation_id | string | True     |             |


### ✅ Responses

| Status Code | Description            | Component                                                   |
|-------------|------------------------|-------------------------------------------------------------|
| 200         | Successful response    | [ConversationDeleteResponse](#conversationdeleteresponse)   |
| 400         | Invalid request format | [BadRequestResponse](#badrequestresponse)                   |
| 401         | Unauthorized           | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied      | [ForbiddenResponse](#forbiddenresponse)                     |
| 500         | Internal server error  | [InternalServerErrorResponse](#internalservererrorresponse) |
| 422         | Validation Error       | [HTTPValidationError](#httpvalidationerror)                 |

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



```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```



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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```




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

## PUT `/v2/conversations/{conversation_id}`

> **Update Conversation Endpoint Handler**

Handle request to update a conversation topic summary by ID.



### 🔗 Parameters

| Name            | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| conversation_id | string | True     |             |


### 📦 Request Body 

[ConversationUpdateRequest](#conversationupdaterequest)

### ✅ Responses

| Status Code | Description            | Component                                                   |
|-------------|------------------------|-------------------------------------------------------------|
| 200         | Successful response    | [ConversationUpdateResponse](#conversationupdateresponse)   |
| 400         | Invalid request format | [BadRequestResponse](#badrequestresponse)                   |
| 401         | Unauthorized           | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied      | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found     | [NotFoundResponse](#notfoundresponse)                       |
| 500         | Internal server error  | [InternalServerErrorResponse](#internalservererrorresponse) |
| 422         | Validation Error       | [HTTPValidationError](#httpvalidationerror)                 |

Examples





```json
{
  "detail": {
    "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
    "response": "Invalid conversation ID format"
  }
}
```



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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



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

## POST `/v1/responses`

> **Responses Endpoint Handler**

Handle request to the /responses endpoint using Responses API (LCORE specification).

Processes a POST request to the responses endpoint, forwarding the
user's request to a selected Llama Stack LLM and returning the generated response
following the LCORE OpenAPI specification.

Returns:
    ResponsesResponse: Contains the response following LCORE specification (non-streaming).
    StreamingResponse: SSE-formatted streaming response with enriched events (streaming).
        - response.created event includes conversation attribute
        - response.completed event includes available_quotas attribute

Raises:
    HTTPException:
        - 401: Unauthorized - Missing or invalid credentials
        - 403: Forbidden - Insufficient permissions or model override not allowed
        - 404: Not Found - Conversation, model, or provider not found
        - 413: Prompt too long - Prompt exceeded model's context window size
        - 422: Unprocessable Entity - Request validation failed
        - 429: Quota limit exceeded - The token quota for model or user has been exceeded
        - 500: Internal Server Error - Configuration not loaded or other server errors
        - 503: Service Unavailable - Unable to connect to Llama Stack backend





### 📦 Request Body 

[ResponsesRequest](#responsesrequest)

### ✅ Responses

| Status Code | Description               | Component                                                   |
|-------------|---------------------------|-------------------------------------------------------------|
| 200         | Successful response       | [ResponsesResponse](#responsesresponse)                     |
| 401         | Unauthorized              | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied         | [ForbiddenResponse](#forbiddenresponse)                     |
| 404         | Resource not found        | [NotFoundResponse](#notfoundresponse)                       |
| 413         | Prompt is too long        | [PromptTooLongResponse](#prompttoolongresponse)             |
| 422         | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse) |
| 429         | Quota limit exceeded      | [QuotaExceededResponse](#quotaexceededresponse)             |
| 503         | Service unavailable       | [ServiceUnavailableResponse](#serviceunavailableresponse)   |
| 500         | Internal server error     | [InternalServerErrorResponse](#internalservererrorresponse) |




```json
"event: response.created\ndata: {\"type\":\"response.created\",\"sequence_number\":0,\"response\":{\"id\":\"resp_abc\",\"created_at\":1704067200,\"status\":\"in_progress\",\"output\":[],\"conversation\":\"0d21ba731f21f798dc9680125d5d6f49\",\"available_quotas\":{},\"output_text\":\"\"}}\n\nevent: response.output_item.added\ndata: {\"response_id\":\"resp_abc\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"Hello! How can I help?\"}]},\"output_index\":0,\"sequence_number\":1}\n\nevent: response.output_item.done\ndata: {\"response_id\":\"resp_abc\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"Hello! How can I help?\"}]},\"output_index\":0,\"sequence_number\":2}\n\nevent: response.completed\ndata: {\"type\":\"response.completed\",\"sequence_number\":3,\"response\":{\"id\":\"resp_abc\",\"created_at\":1704067200,\"completed_at\":1704067250,\"status\":\"completed\",\"output\":[{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"Hello! How can I help?\"}]}],\"usage\":{\"input_tokens\":10,\"output_tokens\":6,\"total_tokens\":16},\"conversation\":\"0d21ba731f21f798dc9680125d5d6f49\",\"available_quotas\":{\"daily\":1000,\"monthly\":50000},\"output_text\":\"Hello! How can I help?\"}}\n\ndata: [DONE]\n\n"
```



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



```json
{
  "detail": {
    "cause": "The prompt exceeds the maximum allowed length.",
    "response": "Prompt is too long"
  }
}
```





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
    "cause": "Invalid attachment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```




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
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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

| Status Code | Description               | Component                                                   |
|-------------|---------------------------|-------------------------------------------------------------|
| 200         | Successful response       | [RlsapiV1InferResponse](#rlsapiv1inferresponse)             |
| 401         | Unauthorized              | [UnauthorizedResponse](#unauthorizedresponse)               |
| 403         | Permission denied         | [ForbiddenResponse](#forbiddenresponse)                     |
| 413         | Prompt is too long        | [PromptTooLongResponse](#prompttoolongresponse)             |
| 422         | Request validation failed | [UnprocessableEntityResponse](#unprocessableentityresponse) |
| 429         | Quota limit exceeded      | [QuotaExceededResponse](#quotaexceededresponse)             |
| 500         | Internal server error     | [InternalServerErrorResponse](#internalservererrorresponse) |
| 503         | Service unavailable       | [ServiceUnavailableResponse](#serviceunavailableresponse)   |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```



```json
{
  "detail": {
    "cause": "The prompt exceeds the maximum allowed length.",
    "response": "Prompt is too long"
  }
}
```


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
    "cause": "Invalid attachment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
    "response": "Invalid attribute value"
  }
}
```



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



```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse) |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse) |
| 503 | Service unavailable | [ServiceUnavailableResponse](#serviceunavailableresponse) |

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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```





```json
{
  "detail": {
    "cause": "Connection error while trying to reach backend service.",
    "response": "Unable to connect to Llama Stack"
  }
}
```

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
| 401 | Unauthorized | [UnauthorizedResponse](#unauthorizedresponse) |
| 403 | Permission denied | [ForbiddenResponse](#forbiddenresponse) |





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
    "cause": "User 6789 is not authorized to access this endpoint.",
    "response": "User does not have permission to access this endpoint"
  }
}
```

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


## AllowedToolsFilter


Filter configuration for restricting which MCP tools can be used.

:param tool_names: (Optional) List of specific tool names that are allowed


| Field | Type | Description |
|-------|------|-------------|
| tool_names |  |  |


## ApprovalFilter


Filter configuration for MCP tool approval requirements.

:param always: (Optional) List of tool names that always require approval
:param never: (Optional) List of tool names that never require approval


| Field | Type | Description |
|-------|------|-------------|
| always |  |  |
| never |  |  |


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
| score_multiplier | number | Multiplier applied to relevance scores from this vector store. Used to weight results when querying multiple knowledge sources. Values > 1 boost this store's results; values < 1 reduce them. |


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
| rag |  | Configuration for all RAG strategies (inline and tool-based). |
| okp |  | OKP provider settings. Only used when 'okp' is listed in rag.inline or rag.tool. |


## ConfigurationResponse


Success response model for the config endpoint.


| Field | Type | Description |
|-------|------|-------------|
| configuration |  |  |


## ConflictResponse


409 Conflict - Resource already exists.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


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
| disable_shield_ids_override | boolean |  |
| system_prompt_path |  |  |
| system_prompt |  |  |
| agent_card_path |  |  |
| agent_card_config |  |  |
| custom_profile |  |  |
| allow_verbose_infer | boolean |  |


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


## IncludeParameter





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


## MCPListToolsTool


Tool definition returned by MCP list tools operation.

:param input_schema: JSON schema defining the tool's input parameters
:param name: Name of the tool
:param description: (Optional) Description of what the tool does


| Field | Type | Description |
|-------|------|-------------|
| input_schema | object |  |
| name | string |  |
| description |  |  |


## MCPServerAuthInfo


Information about MCP server client authentication options.


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name |
| client_auth_headers | array | List of authentication header names for client-provided tokens |


## MCPServerDeleteResponse


Response for a successful MCP server deletion.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Deleted MCP server name |
| message | string | Status message |


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


## MCPServerListResponse


Response listing all registered MCP servers.


| Field | Type | Description |
|-------|------|-------------|
| servers | array | List of all registered MCP servers (static and dynamic) |


## MCPServerRegistrationRequest


Request model for dynamically registering an MCP server.

Attributes:
    name: Unique name for the MCP server.
    url: URL of the MCP server endpoint.
    provider_id: MCP provider identification (defaults to "model-context-protocol").
    authorization_headers: Optional headers to send to the MCP server.
    headers: Optional list of HTTP header names to forward from incoming requests.
    timeout: Optional request timeout in seconds.

Example:
    ```python
    request = MCPServerRegistrationRequest(
        name="my-tools",
        url="http://localhost:8888/mcp",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| name | string | Unique name for the MCP server |
| url | string | URL of the MCP server endpoint |
| provider_id | string | MCP provider identification |
| authorization_headers |  | Headers to send to the MCP server. Values must be one of the supported token resolution keywords: 'client' - forward the caller's token provided via MCP-HEADERS, 'kubernetes' - use the authenticated user's Kubernetes token, 'oauth' - use an OAuth token provided via MCP-HEADERS. File-path based secrets (used in static YAML config) are not supported for dynamically registered servers. |
| headers |  | List of HTTP header names to forward from incoming requests |
| timeout |  | Request timeout in seconds for the MCP server |


## MCPServerRegistrationResponse


Response for a successful MCP server registration.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Registered MCP server name |
| url | string | Registered MCP server URL |
| provider_id | string | MCP provider identification |
| message | string | Status message |


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
| referenced_documents |  | List of documents referenced in the response (assistant messages only) |


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
| authorization_headers | object | Headers to send to the MCP server. The map contains the header name and the path to a file containing the header value (secret). There are 3 special cases: 1. Usage of the kubernetes token in the header. To specify this use a string 'kubernetes' instead of the file path. 2. Usage of the client-provided token in the header. To specify this use a string 'client' instead of the file path. 3. Usage of the oauth token in the header. To specify this use a string 'oauth' instead of the file path.  |
| headers | array | List of HTTP header names to automatically forward from the incoming request to this MCP server. Headers listed here are extracted from the original client request and included when calling the MCP server. This is useful when infrastructure components (e.g. API gateways) inject headers that MCP servers need, such as x-rh-identity in HCC. Header matching is case-insensitive. These headers are additive with authorization_headers and MCP-HEADERS. |
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


## OkpConfiguration


OKP (Offline Knowledge Portal) provider configuration.

Controls provider-specific behaviour for the OKP vector store.
Only relevant when ``"okp"`` is listed in ``rag.inline`` or ``rag.tool``.


| Field | Type | Description |
|-------|------|-------------|
| rhokp_url | string | Base URL for the OKP server. Set to `${env.RH_SERVER_OKP}` in YAML to use the environment variable. When missing or empty, the application default is used. |
| offline | boolean | When True, use parent_id for OKP chunk source URLs. When False, use reference_url for chunk source URLs. |
| chunk_filter_query | string | OKP filter query applied to every OKP search request. Defaults to 'is_chunk:true' to restrict results to chunk documents. To add extra constraints, extend the expression using boolean syntax, e.g. 'is_chunk:true AND product:*openshift*'. |


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


## OpenAIResponseError


Error details for failed OpenAI response requests.

:param code: Error code identifying the type of failure
:param message: Human-readable error message describing the failure


| Field | Type | Description |
|-------|------|-------------|
| code | string |  |
| message | string |  |


## OpenAIResponseInputFunctionToolCallOutput


This represents the output of a function call that gets passed back to the model.


| Field | Type | Description |
|-------|------|-------------|
| call_id | string |  |
| output | string |  |
| type | string |  |
| id |  |  |
| status |  |  |


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
| file_data |  |  |
| file_id |  |  |
| file_url |  |  |
| filename |  |  |


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
| file_id |  |  |
| image_url |  |  |


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
| name |  |  |


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
| filters |  |  |
| max_num_results |  |  |
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
| description |  |  |
| parameters |  |  |
| strict |  |  |


## OpenAIResponseInputToolMCP


Model Context Protocol (MCP) tool configuration for OpenAI response inputs.

:param type: Tool type identifier, always "mcp"
:param server_label: Label to identify this MCP server
:param connector_id: (Optional) ID of the connector to use for this MCP server
:param server_url: (Optional) URL endpoint of the MCP server
:param headers: (Optional) HTTP headers to include when connecting to the server
:param authorization: (Optional) OAuth access token for authenticating with the MCP server
:param require_approval: Approval requirement for tool calls ("always", "never", or filter)
:param allowed_tools: (Optional) Restriction on which tools can be used from this server


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| server_label | string |  |
| connector_id |  |  |
| server_url |  |  |
| headers |  |  |
| authorization |  |  |
| require_approval |  |  |
| allowed_tools |  |  |


## OpenAIResponseInputToolWebSearch


Web search tool configuration for OpenAI response inputs.

:param type: Web search tool type variant to use
:param search_context_size: (Optional) Size of search context, must be "low", "medium", or "high"


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |
| search_context_size |  |  |


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
| id |  |  |
| reason |  |  |


## OpenAIResponseMessage-Input


Corresponds to the various Message types in the Responses API.
They are all under one type because the Responses API gives them all
the same "type" value, and there is no way to tell them apart in certain
scenarios.


| Field | Type | Description |
|-------|------|-------------|
| content |  |  |
| role |  |  |
| type | string |  |
| id |  |  |
| status |  |  |


## OpenAIResponseMessage-Output


Corresponds to the various Message types in the Responses API.
They are all under one type because the Responses API gives them all
the same "type" value, and there is no way to tell them apart in certain
scenarios.


| Field | Type | Description |
|-------|------|-------------|
| content |  |  |
| role |  |  |
| type | string |  |
| id |  |  |
| status |  |  |


## OpenAIResponseOutputMessageContentOutputText-Input



| Field | Type | Description |
|-------|------|-------------|
| text | string |  |
| type | string |  |
| annotations | array |  |
| logprobs |  |  |


## OpenAIResponseOutputMessageContentOutputText-Output



| Field | Type | Description |
|-------|------|-------------|
| text | string |  |
| type | string |  |
| annotations | array |  |
| logprobs |  |  |


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
| results |  |  |


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
| id |  |  |
| status |  |  |


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
| error |  |  |
| output |  |  |


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
| variables |  |  |
| version |  |  |


## OpenAIResponseReasoning


Configuration for reasoning effort in OpenAI responses.

Controls how much reasoning the model performs before generating a response.

:param effort: The effort level for reasoning. "low" favors speed and economical token usage,
               "high" favors more complete reasoning, "medium" is a balance between the two.


| Field | Type | Description |
|-------|------|-------------|
| effort |  |  |


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
| name |  |  |
| schema |  |  |
| description |  |  |
| strict |  |  |


## OpenAIResponseToolMCP


Model Context Protocol (MCP) tool configuration for OpenAI response object.

:param type: Tool type identifier, always "mcp"
:param server_label: Label to identify this MCP server
:param allowed_tools: (Optional) Restriction on which tools can be used from this server


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| server_label | string |  |
| allowed_tools |  |  |


## OpenAIResponseUsage


Usage information for OpenAI response.

:param input_tokens: Number of tokens in the input
:param output_tokens: Number of tokens in the output
:param total_tokens: Total tokens used (input + output)
:param input_tokens_details: Detailed breakdown of input token usage
:param output_tokens_details: Detailed breakdown of output token usage


| Field | Type | Description |
|-------|------|-------------|
| input_tokens | integer |  |
| output_tokens | integer |  |
| total_tokens | integer |  |
| input_tokens_details |  |  |
| output_tokens_details |  |  |


## OpenAIResponseUsageInputTokensDetails


Token details for input tokens in OpenAI response usage.

:param cached_tokens: Number of tokens retrieved from cache


| Field | Type | Description |
|-------|------|-------------|
| cached_tokens | integer |  |


## OpenAIResponseUsageOutputTokensDetails


Token details for output tokens in OpenAI response usage.

:param reasoning_tokens: Number of tokens used for reasoning (o1/o3 models)


| Field | Type | Description |
|-------|------|-------------|
| reasoning_tokens | integer |  |


## OpenAITokenLogProb


The log probability for a token from an OpenAI-compatible chat completion response.


| Field | Type | Description |
|-------|------|-------------|
| token | string | The token. |
| bytes |  | The bytes for the token. |
| logprob | number | The log probability of the token. |
| top_logprobs |  | The top log probabilities for the token. |


## OpenAITopLogProb


The top log probability for a token from an OpenAI-compatible chat completion response.


| Field | Type | Description |
|-------|------|-------------|
| token | string | The token. |
| bytes |  | The bytes for the token. |
| logprob | number | The log probability of the token. |


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


## PromptTooLongResponse


413 Payload Too Large - Prompt is too long.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer |  |
| detail |  |  |


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
    shield_ids: The optional list of safety shield IDs to apply.

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
| shield_ids |  | Optional list of safety shield IDs to apply. If None, all configured shields are used.  |
| solr |  | Solr-specific query parameters including filter queries |


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
| truncated | boolean | Deprecated:Whether conversation history was truncated |
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
| source |  | Index name identifying the knowledge source from configuration |
| score |  | Relevance score |
| attributes |  | Document metadata from the RAG provider (e.g., url, title, author) |


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
| max_header_size | integer | Maximum allowed size in bytes for the base64-encoded x-rh-identity header. Headers exceeding this size are rejected before decoding. |


## RagConfiguration


RAG strategy configuration.

Controls which RAG sources are used for inline and tool-based retrieval.

Each strategy lists RAG IDs to include. The special ID ``"okp"`` defined in constants,
activates the OKP provider; all other IDs refer to entries in ``byok_rag``.

Backward compatibility:
    - ``inline`` defaults to ``[]`` (no inline RAG).
    - ``tool`` defaults to ``[]`` (no tool RAG).

If no RAG strategy is defined (inline and tool are empty),
the RAG tool will register all stores available to llama-stack.


| Field | Type | Description |
|-------|------|-------------|
| inline | array | RAG IDs whose sources are injected as context before the LLM call. Use 'okp' to enable OKP inline RAG. Empty by default (no inline RAG). |
| tool | array | RAG IDs made available to the LLM as a file_search tool. Use 'okp' to include the OKP vector store. When omitted, all registered BYOK vector stores are used (backward compatibility). |


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
| source |  | Index name identifying the knowledge source from configuration |


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
    solr: LCORE-specific Solr vector_io provider query parameters (e.g. filter
        queries). Optional.


| Field | Type | Description |
|-------|------|-------------|
| input |  |  |
| model |  |  |
| conversation |  |  |
| include |  |  |
| instructions |  |  |
| max_infer_iters |  |  |
| max_output_tokens |  |  |
| max_tool_calls |  |  |
| metadata |  |  |
| parallel_tool_calls |  |  |
| previous_response_id |  |  |
| prompt |  |  |
| reasoning |  |  |
| safety_identifier |  |  |
| store | boolean |  |
| stream | boolean |  |
| temperature |  |  |
| text |  |  |
| tool_choice |  |  |
| tools |  |  |
| generate_topic_summary |  |  |
| shield_ids |  |  |
| solr |  |  |


## ResponsesResponse


Model representing a response from the Responses API following LCORE specification.

Attributes:
    created_at: Unix timestamp when the response was created.
    completed_at: Unix timestamp when the response was completed, if applicable.
    error: Error details if the response failed or was blocked.
    id: Unique identifier for this response.
    model: Model identifier in "provider/model" format used for generation.
    object: Object type identifier, always "response".
    output: List of structured output items containing messages, tool calls, and
        other content. This is the primary response content.
    parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
    previous_response_id: Identifier of the previous response in a multi-turn
        conversation.
    prompt: The input prompt object that was sent to the model.
    status: Current status of the response (e.g., "completed", "blocked",
        "in_progress").
    temperature: Temperature parameter used for generation (controls randomness).
    text: Text response configuration object used for OpenAI responses.
    top_p: Top-p sampling parameter used for generation.
    tools: List of tools available to the model during generation.
    tool_choice: Tool selection strategy used (e.g., "auto", "required", "none").
    truncation: Strategy used for handling content that exceeds context limits.
    usage: Token usage statistics including input_tokens, output_tokens, and
        total_tokens.
    instructions: System instructions or guidelines provided to the model.
    max_tool_calls: Maximum number of tool calls allowed in a single response.
    reasoning: Reasoning configuration (effort level) used for the response.
    max_output_tokens: Upper bound for tokens generated in the response.
    safety_identifier: Safety/guardrail identifier applied to the request.
    metadata: Additional metadata dictionary with custom key-value pairs.
    store: Whether the response was stored.
    conversation: Conversation ID linking this response to a conversation thread
        (LCORE-specific).
    available_quotas: Remaining token quotas for the user (LCORE-specific).
    output_text: Aggregated text output from all output_text items in the
        output array.


| Field | Type | Description |
|-------|------|-------------|
| created_at | integer |  |
| completed_at |  |  |
| error |  |  |
| id | string |  |
| model | string |  |
| object | string |  |
| output | array |  |
| parallel_tool_calls | boolean |  |
| previous_response_id |  |  |
| prompt |  |  |
| status | string |  |
| temperature |  |  |
| text |  |  |
| top_p |  |  |
| tools |  |  |
| tool_choice |  |  |
| truncation |  |  |
| usage |  |  |
| instructions |  |  |
| max_tool_calls |  |  |
| reasoning |  |  |
| max_output_tokens |  |  |
| safety_identifier |  |  |
| metadata |  |  |
| store |  |  |
| conversation |  |  |
| available_quotas | object |  |
| output_text | string |  |


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
    tool_calls: MCP tool calls made during inference (verbose mode only).
    tool_results: Results from MCP tool calls (verbose mode only).
    rag_chunks: RAG chunks retrieved from documentation (verbose mode only).
    referenced_documents: Source documents referenced (verbose mode only).
    input_tokens: Number of input tokens consumed (verbose mode only).
    output_tokens: Number of output tokens generated (verbose mode only).


| Field | Type | Description |
|-------|------|-------------|
| text | string | Generated response text |
| request_id |  | Unique request identifier |
| tool_calls |  | Tool calls made during inference (requires include_metadata=true) |
| tool_results |  | Results from tool calls (requires include_metadata=true) |
| rag_chunks |  | Retrieved RAG documentation chunks (requires include_metadata=true) |
| referenced_documents |  | Source documents referenced in answer (requires include_metadata=true) |
| input_tokens |  | Number of input tokens consumed (requires include_metadata=true) |
| output_tokens |  | Number of output tokens generated (requires include_metadata=true) |


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
| ranker |  |  |
| score_threshold |  |  |
| alpha |  | Weight factor for weighted ranker |
| impact_factor |  | Impact factor for RRF algorithm |
| weights |  | Weights for combining vector, keyword, and neural scores. Keys: 'vector', 'keyword', 'neural' |
| model |  | Model identifier for neural reranker |


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
| root_path | string | ASGI root path for serving behind a reverse proxy on a subpath |
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


## StreamingInterruptRequest


Model representing a request to interrupt an active streaming query.

Attributes:
    request_id: Unique ID of the active streaming request to interrupt.


| Field | Type | Description |
|-------|------|-------------|
| request_id | string | The active streaming request ID to interrupt |


## StreamingInterruptResponse


Model representing a response to a streaming interrupt request.

Attributes:
    request_id: The streaming request ID targeted by the interrupt call.
    interrupted: Whether an in-progress stream was interrupted.
    message: Human-readable interruption status message.

Example:
    ```python
    response = StreamingInterruptResponse(
        request_id="123e4567-e89b-12d3-a456-426614174000",
        interrupted=True,
        message="Streaming request interrupted",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| request_id | string | The streaming request ID targeted by the interrupt call |
| interrupted | boolean | Whether an in-progress stream was interrupted |
| message | string | Human-readable interruption status message |


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
