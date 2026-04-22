@e2e_group_1 @Authorized
Feature: Responses endpoint streaming API tests

# Same coverage as ``responses.feature`` with ``stream=true`` (SSE for success paths;

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  Scenario: Streaming responses returns 200 for minimal request
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200
      And The body of the response contains hello

  # https://redhat.atlassian.net/browse/LCORE-1583
  @skip
  Scenario: Streaming responses accepts passthrough parameters with valid types
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Say hello in one short sentence.",
      "model": "{PROVIDER}/{MODEL}",
      "stream": true,
      "instructions": "You are a helpful assistant.",
      "prompt": {"id": "e2e_responses_passthrough_prompt"},
      "reasoning": {"effort": "low"},
      "safety_identifier": "e2e-responses-passthrough",
      "text": {"format": {"type": "text"}},
      "tool_choice": "auto",
      "temperature": 0.2,
      "max_output_tokens": 256,
      "max_infer_iters": 4,
      "max_tool_calls": 8,
      "parallel_tool_calls": false,
      "metadata": {"e2e": "responses-passthrough"},
      "store": true,
      "generate_topic_summary": false
    }
    """
    Then The status code of the response is 200
      And the body of the response has the following structure
        """
        {
          "object": "response",
          "status": "completed",
          "model": "{MODEL_SHORT}",
          "instructions": "You are a helpful assistant.",
          "prompt": {"id": "e2e_responses_passthrough_prompt"},
          "reasoning": {"effort": "low"},
          "safety_identifier": "e2e-responses-passthrough",
          "text": {"format": {"type": "text"}},
          "tool_choice": "auto",
          "temperature": 0.2,
          "max_output_tokens": 256,
          "max_tool_calls": 8,
          "parallel_tool_calls": false,
          "metadata": {"e2e": "responses-passthrough"},
          "store": true
        }
        """

  Scenario: Streaming responses returns 422 for unknown JSON fields on the request body
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "stream": true, "not_a_valid_field": true}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "extra_forbidden",
              "loc": ["body", "not_a_valid_field"],
              "msg": "Extra inputs are not permitted"
            }
          ]
        }
        """

  Scenario: Streaming responses returns 422 for invalid include enum value
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "stream": true, "include": ["not_a_valid_include_token"]}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "literal_error",
              "loc": ["body", "include", 0],
              "input": "not_a_valid_include_token"
            }
          ]
        }
        """

  Scenario: Streaming responses returns 422 when metadata values are not strings
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "stream": true, "metadata": {"k": 1}}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "string_type",
              "loc": ["body", "metadata", "k"],
              "msg": "Input should be a valid string"
            }
          ]
        }
        """

  Scenario: Streaming responses returns 422 when parallel_tool_calls is not a boolean
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "stream": true, "parallel_tool_calls": "maybe"}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "bool_parsing",
              "loc": ["body", "parallel_tool_calls"],
              "input": "maybe"
            }
          ]
        }
        """

  Scenario: Streaming responses returns 422 when input is a bare JSON array
    When I use "responses" to ask question with authorization header
    """
    {"input": ["plain", "strings", "list"], "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "string_type",
              "loc": ["body", "input", "str"],
              "input": ["plain", "strings", "list"]
            }
          ]
        }
        """

  Scenario: Streaming responses accepts string input
    When I use "responses" to ask question with authorization header
    """
    {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200
      And the body of the response has the following structure
        """
        {
          "object": "response",
          "status": "completed",
          "model": "{PROVIDER}/{MODEL}",
          "output": [
            {
              "type": "message",
              "role": "assistant"
            }
          ]
        }
        """
      And The body of the response contains ok

  Scenario: Streaming responses accepts structured input as a list of message objects
    When I use "responses" to ask question with authorization header
    """
    {
      "input": [
        {"type": "message", "role": "user", "content": "Remember the word: alpha."},
        {"type": "message", "role": "user", "content": "What was the word?"}
      ],
      "model": "{PROVIDER}/{MODEL}",
      "stream": true
    }
    """
    Then The status code of the response is 200
      And The body of the response contains alpha

  Scenario: Streaming responses omits model and auto-selects like query when only input is sent
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "stream": true}
    """
    Then The status code of the response is 200
      And The body of the response contains hello

  Scenario: Streaming responses returns 404 for unknown model segment in provider slash model id  
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/unknown-model-id", "stream": true}
    """
    Then The status code of the response is 404
      And the body of the response has the following structure
        """
        {
          "detail": {
            "response": "Model not found",
            "cause": "Model with ID unknown-model-id does not exist"
          }
        }
        """

  Scenario: Streaming responses returns 404 for unknown provider segment in provider slash model id
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "unknown-provider/{MODEL}", "stream": true}
    """
    Then The status code of the response is 404
      And the body of the response has the following structure
        """
        {
          "detail": {
            "response": "Model not found",
            "cause": "Model with ID {MODEL} does not exist"
          }
        }
        """

  Scenario: Streaming responses returns 422 when conversation and previous_response_id are both set
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hi",
      "model": "{PROVIDER}/{MODEL}",
      "conversation": "123e4567-e89b-12d3-a456-426614174000",
      "previous_response_id": "resp_any",
      "stream": true
    }
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "value_error",
              "loc": ["body"],
              "msg": "Value error, `conversation` and `previous_response_id` are mutually exclusive. Only one can be provided at a time."
            }
          ]
        }
        """

  Scenario: Streaming responses returns 422 for malformed conversation id
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "conversation": "short-id", "stream": true}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "value_error",
              "loc": ["body", "conversation"],
              "msg": "Value error, Improper conversation ID 'short-id'",
              "input": "short-id"
            }
          ]
        }
        """

  Scenario: Streaming responses returns 422 when previous_response_id looks like a moderation id
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "previous_response_id": "modr_foo", "stream": true}
    """
    Then The status code of the response is 422
      And the body of the response has the following structure
        """
        {
          "detail": [
            {
              "type": "value_error",
              "loc": ["body", "previous_response_id"],
              "msg": "Value error, You cannot provide context by moderation response.",
              "input": "modr_foo"
            }
          ]
        }
        """

  Scenario: Streaming responses returns 404 for unknown existing-format conversation id
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hi",
      "model": "{PROVIDER}/{MODEL}",
      "conversation": "123e4567-e89b-12d3-a456-426614174000",
      "stream": true
    }
    """
    Then The status code of the response is 404
      And the body of the response has the following structure
        """
        {
          "detail": {
            "response": "Conversation not found",
            "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist"
          }
        }
        """

  @flaky
  Scenario: Streaming responses continues a thread using previous_response_id from latest turn
    When I use "responses" to ask question with authorization header
    """
    {"input": "First turn: say alpha.", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200
      And I store the first responses turn from the last response
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Second turn: say beta.",
      "model": "{PROVIDER}/{MODEL}",
      "previous_response_id": "{RESPONSES_FIRST_RESPONSE_ID}",
      "stream": true
    }
    """
    Then The status code of the response is 200
      And I store the multi-turn baseline from the last responses response
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Third turn: say gamma.",
      "model": "{PROVIDER}/{MODEL}",
      "previous_response_id": "{RESPONSES_SECOND_RESPONSE_ID}",
      "stream": true
    }
    """
    Then The status code of the response is 200
      And The responses conversation id matches the multi-turn baseline

  @flaky
  Scenario: Streaming responses continues a thread using conversation id
    When I use "responses" to ask question with authorization header
    """
    {"input": "First turn: say alpha.", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200
      And The body of the response contains alpha
      And I store the first responses turn from the last response
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Second turn: say beta.",
      "model": "{PROVIDER}/{MODEL}",
      "conversation": "{RESPONSES_CONVERSATION_ID}",
      "stream": true
    }
    """
    Then The status code of the response is 200
      And The body of the response contains beta
      And The responses conversation id matches the first stored conversation

  @flaky
  Scenario: Streaming responses forks to a new conversation when previous_response_id is not the latest turn  
    When I use "responses" to ask question with authorization header
    """
    {"input": "Fork test turn one.", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200
      And The body of the response contains one
      And I store the first responses turn from the last response
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Fork test turn two.",
      "model": "{PROVIDER}/{MODEL}",
      "previous_response_id": "{RESPONSES_FIRST_RESPONSE_ID}",
      "stream": true
    }
    """
    Then The status code of the response is 200
      And The body of the response contains two
      And I store the multi-turn baseline from the last responses response
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Fork from middle using first response id.",
      "model": "{PROVIDER}/{MODEL}",
      "previous_response_id": "{RESPONSES_FIRST_RESPONSE_ID}",
      "stream": true
    }
    """
    Then The status code of the response is 200
      And The body of the response contains middle
      And The responses conversation id is different from the multi-turn baseline
      And I store the forked responses conversation id from the last response
    When I use REST API conversation endpoint with the forked responses conversation id using HTTP GET method
    Then The status code of the response is 200
      And The GET conversation response id matches the forked responses conversation id
      And The body of the response contains Fork from middle
      And The conversation history contains 1 messages
    When I use REST API conversation endpoint with the responses multi-turn baseline conversation id using HTTP GET method
    Then The status code of the response is 200
      And The GET conversation response id matches the responses multi-turn baseline conversation id
      And The body of the response contains Fork test turn two
      And The conversation history contains 2 messages
