@MCP
Feature: MCP tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1


# File-based
  @MCPFileAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP file-based auth token is passed 
    Given The system is in default state
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-file

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPFileAuthConfig
  Scenario: Check if query endpoint succeeds when MCP file-based auth token is passed
    Given The system is in default state
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    And I capture the current token metrics
    When I use "query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPFileAuthConfig
  Scenario: Check if streaming_query endpoint succeeds when MCP file-based auth token is passed
    Given The system is in default state
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    And I capture the current token metrics
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The streamed response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @InvalidMCPFileAuthConfig
  Scenario: Check if tools endpoint reports error when MCP file-based invalid auth token is passed 
    Given The system is in default state
    And The mcp-file mcp server Authorization header is set to "/tmp/invalid-mcp-token"
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

  @skip #TODO: LCORE-1463
  @InvalidMCPFileAuthConfig
  Scenario: Check if query endpoint reports error when MCP file-based invalid auth token is passed 
    Given The system is in default state
    And The mcp-file mcp server Authorization header is set to "/tmp/invalid-mcp-token"
    When I use "query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

  @skip #TODO: LCORE-1463
  @InvalidMCPFileAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP file-based invalid auth token is passed 
    Given The system is in default state
    And The mcp-file mcp server Authorization header is set to "/tmp/invalid-mcp-token"
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

# Kubernetes
  @MCPKubernetesAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP kubernetes auth token is passed 
    Given The system is in default state
    And I set the Authorization header to Bearer kubernetes-test-token
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-kubernetes

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPKubernetesAuthConfig
  Scenario: Check if query endpoint succeeds when MCP kubernetes auth token is passed
    Given The system is in default state
    And I set the Authorization header to Bearer kubernetes-test-token
    And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPKubernetesAuthConfig
  Scenario: Check if streaming_query endpoint succeeds when MCP kubernetes auth token is passed
    Given The system is in default state
    And I set the Authorization header to Bearer kubernetes-test-token
    And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The streamed response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @MCPKubernetesAuthConfig
  Scenario: Check if tools endpoint reports error when MCP kubernetes invalid auth token is passed 
    Given The system is in default state
    And I set the Authorization header to Bearer kubernetes-invalid-token
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

  @skip #TODO: LCORE-1463
  @MCPKubernetesAuthConfig
  Scenario: Check if query endpoint reports error when MCP kubernetes invalid auth token is passed
    Given The system is in default state
    And I set the Authorization header to Bearer kubernetes-invalid-token
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

  @skip #TODO: LCORE-1463
  @MCPKubernetesAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP kubernetes invalid auth token is passed 
    Given The system is in default state
    And I set the Authorization header to Bearer kubernetes-invalid-token
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

# Client-provided
  @skip #TODO: LCORE-1462
  @MCPClientAuthConfig
  Scenario: Check if tools endpoint succeeds by skipping when MCP client-provided auth token is omitted
    Given The system is in default state
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client

  @MCPClientAuthConfig
  Scenario: Check if query endpoint succeeds by skipping when MCP client-provided auth token is omitted
    Given The system is in default state
    And I capture the current token metrics
    When I use "query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client
    And The response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @MCPClientAuthConfig
  Scenario: Check if streaming_query endpoint succeeds by skipping when MCP client-provided auth token is omitted
    Given The system is in default state
    And I capture the current token metrics
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client
    And The streamed response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @MCPClientAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP client-provided auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-client

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPClientAuthConfig
  Scenario: Check if query endpoint succeeds when MCP client-provided auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-test-token"}}
    """
    And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPClientAuthConfig
  Scenario: Check if streaming_query endpoint succeeds when MCP client-provided auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-test-token"}}
    """
    And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The streamed response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @MCPClientAuthConfig
  Scenario: Check if tools endpoint reports error when MCP client-provided invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-invalid-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

  @MCPClientAuthConfig
  Scenario: Check if query endpoint reports error when MCP client-provided invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-invalid-token"}}
    """
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

  @MCPClientAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP client-provided invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-invalid-token"}}
    """
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """

# OAuth

  @MCPOAuthAuthConfig
  Scenario: Check if tools endpoint reports error when MCP OAuth requires authentication
    Given The system is in default state
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if query endpoint reports error when MCP OAuth requires authentication
    Given The system is in default state
    When I use "query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP OAuth requires authentication
    Given The system is in default state
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP OAuth auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-oauth

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPOAuthAuthConfig
  Scenario: Check if query endpoint succeeds when MCP OAuth auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-test-token"}}
    """
    And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @skip-in-library-mode #TODO: LCORE-1428
  @MCPOAuthAuthConfig
  Scenario: Check if streaming_query endpoint succeeds when MCP OAuth auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-test-token"}}
    """
    And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The streamed response should contain following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics should have increased

  @MCPOAuthAuthConfig
  Scenario: Check if tools endpoint reports error when MCP OAuth invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-invalid-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if query endpoint reports error when MCP OAuth invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-invalid-token"}}
    """
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP OAuth invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-invalid-token"}}
    """
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3001 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"
