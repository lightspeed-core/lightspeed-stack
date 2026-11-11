@cfg_authorized @OTel @skip-in-prow
Feature: OpenTelemetry observability tests

  Background:
    Given The service is started locally
      And The system is in default state
      And An OpenTelemetry service is running and listening for OTLP data
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-authorized.yaml configuration
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
     And The OpenTelemetry service received data containing e2e-otel-delivery-marker


  Scenario: PII in span content is redacted in-process before telemetry export
    # One request carrying every default-redacted entity type. safety_identifier is
    # intentionally not redacted (it is a caller-supplied tracking id, not user
    # content), so it doubles as the delivery marker.
    Given The system is in default state
    When I use "responses" to ask question with authorization header
      """
      {
        "input": "Reach me at test.user@redhat.com or 212-555-0199, host db.example.com at 10.1.2.3; contact Barack Obama in Chicago. Card 4111 1111 1111 1111, SSN 457-55-5462, IBAN GB33BUKB20201555555555 regarding e2e-redaction-check",
        "model": "{PROVIDER}/{MODEL}",
        "stream": false,
        "safety_identifier": "e2e-redaction-check"
      }
      """
    Then The status code of the response is 200
     And The OpenTelemetry service received data containing e2e-redaction-check
     # Raw PII values must never reach the collector.
     And The OpenTelemetry service did not receive data containing test.user@redhat.com
     And The OpenTelemetry service did not receive data containing 212-555-0199
     And The OpenTelemetry service did not receive data containing db.example.com
     And The OpenTelemetry service did not receive data containing 10.1.2.3
     And The OpenTelemetry service did not receive data containing 4111 1111 1111 1111
     And The OpenTelemetry service did not receive data containing 457-55-5462
     And The OpenTelemetry service did not receive data containing GB33BUKB20201555555555
     # Each entity is replaced in-process with its typed marker.
     And The OpenTelemetry service received data containing <EMAIL_ADDRESS>
     And The OpenTelemetry service received data containing <PHONE_NUMBER>
     And The OpenTelemetry service received data containing <HOSTNAME>
     And The OpenTelemetry service received data containing <IP_ADDRESS>
     And The OpenTelemetry service received data containing <PERSON>
     And The OpenTelemetry service received data containing <LOCATION>
     And The OpenTelemetry service received data containing <CREDIT_CARD>
     And The OpenTelemetry service received data containing <US_SSN>
     And The OpenTelemetry service received data containing <IBAN_CODE>
