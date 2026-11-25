@cfg_unified @skip-in-prow
Feature: Unified mode configuration synthesis

  Background:
    Given The service is started locally
      And The system is in default state
      And the Lightspeed stack configuration directory is "tests/e2e/configuration/unified-mode"


  # Synthesis semantics — native_override replacement (R5), secrets kept as
  # environment references (R6), owner-only output mode (R10) and the
  # --synthesized-config-output override — are covered in-process by
  # tests/integration/test_unified_synthesis.py: e2e steps never run src/ CLIs
  # (docs/testing/e2e_testing.md, "Choosing the Test Layer"). What remains here
  # is the one thing only a deployed stack can show: the synthesized path is
  # logged at startup (R10).

  @openai-only
  Scenario: Synthesized run.yaml path is logged at startup in library mode
    Given The service uses the lightspeed-stack-unified-providers.yaml configuration
      And The service is restarted
     Then the lightspeed-stack container logs contain synthesized run.yaml
