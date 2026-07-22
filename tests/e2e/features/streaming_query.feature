@e2e_group_2 @Authorized
Feature: streaming_query endpoint API tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  Scenario: Check if streaming_query response in tokens matches the full response
    And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
     When I wait for the response to be completed
     Then The status code of the response is 200
      And The streamed response is equal to the full response

  @flaky
  Scenario: Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
      And I capture the current token metrics
      And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "refuse to answer anything but openshift questions", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | questions                 |
      And The token metrics have increased

  @flaky
  Scenario: Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
      And I capture the current token metrics
      And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Generate sample yaml file for simple GitHub Actions workflow.", "system_prompt": "you are linguistic assistant", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | checkout                  |
      And The streamed response contains token counter fields
      And The token metrics have increased

  #enable on demand
  @skip 
  Scenario: Check if LLM ignores new system prompt in same conversation
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
      Then The streamed response contains following fragments
          | Fragments in LLM response |
          | questions                 |

  Scenario: Check if LLM responds for streaming_query request with error for missing query
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
      And The token metrics are not changed

  Scenario: Check if LLM responds for streaming_query request for missing model and provider
     When I use "streaming_query" to ask question with authorization header
     """
     {"query": "Say hello"}
     """
     Then The status code of the response is 200

  Scenario: Check if LLM responds for streaming_query request with error for missing model
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 422
      And The body of the response contains Value error, Model must be specified if provider is specified
      And The token metrics are not changed

  Scenario: Check if LLM responds for streaming_query request with error for missing provider
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}"}
    """
    Then The status code of the response is 422
      And The body of the response contains Value error, Provider must be specified if model is specified

  Scenario: Check if LLM responds for streaming_query request with error for unknown model
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "provider": "{PROVIDER}", "model":"unknown"}
    """
    Then The status code of the response is 404
      And The body of the response contains Model with ID unknown does not exist

  Scenario: Check if LLM responds for streaming_query request with error for unknown provider
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider":"unknown"}
    """
    Then The status code of the response is 404
      And The body of the response contains Model with ID {MODEL} does not exist
      And The token metrics are not changed

  Scenario: Check if LLM responds properly when XML and JSON attachments are sent
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

  @flaky
  Scenario: Check if LLM responds properly when a valid image attachment is sent via streaming
    And I use "streaming_query" to ask question with authorization header
    """
    {
      "query": "Describe this image",
      "attachments": [
        {
          "attachment_type": "image",
          "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
          "content_type": "image/png"
        }
      ],
      "model": "{MODEL}",
      "provider": "{PROVIDER}",
      "system_prompt": "You are a helpful assistant"
    }
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | image                     |

  Scenario: Check if streaming_query rejects image attachment with mismatched attachment_type and content_type
    When I use "streaming_query" to ask question with authorization header
    """
    {
      "query": "Describe this image",
      "attachments": [
        {
          "attachment_type": "configuration",
          "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
          "content_type": "image/png"
        }
      ],
      "model": "{MODEL}",
      "provider": "{PROVIDER}"
    }
    """
    Then The status code of the response is 422
      And The body of the response contains attachment_type and content_type are inconsistent

  Scenario: Check if streaming_query rejects image attachment with valid base64 but non-image data
    When I use "streaming_query" to ask question with authorization header
    """
    {
      "query": "Describe this image",
      "attachments": [
        {
          "attachment_type": "image",
          "content": "dGhpcyBpcyBub3QgYW4gaW1hZ2UgYXQgYWxs",
          "content_type": "image/png"
        }
      ],
      "model": "{MODEL}",
      "provider": "{PROVIDER}"
    }
    """
    Then The status code of the response is 422
      And The body of the response contains invalid image data

  Scenario: Check if streaming_query rejects image attachment with invalid base64 content
    When I use "streaming_query" to ask question with authorization header
    """
    {
      "query": "Describe this image",
      "attachments": [
        {
          "attachment_type": "image",
          "content": "not-valid-base64!!!",
          "content_type": "image/png"
        }
      ],
      "model": "{MODEL}",
      "provider": "{PROVIDER}"
    }
    """
    Then The status code of the response is 422
      And The body of the response contains Invalid base64 content for image attachment

  @flaky
  Scenario: Check if LLM responds properly when text and image attachments are sent together via streaming
    And I use "streaming_query" to ask question with authorization header
    """
    {
      "query": "Summarize the log and describe the image",
      "attachments": [
        {
          "attachment_type": "log",
          "content": "error: something went wrong",
          "content_type": "text/plain"
        },
        {
          "attachment_type": "image",
          "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
          "content_type": "image/png"
        }
      ],
      "model": "{MODEL}",
      "provider": "{PROVIDER}",
      "system_prompt": "You are a helpful assistant"
    }
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | error                     |
          | image                     |

  Scenario: Check if streaming_query with shields returns 413 when question is too long for model context
    When I use "streaming_query" to ask question with too-long query and authorization header
    Then The status code of the response is 413
    And The body of the response contains Prompt is too long

  Scenario: Check if streaming_query without shields returns 200 and error in stream when question is too long for model context
    Given shields are disabled for this scenario
    When I use "streaming_query" to ask question with too-long query and authorization header
    Then The status code of the response is 200
    And The streamed response contains error message Prompt is too long
