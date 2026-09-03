@e2e_group_2
Feature: REST API tests


  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack.yaml configuration
      And The service is restarted


  Scenario: Check if service report proper readiness state
    Given The system is in default state
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response has the following schema
          """
          {
              "ready": "bool",
              "reason": "str",
              "overall_status": "str",
              "impacts": "list[str] | None",
              "providers": "list[str]"
          }
          """
      And The body of the response is the following
          """
          {"ready": true, "reason": "All providers are healthy", "overall_status": "healthy", "impacts": null, "providers": []}
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