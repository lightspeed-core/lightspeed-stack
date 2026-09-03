@e2e_group_3
Feature: Smoke tests


  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack.yaml configuration
      And The service is restarted


  Scenario: Check if the main endpoint is reachable
    Given The system is in default state
     When I access endpoint "/" using HTTP GET method
     Then The status code of the response is 200
      And Content type of response is set to "text/html"
