@e2e_group_3 @MCP
Feature: MCP Server Management API tests

  Tests for the dynamic MCP server management endpoints:
  POST /v1/mcp-servers, GET /v1/mcp-servers, DELETE /v1/mcp-servers/{name}

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-mcp.yaml configuration
      And The service is restarted

  Scenario: List MCP servers returns pre-configured servers
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-oauth
    And The body of the response contains config

  Scenario: List MCP servers response has expected structure
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And the body of the response has the following structure
    """
    {
        "servers": [
            {
                "name": "mcp-oauth",
                "url": "http://mock-mcp:3000",
                "provider_id": "model-context-protocol",
                "source": "config"
            }
        ]
    }
    """

  Scenario: Register duplicate MCP server returns 409
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "mcp-oauth", "url": "http://mock-mcp:3000", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 409
    And The body of the response contains already exists

  Scenario: Delete statically configured MCP server returns 403
    When I access REST API endpoint "mcp-servers/mcp-oauth" using HTTP DELETE method
    Then The status code of the response is 403
    And The body of the response contains statically configured

  Scenario: Delete non-existent MCP server returns 200 with not-found outcome
    When I access REST API endpoint "mcp-servers/non-existent-server" using HTTP DELETE method
    Then The status code of the response is 200
    And The body of the response is the following
    """
    {
        "deleted": false,
        "name": "non-existent-server",
        "response": "MCP server not found",
        "success": true
    }
    """

  Scenario: Register MCP server with missing required fields returns 422
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"url": "http://mock-mcp:3000"}
    """
    Then The status code of the response is 422
    And The body of the response contains name

  Scenario: Register MCP server with invalid URL scheme returns 422
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "bad-url-server", "url": "ftp://mock-mcp:3000", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 422
    And The body of the response contains scheme

  @skip-in-library-mode
  Scenario: Register and delete MCP server lifecycle
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "e2e-lifecycle-server", "url": "http://mock-mcp:3000", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 201
    And The body of the response contains e2e-lifecycle-server
    And The body of the response contains registered successfully
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And the body of the response has the following structure
    """
    {
        "servers": [
            {
                "name": "mcp-oauth",
                "source": "config"
            },
            {
                "name": "e2e-lifecycle-server",
                "url": "http://mock-mcp:3000",
                "provider_id": "model-context-protocol",
                "source": "api"
            }
        ]
    }
    """
    When I access REST API endpoint "mcp-servers/e2e-lifecycle-server" using HTTP DELETE method
    Then The status code of the response is 200
    And The body of the response contains e2e-lifecycle-server
    And The body of the response contains deleted successfully
    When I access REST API endpoint "mcp-servers/e2e-lifecycle-server" using HTTP DELETE method
    Then The status code of the response is 200
    And The body of the response is the following
    """
    {
        "deleted": false,
        "name": "e2e-lifecycle-server",
        "response": "MCP server not found",
        "success": true
    }
    """
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And the body of the response has the following structure
    """
    {
        "servers": [
            {
                "name": "mcp-oauth",
                "source": "config"
            }
        ]
    }
    """
