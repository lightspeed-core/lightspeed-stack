@skip
Feature: Human-in-the-Loop MCP approval tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  # --- require_approval: "never" returns successful query, and no pending approvals are recorded ---

  Scenario: Query with require_approval "never" returns successful response
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the divide tool from the mcp-approval-never server to divide 10 by 2.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response does not contain requires_action
    When I access REST API endpoint "approvals" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response is the following
      """
      {"approvals": []}
      """

  Scenario: Streaming query with require_approval "never" returns successful response
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Use the divide tool from the mcp-approval-never server to divide 10 by 2.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response does not contain approval_required
    When I access REST API endpoint "approvals" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response is the following
      """
      {"approvals": []}
      """


  # --- require_approval: granular (always/never filter) ---

  Scenario: Query with granular approval filter returns requires_action for "always" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the add tool from the mcp-approval-granular server to add 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And The body of the response contains mcp_approval

  Scenario: Query with granular approval filter returns successful response for "never" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the subtract tool from the mcp-approval-granular server to subtract 1 from 5.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response does not contain requires_action
    When I access REST API endpoint "approvals" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response is the following
      """
      {"approvals": []}
      """

  Scenario: Streaming query with granular approval filter returns approval_required for "always" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Use the add tool from the mcp-approval-granular server to add 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response contains approval_required

  Scenario: Streaming query with granular approval filter returns successful response for "never" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Use the subtract tool from the mcp-approval-granular server to subtract 1 from 5.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response does not contain approval_required
    When I access REST API endpoint "approvals" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response is the following
      """
      {"approvals": []}
      """


  # --- Approve a pending approval ---

  Scenario: Approve a pending approval via POST /approvals/{id} on query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 200
      And The body of the response contains approved
    When I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The status message of the response is "approved"

  Scenario: Approve a pending approval via POST /approvals/{id} on streaming_query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response contains approval_required
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 200
      And The body of the response contains approved
    When I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The status message of the response is "approved"


  # --- Deny a pending approval ---

  Scenario: Deny a pending approval via POST /approvals/{id} on query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": false}
    """
    Then The status code of the response is 200
      And The body of the response contains denied
    When I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The status message of the response is "denied"

  Scenario: Deny a pending approval via POST /approvals/{id} on streaming_query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response contains approval_required
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": false}
    """
    Then The status code of the response is 200
      And The body of the response contains denied
    When I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The status message of the response is "denied"


  # --- GET /approvals returns all approvals ---

  @MCPApprovalsConfig @flaky
  Scenario: GET /approvals returns list of pending approvals
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I access REST API endpoint "approvals" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains approvals
      And The body of the response contains pending


  # --- GET /approvals/{id} returns a single approval ---

  @MCPApprovalsConfig @flaky
  Scenario: GET /approvals/{id} returns a specific approval
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains pending
      And The body of the response contains mcp-approval-always

  # --- Approval timeout / expiry ---

  Scenario: Expired approval returns 410 when attempting to decide
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-timeout.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And I wait for 6 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 410
      And The body of the response contains approval_expired

  # --- Retention cleanup: decided approvals purged after approval_retention_seconds ---

  Scenario: Decided approval remains queryable within retention period then purged after it expires
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-retention.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 200
      And The body of the response contains approved
    When I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains approved
      And The body of the response contains decided_at
    When I wait for 3 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains approved
    When I wait for 8 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found

  Scenario: Expired approval is purged after retention period
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-retention.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Use the multiply tool from the mcp-approval-always server to multiply 2 and 3.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And I wait for 11 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found

  # --- Approval not found returns 404 ---

  Scenario: Requests for a non-existent approval return 404
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I access REST API endpoint "approvals/non-existent-id-12345" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found
    When I access REST API endpoint "approvals/non-existent-id-12345" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 404
      And The body of the response contains approval_not_found