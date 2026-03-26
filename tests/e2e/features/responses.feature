@Authorized
Feature: Responses endpoint API tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if responses endpoint answers a minimal question
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": false}
    """
    Then The status code of the response is 200

  Scenario: Check if responses endpoint streams a minimal answer
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200

  Scenario: Check if responses endpoint with tool_choice none answers knowledge question without file search usage
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
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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

  Scenario: Allowed tools auto mode with only MCP in allowlist does not use file search for article question
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
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
