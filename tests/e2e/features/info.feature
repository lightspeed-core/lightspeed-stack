@e2e_group_3
Feature: Info tests


  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack.yaml configuration
      And The service is restarted

  Scenario: Check if the OpenAPI endpoint works as expected
     When I access endpoint "openapi.json" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains OpenAPI

  Scenario: Check if info endpoint is working
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper name Lightspeed Core Service (LCS) and version 0.5.0
      And The body of the response has llama-stack version 0.6.0

  Scenario: Check if shields endpoint is working
     When I access REST API endpoint "shields" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper shield structure


  #https://issues.redhat.com/browse/LCORE-1211
  @skip
  Scenario: Check if tools endpoint is working
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


  Scenario: Check if metrics endpoint is working
     When I access endpoint "metrics" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains ls_provider_model_configuration