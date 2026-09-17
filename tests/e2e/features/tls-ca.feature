@cfg_tls @skip-in-library-mode @skip-in-prow
Feature: TLS configuration — CA certificate verification
  Validate OGX NetworkConfig.tls CA trust settings against the mock HTTPS
  inference provider (standard TLS port).

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The original OGX config is restored if modified
      And The mock TLS inference server is deployed
      And The service uses the lightspeed-stack-tls.yaml configuration
      And The service is restarted

  Scenario: Inference succeeds with TLS verification disabled
    Given OGX is configured with TLS verification disabled
      And OGX is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200
      And The body of the response contains Hello from the TLS mock inference server

  Scenario: Inference succeeds with CA certificate verification
    Given OGX is configured with CA certificate verification
      And OGX is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 200
      And The body of the response contains Hello from the TLS mock inference server

  Scenario: Inference fails with an untrusted CA certificate
    Given OGX is configured with CA certificate path "/certs/untrusted-ca.crt"
      And OGX is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with an expired CA certificate
    Given OGX is configured with CA certificate path "/certs/expired-ca.crt"
      And OGX is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails when TLS verify is true against self-signed cert
    Given OGX is configured with TLS verification enabled
      And OGX is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server

  Scenario: Inference fails with CA certificate verification and hostname mismatch
    Given OGX is configured with CA certificate and hostname mismatch server
      And OGX is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "Say hello", "model": "mock-tls-model", "provider": "tls-openai"}
    """
     Then The status code of the response is 500
      And The body of the response does not contain Hello from the TLS mock inference server
