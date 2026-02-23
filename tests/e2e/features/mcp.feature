@MCP
Feature: MCP tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if tools endpoint reports error when mcp requires authentication
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

  Scenario: Check if query endpoint reports error when mcp requires authentication
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

  Scenario: Check if streaming_query endpoint reports error when mcp requires authentication
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
