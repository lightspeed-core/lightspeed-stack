Feature: REST API tests


  Background:
    Given The service is started locally
      And REST API service hostname is localhost
      And REST API service port is 8080
      And REST API service prefix is /v1


  Scenario: Check if service report proper readiness state
    Given The system is in default state
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has the following schema
          """
          {
              "ready": "bool",
              "reason": "str",
              "providers": "list[str]"
          }
          """
      And The body of the response is the following
          """
          {"ready": true, "reason": "All providers are healthy", "providers": []}
          """


  Scenario: Check if service report proper liveness state
    Given The system is in default state
     When I access endpoint "liveness" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has the following schema
          """
          {
              "alive": "bool"
          }
          """
      And The body of the response is the following
          """
          {"alive": true}
          """


  Scenario: Check if service report proper readiness state when llama stack is not available
    Given The system is in default state
      And The llama-stack connection is disrupted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 503
      And The body of the response, ignoring the "providers" field, is the following
          """
          {"ready": false, "reason": "Providers not healthy: unknown"}
          """


  Scenario: Check if service report proper liveness state even when llama stack is not available
    Given The system is in default state
      And The llama-stack connection is disrupted
     When I access endpoint "liveness" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response is the following
          """
          {"alive": true}
          """