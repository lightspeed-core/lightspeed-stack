@Authorized
Feature: streaming_query endpoint API tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1


  Scenario: Check if streaming_query response in tokens matches the full response
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
     When I wait for the response to be completed
     Then The status code of the response is 200
      And The streamed response is equal to the full response

  Scenario: Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
      And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything but openshift questions", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response should contain following fragments
          | Fragments in LLM response |
          | questions                 |
      And The token metrics should have increased

  Scenario: Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
      And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "you are linguistic assistant", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response should contain following fragments
          | Fragments in LLM response |
          | checkout                  |
      And The streamed response should contain token counter fields
      And The token metrics should have increased

  #enable on demand
  @skip 
  Scenario: Check if LLM ignores new system prompt in same conversation
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    And I use "streaming_query" to ask question with same conversation_id
    """
    {"query": "Write a simple code for reversing string", "system_prompt": "provide coding assistance", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    When I wait for the response to be completed
      Then The streamed response should contain following fragments
          | Fragments in LLM response |
          | questions                 |

  Scenario: Check if LLM responds for streaming_query request with error for missing query
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"provider": "{PROVIDER}"}
    """
    Then The status code of the response is 422
      And The body of the response is the following
          """
          { "detail": [{"type": "missing", "loc": [ "body", "query" ], "msg": "Field required", "input": {"provider": "{PROVIDER}"}}] }
          """
      And The token metrics should not have changed

  Scenario: Check if LLM responds for streaming_query request for missing model and provider
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I use "streaming_query" to ask question with authorization header
     """
     {"query": "Say hello"}
     """
     Then The status code of the response is 200

  Scenario: Check if LLM responds for streaming_query request with error for missing model
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 422
      And The body of the response contains Value error, Model must be specified if provider is specified
      And The token metrics should not have changed

  Scenario: Check if LLM responds for streaming_query request with error for missing provider
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}"}
    """
    Then The status code of the response is 422
      And The body of the response contains Value error, Provider must be specified if model is specified

  Scenario: Check if LLM responds for streaming_query request with error for unknown model
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "provider": "{PROVIDER}", "model":"unknown"}
    """
    Then The status code of the response is 404
      And The body of the response contains Model with ID unknown does not exist

  Scenario: Check if LLM responds for streaming_query request with error for unknown provider
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider":"unknown"}
    """
    Then The status code of the response is 404
      And The body of the response contains Model with ID gpt-4o-mini does not exist
      And The token metrics should not have changed

  Scenario: Check if LLM responds properly when XML and JSON attachments are sent
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "streaming_query" to ask question with authorization header
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

  Scenario: Check if LLM responds to sent question with error when not authenticated
    Given The system is in default state
    When I use "streaming_query" to ask question
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
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

  Scenario: Check if LLM responds to sent question with error when not authenticated
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
        {
            "detail": {
                "response": "Missing or invalid credentials provided by client",
                "cause": "MCP server at http://mock-mcp:3000 requires OAuth"
            }
        }
    """
    And The headers of the response contains the following "www-authenticate"

