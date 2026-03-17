@MCP
Feature: MCP Server Management API tests

  Tests for the dynamic MCP server management endpoints:
  POST /v1/mcp-servers, GET /v1/mcp-servers, DELETE /v1/mcp-servers/{name}

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: List MCP servers returns pre-configured servers
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains mcp-oauth
    And The body of the response contains config

  Scenario: List MCP servers response has expected structure
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And the body of the response has the following structure
    """
    {
        "servers": [
            {
                "name": "mcp-oauth",
                "url": "http://mock-mcp:3001",
                "provider_id": "model-context-protocol",
                "source": "config"
            }
        ]
    }
    """

  Scenario: Register duplicate MCP server returns 409
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "mcp-oauth", "url": "http://mock-mcp:3001", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 409
    And The body of the response contains already exists

  Scenario: Delete statically configured MCP server returns 403
    Given The system is in default state
    When I access REST API endpoint "mcp-servers/mcp-oauth" using HTTP DELETE method
    Then The status code of the response is 403
    And The body of the response contains statically configured

  Scenario: Delete non-existent MCP server returns 404
    Given The system is in default state
    When I access REST API endpoint "mcp-servers/non-existent-server" using HTTP DELETE method
    Then The status code of the response is 404

  Scenario: Register MCP server with invalid request body returns 422
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"url": "http://mock-mcp:3001"}
    """
    Then The status code of the response is 422

  Scenario: Register MCP server with invalid URL scheme returns 422
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "bad-url-server", "url": "ftp://mock-mcp:3001"}
    """
    Then The status code of the response is 422

  @skip-in-library-mode
  Scenario: Register and delete MCP server lifecycle
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "e2e-lifecycle-server", "url": "http://mock-mcp:3001", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 201
    And The body of the response contains e2e-lifecycle-server
    And The body of the response contains registered successfully
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response contains e2e-lifecycle-server
    And The body of the response contains api
    When I access REST API endpoint "mcp-servers/e2e-lifecycle-server" using HTTP DELETE method
    Then The status code of the response is 200
    And The body of the response contains unregistered successfully
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
