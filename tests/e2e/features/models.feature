Feature: Models endpoint tests


  Background:
    Given The service is started locally
      And REST API service prefix is /v1


  Scenario: Check if models endpoint is working
    Given The system is in default state
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has proper model structure
      And The models list should not be empty


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
