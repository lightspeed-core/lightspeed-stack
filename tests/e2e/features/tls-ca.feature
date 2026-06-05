@e2e_group_1 @skip-in-library-mode
Feature: TLS configuration — CA certificate verification
  Validate Llama Stack NetworkConfig.tls CA trust settings against the mock HTTPS
  inference provider (standard TLS port).

  # Only Llama run.yaml changes per scenario; LCS uses lightspeed-stack-tls.yaml
  # throughout (Background). ``Llama Stack is restarted`` also refreshes LCS.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The original Llama Stack config is restored if modified
      And The mock TLS inference server is deployed
      And The service uses the lightspeed-stack-tls.yaml configuration
      And The service is restarted

  Scenario: Inference succeeds with TLS verification disabled
    Given Llama Stack is configured with TLS verification disabled
      And Llama Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200

  Scenario: Inference succeeds with CA certificate verification
    Given Llama Stack is configured with CA certificate verification
      And Llama Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200

  Scenario: Inference fails with an untrusted CA certificate
    Given Llama Stack is configured with CA certificate path "/certs/untrusted-ca.crt"
      And Llama Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with an expired CA certificate
    Given Llama Stack is configured with CA certificate path "/certs/expired-ca.crt"
      And Llama Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails when TLS verify is true against self-signed cert
    Given Llama Stack is configured with TLS verification enabled
      And Llama Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with CA certificate verification and hostname mismatch
    Given Llama Stack is configured with CA certificate and hostname mismatch server
      And Llama Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server
