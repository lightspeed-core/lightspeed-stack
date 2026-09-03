@e2e_group_1 @OTel @skip
Feature: OpenTelemetry observability tests

  Background:
    Given The service is started locally
      And The system is in default state
      And An OpenTelemetry service is running and listening for OTLP data
      And The service is configured to export data to the OpenTelemetry service
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted


  Scenario: Successful responses request processing is visible in delivered telemetry
    Given The system is in default state
    When I use "responses" to ask question with authorization header
      """
      {
        "input": "Say hello in one short sentence.",
        "model": "{PROVIDER}/{MODEL}",
        "stream": false,
        "safety_identifier": "e2e-otel-delivery-marker"
      }
      """
    Then The status code of the response is 200
     And The service exported an OpenTelemetry event containing e2e-otel-delivery-marker
     And The OpenTelemetry service received data containing e2e-otel-delivery-marker
