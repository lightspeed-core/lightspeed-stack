@e2e_group_2 @Authorized
Feature: rlsapi v1 /infer endpoint API tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  Scenario: Basic inference with minimal request (question only)
    When I use "infer" to ask question with authorization header
    """
    {"question": "How do I list files in Linux?"}
    """
    Then The status code of the response is 200
    And The rlsapi response has valid structure

  Scenario: Inference with full context (systeminfo populated)
    When I use "infer" to ask question with authorization header
    """
    {"question": "How do I configure SELinux?", "context": {"systeminfo": {"os": "RHEL", "version": "9.3", "arch": "x86_64"}}}
    """
    Then The status code of the response is 200
    And The rlsapi response has valid structure

  Scenario: Empty/whitespace question returns 422
    When I use "infer" to ask question with authorization header
    """
    {"question": "   "}
    """
    Then The status code of the response is 422
    And The body of the response contains Question cannot be empty

  Scenario: Response contains valid structure (data.text, data.request_id)
    When I use "infer" to ask question with authorization header
    """
    {"question": "What is RHEL?"}
    """
    Then The status code of the response is 200
    And The rlsapi response has valid structure

  Scenario: Multiple requests generate unique request_ids
    When I use "infer" to ask question with authorization header
    """
    {"question": "First question"}
    """
    Then The status code of the response is 200
    And I store the rlsapi request_id
    When I use "infer" to ask question with authorization header
    """
    {"question": "Second question"}
    """
    Then The status code of the response is 200
    And The rlsapi request_id is different from the stored one
