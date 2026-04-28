@e2e_group_3 @skip-in-library-mode @skip-in-prow
Feature: Proxy and TLS networking tests for Llama Stack providers

  Verify that the Lightspeed Stack works correctly when Llama Stack's
  remote inference providers are configured with proxy and TLS settings
  via the run.yaml NetworkConfig.

  Query bodies use shield_ids: [] because Llama Guard moderation issues a separate
  OpenAI request inside Llama Stack that does not inherit the same proxy/TLS CA
  trust as remote::openai inference, which breaks MITM interception tests.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
      And The original Llama Stack config is restored if modified


  # --- AC1: Tunnel proxy routing ---

  @TunnelProxy
  Scenario: LLM traffic is routed through a configured tunnel proxy
    Given A tunnel proxy is running on port 8888
      And Llama Stack is configured to route inference through the tunnel proxy
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 200
      And The tunnel proxy handled at least 1 CONNECT request to the LLM provider

  # NOTE: no_proxy is defined on Llama Stack's ProxyConfig model but not
  # implemented in _build_proxy_mounts (http_client.py). The field is ignored.
  # When Llama Stack implements no_proxy support, add a test here.

  @TunnelProxy
  Scenario: LLM query fails gracefully when proxy is unreachable
    Given Llama Stack is configured to route inference through proxy "http://127.0.0.1:19999"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 500


  # --- AC2: Interception proxy with CA certificate ---

  @InterceptionProxy
  Scenario: LLM traffic works through interception proxy with correct CA
    Given An interception proxy with trustme CA is running on port 8889
      And Llama Stack is configured to route inference through the interception proxy with CA cert
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 200
      And The interception proxy intercepted at least 1 connection

  @InterceptionProxy
  Scenario: LLM query fails when interception proxy CA is not provided
    Given An interception proxy with trustme CA is running on port 8890
      And Llama Stack is configured to route inference through the interception proxy without CA cert
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 500


  # --- AC3: TLS version and cipher configuration ---

  @TLSVersion
  Scenario: TLS minimum version TLSv1.2 is respected
    Given Llama Stack is configured with minimum TLS version "TLSv1.2"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 200

  @TLSVersion
  Scenario: TLS minimum version TLSv1.3 is respected
    Given Llama Stack is configured with minimum TLS version "TLSv1.3"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 200

  @TLSCipher
  Scenario: Custom cipher suite configuration is respected
    Given Llama Stack is configured with ciphers "ECDHE+AESGCM:DHE+AESGCM"
      And Llama Stack is restarted
      And Lightspeed Stack is restarted
     When I use "query" to ask question
    """
    {"query": "What is 2+2?", "model": "{MODEL}", "provider": "{PROVIDER}", "shield_ids": []}
    """
     Then The status code of the response is 200
