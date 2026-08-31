Feature: redaction shield functional tests

  Functional tests for the LCORE-owned `redaction` shield

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-shields.yaml configuration
      And The service is restarted

  @cfg_shields @flaky
  Scenario Outline: redaction shield redacts matching PII and leaves non-matching text unchanged
    When I use "query" to ask question
    """
    {
      "query": "<query>",
      "system_prompt": "You are a strict echo assistant. Repeat the user's message back exactly, character for character, with no other commentary.",
      "model": "{MODEL}",
      "provider": "{PROVIDER}"
    }
    """
    Then The status code of the response is 200
      And The body of the response contains <expected_fragment>

    Examples:
      | query                                                                                                | expected_fragment                            |
      | My OpenShift support ticket number is 48213. Repeat that exact sentence back to me and nothing else. | My OpenShift support ticket number is [NUM]. |
      | My OpenShift cluster is healthy and stable. Repeat that exact sentence back to me and nothing else.   | My OpenShift cluster is healthy and stable.  |

  @cfg_shields @flaky
  Scenario Outline: redaction shield redacts matching PII and leaves non-matching text unchanged via streaming_query
    When I use "streaming_query" to ask question
    """
    {
      "query": "<query>",
      "system_prompt": "You are a strict echo assistant. Repeat the user's message back exactly, character for character, with no other commentary.",
      "model": "{MODEL}",
      "provider": "{PROVIDER}"
    }
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response contains <expected_fragment>

    Examples:
      | query                                                                                                | expected_fragment                            |
      | My OpenShift support ticket number is 48213. Repeat that exact sentence back to me and nothing else. | My OpenShift support ticket number is [NUM]. |
      | My OpenShift cluster is healthy and stable. Repeat that exact sentence back to me and nothing else.   | My OpenShift cluster is healthy and stable.  |
