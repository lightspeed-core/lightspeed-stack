@e2e_group_3 @skip-in-library-mode @Authorized
Feature: Degraded mode startup

  End-to-end scenarios that test LCORE startup behavior when llama-stack
  is NOT available at startup time and allow_degraded_mode is enabled.

  These tests verify that LCORE metrics correctly reflect startup state
  in both healthy and degraded modes.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  Scenario: Degraded mode metric is set to 0.0 when started with llama-stack
    Given The service uses the lightspeed-stack-degraded-mode.yaml configuration
      And The service is restarted
    When I access endpoint "metrics" using HTTP GET method
    Then The status code of the response is 200
    And The response body contains "ls_started_in_degraded_mode 0.0"

  Scenario: Degraded mode metric is set to 1.0 when started without llama-stack
    Given The llama-stack connection is disrupted
      And The service uses the lightspeed-stack-degraded-mode.yaml configuration
      And The service is restarted
    When I access endpoint "metrics" using HTTP GET method
    Then The status code of the response is 200
    And The response body contains "ls_started_in_degraded_mode 1.0"

  Scenario: Readiness endpoint reports degraded state when started without llama-stack
    Given The llama-stack connection is disrupted
      And The service uses the lightspeed-stack-degraded-mode.yaml configuration
      And The service is restarted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is 503
    And The body of the response, ignoring the "providers" field, is the following
    """
    {"ready": false, "reason": "Cannot connect to backend service", "overall_status": "unhealthy", "impacts": ["LLM inference unavailable", "Provider health checks unavailable"]}
    """
