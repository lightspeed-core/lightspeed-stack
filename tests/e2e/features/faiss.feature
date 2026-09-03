@e2e_group_1 @Authorized
Feature: FAISS support tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  Scenario: check if vector store is registered
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

  Scenario: Query vector db using the file_search tool
    When I use "query" to ask question with authorization header
    """
    {"query": "What is the title of the article from Paul?", "system_prompt": "You are an assistant. Always use the file_search tool to answer. Write only lowercase letters", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
     Then The status code of the response is 200
      And The response contains following fragments
          | Fragments in LLM response |
          | great work                |
