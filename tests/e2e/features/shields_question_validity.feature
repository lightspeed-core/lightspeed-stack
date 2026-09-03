Feature: question_validity shield functional tests

  Functional tests for the LCORE-owned `question_validity` shield

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-shields.yaml configuration
      And The service is restarted

  @cfg_shields @flaky
  Scenario Outline: question_validity allows in-topic and rejects off-topic questions
    When I use "<endpoint>" to ask question
    """
    <request_body>
    """
    Then The status code of the response is 200
      And The body of the response contains <expected_fragment>

    Examples:
      | endpoint  | request_body                                                                                                              | expected_fragment                            |
      | query     | {"query": "What is OpenShift and how do I deploy an application on it?", "model": "{MODEL}", "provider": "{PROVIDER}"}   | deploy                                       |
      | query     | {"query": "What is the best topping for a pizza?", "model": "{MODEL}", "provider": "{PROVIDER}"}                         | I can only answer questions about OpenShift. |
      | responses | {"input": "What is OpenShift and how do I deploy an application on it?", "model": "{PROVIDER}/{MODEL}", "stream": false} | deploy                                       |
      | responses | {"input": "What is the best topping for a pizza?", "model": "{PROVIDER}/{MODEL}", "stream": false}                       | I can only answer questions about OpenShift. |
      | infer     | {"question": "What is OpenShift and how do I deploy an application on it?"}                                              | deploy                                       |
      | infer     | {"question": "What is the best topping for a pizza?"}                                                                    | I can only answer questions about OpenShift. |

  @cfg_shields @flaky
  Scenario Outline: question_validity allows in-topic and rejects off-topic questions via streaming_query
    When I use "streaming_query" to ask question
    """
    <request_body>
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The body of the response contains <expected_fragment>

    Examples:
      | request_body                                                                                                            | expected_fragment                            |
      | {"query": "What is OpenShift and how do I deploy an application on it?", "model": "{MODEL}", "provider": "{PROVIDER}"} | deploy                                       |
      | {"query": "What is the best topping for a pizza?", "model": "{MODEL}", "provider": "{PROVIDER}"}                       | I can only answer questions about OpenShift. |
