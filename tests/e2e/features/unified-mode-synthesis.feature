@e2e_group_2 @skip
Feature: Unified mode configuration synthesis

  Background:
    Given The service is started locally
      And The system is in default state
      And the Lightspeed stack configuration directory is "tests/e2e/configuration/unified-mode"


  Scenario: native_override replaces an overlapping scalar key
    Given The service uses the lightspeed-stack-unified-native-override-scalar.yaml configuration
     When the active unified configuration is synthesized to run.yaml
     Then the synthesized run.yaml contains the native_override scalar value for safety.excluded_categories


  Scenario: native_override replaces an overlapping list key wholesale
    Given The service uses the lightspeed-stack-unified-native-override-list.yaml configuration
     When the active unified configuration is synthesized to run.yaml
     Then the synthesized run.yaml contains exactly the native_override list for apis


  Scenario: LCORE-emitted secrets remain as environment references on disk
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
     When the active unified configuration is synthesized to run.yaml
     Then the synthesized run.yaml contains ${env.OPENAI_API_KEY}
      And the synthesized run.yaml does not contain the resolved OPENAI_API_KEY value


  Scenario: Synthesized run.yaml is written with owner-only permissions
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
     When the active unified configuration is synthesized to run.yaml
     Then the synthesized run.yaml file permissions are 0600


  Scenario: synthesized-config-output overrides the default synthesis location
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
      And lightspeed-stack is started with --synthesized-config-output set to a custom path
     When the active unified configuration is synthesized to run.yaml
     Then the synthesized run.yaml is written to the custom output path
      And the default synthesized run.yaml path does not exist


  # --- library mode (@skip-in-server-mode) ---

  @skip-in-server-mode
  Scenario: Synthesized run.yaml path is logged at startup in library mode
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
      And The service is restarted
     Then the lightspeed-stack container logs contain synthesized run.yaml


  # --- server mode (@skip-in-library-mode) ---

  @skip-in-library-mode
  Scenario: Synthesized run.yaml path is logged at startup in server mode
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     Then the lightspeed-stack container logs contain synthesized run.yaml
