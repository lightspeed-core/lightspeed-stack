Feature: Shields endpoint tests

  Tests for the LCORE-owned GET /v1/shields catalog endpoint. These shields
  (question_validity, redaction) are configured directly in
  lightspeed-stack.yaml; they are not Llama Stack / OGX Safety API resources.
  See docs/user_doc/shields_guide.md for the full shield configuration and
  runtime-behavior reference.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  @cfg_shields
  Scenario: Shields endpoint returns every configured shield type
    Given The service uses the lightspeed-stack-shields.yaml configuration
      And The service is restarted
     When I access REST API endpoint "shields" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response is the following
      """
      {
        "shields": [
          {
            "name": "topic-guard",
            "provider_id": "question_validity",
            "type": "shield",
            "config": {
              "model_id": "openai/gpt-4o-mini",
              "model_prompt": "Classify whether the following question is about OpenShift or Kubernetes. Reply with exactly one word: ${allowed} if it is about OpenShift or Kubernetes, or ${rejected} if it is not. Do not explain your answer or add any other text.\n\nQuestion: ${message}\nAnswer:",
              "invalid_question_response": "I can only answer questions about OpenShift."
            }
          },
          {
            "name": "pii-redaction",
            "provider_id": "redaction",
            "type": "shield",
            "config": {
              "rules": [
                {
                  "pattern": "\\d+",
                  "replacement": "[NUM]",
                  "case_sensitive": null
                }
              ],
              "case_sensitive": false
            }
          }
        ]
      }
      """

  @cfg_shields
  Scenario: Shields endpoint returns an empty list when no shields are configured
    Given The service uses the lightspeed-stack-shields-empty.yaml configuration
      And The service is restarted
     When I access REST API endpoint "shields" using HTTP GET method
     Then The status code of the response is 200
      And The body of the response is the following
      """
      {
        "shields": []
      }
      """
