@e2e_group_2 @skip
Feature: Legacy two-file configuration during deprecation window

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  # --- library mode (@skip-in-server-mode) ---

  @skip-in-server-mode
  Scenario: Legacy two-file configuration still boots and serves requests in library mode
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200


  # --- server mode (@skip-in-library-mode) ---

  @skip-in-library-mode
  Scenario: Legacy two-file configuration still boots and serves requests in server mode
    Given The service uses the lightspeed-stack.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
