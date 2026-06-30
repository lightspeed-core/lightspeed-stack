@e2e_group_2 @skip
Feature: Legacy to unified configuration migration

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration/unified-mode"


  Scenario: migrate-config produces a unified configuration from a legacy pair
     When lightspeed-stack --migrate-config is run for the legacy migration fixture pair
     Then the file lightspeed-stack-unified-migrated.yaml contains native_override
      And the file lightspeed-stack-unified-migrated.yaml does not contain library_client_config_path


  Scenario: migrate then synthesize round-trips to the original run.yaml
     When lightspeed-stack --migrate-config is run for the legacy migration fixture pair
      And the active unified configuration is synthesized to run.yaml
     Then the synthesized run.yaml parses to the same data as the legacy migration fixture run.yaml


  # --- library mode (@skip-in-server-mode) ---

  @skip-in-server-mode
  Scenario: Migrated unified configuration drives byte-identical Llama Stack behavior in library mode
    Given lightspeed-stack --migrate-config is run for the legacy migration fixture pair
      And The service uses the lightspeed-stack-unified-migrated.yaml configuration
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
  Scenario: Migrated unified configuration drives byte-identical Llama Stack behavior in server mode
    Given lightspeed-stack --migrate-config is run for the legacy migration fixture pair
      And The service uses the lightspeed-stack-unified-migrated.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
