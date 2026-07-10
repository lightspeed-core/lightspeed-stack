Feature: Human-in-the-Loop MCP approval tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  # --- require_approval: "never" returns successful query ---

  Scenario: Query with require_approval "never" returns successful response
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-never' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response does not contain requires_action

  Scenario: Streaming query with require_approval "never" returns successful response
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-never' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response does not contain approval_required


  # --- require_approval: "always" returns requires_action ---

  Scenario: Query with require_approval "always" returns requires_action status
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
      And The body of the response contains mcp_approval

  Scenario: Streaming query with require_approval "always" returns approval_required event
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed    
    Then The status code of the response is 200
      And The body of the response contains approval_required


  # --- require_approval: granular (always/never filter) ---

  Scenario: Query with granular approval filter returns requires_action for "always" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-granular' always tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
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
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-granular' never tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response does not contain requires_action

  Scenario: Streaming query with granular approval filter returns approval_required for "always" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-granular' always tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains approval_required

  Scenario: Streaming query with granular approval filter returns successful response for "never" tool
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-granular' never tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response does not contain approval_required


  # --- Approve a pending approval ---

  Scenario: Approve a pending approval via POST /approvals/{id} on query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 200
      And The body of the response contains approved

  Scenario: Approve a pending approval via POST /approvals/{id} on streaming_query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains approval_required
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 200
      And The body of the response contains approved


  # --- Deny a pending approval ---

  Scenario: Deny a pending approval via POST /approvals/{id} on query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": false}
    """
    Then The status code of the response is 200
      And The body of the response contains denied

  Scenario: Deny a pending approval via POST /approvals/{id} on streaming_query
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains approval_required
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": false}
    """
    Then The status code of the response is 200
      And The body of the response contains denied


  # --- GET /approvals returns all approvals ---

  @MCPApprovalsConfig @flaky
  Scenario: GET /approvals returns list of pending approvals
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
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
    {"query": "Use the mcp-approval-always server to list repos", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains pending
      And The body of the response contains mcp-approval-always

  # --- Approval timeout / expiry ---

  Scenario: Expired approval returns 410 when attempting to approve
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-timeout.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I wait for 6 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 410
      And The body of the response contains approval_expired

  Scenario: Expired approval returns 410 when attempting to deny
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-timeout.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I wait for 6 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": false}
    """
    Then The status code of the response is 410
      And The body of the response contains approval_expired

  # --- Retention cleanup: decided approvals purged after approval_retention_seconds ---

  Scenario: Approved approval is purged after retention period expires
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-retention.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 200
      And The body of the response contains approved
    When I wait for 6 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found

  Scenario: Denied approval is purged after retention period expires
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-retention.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP POST method
    """
    {"approve": false}
    """
    Then The status code of the response is 200
      And The body of the response contains denied
    When I wait for 6 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found

  Scenario: Expired approval is purged after retention period
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-timeout.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
      And I wait for 11 seconds
      And I access REST API endpoint "approvals/{APPROVAL_ID}" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found

  Scenario: Decided approval remains queryable within retention period
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals-short-retention.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "<PLACEHOLDER: prompt to trigger 'mcp-approval-always' tool>", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains requires_action
    When I extract the approval id from the response
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

  # --- Approval not found returns 404 ---

  Scenario: GET on non-existent approval returns 404
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I access REST API endpoint "approvals/non-existent-id-12345" using HTTP GET method
    Then The status code of the response is 404
      And The body of the response contains approval_not_found

  Scenario: POST to non-existent approval returns 404
    Given MCP toolgroups are reset for a new MCP configuration
      And The service uses the lightspeed-stack-mcp-approvals.yaml configuration
      And The service is restarted
    When I access REST API endpoint "approvals/non-existent-id-12345" using HTTP POST method
    """
    {"approve": true}
    """
    Then The status code of the response is 404
      And The body of the response contains approval_not_found