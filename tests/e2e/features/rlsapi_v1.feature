@Authorized
Feature: rlsapi v1 /infer endpoint API tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Basic inference with minimal request (question only)
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "infer" to ask question with authorization header
    """
    {"question": "How do I list files in Linux?"}
    """
    Then The status code of the response is 200
    And The rlsapi response should have valid structure

  Scenario: Inference with full context (systeminfo populated)
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "infer" to ask question with authorization header
    """
    {"question": "How do I configure SELinux?", "context": {"systeminfo": {"os": "RHEL", "version": "9.3", "arch": "x86_64"}}}
    """
    Then The status code of the response is 200
    And The rlsapi response should have valid structure

  Scenario: Request without authorization returns 401
    Given The system is in default state
    When I use "infer" to ask question
    """
    {"question": "How do I list files?"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
    {
      "detail": {
        "response": "Missing or invalid credentials provided by client",
        "cause": "No Authorization header found"
      }
    }
    """

  Scenario: Request with empty bearer token returns 401
    Given The system is in default state
    And I set the Authorization header to Bearer
    When I use "infer" to ask question with authorization header
    """
    {"question": "How do I list files?"}
    """
    Then The status code of the response is 401
    And The body of the response contains No token found in Authorization header

  Scenario: Empty/whitespace question returns 422
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "infer" to ask question with authorization header
    """
    {"question": "   "}
    """
    Then The status code of the response is 422
    And The body of the response contains Question cannot be empty

  Scenario: Response contains valid structure (data.text, data.request_id)
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "infer" to ask question with authorization header
    """
    {"question": "What is RHEL?"}
    """
    Then The status code of the response is 200
    And The rlsapi response should have valid structure

  Scenario: Multiple requests generate unique request_ids
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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
    And The rlsapi request_id should be different from the stored one
