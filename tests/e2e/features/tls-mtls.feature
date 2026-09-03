@e2e_group_1 @skip-in-library-mode @skip-in-prow
Feature: TLS configuration — mutual TLS authentication
  Validate Llama Stack NetworkConfig.tls client certificate settings against the
  mock HTTPS inference provider (mTLS port).

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The original Llama Stack config is restored if modified
      And The mock TLS inference server is deployed
      And The service uses the lightspeed-stack-tls.yaml configuration
      And The service is restarted

  Scenario: Inference succeeds with mutual TLS authentication
    Given Llama Stack is configured with mutual TLS authentication
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200
      And The body of the response contains Hello from the TLS mock inference server

  Scenario: Inference fails when mTLS is required but no client certificate is provided
    Given Llama Stack is configured for mTLS without client certificate
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails when mTLS is required but wrong client certificate is provided
    Given Llama Stack is configured for mTLS with wrong client certificate
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails when mTLS is required but untrusted client certificate is provided
    Given Llama Stack is configured for mTLS with untrusted client certificate
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails when mTLS is required but expired client certificate is provided
    Given Llama Stack is configured for mTLS with expired client certificate
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with mutual TLS and hostname mismatch
    Given Llama Stack is configured with mutual TLS and hostname mismatch server
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server
