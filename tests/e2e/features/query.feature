@Authorized
Feature: Query endpoint API tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything but openshift questions"}
    """
     Then The status code of the response is 200
      And The response should contain following fragments
          | Fragments in LLM response |
          | ask                       |

  Scenario: Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "you are linguistic assistant"}
    """
     Then The status code of the response is 200
      And The response should contain following fragments
          | Fragments in LLM response |
          | checkout                  |

  Scenario: Check if LLM ignores new system prompt in same conversation
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything but openshift questions"}
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
     {"query": "Write a simple code for reversing string"}
     """
      Then The status code of the response is 401
      And The body of the response is the following
          """
          {"detail": "No Authorization header found"}
          """

  Scenario: Check if LLM responds to sent question with error when authenticated with invalid token
    Given The service is started locally
    And REST API service prefix is /v1
    Given The system is in default state
    And I set the Authorization header to Bearer invalid
    When I use "query" to ask question with authorization header
     """
     {"query": "Write a simple code for reversing string"}
     """
      Then The status code of the response is 401
      And The body of the response is the following
          """
          {"detail":"Invalid token: decode error"}
          """

  Scenario: Check if LLM responds to sent question with error when model does not exist
    Given The service is started locally
    And REST API service prefix is /v1
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
     """
     {"query": "Write a simple code for reversing string", "model": "does-not-exist", "provider": "does-not-exist"}
     """
      Then The status code of the response is 404
      And The body of the response contains Model does-not-exist from provider does-not-exist not found in available models


  Scenario: Check if LLM responds to sent question with error when attempting to access conversation
    Given The service is started locally
    And REST API service prefix is /v1
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567-e89b-12d3-a456-426614174000", "query": "Write a simple code for reversing string"}
     """
      Then The status code of the response is 404
      And The body of the response contains Conversation not found

Scenario: Check if LLM responds for query request with error for missing query
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "query" to ask question with authorization header
     """
     {"provider": "{PROVIDER}"}
     """
     Then The status code of the response is 422
     And The body of the response is the following
        """
        { "detail": [{"type": "missing", "loc": [ "body", "query" ], "msg": "Field required", "input": {"provider": "{PROVIDER}"}}] }
        """

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

  Scenario: Check if LLM responds for query request with error for missing provider
    Given The system is in default state
    And The llama-stack connection is disrupted
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello"}
    """
     Then The status code of the response is 500
      And The body of the response contains Unable to connect to Llama Stack

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

  @no_models
  Scenario: Check if LLM responds with an error when no models are configured
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
      """
      {"query": "Write a simple code for reversing string"}
      """
    Then The status code of the response is 404
    And The body of the response contains No models available
