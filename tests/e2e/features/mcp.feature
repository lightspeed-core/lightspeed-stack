@e2e_group_2
Feature: MCP tests

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


# File-based (valid token) — lightspeed-stack-mcp-file-auth.yaml
  @MCPFileAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP file-based auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-file-auth.yaml configuration
      And The service is restarted
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-file

  @MCPFileAuthConfig @flaky
  Scenario: Check if query endpoint succeeds when MCP file-based auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-file-auth.yaml configuration
      And The service is restarted
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

  @MCPFileAuthConfig @flaky
  Scenario: Check if streaming_query endpoint succeeds when MCP file-based auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-file-auth.yaml configuration
      And The service is restarted
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

# File-based (invalid token) — lightspeed-stack-invalid-mcp-file-auth.yaml
  @InvalidMCPFileAuthConfig
  Scenario: Check if tools endpoint reports error when MCP file-based invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-invalid-mcp-file-auth.yaml configuration
      And The service is restarted
    And The mcp-file mcp server Authorization header is set to "/tmp/invalid-mcp-token"
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

  @InvalidMCPFileAuthConfig
  Scenario: Check if query endpoint reports error when MCP file-based invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-invalid-mcp-file-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

  @InvalidMCPFileAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP file-based invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-invalid-mcp-file-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

# Kubernetes — lightspeed-stack-mcp-kubernetes-auth.yaml (success paths then invalid token)
  @MCPKubernetesAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP kubernetes auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer kubernetes-test-token
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-kubernetes

  @MCPKubernetesAuthConfig @flaky
  Scenario: Check if query endpoint succeeds when MCP kubernetes auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
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

  @MCPKubernetesAuthConfig @flaky
  Scenario: Check if streaming_query endpoint succeeds when MCP kubernetes auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
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
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer kubernetes-invalid-token
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

  @MCPKubernetesAuthConfig
  Scenario: Check if query endpoint reports error when MCP kubernetes invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

  @MCPKubernetesAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP kubernetes invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

# Client-provided — lightspeed-stack-mcp-clientauth.yaml
@MCPClientAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP client-provided auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-client

  @MCPClientAuthConfig @flaky
  Scenario: Check if query endpoint succeeds when MCP client-provided auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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

  @MCPClientAuthConfig @flaky
  Scenario: Check if streaming_query endpoint succeeds when MCP client-provided auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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
  Scenario: Check if tools endpoint succeeds by skipping when MCP client-provided auth token is omitted
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client

  @MCPClientAuthConfig @flaky
  Scenario: Check if query endpoint succeeds by skipping when MCP client-provided auth token is omitted
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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

  @MCPClientAuthConfig @flaky
  Scenario: Check if streaming_query endpoint succeeds by skipping when MCP client-provided auth token is omitted
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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
  Scenario: Check if tools endpoint reports error when MCP client-provided invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

  @MCPClientAuthConfig
  Scenario: Check if query endpoint reports error when MCP client-provided invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

  @MCPClientAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP client-provided invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """

# OAuth — lightspeed-stack-mcp-oauth-auth.yaml (valid token, then unauthenticated, then invalid token)
  @MCPOAuthAuthConfig
  Scenario: Check if tools endpoint succeeds when MCP OAuth auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-oauth

  @MCPOAuthAuthConfig @flaky
  Scenario: Check if query endpoint succeeds when MCP OAuth auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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

  @MCPOAuthAuthConfig @flaky
  Scenario: Check if streaming_query endpoint succeeds when MCP OAuth auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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
  Scenario: Check if tools endpoint reports error when MCP OAuth requires authentication
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if query endpoint reports error when MCP OAuth requires authentication
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP OAuth requires authentication
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if tools endpoint reports error when MCP OAuth invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if query endpoint reports error when MCP OAuth invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  @MCPOAuthAuthConfig
  Scenario: Check if streaming_query endpoint reports error when MCP OAuth invalid auth token is passed
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
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
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following header "www-authenticate"

  Scenario: Check if MCP client auth options endpoint is working
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp.yaml configuration
      And The service is restarted
    When I access REST API endpoint "mcp-auth/client-options" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response has proper client auth options structure
      And The response contains server "mcp-client" with client auth header "Authorization"
