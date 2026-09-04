@cfg_okp @konflux-only
Feature: OKP(Solr) RAG retrieval tests
  # Server-mode tests: OGX is a separate pod and re-enriches Solr/OKP from the
  # Lightspeed ConfigMap on restart. Restart Llama Stack after each YAML change
  # so the Solr provider picks up inline/tool/offline/online settings.
  # Konflux only: before_feature deploys OKP Solr (7GB image) once.
  # Background "OKP is running" checks Solr from the OGX pod (not runner :8081).
  # @konflux-only: skipped on GitHub Actions, classic Prow, and local Docker.

  # Offline Knowledge Portal (OKP) provides a Solr-backed RAG source to LSC.
  # Tests verify that Lightspeed Stack can use OKP for both Inline RAG
  # (context injected before the LLM request) and Tool RAG (context
  # retrieved on demand via file_search), in both offline and online modes.
  Background:
    Given The service is started locally
      And The system is in default state
      And OKP(Solr) server is running
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  # ── Inline RAG — Query (offline) ──

  Scenario: Offline mode query with inline RAG returns rag_chunks and referenced_documents
    Given The service uses the lightspeed-stack-okp-offline.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The number of rag_chunk returned is 1
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And The number of referenced_document returned is 1
      And Each referenced_document doc_url contains "localhost:8081"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

  # ── Inline RAG — Streaming Query (online) ──

  Scenario: Online mode streaming query with inline RAG returns referenced_documents
    Given The service uses the lightspeed-stack-okp-online.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And I wait for the response to be completed
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And The number of referenced_document returned is 3
      And Each referenced_document doc_url contains "docs.redhat.com"
      And Each referenced_document doc_title is not empty
      And Each referenced_document doc_title contains "openshift container platform 4.21"
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

  # ── Inline RAG — Query with Dynamic Filter ──

  Scenario: Query with inline RAG with dynamic semantic filter returns rag_chunks and referenced_documents
    Given The service uses the lightspeed-stack-okp-offline.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Security best practices",
      "solr": {
        "mode": "semantic",
        "filters": {
          "filters": {
            "type": "in",
            "key": "product",
            "value": ["openshift_container_platform", "ansible_automation_platform", "red_hat_enterprise_linux"]
          }
        }
      }
    }
    """
    Then The status code of the response is 200
      And The response contains "security best practices"
      And The number of rag_chunk returned is 1
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And The number of referenced_document returned is 1
      And Each referenced_document doc_url contains "localhost:8081"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

  # ── Tool RAG — Query API (offline) ──

  Scenario: Offline query API with OKP tool RAG has rag_chunk and referenced_documents returned
    Given The service uses the lightspeed-stack-okp-tool-offline.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {
      "query": "Troubleshooting guide",
      "model": "{MODEL}",
      "provider": "{PROVIDER}",
      "system_prompt": "You MUST use the file_search tool to answer."
    }
    """
    Then The status code of the response is 200
      And The response contains non-empty tool_calls
      And A tool_call has name "file_search"
      And The response contains non-empty rag_chunks
      And The number of rag_chunk returned is 2
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And The response contains non-empty referenced_documents
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And Each referenced_document doc_url contains "localhost:8081"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

  # ── Tool RAG — Responses API (online) ──

  Scenario: Online responses API with OKP tool RAG has rag results returned
    Given The service uses the lightspeed-stack-okp-tool-online.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "Troubleshooting guide",
      "model": "{PROVIDER}/{MODEL}",
      "stream": false,
      "instructions": "You MUST use the file_search tool to answer."
    }
    """
    Then The status code of the response is 200
      And The responses output includes an item with type "file_search_call"
      And The response contains non-empty tool_calls
      And A tool_call has type "file_search"
      And The response contains non-empty results
      And The number of results returned is 3
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And Each rag_chunk reference_url contains "access.redhat.com"

  # ── OKP Server Unavailable — Graceful Error Handling ──

  Scenario: Query succeeds with empty rag_chunks when OKP server is unavailable
    Given The service uses the lightspeed-stack-okp-online.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
      And The OKP(Solr) server is stopped
    When I use "query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The response contains no rag_chunks
      And The response contains no referenced_documents

  Scenario: Streaming query succeeds with empty referenced_documents when OKP server is unavailable
    Given The service uses the lightspeed-stack-okp-online.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
      And The OKP(Solr) server is stopped
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And I wait for the response to be completed
      And The response contains no referenced_documents

  # ── OKP RAG Disabled (okp not in rag.retrieval.inline.sources) ─────

  Scenario: Query returns no rag_chunks and no reference_documents when OKP is disabled
    Given The service uses the lightspeed-stack-okp-negative.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The response contains no rag_chunks
     And The response contains no referenced_documents

  Scenario: Streaming query returns no referenced_documents when OKP is disabled
    Given The service uses the lightspeed-stack-okp-negative.yaml configuration
      And Llama Stack is restarted
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And I wait for the response to be completed
     And The response contains no referenced_documents
