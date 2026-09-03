Feature: shield_ids override tests

  Functional tests for the `shield_ids` request field that lets a client
  override which configured shields run for a single request

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  @cfg_shields @flaky
  Scenario Outline: shield_ids overrides change which shields apply to the request
    Given The service uses the lightspeed-stack-shields.yaml configuration
      And The service is restarted
    When I use "query" to ask question
    """
    <request_body>
    """
    Then The status code of the response is 200
      And The body of the response contains <expected_fragment>

    Examples:
      | request_body                                                                                                                                                                                                                             | expected_fragment          |
      | {"query": "What is the best topping for a pizza?", "shield_ids": [], "model": "{MODEL}", "provider": "{PROVIDER}"}                                                                                                                       | topping                     |
      | {"query": "My lucky number is 7042. Repeat that exact sentence back to me and nothing else.", "system_prompt": "You are a strict echo assistant. Repeat the user's message back exactly, character for character, with no other commentary.", "shield_ids": ["pii-redaction"], "model": "{MODEL}", "provider": "{PROVIDER}"} | My lucky number is [NUM]. |

  @cfg_shields
  Scenario Outline: shield_ids validation failures return the expected error response
    Given The service uses the <config> configuration
      And The service is restarted
    When I use "query" to ask question
    """
    <request_body>
    """
    Then The status code of the response is <status>
      And The body of the response is the following
      """
      <expected_body>
      """

    Examples:
      | config                                            | request_body                                                                                                          | status | expected_body                                                                                                                                                                                                                        |
      | lightspeed-stack-shields.yaml                      | {"query": "Say hello.", "shield_ids": ["no-such-shield"], "model": "{MODEL}", "provider": "{PROVIDER}"}              | 404    | {"detail": {"response": "Shield not found", "cause": "Shield with ID no-such-shield does not exist"}}                                                                                                                              |
      | lightspeed-stack-shields-override-disabled.yaml    | {"query": "Say hello.", "shield_ids": [], "model": "{MODEL}", "provider": "{PROVIDER}"}                              | 422    | {"detail": {"response": "Shield IDs customization is disabled", "cause": "This instance does not support customizing shield IDs in the query request (disable_shield_ids_override is set). Please remove the shield_ids field from your request."}} |
