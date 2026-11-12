@cfg_quota
Feature: Quota management

  Token quotas are checked before a request reaches the model and charged
  after it answered: a user limiter keeps one balance per user, a cluster
  limiter one balance every user pays into. The quota fixture gives each
  user a single token, so the first request of a user the service has not
  seen is served (the check passes while the balance is positive) and its
  usage drives the balance below zero whatever the provider counts; the
  second request is rejected with HTTP 429 and costs nothing. The scheduler
  renews balances once their period has elapsed; the renewal fixture
  shortens that period to two seconds so it can be observed while the
  service runs.

  Every scenario acts as a user the service has never seen, so the balances
  it reads are its own whatever the quota database already holds, and the
  cluster balance, which every scenario pays into, is only ever compared
  with an earlier reading of the same scenario. Charging and rejection on
  query and streaming_query are covered by the integration tests; the
  responses endpoint stands for all of them here.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-quota.yaml configuration
      And The service is restarted
      And I am a user the service has not seen before


  Scenario: responses reports the balances in its body, then is rejected
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 200
      And The response reports a positive token usage of the turn
      And The available quota "UserQuotaLimiter" is 1 minus the tokens of the turn
      And The available quota "ClusterQuotaLimiter" is reported
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 429
      And The response is the quota exceeded error for that user


  Scenario: streamed responses reports the balances in its terminal event, then is rejected
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}", "stream": true}
     """
     Then The status code of the response is 200
      And The response reports a positive token usage of the turn
      And The available quota "UserQuotaLimiter" is 1 minus the tokens of the turn
      And The available quota "ClusterQuotaLimiter" is reported
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}", "stream": true}
     """
     Then The status code of the response is 429
      And The response is the quota exceeded error for that user


  Scenario: infer is served once, then is rejected, when the quota subject is the user id
     When I use "infer" to ask question
     """
     {"question": "Reply with the single word: ok."}
     """
     Then The status code of the response is 200
      And The rlsapi response has valid structure
     When I use "infer" to ask question
     """
     {"question": "Reply with the single word: ok."}
     """
     Then The status code of the response is 429
      And The response is the quota exceeded error for that user


  Scenario: the cluster balance is paid by every user and a rejected request costs nothing
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 200
      And I remember the available cluster quota
    Given I am a user the service has not seen before
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 200
      And The response reports a positive token usage of the turn
      And The available cluster quota went down by the tokens of the turn since I remembered it
      And I remember the available cluster quota
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 429
    Given I am a user the service has not seen before
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 200
      And The response reports a positive token usage of the turn
      And The rejected request cost nothing: the available cluster quota went down only by the tokens of this turn since I remembered it


  Scenario: an exhausted balance is renewed by the scheduler while the service runs
    Given The service uses the lightspeed-stack-quota-renewal.yaml configuration
      And The service is restarted
     When I use "responses" to ask question
     """
     {"input": "Reply with the single word: ok.", "model": "{PROVIDER}/{MODEL}"}
     """
     Then The status code of the response is 429
      And The response is the quota exceeded error for that user
     When I resend the question once a second until it is served, at most 30 times
     Then The status code of the response is 200
      And The response reports a positive token usage of the turn
      And The available quota "UserQuotaLimiter" is at least 1000000 minus the tokens of the turn
