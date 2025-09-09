Feature: Info tests


  Background:
    Given The service is started locally
      And REST API service hostname is localhost
      And REST API service port is 8080
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
      And The body of the response has proper name Lightspeed Core Service (LCS) and version 0.2.0
      And The body of the response has llama-stack version 0.2.22

  Scenario: Check if info endpoint reports error when llama-stack connection is not working
    Given The system is in default state
    And  The llama-stack connection is disrupted
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 500
      And The body of the response is the following
      """
         {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
      """

  Scenario: Check if models endpoint is working
    Given The system is in default state
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response for model gpt-4o-mini has proper structure


  Scenario: Check if models endpoint is working
    Given The system is in default state
    And  The llama-stack connection is disrupted
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 500
      And The body of the response is the following
      """
         {"detail": {"response": "Unable to connect to Llama Stack", "cause": "Connection error."}}
      """


  Scenario: Check if metrics endpoint is working
    Given The system is in default state
     When I access endpoint "metrics" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains ls_provider_model_configuration
