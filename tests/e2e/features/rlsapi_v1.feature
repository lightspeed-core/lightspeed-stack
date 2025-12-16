@RlsapiConfig
Feature: RLSAPI v1 infer endpoint
  Basic tests for the RLSAPI v1 inference endpoint.

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Verify RLSAPI v1 infer endpoint returns 200
    Given The system is in default state
     When I access REST API endpoint "infer" using HTTP POST method
      """
      {"question": "Say hello"}
      """
     Then The status code of the response is 200
      And Content type of response should be set to "application/json"
