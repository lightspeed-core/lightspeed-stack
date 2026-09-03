@e2e_group_3 @skip-in-server-mode
Feature: BYOK PDF support tests

  # Validates that a vector store built from a PDF by rag-content's `pdf`
  # module (LCORE-2091) is consumed correctly by lightspeed-stack: the BYOK
  # source is registered and a query retrieves content that exists only in the
  # source PDF. The fixture store (tests/e2e/rag/pdf_kv_store.db) holds a single
  # deliberately-fabricated fact, so a correct answer can only come from the
  # store, not from the LLM's own knowledge.

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-byok-pdf.yaml configuration
      And The service is restarted

  Scenario: PDF-built inline RAG source is registered
    When I access REST API endpoint rags using HTTP GET method
    Then The status code of the response is 200
     And the body of the response has the following structure
    """
    {
      "rags": [
        "pdf-field-notes"
      ]
    }
    """

  Scenario: Query retrieves content sourced from the PDF
    When I use "query" to ask question with authorization header
    """
    {"query": "According to the field notes, what is the name of the mascot of Red Hat Lightspeed?", "system_prompt": "You are an assistant. Answer only from the provided context. Write only lowercase letters", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The response contains following fragments
         | Fragments in LLM response |
         | zephyr                    |
     And The response contains non-empty rag_chunks

  Scenario: Streaming query retrieves content sourced from the PDF
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "According to the field notes, what is the name of the mascot of Red Hat Lightspeed?", "system_prompt": "You are an assistant. Answer only from the provided context. Write only lowercase letters", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And I wait for the response to be completed
     And The streamed response contains following fragments
         | Fragments in LLM response |
         | zephyr                    |
