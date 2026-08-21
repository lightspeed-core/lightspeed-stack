@cfg_okp
Feature: OKP(Solr) RAG retrieval tests

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

  # ── Inline RAG — Query ──

  Scenario Outline: <mode> mode query with inline RAG returns rag_chunks and referenced_documents
    Given The service uses the <config> configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The response contains non-empty rag_chunks
      And The response contains non-empty referenced_documents
      And The number of rag_chunk returned is <max_chunks>
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And Each referenced_document doc_url contains "<doc_url_domain>"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

    Examples: Offline
      | mode    | config                            | max_chunks | doc_url_domain |
      | Offline | lightspeed-stack-okp-offline.yaml | 5          | localhost:8081 |

    Examples: Online
      | mode   | config                           | max_chunks | doc_url_domain  |
      | Online | lightspeed-stack-okp-online.yaml | 1          | docs.redhat.com |

  # ── Inline RAG — Streaming Query ──

  Scenario Outline: <mode> mode streaming query with inline RAG returns referenced_documents
    Given The service uses the <config> configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And I wait for the response to be completed
      And The response contains non-empty referenced_documents
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And Each referenced_document doc_url contains "<doc_url_domain>"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

    Examples: Offline
      | mode    | config                            | doc_url_domain |
      | Offline | lightspeed-stack-okp-offline.yaml | localhost:8081 |

    Examples: Online
      | mode   | config                           | doc_url_domain  |
      | Online | lightspeed-stack-okp-online.yaml | docs.redhat.com |

  # ── Inline RAG — Query with Dynamic Filter ──

  Scenario Outline: Query with inline RAG with dynamic <filter_mode> filter returns rag_chunks and referenced_documents
    Given The service uses the lightspeed-stack-okp-offline.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Security best practices",
      "solr": {
        "mode": "<filter_mode>",
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
      And The response contains non-empty rag_chunks
      And The response contains non-empty referenced_documents
      And The number of rag_chunk returned is 5
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And Each referenced_document doc_url contains "<doc_url_domain>"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

    Examples:
      | filter_mode | doc_url_domain  |
      | semantic    | localhost:8081  |
      | hybrid      | docs.redhat.com |

  # ── Tool RAG — Query API ──

  Scenario Outline: <mode> queries API with OKP tool RAG has rag_chunk and referenced_documents returned
    Given The service uses the <config> configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {
      "query": "configure remote desktop using gnome",
      "model": "{MODEL}",
      "provider": "{PROVIDER}",
      "system_prompt": "You MUST use the file_search tool to answer."
    }
    """
    Then The status code of the response is 200
      And The response contains non-empty tool_calls
      And A tool_call has name "file_search"
      And The response contains non-empty rag_chunks
      And The number of rag_chunk returned is <max_chunks>
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And The response contains non-empty referenced_documents
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And Each referenced_document doc_url contains "<doc_url_domain>"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

    Examples: Offline
      | mode    | config                            | max_chunks | doc_url_domain |
      | Offline | lightspeed-stack-okp-tool-offline.yaml    | 5          | localhost:8081 |

    Examples: Online
      | mode   | config                                 | max_chunks | doc_url_domain    |
      | Online | lightspeed-stack-okp-tool-online.yaml | 1          | access.redhat.com |

  # ── Tool RAG — Streaming Query API ──

  Scenario Outline: <mode> streaming query API with OKP tool RAG has rag_chunk and referenced_documents returned
    Given The service uses the <config> configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {
      "query": "configure remote desktop using gnome",
      "model": "{MODEL}",
      "provider": "{PROVIDER}",
      "system_prompt": "You MUST use the file_search tool to answer."
    }
    """
    Then The status code of the response is 200
      And A tool_call has name "file_search"
      And The response contains non-empty content
      And The response contains non-empty referenced_documents
      And Each referenced_document has fields doc_url, doc_title, source, and document_id
      And Each referenced_document doc_url contains "<doc_url_domain>"
      And Each referenced_document doc_title is not empty
      And Each referenced_document source is "okp"
      And Each referenced_document has a non-empty document_id

    Examples: Offline
      | mode    | config                            | doc_url_domain |
      | Offline | lightspeed-stack-okp-tool-offline.yaml    | localhost:8081 |

    Examples: Online
      | mode   | config                                 | doc_url_domain    |
      | Online | lightspeed-stack-okp-tool-online.yaml | access.redhat.com |

  # ── Tool RAG — Responses API ──

  Scenario Outline: <mode> responses API with OKP tool RAG has rag results returned
    Given The service uses the <config> configuration
      And The service is restarted
    When I use "responses" to ask question with authorization header
    """
    {
      "input": "configure remote desktop using gnome",
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
      And The number of results returned is <max_chunks>
      And Each rag_chunk has a non-empty score
      And Each rag_chunk source is "okp"
      And Each rag_chunk reference_url contains "<doc_url_domain>"

    Examples: Offline
      | mode    | config                            | max_chunks | doc_url_domain |
      | Offline | lightspeed-stack-okp-tool-offline.yaml    | 5          | localhost:8081 |

    Examples: Online
      | mode   | config                                 | max_chunks | doc_url_domain    |
      | Online | lightspeed-stack-okp-tool-online.yaml | 1          | access.redhat.com |

  # # ── OKP Server Unavailable — Graceful Error Handling ───────────────

  Scenario: Query succeeds with empty rag_chunks when OKP server is unavailable
    Given The OKP(Solr) server is stopped
    When I use "query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The response contains no rag_chunks
      And The response contains no referenced_documents

  Scenario: Streaming query succeeds with empty referenced_documents when OKP server is unavailable
    Given The OKP(Solr) server is stopped
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "configure remote desktop using gnome", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And I wait for the response to be completed
      And The response contains no referenced_documents
