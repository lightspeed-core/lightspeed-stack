@e2e_group_3
Feature: Inline RAG (BYOK) support tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-inline-rag.yaml configuration
      And The service is restarted

  Scenario: Check if inline RAG source is registered
    When I access REST API endpoint rags using HTTP GET method
    Then The status code of the response is 200
     And the body of the response has the following structure
    """
    {
      "rags": [
        "e2e-test-docs"
      ]
    }
    """

  Scenario: Query with inline RAG returns relevant content
    When I use "query" to ask question with authorization header
    """
    {"query": "What is the title of the article from Paul?", "system_prompt": "You are an assistant. Write only lowercase letters", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The response contains following fragments
         | Fragments in LLM response |
         | great work                |
     And The response contains non-empty rag_chunks

  Scenario: Inline RAG query includes referenced documents
    When I use "query" to ask question with authorization header
    """
    {"query": "What does Paul Graham say about great work?", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The response contains non-empty referenced_documents

  Scenario: Streaming query with inline RAG returns relevant content
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "What is the title of the article from Paul?", "system_prompt": "You are an assistant. Write only lowercase letters", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And I wait for the response to be completed
     And The streamed response contains following fragments
         | Fragments in LLM response |
         | great work                |

  Scenario: Responses API with inline RAG returns relevant content
    When I use "responses" to ask question with authorization header
    """
    {"input": "What is the title of the article from Paul?", "model": "{PROVIDER}/{MODEL}", "stream": false, "instructions": "You are an assistant. Write only lowercase letters"}
    """
    Then The status code of the response is 200
     And The response contains following fragments
         | Fragments in LLM response |
         | great work                |

  Scenario: Streaming Responses API with inline RAG returns relevant content
    When I use "responses" to ask question with authorization header
    """
    {"input": "What is the title of the article from Paul?", "model": "{PROVIDER}/{MODEL}", "stream": true, "instructions": "You are an assistant. Write only lowercase letters"}
    """
    Then The status code of the response is 200
     And The body of the response contains great work
