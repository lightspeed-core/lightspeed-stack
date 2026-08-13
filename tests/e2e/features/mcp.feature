Feature: MCP tests

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

# Per-auth single-server configs (@cfg_mcp). Cannot share one multi-server YAML:
# check_mcp_auth probes every configured MCP server. lightspeed-stack-mcp.yaml is for mcp_servers_api.

  @MCPFileAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint succeeds when MCP file-based auth token is passed
    Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-file-auth.yaml configuration
      And The service is restarted
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-file


  @MCPFileAuthConfig @flaky @cfg_mcp
  Scenario: Check if query endpoint succeeds when MCP file-based auth token is passed
      Given The service uses the lightspeed-stack-mcp-file-auth.yaml configuration
      And The service is restarted
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    And I capture the current token metrics
    When I use "query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPFileAuthConfig @flaky @cfg_mcp
  Scenario: Check if streaming_query endpoint succeeds when MCP file-based auth token is passed
      Given The service uses the lightspeed-stack-mcp-file-auth.yaml configuration
      And The service is restarted
    And The mcp-file mcp server Authorization header is set to "/tmp/mcp-token"
    And I capture the current token metrics
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The streamed response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPKubernetesAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint succeeds when MCP kubernetes auth token is passed
      Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer kubernetes-test-token
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-kubernetes


  @MCPKubernetesAuthConfig @flaky @cfg_mcp
  Scenario: Check if query endpoint succeeds when MCP kubernetes auth token is passed
      Given The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer kubernetes-test-token
    And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPKubernetesAuthConfig @flaky @cfg_mcp
  Scenario: Check if streaming_query endpoint succeeds when MCP kubernetes auth token is passed
      Given The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
      And The service is restarted
    And I set the Authorization header to Bearer kubernetes-test-token
    And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The streamed response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPKubernetesAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint reports error when MCP kubernetes invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
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


  @MCPKubernetesAuthConfig @cfg_mcp
  Scenario: Check if query endpoint reports error when MCP kubernetes invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
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


  @MCPKubernetesAuthConfig @cfg_mcp
  Scenario: Check if streaming_query endpoint reports error when MCP kubernetes invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-kubernetes-auth.yaml configuration
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


@MCPClientAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint succeeds when MCP client-provided auth token is passed
      Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-client": {"Authorization": "Bearer client-test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-client


  @MCPClientAuthConfig @flaky @cfg_mcp
  Scenario: Check if query endpoint succeeds when MCP client-provided auth token is passed
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
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
    And The response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPClientAuthConfig @flaky @cfg_mcp
  Scenario: Check if streaming_query endpoint succeeds when MCP client-provided auth token is passed
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
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
    And The streamed response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPClientAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint succeeds by skipping when MCP client-provided auth token is omitted
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client


  @MCPClientAuthConfig @flaky @cfg_mcp
  Scenario: Check if query endpoint succeeds by skipping when MCP client-provided auth token is omitted
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    And I capture the current token metrics
    When I use "query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client
    And The response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPClientAuthConfig @flaky @cfg_mcp
  Scenario: Check if streaming_query endpoint succeeds by skipping when MCP client-provided auth token is omitted
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    And I capture the current token metrics
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
    And The body of the response does not contain mcp-client
    And The streamed response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPClientAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint reports error when MCP client-provided invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
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


  @MCPClientAuthConfig @cfg_mcp
  Scenario: Check if query endpoint reports error when MCP client-provided invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
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


  @MCPClientAuthConfig @cfg_mcp
  Scenario: Check if streaming_query endpoint reports error when MCP client-provided invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
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


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint succeeds when MCP OAuth auth token is passed
      Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
      And The service is restarted
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer oauth-test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-oauth


  @MCPOAuthAuthConfig @flaky @cfg_mcp
  Scenario: Check if query endpoint succeeds when MCP OAuth auth token is passed
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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
    And The response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPOAuthAuthConfig @flaky @cfg_mcp
  Scenario: Check if streaming_query endpoint succeeds when MCP OAuth auth token is passed
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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
    And The streamed response contains following fragments
        | Fragments in LLM response |
        | Hello                     |
    And The token metrics have increased


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint reports error when MCP OAuth requires authentication
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if query endpoint reports error when MCP OAuth requires authentication
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if streaming_query endpoint reports error when MCP OAuth requires authentication
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if tools endpoint reports error when MCP OAuth invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if query endpoint reports error when MCP OAuth invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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


  @MCPOAuthAuthConfig @cfg_mcp
  Scenario: Check if streaming_query endpoint reports error when MCP OAuth invalid auth token is passed
      Given The service uses the lightspeed-stack-mcp-oauth-auth.yaml configuration
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


  @cfg_mcp
  Scenario: Check if MCP client auth options endpoint is working
      Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-client-auth.yaml configuration
      And The service is restarted
    When I access REST API endpoint "mcp-auth/client-options" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response has proper client auth options structure
      And The response contains server "mcp-client" with client auth header "Authorization"

# Invalid MCP file token uses lightspeed-stack-mcp-invalid.yaml (@cfg_mcp_invalid)

  @InvalidMCPFileAuthConfig @cfg_mcp_invalid
  Scenario: Check if tools endpoint reports error when MCP file-based invalid auth token is passed
    Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-invalid.yaml configuration
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


  @InvalidMCPFileAuthConfig @cfg_mcp_invalid
  Scenario: Check if query endpoint reports error when MCP file-based invalid auth token is passed
    Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-invalid.yaml configuration
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


  @InvalidMCPFileAuthConfig @cfg_mcp_invalid
  Scenario: Check if streaming_query endpoint reports error when MCP file-based invalid auth token is passed
    Given MCP configuration is reset for a new scenario
      And The service uses the lightspeed-stack-mcp-invalid.yaml configuration
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


