Feature: REST API tests


  Background:
    Given The service is started locally
      And REST API service hostname is localhost
      And REST API service port is 8080
      And REST API service prefix is /v1


  Scenario: Check if service report proper readiness state
    Given the system is in default state
     When I access REST API endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has the following schema
          """
          {
              "ready": "bool",
              "reason": "str",
              "providers": "list"
          }
          """
      And The body of the response is the following
          """
          {"ready": true, "reason": "All providers are healthy", "providers": []}
          """


  Scenario: Check if service report proper liveness state
    Given the system is in default state
     When I access REST API endpoint "liveness" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has the following schema
          """
          {
              "alive": "bool"
          }
          """
      And The body of the response is the following
          """
          {"alive":true}
          """


  Scenario: Check if the OpenAPI endpoint works as expected
    Given the system is in default state
     When I access endpoint "openapi.json" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains OpenAPI


  Scenario: Check if info endpoint is working
    Given the system is in default state
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response contains name
      And The body of the response contains version
