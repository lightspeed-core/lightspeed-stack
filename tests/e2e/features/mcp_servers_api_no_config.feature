@MCPNoConfig
Feature: MCP Server API tests without configured MCP servers

  Tests that the MCP server management endpoints work correctly
  when no MCP servers are configured in lightspeed-stack.yaml.

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: List MCP servers returns empty list when none configured
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response is the following
    """
    {"servers": []}
    """
