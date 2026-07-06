@e2e_group_2 @skip
Feature: Unified mode configuration boot

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration/unified-mode"


  # --- library mode (@skip-in-server-mode) ---

  @skip-in-server-mode
  Scenario: Unified config with inference.providers boots and serves requests in library mode
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
      And The service is restarted
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
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200


  @skip-in-server-mode
  Scenario: Unified config with llama_stack.config only boots and serves requests in library mode
    Given The service uses the lightspeed-stack-unified-config-only.yaml configuration
      And The service is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200


  @skip-in-server-mode
  Scenario: Unified config with relative profile path boots in library mode
    Given The service uses the lightspeed-stack-unified-relative-profile.yaml configuration
      And The service is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200


  @skip-in-server-mode
  Scenario: Unified config with absolute profile path boots in library mode
    Given The service uses the lightspeed-stack-unified-absolute-profile.yaml configuration
      And The service is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200


  # --- server mode (@skip-in-library-mode) ---

  @skip-in-library-mode
  Scenario: Unified config with inference.providers boots and serves requests in server mode
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
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
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200


  @skip-in-library-mode
  Scenario: Unified config with llama_stack.config only boots and serves requests in server mode
    Given The service uses the lightspeed-stack-unified-config-only.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200


  @skip-in-library-mode
  Scenario: Unified config with relative profile path boots in server mode
    Given The service uses the lightspeed-stack-unified-relative-profile.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200


  @skip-in-library-mode
  Scenario: Unified config with absolute profile path boots in server mode
    Given The service uses the lightspeed-stack-unified-absolute-profile.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
