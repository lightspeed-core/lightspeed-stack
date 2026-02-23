Feature: Models endpoint tests


  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if models endpoint is working
    Given The system is in default state
     When I retrieve list of available models
     Then The status code of the response is 200
      And The body of the response has proper model structure
      And The models list should not be empty

  Scenario: Check if models can be filtered
    Given The system is in default state
     When I retrieve list of available models with type set to "llm"
     Then The status code of the response is 200
      And The body of the response has proper model structure
      And The models list should not be empty
      And The models list should contain only models of type "llm"

  Scenario: Check if filtering can return empty list of models
    Given The system is in default state
     When I retrieve list of available models with type set to "xyzzy"
     Then The status code of the response is 200
      And The models list should be empty
