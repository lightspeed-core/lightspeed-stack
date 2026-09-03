@e2e_group_1 @MCPNoConfig
Feature: MCP Server API tests without configured MCP servers

  Tests that the MCP server management endpoints work correctly
  when no MCP servers are configured in lightspeed-stack.yaml.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And I set the Authorization header to Bearer mcp-e2e-no-config-token
      And The service uses the lightspeed-stack-no-cache.yaml configuration
      And The service is restarted

  Scenario: List MCP servers returns empty list when none configured
    Given The system is in default state
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 200
    And The body of the response is the following
    """
    {"servers": []}
    """
