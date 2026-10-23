# In-process PII redaction e2e.
#
# The e2e stack runs with in-process redaction on by default: lightspeed-stack is
# built with a spaCy model (SPACY_MODEL, default en_core_web_trf) and runs the
# RedactingSpanExporter (OTEL_TRACES_EXPORTER=redacting_otlp, set in docker-compose).
# Spans are redacted in-process before being exported over OTLP to the mock
# collector (mock-otel), which the test uses as a telemetry sink. This scenario
# asserts a known PII value sent in a query never reaches the collector, while a
# non-PII marker still arrives.
@cfg_authorized @OTel @OTel-redaction @skip-in-prow
Feature: In-process PII redaction of exported telemetry

  Background:
    Given The service is started locally
      And The system is in default state
      And An OpenTelemetry service is running and listening for OTLP data
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-authorized.yaml configuration
      And The service is restarted


  Scenario: PII in a query is redacted in-process before telemetry is exported
    Given The system is in default state
    When I use "responses" to ask question with authorization header
      """
      {
        "input": "Reach me at sam@redhat.com regarding e2e-redaction-marker",
        "model": "{PROVIDER}/{MODEL}",
        "stream": false,
        "safety_identifier": "e2e-redaction-marker"
      }
      """
    Then The status code of the response is 200
     And The OpenTelemetry service received data containing e2e-redaction-marker
     And The OpenTelemetry service did not receive data containing sam@redhat.com
