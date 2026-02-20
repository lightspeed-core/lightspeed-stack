@MCP
Feature: MCP Server Integration

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  # ============================================================================
  # Basic Operations - Discovery and Configuration
  # ============================================================================

  Scenario: MCP client auth options endpoint returns configured servers
    Given The system is in default state
      And I set the Authorization header to Bearer test-token
     When I access REST API endpoint "mcp-auth/client-options" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper client auth options structure
      And The response contains server "mock-client-auth" with client auth header "Authorization"

  # ============================================================================
  # Authentication Methods
  # ============================================================================

  Scenario: MCP mock server receives file-based static token
    Given The system is in default state
      And The MCP mock server request log is cleared
     When I send a query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received requests
      And The MCP mock server should have captured Authorization header "Bearer test-secret-token-123" from file-auth server

  Scenario: MCP mock server receives kubernetes token from request
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And The MCP mock server request log is cleared
     When I send a query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received requests
      And The MCP mock server should have captured Authorization header containing "my-k8s-token" from k8s-auth server

  Scenario: MCP mock server receives client-provided token via MCP-HEADERS
    Given The system is in default state
      And I set the MCP-HEADERS header with client token for "mock-client-auth"
      And The MCP mock server request log is cleared
     When I send a query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received requests
      And The MCP mock server should have captured Authorization header containing "my-client-token" from client-auth server
      And The MCP mock server request log should contain exactly tools mock_tool_file, mock_tool_k8s, mock_tool_client

  Scenario: MCP server with client auth is skipped when MCP-HEADERS is missing
    Given The system is in default state
      And The MCP mock server request log is cleared
     When I send a query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server request log should contain exactly tools mock_tool_file, mock_tool_k8s

  Scenario: All three MCP auth types work in a single request
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And I set the MCP-HEADERS header with client token for "mock-client-auth"
      And The MCP mock server request log is cleared
     When I send a query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received at least 6 requests
      And The MCP mock server request log should contain tool "mock_tool_file"
      And The MCP mock server request log should contain tool "mock_tool_k8s"
      And The MCP mock server request log should contain tool "mock_tool_client"

  # ============================================================================
  # Tool Execution
  # ============================================================================

  Scenario: LLM successfully discovers and lists MCP tools
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And The MCP mock server request log is cleared
     When I send a query asking about available tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received requests
      And The MCP mock server should have received tools/list method calls

  Scenario: LLM calls an MCP tool and receives results
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And The MCP mock server request log is cleared
     When I send a query that explicitly requests tool usage
      And I wait for MCP server to process tool calls
     Then The MCP mock server should have received tools/call method
      And The response should contain MCP tool execution results
      And The response should indicate successful tool execution

  Scenario: MCP tool execution appears in query response
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And I set the MCP-HEADERS header with client token for "mock-client-auth"
     When I send a query that triggers MCP tool usage
     Then The status code of the response is 200
      And The response should contain tool call information
      And The tool execution results should be included in the response

  Scenario: Failed MCP tool execution is handled gracefully
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And The MCP mock server is configured to return errors
     When I send a query that uses MCP tools
     Then The status code of the response is 200
      And The response should indicate tool execution failed
      And The MCP mock server should confirm error mode is active

  # Note: This scenario can be slow in CI (up to 120s) due to multiple LLM+tool roundtrips
  # Completes in ~8s locally but timing is highly variable in containerized CI environments
  Scenario: Multiple MCP tools can be called in sequence
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And I set the MCP-HEADERS header with client token for "mock-client-auth"
      And The MCP mock server request log is cleared
     When I send a query that requires multiple tool calls
      And I wait for MCP server to process tool calls
     Then The MCP mock server should have received multiple tools/call methods
      And All tool calls should have succeeded
      And The response should contain results from all tool calls

  Scenario: Streaming query discovers and uses MCP tools
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And The MCP mock server request log is cleared
     When I send a streaming query that uses MCP tools
      And I wait for MCP server to process tool calls
     Then The MCP mock server should have received requests
      And The MCP mock server should have received tools/call method
      And The streaming response should be successful

  # Note: This scenario can be slow in CI (up to 120s) due to multiple LLM+tool roundtrips
  # Completes in ~8s locally but timing is highly variable in containerized CI environments
  Scenario: Streaming query with multiple MCP tools
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And I set the MCP-HEADERS header with client token for "mock-client-auth"
      And The MCP mock server request log is cleared
     When I send a streaming query requiring multiple tools
      And I wait for MCP server to process tool calls
     Then The MCP mock server should have received multiple tools/call methods
      And The streaming response should contain tool execution results

  Scenario: Failed MCP tool execution in streaming query is handled gracefully
    Given The system is in default state
      And I set the Authorization header to Bearer my-k8s-token
      And The MCP mock server is configured to return errors
     When I send a streaming query that uses MCP tools
     Then The streaming response should be successful
      And The MCP mock server should confirm error mode is active

  Scenario: Streaming query receives file-based static token
    Given The system is in default state
      And The MCP mock server request log is cleared
     When I send a streaming query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received requests
      And The MCP mock server should have captured Authorization header "Bearer test-secret-token-123" from file-auth server
      And The streaming response should be successful

  Scenario: Streaming query receives client-provided token via MCP-HEADERS
    Given The system is in default state
      And I set the MCP-HEADERS header with client token for "mock-client-auth"
      And The MCP mock server request log is cleared
     When I send a streaming query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server should have received requests
      And The MCP mock server should have captured Authorization header containing "my-client-token" from client-auth server
      And The MCP mock server request log should contain exactly tools mock_tool_file, mock_tool_k8s, mock_tool_client
      And The streaming response should be successful

  Scenario: Streaming query skips MCP server with client auth when MCP-HEADERS is missing
    Given The system is in default state
      And The MCP mock server request log is cleared
     When I send a streaming query that uses MCP tools
      And I wait for MCP server to receive requests
     Then The MCP mock server request log should contain exactly tools mock_tool_file, mock_tool_k8s
      And The streaming response should be successful
