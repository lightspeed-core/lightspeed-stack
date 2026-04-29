@e2e_group_3 @skip-in-library-mode @Authorized
Feature: Llama Stack connection disrupted

  End-to-end scenarios that stop the Llama Stack container (or simulate disconnect) and
  assert degraded responses (503, readiness, etc.). Config order matches test_list.txt:
  default stack, then noop-token (query/conversations/…), then rbac (rlsapi errors), then
  mcp (immediately before mcp.feature). Skipped in library mode.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  # --- lightspeed-stack.yaml (aligned with health, info, models, …) ---
  Scenario: Check if models endpoint reports error when llama-stack is unreachable
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    Given The system is in default state
    And The llama-stack connection is disrupted
    When I access REST API endpoint "models" using HTTP GET method
    Then The status code of the response is 503
    And The body of the response is the following
    """
       {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
    """

  Scenario: Check if service report proper readiness state when llama stack is not available
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    Given The system is in default state
    And The llama-stack connection is disrupted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is 503
    And The body of the response, ignoring the "providers" field, is the following
    """
    {"ready": false, "reason": "Providers not healthy: unknown; Failed to check model availability: Connection error."}
    """

  Scenario: Check if service report proper liveness state even when llama stack is not available
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    Given The system is in default state
    And The llama-stack connection is disrupted
    When I access endpoint "liveness" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response is the following
    """
    {"alive": true}
    """

  Scenario: Check if info endpoint reports error when llama-stack connection is not working
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    And The llama-stack connection is disrupted
    When I access REST API endpoint "info" using HTTP GET method
    Then The status code of the response is 503
    And The body of the response is the following
    """
       {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
    """

  Scenario: Check if shields endpoint reports error when llama-stack is unreachable
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    And The llama-stack connection is disrupted
    When I access REST API endpoint "shields" using HTTP GET method
    Then The status code of the response is 503
    And The body of the response is the following
    """
       {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
    """

  Scenario: Check if tools endpoint reports error when llama-stack is unreachable
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    And The llama-stack connection is disrupted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 503
    And The body of the response is the following
    """
       {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
    """


  # --- lightspeed-stack-auth-noop-token.yaml (aligned with query, responses, conversations, …) ---
  Scenario: Check if LLM responds for query request with error for inability to connect to llama-stack
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And The llama-stack connection is disrupted
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello"}
    """
    Then The status code of the response is 503
    And The body of the response contains Unable to connect to Llama Stack

  Scenario: Responses returns error when unable to connect to llama-stack
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    Given The system is in default state
    And The llama-stack connection is disrupted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": false}
    """
    Then The status code of the response is 503
    And The body of the response contains Unable to connect to Llama Stack

  Scenario: Streaming responses returns error when unable to connect to llama-stack
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And The llama-stack connection is disrupted
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 503
    And The body of the response contains Unable to connect to Llama Stack

  Scenario: Check if rags endpoint fails when llama-stack is unavailable
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And The llama-stack connection is disrupted
    When I access REST API endpoint rags using HTTP GET method
    Then The status code of the response is 503
    And The body of the response contains Unable to connect to Llama Stack

  Scenario: Check if conversations/{conversation_id} GET endpoint fails when llama-stack is unavailable
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    And The status code of the response is 200
    And I store conversation details
    And The llama-stack connection is disrupted
    When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
    Then The status code of the response is 503
    And The body of the response contains Unable to connect to Llama Stack

  Scenario: Check if conversations/{conversation_id} DELETE endpoint fails when llama-stack is unavailable
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    And The status code of the response is 200
    And I store conversation details
    And The llama-stack connection is disrupted
    When I use REST API conversation endpoint with conversation_id from above using HTTP DELETE method
    Then The status code of the response is 503
    And The body of the response contains Unable to connect to Llama Stack

  Scenario: Check conversations/{conversation_id} works when llama-stack is down
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "What is OpenShift?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And The llama-stack connection is disrupted
    And REST API service prefix is /v2
    When I access REST API endpoint "conversations" using HTTP GET method
    Then The status code of the response is 200
    When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
    Then The status code of the response is 200
    And The conversation history contains 1 messages
    And The conversation history has correct metadata
    And The conversation uses model {MODEL} and provider {PROVIDER}

  Scenario: V2 conversations DELETE endpoint works even when llama-stack is down
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "Test resilience", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And The llama-stack connection is disrupted
    And REST API service prefix is /v2
    When I use REST API conversation endpoint with conversation_id from above using HTTP DELETE method
    Then The status code of the response is 200
    And The returned conversation details have expected conversation_id
    And The body of the response, ignoring the "conversation_id" field, is the following
    """
    {"success": true, "response": "Conversation deleted successfully", "deleted": true}
    """
    When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
    Then The status code of the response is 404
    And The body of the response contains Conversation not found


  # --- lightspeed-stack-rbac.yaml (aligned with rbac.feature / rlsapi_v1_errors.feature) ---
  @RBAC
  Scenario: Returns 503 when llama-stack connection is broken
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-rbac.yaml configuration
      And The service is restarted
    And I authenticate as "user" user
    And The llama-stack connection is disrupted
    When I use "infer" to ask question with authorization header
    """
    {"question": "How do I list files?"}
    """
    Then The status code of the response is 503
    And The body of the response contains Llama Stack


  # --- lightspeed-stack-mcp.yaml (aligned with mcp.feature / mcp_servers_api.feature next in test_list) ---
  @MCP
  Scenario: Register MCP server returns 503 when Llama Stack is unreachable
    Given Llama Stack is restarted
    And The service uses the lightspeed-stack-mcp.yaml configuration
      And The service is restarted
    And The llama-stack connection is disrupted
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "unreachable-server", "url": "http://mock-mcp:3000", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 503
    And The body of the response contains Llama Stack
