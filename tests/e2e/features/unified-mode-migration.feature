@cfg_unified @skip-in-prow
Feature: Legacy to unified configuration migration

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration/unified-mode"


  # The --migrate-config CLI itself (output shape, owner-only mode, migrate-then-
  # synthesize round trip) is covered by tests/integration/test_unified_mode_cli.py:
  # e2e steps never run src/ CLIs (docs/testing/e2e_testing.md, "Choosing the
  # Test Layer"). The scenarios below boot the committed
  # lightspeed-stack-unified-migrated.yaml fixture — generated once from the
  # legacy migration fixture pair (lightspeed-stack-legacy-for-migration.yaml +
  # tests/e2e/configs/run-ci.yaml) and guarded against CLI drift by that same
  # integration module. It inlines the openai run-ci.yaml, hence @openai-only.

  # --- library mode (@skip-in-server-mode) ---

  @skip-in-server-mode @openai-only
  Scenario: Migrated unified configuration boots and serves queries in library mode
    Given The service uses the lightspeed-stack-unified-migrated.yaml configuration
      And The service is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200


  # --- server mode (@skip-in-library-mode) ---

  @skip-in-library-mode @openai-only
  Scenario: Migrated unified configuration boots and serves queries in server mode
    Given The service uses the lightspeed-stack-unified-migrated.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I access endpoint "readiness" using HTTP GET method
     Then The status code of the response is 200
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
