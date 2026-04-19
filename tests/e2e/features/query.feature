@e2e_group_3 @Authorized
Feature: Query endpoint API tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  @flaky
  Scenario: Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
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

  @flaky
  Scenario: Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
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

  Scenario: Check if LLM responds to sent question with error when attempting to access conversation
     And I capture the current token metrics
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567-e89b-12d3-a456-426614174000", "query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
      Then The status code of the response is 404
      And The body of the response contains Conversation not found
      And The token metrics should not have changed

Scenario: Check if LLM responds to sent question with error when attempting to access conversation with incorrect conversation ID format
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567", "query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
      Then The status code of the response is 422
      And The body of the response contains Value error, Improper conversation ID '123e4567'

Scenario: Check if LLM responds for query request with error for missing query
     When I use "query" to ask question with authorization header
     """
     {"conversation_id": "123e4567", "query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
      Then The status code of the response is 422
      And The body of the response contains Value error, Improper conversation ID '123e4567'

  Scenario: Check if LLM responds for query request with error for missing query
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
     When I use "query" to ask question with authorization header
     """
     {"query": "Say hello"}
     """
     Then The status code of the response is 200

  Scenario: Check if LLM responds for query request with error for missing model
     When I use "query" to ask question with authorization header
     """
     {"query": "Say hello", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 422
      And The body of the response contains Value error, Model must be specified if provider is specified

  Scenario: Check if LLM responds for query request with error for missing provider
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}"}
    """
     Then The status code of the response is 422
      And The body of the response contains Value error, Provider must be specified if model is specified

    Scenario: Check if LLM responds for query request with error for unknown model
     When I use "query" to ask question with authorization header
     """
     {"query": "Say hello", "provider": "{PROVIDER}", "model":"unknown"}
     """
     Then The status code of the response is 404
      And The body of the response contains Model with ID unknown does not exist

  Scenario: Check if LLM responds for query request with error for unknown provider
    When I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider":"unknown"}
    """
     Then The status code of the response is 404
      And The body of the response contains Model with ID {MODEL} does not exist

  Scenario: Check if LLM responds properly when XML and JSON attachments are sent
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

  Scenario: Check if query with shields returns 413 when question is too long for model context 
    When I use "query" to ask question with too-long query and authorization header
    Then The status code of the response is 413
    And The body of the response contains Prompt is too long

  #https://issues.redhat.com/browse/LCORE-1387
  @skip
  Scenario: Check if query without shields returns 413 when question is too long for model context
    Given shields are disabled for this scenario
    When I use "query" to ask question with too-long query and authorization header
    Then The status code of the response is 413
    And The body of the response contains Prompt is too long
