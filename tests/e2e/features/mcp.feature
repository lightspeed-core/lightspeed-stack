@MCP
Feature: MCP tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if tools endpoint reports error when MCP requires authentication
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

  Scenario: Check if query endpoint reports error when MCP requires authentication
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

  Scenario: Check if streaming_query endpoint reports error when MCP requires authentication
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

  Scenario: Check if tools endpoint reports error when MCP invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer invalid-token"}}
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

  Scenario: Check if query endpoint reports error when MCP invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer invalid-token"}}
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

  Scenario: Check if streaming_query endpoint reports error when MCP invalid auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer invalid-token"}}
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

  Scenario: Check if tools endpoint succeeds when MCP auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer test-token"}}
    """
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response is the following
    """
        {
            "tools":[
                {
                    "identifier":"insert_into_memory",
                    "description":"Insert documents into memory",
                    "parameters":[],
                    "provider_id":"rag-runtime",
                    "toolgroup_id":"builtin::rag",
                    "server_source":"builtin",
                    "type":"tool_group"
                },
                {
                    "identifier":"knowledge_search",
                    "description":"Search for information in a database.",
                    "parameters":[
                        {
                        "name":"query",
                        "description":"The query to search for. Can be a natural language sentence or keywords.",
                        "parameter_type":"string",
                        "required":true,
                        "default": null
                        }
                    ],
                    "provider_id":"rag-runtime",
                    "toolgroup_id":"builtin::rag",
                    "server_source":"builtin",
                    "type":"tool_group"
                },
                {
                    "identifier":"mock_tool_no_auth",
                    "description":"Mock tool with no authorization",
                    "parameters":[
                        {
                        "name":"message",
                        "description":"Test message",
                        "parameter_type":"string",
                        "required":false,
                        "default": null
                        }
                    ],
                    "provider_id":"model-context-protocol",
                    "toolgroup_id":"github-api",
                    "server_source":"builtin",
                    "type":"tool_group"
                },
                {
                    "identifier":"mock_tool_no_auth",
                    "description":"Mock tool with no authorization",
                    "parameters":[
                        {
                        "name":"message",
                        "description":"Test message",
                        "parameter_type":"string",
                        "required":false,
                        "default": null
                        }
                    ],
                    "provider_id":"model-context-protocol",
                    "toolgroup_id":"gitlab-api",
                    "server_source":"builtin",
                    "type":"tool_group"
                },
                {
                    "identifier":"mock_tool_no_auth",
                    "description":"Mock tool with no authorization",
                    "parameters":[
                        {
                        "name":"message",
                        "description":"Test message",
                        "parameter_type":"string",
                        "required":false,
                        "default": null
                        }
                    ],
                    "provider_id":"model-context-protocol",
                    "toolgroup_id":"public-api",
                    "server_source":"builtin",
                    "type":"tool_group"
                },
                {
                    "identifier":"mock_tool_e2e",
                    "description":"Mock tool for E2E",
                    "parameters":[
                        {
                        "name":"message",
                        "description":"Test message",
                        "parameter_type":"string",
                        "required":false,
                        "default": null
                        }
                    ],
                    "provider_id":"model-context-protocol",
                    "toolgroup_id":"mcp-oauth",
                    "server_source":"http://mock-mcp:3001",
                    "type":"tool_group"
                }
            ]
        }
    """

  Scenario: Check if query endpoint succeeds when MCP auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer test-token"}}
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

  Scenario: Check if streaming_query endpoint succeeds when MCP auth token is passed
    Given The system is in default state
    And I set the "MCP-HEADERS" header to
    """
    {"mcp-oauth": {"Authorization": "Bearer test-token"}}
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
