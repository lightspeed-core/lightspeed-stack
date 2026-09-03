@e2e_group_2
Feature: Models endpoint tests


  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack.yaml configuration
      And The service is restarted


  Scenario: Check if models endpoint is working
    Given The system is in default state
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper model structure
      And The models list is not empty

  Scenario: Check if models can be filtered
    Given The system is in default state
     When I retrieve list of available models with type set to "llm"
     Then The status code of the response is 200
      And The body of the response has proper model structure
      And The models list is not empty
      And The models list contains only models of type "llm"

  Scenario: Check if filtering can return empty list of models
    Given The system is in default state
     When I retrieve list of available models with type set to "xyzzy"
     Then The status code of the response is 200
      And The models list is empty
