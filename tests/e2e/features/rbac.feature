@e2e_group_2 @RBAC
Feature: Role-Based Access Control (RBAC)

  Comprehensive tests for role-based access control to ensure
  authentication and authorization work correctly.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-rbac.yaml configuration
      And The service is restarted

  # ============================================
  # Admin Role - Full Access
  # ============================================

  Scenario: Admin can access query endpoint
      And I authenticate as "admin" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 200

  Scenario: Admin can access models endpoint
      And I authenticate as "admin" user
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 200

  Scenario: Admin can list conversations
      And I authenticate as "admin" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200

  # ============================================
  # User Role - Standard Access
  # ============================================

  Scenario: User can access query endpoint
      And I authenticate as "user" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 200

  Scenario: User can list conversations
      And I authenticate as "user" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200

  # ============================================
  # Viewer Role - Read Only
  # ============================================

  Scenario: Viewer can list conversations
      And I authenticate as "viewer" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200

  Scenario: Viewer can access info endpoint
      And I authenticate as "viewer" user
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: Viewer cannot query - returns 403
      And I authenticate as "viewer" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  # ============================================
  # Query-Only Role - Limited Access (no model_override)
  # ============================================

  Scenario: Query-only user can query without specifying model
      And I authenticate as "query_only" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi"}
      """
     Then The status code of the response is 200

  Scenario: Query-only user cannot override model - returns 403
      And I authenticate as "query_only" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 403
      And The body of the response contains model_override

  Scenario: Query-only user cannot list conversations - returns 403
      And I authenticate as "query_only" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  # ============================================
  # No Role - Minimal Access (everyone role only)
  # ============================================

  Scenario: No-role user can access info endpoint (everyone role)
      And I authenticate as "no_role" user
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: No-role user cannot query - returns 403
      And I authenticate as "no_role" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  Scenario: No-role user cannot list conversations - returns 403
      And I authenticate as "no_role" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  Scenario: No-role user cannot hit responses API - returns 403
    And I authenticate as "no_role" user
    And I use "responses" to ask question with authorization header
    """
    {
      "input": "Tell me a short bedtime story. Max length: 15 sentences",
      "model": "{PROVIDER}/{MODEL}",
      "instructions": "You are a helpful assistant",
      "stream": false
    }
    """
    Then The status code of the response is 403
    And The body of the response contains does not have permission

  # ============================================
  # Testing resource ownership - authorization checks
  # ============================================

  Scenario: Query on another user's conversation - returns 403
    And I authenticate as "user" user
    And I use "query" to ask question with authorization header
    """
    {"query": "Give me first 6 digits of PI", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    And The status code of the response is 200
    And I store conversation details
    And I authenticate as "user2" user
    When I use "query" to ask question with authorization header
     """
     {"query": "Say hi", "conversation_id": "{CONVERSATION_ID}", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 403
     And The body of the response contains does not have permission
     And The body of the response is the following
     """
     {
        "detail": {
          "response": "User does not have permission to perform this action",
         "cause": "User user2-id does not have permission to read conversation with ID {CONVERSATION_ID}"
        }
      }
     """

  Scenario: Streaming query on another user's conversation - returns 403
    And I authenticate as "user" user
    And I use "streaming_query" to ask question with authorization header
    """
    {"query": "Give me first 6 digits of PI", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    And I wait for the response to be completed
    And The status code of the response is 200
    And I authenticate as "user2" user
    When I use "streaming_query" to ask question with same conversation_id
     """
     {"query": "Say hi!", "system_prompt": "provide coding assistance", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 403
     And The body of the response contains does not have permission
     And The body of the response is the following
     """
     {
        "detail": {
          "response": "User does not have permission to perform this action",
         "cause": "User user2-id does not have permission to read conversation with ID {CONVERSATION_ID}"
        }
      }
     """

  Scenario: Accessing another user's responses returns 403 Forbidden - returns 403
    And I authenticate as "user" user
    And I use "responses" to ask question with authorization header
    """
    {
      "input": "List all colors of the rainbow",
      "model": "{PROVIDER}/{MODEL}",
      "instructions": "You are a helpful assistant",
      "stream": false
    }
    """
    And The status code of the response is 200
    And I store conversation details
    And I authenticate as "user2" user
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hello there!",
      "model": "{PROVIDER}/{MODEL}",
      "instructions": "You are a helpful assistant",
      "stream": false,
      "conversation": "{CONVERSATION_ID}"
    }
    """
     Then The status code of the response is 403
     And The body of the response contains does not have permission
     And The body of the response is the following
    """
     {
        "detail": {
          "response": "User does not have permission to perform this action",
         "cause": "User user2-id does not have permission to read conversation with ID {CONVERSATION_ID}"
        }
      }
    """

  Scenario: Accessing another user's streaming responses - returns 403
    And I authenticate as "user" user
    And I use "responses" to ask question with authorization header
    """
    {
      "input": "List all colors of the rainbow",
      "model": "{PROVIDER}/{MODEL}",
      "instructions": "You are a helpful assistant",
      "stream": true
    }
    """
    And The status code of the response is 200
    And I store conversation details
    And I authenticate as "user2" user
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Hello there!",
      "model": "{PROVIDER}/{MODEL}",
      "instructions": "You are a helpful assistant",
      "stream": true,
      "conversation": "{CONVERSATION_ID}"
    }
    """
     Then The status code of the response is 403
     And The body of the response contains does not have permission
     And The body of the response is the following
    """
     {
        "detail": {
          "response": "User does not have permission to perform this action",
         "cause": "User user2-id does not have permission to read conversation with ID {CONVERSATION_ID}"
        }
      }
    """
