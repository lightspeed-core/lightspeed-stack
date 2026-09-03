@e2e_group_1 @skip-in-library-mode  @skip-in-prow
Feature: TLS configuration — TLS minimum version 1.3
  Validate Llama Stack NetworkConfig.tls min_version TLSv1.3 against the mock
  HTTPS inference provider.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The original Llama Stack config is restored if modified
      And The mock TLS inference server is deployed
      And The service uses the lightspeed-stack-tls.yaml configuration
      And The service is restarted

  Scenario: Inference succeeds with TLS minimum version TLSv1.3
    Given Llama Stack is configured with TLS minimum version "TLSv1.3" and CA certificate path "/certs/ca.crt"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200
     And The body of the response contains Hello from the TLS mock inference server

  Scenario: Inference fails with TLS minimum version TLSv1.3 and untrusted CA certificate
    Given Llama Stack is configured with TLS minimum version "TLSv1.3" and CA certificate path "/certs/untrusted-ca.crt"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with TLS minimum version TLSv1.3 and hostname mismatch
    Given Llama Stack is configured with TLS minimum version "TLSv1.3" and hostname mismatch server
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with TLS minimum version TLSv1.3 and expired CA certificate
    Given Llama Stack is configured with TLS minimum version "TLSv1.3" and CA certificate path "/certs/expired-ca.crt"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server
