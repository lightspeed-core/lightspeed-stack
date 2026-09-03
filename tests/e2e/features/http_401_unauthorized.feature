@e2e_group_3 @Authorized @Feedback @RHIdentity @RBAC
Feature: HTTP 401 Unauthorized

  Aggregates end-to-end scenarios that assert a 401 response when authentication
  is missing, invalid, or rejected by the configured auth module.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      

  # --- query / streaming_query ---

  Scenario: Check if LLM responds to sent question with error when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
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
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I use "query" to ask question
    """
    {"query": "Write a simple code for reversing string", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 401
    And The body of the response contains No Authorization header found

  Scenario: Check if LLM responds to sent question with error when not authenticated (streaming_query)
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
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

  # --- conversations ---

  Scenario: Check if conversations endpoint fails when the auth header is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    And The status code of the response is 200
    And I store conversation details
    And I remove the auth header
    When I access REST API endpoint "conversations" using HTTP GET method
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

  Scenario: Check if conversations/{conversation_id} endpoint fails when the auth header is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    And The status code of the response is 200
    And I store conversation details
    And I remove the auth header
    When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
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

  # --- FAISS ---

  Scenario: Check if rags endpoints responds with error when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access REST API endpoint rags using HTTP GET method
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

  # --- prompts ---

  Scenario: Prompts list returns 401 when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access REST API endpoint "prompts" using HTTP GET method
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

  Scenario: Prompts create returns 401 when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 401
    And The body of the response contains No Authorization header found

  Scenario: Prompts get by id returns 401 when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access REST API endpoint "prompts/pmpt_5c76d7f7c633ef97477adeb2f642150d8d08e8a6526e9909" using HTTP GET method
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

  Scenario: Prompts update returns 401 when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access REST API endpoint "prompts/pmpt_5c76d7f7c633ef97477adeb2f642150d8d08e8a6526e9909" using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 1, "set_as_default": true, "variables": ["text"]}
    """
    Then The status code of the response is 401
    And The body of the response contains No Authorization header found

  Scenario: Prompts delete returns 401 when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access REST API endpoint "prompts/pmpt_5c76d7f7c633ef97477adeb2f642150d8d08e8a6526e9909" using HTTP DELETE method
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

  # --- authorized (noop token) ---

  Scenario: Check if the authorized endpoint fails when user_id and auth header are not provided
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access endpoint "authorized" using HTTP POST method
    """
    {"placeholder":"abc"}
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

  Scenario: Check if the authorized endpoint works with proper user_id but bearer token is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
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

  Scenario: Check if the authorized endpoint works when auth token is malformed
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
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

  # --- rlsapi v1 ---

  Scenario: Request without authorization returns 401 (rlsapi infer)
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
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

  Scenario: Request with empty bearer token returns 401 (rlsapi infer)
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I use "infer" to ask question
    """
    {"question": "How do I list files?"}
    """
    Then The status code of the response is 401
    And The body of the response contains No Authorization header found

  # --- rh-identity ---

  Scenario: Request fails when x-rh-identity header is missing (rh-identity)
    Given The service uses the lightspeed-stack-auth-rh-identity.yaml configuration
    And The service is restarted
    And I remove the auth header
    When I access endpoint "authorized" using HTTP POST method
    """
    {"placeholder":"abc"}
    """
    Then The status code of the response is 401
    And The body of the response is the following
    """
    {"detail": "Missing x-rh-identity header"}
    """

  # --- RBAC ---

  Scenario: Request without token returns 401 (RBAC)
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    And I remove the auth header
    When I access REST API endpoint "models" using HTTP GET method
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

  Scenario: Request with malformed Authorization header returns 401 (RBAC)
    Given The service uses the lightspeed-stack-rbac.yaml configuration
    And The service is restarted
    And I set the Authorization header to NotBearer sometoken
    When I access REST API endpoint "models" using HTTP GET method
    Then The status code of the response is 401

  # --- conversation cache v2 ---

  Scenario: V2 conversations endpoint fails when auth header is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given REST API service prefix is /v2
    And I remove the auth header
    When I access REST API endpoint "conversations" using HTTP GET method
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

  Scenario: V2 conversations/{conversation_id} endpoint fails when auth header is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given REST API service prefix is /v1
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "Explain the difference between SQL and NoSQL databases", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And I remove the auth header
    And REST API service prefix is /v2
    When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
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

  Scenario: V2 conversations/{conversation_id} DELETE endpoint fails when auth header is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given REST API service prefix is /v1
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "How does load balancing work in microservices architecture?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And I remove the auth header
    And REST API service prefix is /v2
    When I use REST API conversation endpoint with conversation_id from above using HTTP DELETE method
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

  Scenario: V2 conversations PUT endpoint fails when auth header is not present
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given REST API service prefix is /v1
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And I use "query" to ask question with authorization header
    """
    {"query": "What is continuous integration?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And I remove the auth header
    And REST API service prefix is /v2
    When I use REST API conversation endpoint with conversation_id from above and topic_summary "CI/CD Pipeline" using HTTP PUT method
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

  # --- responses ---

  Scenario: Responses returns error when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given The system is in default state
    When I use "responses" to ask question
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": false}
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

  Scenario: Responses returns error when bearer token is missing
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given The system is in default state
    And I set the Authorization header to Bearer
    When I use "responses" to ask question
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": false}
    """
    Then The status code of the response is 401
    And The body of the response contains No Authorization header found

  # --- responses streaming ---

  Scenario: Streaming responses returns error when not authenticated
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I use "responses" to ask question
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": true}
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

  Scenario: Streaming responses returns error when bearer token is missing
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    When I use "responses" to ask question
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 401
    And The body of the response contains No Authorization header found

  # --- feedback ---

  Scenario: Check if feedback endpoint is not working when not authorized
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    Given I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And A new conversation is initialized
    And I remove the auth header
    When I submit the following feedback for the conversation created before
    """
    {
        "llm_response": "Sample Response",
        "sentiment": -1,
        "user_feedback": "Not satisfied with the response quality",
        "user_question": "Sample Question"
    }
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

  Scenario: Check if update feedback status endpoint is not working when not authorized
    Given The service uses the lightspeed-stack-auth-noop-token.yaml configuration
    And The service is restarted
    And I remove the auth header
    When The feedback is enabled
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