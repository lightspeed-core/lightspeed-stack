Feature: Info tests


  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if the OpenAPI endpoint works as expected
    Given The system is in default state
     When I access endpoint "openapi.json" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains OpenAPI

  Scenario: Check if info endpoint is working
    Given The system is in default state
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper name Lightspeed Core Service (LCS) and version 0.4.1
      And The body of the response has llama-stack version 0.4.3

  @skip-in-library-mode
  Scenario: Check if info endpoint reports error when llama-stack connection is not working
    Given The system is in default state
    And  The llama-stack connection is disrupted
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 503
      And The body of the response is the following
      """
         {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
      """

  Scenario: Check if models endpoint is working
    Given The system is in default state
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper model structure


  @skip-in-library-mode
  Scenario: Check if models endpoint reports error when llama-stack is unreachable
    Given The system is in default state
    And  The llama-stack connection is disrupted
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 503
      And The body of the response is the following
      """
         {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
      """

  Scenario: Check if shields endpoint is working
    Given The system is in default state
     When I access REST API endpoint "shields" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper shield structure


  @skip-in-library-mode
  Scenario: Check if shields endpoint reports error when llama-stack is unreachable
    Given The system is in default state
    And  The llama-stack connection is disrupted
     When I access REST API endpoint "shields" using HTTP GET method
     Then The status code of the response is 503
      And The body of the response is the following
      """
         {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
      """

  #https://issues.redhat.com/browse/LCORE-1211
  @skip
  Scenario: Check if tools endpoint is working
    Given The system is in default state
     When I access REST API endpoint "tools" using HTTP GET method
     Then The status code of the response is 200
      And The response contains 2 tools listed for provider rag-runtime
      And The body of the response has the following schema
      """
         {
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "type": "object",
          "properties": {
            "identifier": { "type": "string" },
            "description": { "type": "string" },
            "parameters": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "description": { "type": "string" },
                  "name": { "type": "string" },
                  "parameter_type": { "type": "string" },
                  "required": { "type": "boolean" },
                  "default": { "type": ["string", "null"] }
                }
              }
            },
            "provider_id": { "type": "string" },
            "toolgroup_id": { "type": "string" },
            "server_source": { "type": "string" },
            "type": { "type": "string" }
          }
        }
      """
      And The body of the response has proper structure for provider rag-runtime
      """
      {
        "identifier": "insert_into_memory",
        "description": "Insert documents into memory",
        "provider_id": "rag-runtime",
        "toolgroup_id": "builtin::rag",
        "server_source": "builtin",
        "type": "tool"
      }
      """


  @skip-in-library-mode
  Scenario: Check if tools endpoint reports error when llama-stack is unreachable
    Given The system is in default state
    And  The llama-stack connection is disrupted
     When I access REST API endpoint "tools" using HTTP GET method
     Then The status code of the response is 503
      And The body of the response is the following
      """
         {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
      """

  Scenario: Check if metrics endpoint is working
    Given The system is in default state
     When I access endpoint "metrics" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains ls_provider_model_configuration

  Scenario: Check if MCP client auth options endpoint is working
    Given The system is in default state
     When I access REST API endpoint "mcp-auth/client-options" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper client auth options structure
      And The response contains server "github-api" with client auth header "Authorization"
      And The response contains server "gitlab-api" with client auth header "X-API-Token"