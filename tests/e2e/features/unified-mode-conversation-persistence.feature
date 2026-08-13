@cfg_unified @skip-in-server-mode
Feature: Unified mode conversation persistence across restart

  # Proves RHIDP-14967: with conversation_cache + matching database on a
  # non-/tmp sqlite path, synthesis wires OGX stores.conversations to
  # conversations_default so a conversation-id continue succeeds after
  # lightspeed-stack process restart (docker restart). Re-run on ogx bumps.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-unified-conversation-persistence-sqlite.yaml configuration
      And The service is restarted

  Scenario: Continue chat after Lightspeed restart with sqlite conversation persistence
    When I use "query" to ask question
    """
    {"query": "Say the word apple and nothing else", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    Then The status code of the response is 200
    When The service is restarted
    And I use "query" to ask question with same conversation_id
    """
    {"query": "What single word did I ask you to say earlier?", "model": "{MODEL}", "provider": "{PROVIDER}", "no_tools": true}
    """
    Then The status code of the response is 200
      And The body of the response contains apple
