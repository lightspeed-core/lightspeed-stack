@e2e_group_2 @Authorized
Feature: Conversation Cache V2 API tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted


  # ====================================================================
  # V2 Conversations List Endpoint Tests
  # ====================================================================

  # BUG: Test without no_tools to expose AttributeError with empty vector database
  # TODO: Remove @skip when bug is fixed (empty vector DB causes 500 error)
  @skip
  Scenario: V2 conversations endpoint WITHOUT no_tools (known bug - empty vector DB)
    Given REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "Search the documentation for Kubernetes deployment strategies", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And I store conversation details
    And REST API service prefix is /v2
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200
     And The conversation with conversation_id from above is returned


  Scenario: V2 conversations endpoint finds the correct conversation when it exists
    Given REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "Explain the benefits of containerization in cloud environments", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And REST API service prefix is /v2
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200
     And The conversation with conversation_id from above is returned
     And The conversation has topic_summary and last_message_timestamp
     And The body of the response has the following schema
     """
     {
       "$schema": "https://json-schema.org/draft/2020-12/schema",
       "type": "object",
       "properties": {
         "conversations": {
           "type": "array",
           "items": {
             "type": "object",
             "properties": {
               "conversation_id": { "type": "string" },
               "topic_summary": { "type": ["string", "null"] },
               "last_message_timestamp": { "type": "number" }
             },
             "required": ["conversation_id", "topic_summary", "last_message_timestamp"]
           }
         }
       },
       "required": ["conversations"]
     }
     """

  # ====================================================================
  # V2 Conversation GET by ID Endpoint Tests
  # ====================================================================

  Scenario: V2 conversations/{conversation_id} endpoint finds conversation with full metadata
    Given REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "What is Kubernetes?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And I use "query" to ask question with same conversation_id
    """
    {"query": "How do I install it?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
     Then The status code of the response is 200
     And The returned conversation details have expected conversation_id
     And The conversation history contains 2 messages
     And The conversation history has correct metadata
     And The conversation uses model {MODEL} and provider {PROVIDER}
     And The body of the response has the following schema
     """
     {
       "$schema": "https://json-schema.org/draft/2020-12/schema",
       "type": "object",
       "properties": {
         "conversation_id": { "type": "string" },
         "chat_history": {
           "type": "array",
           "items": {
             "type": "object",
             "properties": {
               "provider": { "type": "string" },
               "model": { "type": "string" },
               "messages": {
                 "type": "array",
                 "items": {
                   "type": "object",
                   "properties": {
                     "content": { "type": "string" },
                     "type": { "type": "string", "enum": ["user", "assistant"] }
                   }
                 }
               },
               "tool_calls": {
                 "type": "array",
                 "items": { "type": "object" }
               },
               "tool_results": {
                 "type": "array",
                 "items": { "type": "object" }
               },
               "started_at": { "type": "string", "format": "date-time" },
               "completed_at": { "type": "string", "format": "date-time" }
             },
             "required": ["provider", "model", "messages", "tool_calls", "tool_results", "started_at", "completed_at"]
           }
         }
       }
     }
     """


  Scenario: V2 conversations/{conversation_id} GET endpoint fails when conversation_id is malformed
    Given REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id "abcdef" using HTTP GET method
     Then The status code of the response is 400
     And The body of the response is the following
     """
     {
       "detail": {
         "response": "Invalid conversation ID format",
         "cause": "The conversation ID abcdef has invalid format."
       }
     }
     """


  Scenario: V2 conversations/{conversation_id} GET endpoint fails when conversation does not exist
    Given REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id "12345678-abcd-0000-0123-456789abcdef" using HTTP GET method
     Then The status code of the response is 404
     And The body of the response contains Conversation not found

  @NoCacheConfig
  Scenario: Check conversations/{conversation_id} fails when cache not configured
    Given The service uses the lightspeed-stack-no-cache.yaml configuration
      And The service is restarted
      And REST API service prefix is /v2
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 500
     And The body of the response contains Conversation cache not configured


  # ====================================================================
  # V2 Conversation DELETE Endpoint Tests
  # ====================================================================

  Scenario: V2 conversations DELETE endpoint removes the correct conversation
    Given REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "What are the advantages of using Terraform for infrastructure as code?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id from above using HTTP DELETE method
     Then The status code of the response is 200
     And The returned conversation details have expected conversation_id
     And The body of the response, ignoring the "conversation_id" field, is the following
      """
      {"success": true, "response": "Conversation deleted successfully", "deleted": true}
      """
     When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
     Then The status code of the response is 404
     And The body of the response contains Conversation not found


  Scenario: V2 conversations/{conversation_id} DELETE endpoint fails when conversation_id is malformed
    Given REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id "abcdef" using HTTP DELETE method
     Then The status code of the response is 400
     And The body of the response contains Invalid conversation ID format


  Scenario: V2 conversations DELETE endpoint fails when the conversation does not exist
    Given REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id "12345678-abcd-0000-0123-456789abcdef" using HTTP DELETE method
     Then The status code of the response is 200
     And The body of the response, ignoring the "conversation_id" field, is the following
      """
      {"success": true, "response": "Conversation not found", "deleted": false}
      """

  # ====================================================================
  # V2 Conversation PUT (Update Topic Summary) Endpoint Tests
  # ====================================================================

  Scenario: V2 conversations PUT endpoint successfully updates topic summary
    Given REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "How do I deploy applications on Kubernetes?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id from above and topic_summary "Kubernetes Deployment Strategies" using HTTP PUT method
     Then The status code of the response is 200
     And The returned conversation details have expected conversation_id
     And The body of the response, ignoring the "conversation_id" field, is the following
      """
      {"success": true, "message": "Topic summary updated successfully"}
      """
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200
     And The conversation with conversation_id from above is returned
     And The conversation topic_summary is "Kubernetes Deployment Strategies"


  Scenario: V2 conversations PUT endpoint fails when conversation_id is malformed
    Given REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id "invalid-id" and topic_summary "Updated Summary" using HTTP PUT method
     Then The status code of the response is 400
     And The body of the response is the following
     """
     {
       "detail": {
         "response": "Invalid conversation ID format",
         "cause": "The conversation ID invalid-id has invalid format."
       }
     }
     """


  Scenario: V2 conversations PUT endpoint fails when conversation does not exist
    Given REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id "12345678-abcd-0000-0123-456789abcdef" and topic_summary "Updated Summary" using HTTP PUT method
     Then The status code of the response is 404
     And The body of the response contains Conversation not found


  Scenario: V2 conversations PUT endpoint fails with empty topic summary (422)
    Given REST API service prefix is /v1
    And I use "query" to ask question with authorization header
    """
    {"query": "Explain GraphQL advantages over REST", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    And The status code of the response is 200
    And I store conversation details
    And REST API service prefix is /v2
     When I use REST API conversation endpoint with conversation_id from above and empty topic_summary using HTTP PUT method
     Then The status code of the response is 422
     And The body of the response contains String should have at least 1 character
