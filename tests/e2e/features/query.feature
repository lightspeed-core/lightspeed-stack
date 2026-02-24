@Authorized
Feature: Query endpoint API tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything but openshift questions", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
     Then The status code of the response is 200
      And The response should contain following fragments
          | Fragments in LLM response |
          | ask                       |
      And The token metrics should have increased

  Scenario: Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "you are linguistic assistant", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The response should contain following fragments
          | Fragments in LLM response |
          | checkout                  |
      And The response should contain token counter fields
      And The token metrics should have increased

  #enable on demand
  @skip 
  Scenario: Check if LLM ignores new system prompt in same conversation
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything but openshift questions", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And I store conversation details
    And I use "query" to ask question with same conversation_id
    """
    {"query": "Write a simple code for reversing string", "system_prompt": "provide coding assistance", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The response should contain following fragments
          | Fragments in LLM response |
          | ask                       |

  Scenario: Check if LLM responds to sent question with error when not authenticated
    Given The system is in default state
     When I use "query" to ask question
     """
     {"query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
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

  Scenario: Check if LLM responds to sent question with error when bearer token is missing
    Given The system is in default state
    And I set the Authorization header to Bearer
    When I use "query" to ask question with authorization header
    """
    {"query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
      Then The status code of the response is 401
      And The body of the response contains No token found in Authorization header

  Scenario: Check if LLM responds to sent question with error when attempting to access conversation
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     And I capture the current token metrics
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567-e89b-12d3-a456-426614174000", "query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
      Then The status code of the response is 404
      And The body of the response contains Conversation not found
      And The token metrics should not have changed

Scenario: Check if LLM responds to sent question with error when attempting to access conversation with incorrect conversation ID format
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567", "query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
      Then The status code of the response is 422
      And The body of the response contains Value error, Improper conversation ID '123e4567'

Scenario: Check if LLM responds for query request with error for missing query
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567", "query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
      Then The status code of the response is 422
      And The body of the response contains Value error, Improper conversation ID '123e4567'

  Scenario: Check if LLM responds for query request with error for missing query
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"provider": "{PROVIDER}"}
    """
    Then The status code of the response is 422
      And The body of the response is the following
        """
        { "detail": [{"type": "missing", "loc": [ "body", "query" ], "msg": "Field required", "input": {"provider": "{PROVIDER}"}}] }
        """
      And The token metrics should not have changed

  Scenario: Check if LLM responds for query request for missing model and provider
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"query": "Say hello"}
     """
     Then The status code of the response is 200

  Scenario: Check if LLM responds for query request with error for missing model
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"query": "Say hello", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 422
      And The body of the response contains Value error, Model must be specified if provider is specified

  Scenario: Check if LLM responds for query request with error for missing provider
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}"}
    """
     Then The status code of the response is 422
      And The body of the response contains Value error, Provider must be specified if model is specified

    Scenario: Check if LLM responds for query request with error for unknown model
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"query": "Say hello", "provider": "{PROVIDER}", "model":"unknown"}
     """
     Then The status code of the response is 404
      And The body of the response contains Model with ID unknown does not exist

  Scenario: Check if LLM responds for query request with error for unknown provider
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider":"unknown"}
    """
     Then The status code of the response is 404
      And The body of the response contains Model with ID gpt-4o-mini does not exist

  @skip-in-library-mode
  Scenario: Check if LLM responds for query request with error for inability to connect to llama-stack
    Given The system is in default state
    And The llama-stack connection is disrupted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello"}
    """
     Then The status code of the response is 503
      And The body of the response contains Unable to connect to Llama Stack
      And The token metrics should not have changed

  Scenario: Check if LLM responds properly when XML and JSON attachments are sent
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {
      "query": "Say hello",
      "attachments": [
        {
          "attachment_type": "configuration",
          "content": "<note><to>User</to><from>System</from><message>Hello</message></note>",
          "content_type": "application/xml"
        },
        {
          "attachment_type": "configuration",
          "content": "{\"foo\": \"bar\"}",
          "content_type": "application/json"
        }
      ],
      "model": "{MODEL}", 
      "provider": "{PROVIDER}",
      "system_prompt": "You are a helpful assistant"
    }
    """
    Then The status code of the response is 200
