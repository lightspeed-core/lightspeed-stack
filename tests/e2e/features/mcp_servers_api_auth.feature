@e2e_group_1 @MCPServerAPIAuth
Feature: MCP Server Management API authentication tests

  Tests that the MCP server management endpoints enforce authentication
  when authentication is enabled (noop-with-token module).

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-mcp-auth.yaml configuration
      And The service is restarted

  Scenario: List MCP servers returns 401 without auth token
    And I remove the auth header
    When I access REST API endpoint "mcp-servers" using HTTP GET method
    Then The status code of the response is 401

  Scenario: Register MCP server returns 401 without auth token
    And I remove the auth header
    When I access REST API endpoint "mcp-servers" using HTTP POST method
    """
    {"name": "auth-test-server", "url": "http://mock-mcp:3000", "provider_id": "model-context-protocol"}
    """
    Then The status code of the response is 401

  Scenario: Delete MCP server returns 401 without auth token
    And I remove the auth header
    When I access REST API endpoint "mcp-servers/mcp-oauth" using HTTP DELETE method
    Then The status code of the response is 401
