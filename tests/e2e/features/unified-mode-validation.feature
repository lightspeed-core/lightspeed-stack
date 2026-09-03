@e2e_group_2 @skip
Feature: Unified mode configuration validation

  Background:
    Given The service is started locally
      And The system is in default state
      And the Lightspeed stack configuration directory is "tests/e2e/configuration/unified-mode"


  Scenario: inference.providers together with library_client_config_path fails at load
    Given The service uses the lightspeed-stack-invalid-providers-and-legacy.yaml configuration
     When configuration validation is attempted for the active configuration
     Then the validation error contains --migrate-config


  Scenario: llama_stack.config together with library_client_config_path fails at load
    Given The service uses the lightspeed-stack-invalid-config-and-legacy.yaml configuration
     When configuration validation is attempted for the active configuration
     Then the validation error contains --migrate-config


  Scenario: config_format_version legacy with unified-shaped body fails at load
    Given The service uses the lightspeed-stack-invalid-version-legacy-unified-body.yaml configuration
     When configuration validation is attempted for the active configuration
     Then the validation error contains config_format_version
