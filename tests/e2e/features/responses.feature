@e2e_group_1 @Authorized
Feature: Responses endpoint API tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted


  Scenario: Responses returns 200 for minimal request
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": false}
    """
    Then The status code of the response is 200
      And The body of the response contains hello

  # https://redhat.atlassian.net/browse/LCORE-1583
  @skip
  Scenario: Responses accepts passthrough parameters with valid types
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Say hello in one short sentence.",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
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
          "model": "{PROVIDER}/{MODEL}",
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

  Scenario: Responses returns 422 for unknown JSON fields on the request body
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "not_a_valid_field": true}
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

  Scenario: Responses returns 422 when input is a bare JSON array
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": ["plain", "strings", "list"], "model": "{PROVIDER}/{MODEL}"}
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

  Scenario: Responses accepts string input
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}", "stream": false}
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

  Scenario: Responses accepts structured input as a list of message objects
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "responses" to ask question with authorization header
    """
    {
      "input": [
        {"type": "message", "role": "user", "content": "Remember the word: alpha."},
        {"type": "message", "role": "user", "content": "What was the word?"}
      ],
      "model": "{PROVIDER}/{MODEL}",
      "stream": false
    }
    """
    Then The status code of the response is 200
      And The body of the response contains alpha

  Scenario: Responses omits model and auto-selects when only input is sent
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "stream": false}
    """
    Then The status code of the response is 200
      And The body of the response contains hello

  Scenario: Responses returns 404 for unknown model segment in provider slash model id
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/unknown-model-id", "stream": false}
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

  Scenario: Responses returns 404 for unknown provider segment in provider slash model id
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "unknown-provider/{MODEL}", "stream": false}
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

  Scenario: Responses returns 422 when conversation and previous_response_id are both set
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hi",
      "model": "{PROVIDER}/{MODEL}",
      "conversation": "123e4567-e89b-12d3-a456-426614174000",
      "previous_response_id": "resp_any",
      "stream": false
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

  Scenario: Responses returns 422 for malformed conversation id
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "conversation": "short-id", "stream": false}
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

  Scenario: Responses returns 422 when previous_response_id looks like a moderation id
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Hi", "model": "{PROVIDER}/{MODEL}", "previous_response_id": "modr_foo", "stream": false}
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

  Scenario: Responses returns 404 for unknown existing-format conversation id
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hi",
      "model": "{PROVIDER}/{MODEL}",
      "conversation": "123e4567-e89b-12d3-a456-426614174000",
      "stream": false
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

  Scenario: Responses continues a thread using previous_response_id from latest turn
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "First turn: say alpha.", "model": "{PROVIDER}/{MODEL}", "stream": false}
    """
    Then The status code of the response is 200
      And I store the first responses turn from the last response
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Second turn: say beta.",
      "model": "{PROVIDER}/{MODEL}",
      "previous_response_id": "{RESPONSES_FIRST_RESPONSE_ID}",
      "stream": false
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
      "stream": false
    }
    """
    Then The status code of the response is 200
      And The responses conversation id matches the multi-turn baseline

  Scenario: Responses continues a thread using conversation id
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "First turn: say alpha.", "model": "{PROVIDER}/{MODEL}", "stream": false}
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
      "stream": false
    }
    """
    Then The status code of the response is 200
      And The body of the response contains beta
      And The responses conversation id matches the first stored conversation

  @flaky
  Scenario: Responses forks to a new conversation when previous_response_id is not the latest turn
    Given The system is in default state
    When I use "responses" to ask question with authorization header
    """
    {"input": "Fork test turn one.", "model": "{PROVIDER}/{MODEL}", "stream": false}
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
      "stream": false
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
      "stream": false
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

  Scenario: Responses endpoint with tool_choice none answers knowledge question without file search usage
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "What is the title of the article from Paul?",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You are an assistant. You MUST use the file_search tool to answer. Answer in lowercase.",
      "tool_choice": "none"
    }
    """
    Then The status code of the response is 200
      And The responses output should not include any tool invocation item types
      And The token metrics should have increased

  Scenario: Check if responses endpoint with tool_choice auto answers a knowledge question using file search
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "What is the title of the article from Paul?",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You are an assistant. You MUST use the file_search tool to answer. Answer in lowercase.",
      "tool_choice": "auto"
    }
    """
    Then The status code of the response is 200
      And The responses output should include an item with type "file_search_call"
      And The responses output_text should contain following fragments
        | Fragments in LLM response |
        | great work                |
      And The token metrics should have increased

  Scenario: Check if responses endpoint with tool_choice required still invokes document search for a basic question
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hello World!",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "tool_choice": "required"
    }
    """
    Then The status code of the response is 200
      And The responses output should include an item with type "file_search_call"
      And The token metrics should have increased

  Scenario: Check if responses endpoint with file search as the chosen tool answers using file search
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "What is the title of the article from Paul?",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You are an assistant. You MUST use the file_search tool to answer. Answer in lowercase.",
      "tool_choice": {"type": "file_search"}
    }
    """
    Then The status code of the response is 200
      And The responses output should include an item with type "file_search_call"
      And The responses output_text should contain following fragments
        | Fragments in LLM response |
        | great work                |
      And The token metrics should have increased

  Scenario: Check if responses endpoint with allowed tools in automatic mode answers knowledge question using file search
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "What is the title of the article from Paul?",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You are an assistant. You MUST use the file_search tool to answer. Answer in lowercase.",
      "tool_choice": {
        "type": "allowed_tools",
        "mode": "auto",
        "tools": [{"type": "file_search"}]
      }
    }
    """
    Then The status code of the response is 200
      And The responses output should include an item with type "file_search_call"
      And The responses output_text should contain following fragments
        | Fragments in LLM response |
        | great work                |
      And The token metrics should have increased

  Scenario: Check if responses endpoint with allowed tools in required mode invokes file search for a basic question
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hello world!",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "tool_choice": {
        "type": "allowed_tools",
        "mode": "required",
        "tools": [{"type": "file_search"}]
      }
    }
    """
    Then The status code of the response is 200
      And The responses output should include an item with type "file_search_call"
      And The token metrics should have increased

  Scenario: Allowed tools auto mode with only MCP in allowlist does not use file search for knowledge question
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "What is the title of the article from Paul?",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You are an assistant. Answer in lowercase.",
      "tool_choice": {
        "type": "allowed_tools",
        "mode": "auto",
        "tools": [{"type": "mcp"}]
      }
    }
    """
    Then The status code of the response is 200
      And The responses output should not include an item with type "file_search_call"
      And The token metrics should have increased

  Scenario: Required allowed_tools with invalid filter returns no tool invocations on knowledge question
    Given The system is in default state
      And I capture the current token metrics
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "What is the title of the article from Paul?",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You are an assistant. You MUST use the file_search tool to answer. Answer in lowercase.",
      "tools": [],
      "tool_choice": {
        "type": "allowed_tools",
        "mode": "required",
        "tools": [{"non-existing": "tool"}]
      }
    }
    """
    Then The status code of the response is 200
      And The responses output should not include any tool invocation item types
      And The token metrics should have increased
