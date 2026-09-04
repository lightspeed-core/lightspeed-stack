@cfg_compaction
Feature: Conversation compaction

  When a conversation's estimated input approaches the model's context
  window, older turns are summarized before the request reaches the LLM
  (docs/design/conversation-compaction/conversation-compaction.md). These
  scenarios observe compaction from outside only: the context_status field
  on responses (R7), the compaction event on the native stream (R12), the
  full history the Conversations API keeps serving (R6), and the assistant's
  recall of what was said before the summary. The trigger is driven by the
  admin configuration (R1, R9): the compaction fixtures register a small
  context window for the openai model and a low threshold ratio, so a
  three-turn conversation crosses it.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  Scenario: context_status reports full while compaction never triggers
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "Say hello", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "full"


  @openai-only
  Scenario: context_status reports summarized once the conversation crosses the threshold
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a pod is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a deployment is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"


  @openai-only
  Scenario: the assistant still recalls what was said before the summary
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a pod is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a deployment is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"
     When I use "query" to ask question with same conversation_id
     """
     {"query": "What is the name of my cluster? Reply with the name only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"
      And The response contains following fragments
          | Fragments in LLM response |
          | aurora-prod-7             |


  @openai-only
  Scenario: the full conversation history stays available after compaction
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a pod is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a deployment is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"
     When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
     Then The status code of the response is 200
      And The conversation history includes the following user queries
          | User query                                                        |
          | My OpenShift cluster is named aurora-prod-7. Remember that name.  |
          | Explain what a pod is in about five sentences.                   |
          | Explain what a deployment is in about five sentences.            |


  @openai-only
  Scenario: the native stream announces compaction and reports context_status
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And The service is restarted
     When I use "streaming_query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I wait for the response to be completed
      And I store conversation details
     When I use "streaming_query" to ask question with same conversation_id
     """
     {"query": "Explain what a pod is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I wait for the response to be completed
     When I use "streaming_query" to ask question with same conversation_id
     """
     {"query": "Explain what a deployment is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I wait for the response to be completed
      And The streamed response contains a compaction event before the first token
      And The streamed response end event has context_status "summarized"


  @openai-only
  Scenario: compaction stays off when disabled, even past the threshold
    Given The service uses the lightspeed-stack-compaction-disabled.yaml configuration
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a pod is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Explain what a deployment is in about five sentences.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "full"
