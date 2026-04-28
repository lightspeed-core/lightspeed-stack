@e2e_group_1 @skip-in-library-mode @skip-in-prow
Feature: TLS configuration for remote inference providers
  Validate that Llama Stack's NetworkConfig.tls settings are applied correctly
  when connecting to a remote inference provider over HTTPS.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-tls.yaml configuration
      And The service is restarted
      And The original Llama Stack config is restored if modified

  Scenario: Inference succeeds with TLS verification disabled
    Given Llama Stack is configured with TLS verification disabled
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200

  Scenario: Inference succeeds with CA certificate verification
    Given Llama Stack is configured with CA certificate verification
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200

  Scenario: Inference fails with an untrusted CA certificate
    Given Llama Stack is configured with CA certificate path "/certs/untrusted-ca.crt"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with an expired CA certificate
    Given Llama Stack is configured with CA certificate path "/certs/expired-ca.crt"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails when TLS verify is true against self-signed cert
    Given Llama Stack is configured with TLS verification enabled
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference succeeds with mutual TLS authentication
    Given Llama Stack is configured with mutual TLS authentication
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200

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

  Scenario: Inference fails with CA certificate verification and hostname mismatch
    Given Llama Stack is configured with CA certificate and hostname mismatch server
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

  Scenario: Inference succeeds with TLS minimum version TLSv1.3
    Given Llama Stack is configured with TLS minimum version "TLSv1.3" and CA certificate path "/certs/ca.crt"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200

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
