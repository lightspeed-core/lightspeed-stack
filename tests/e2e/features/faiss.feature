@Authorized
Feature: FAISS support tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  @skip-in-library-mode
  Scenario: Verify vector store is registered
    Given The system is in default state
     And REST API service hostname is localhost
     And REST API service port is 8321
    When I access REST API endpoint vector_stores using HTTP GET method
    Then The status code of the response is 200
     And I should see attribute named data in response
     And the body of the response has the following structure
    """
    {
      "object": "list",
      "data": [
        {
          "object": "vector_store",
          "name": "paul_graham_essay"
        }
      ]
    }
    """

  Scenario: Query vector db using the file_search tool
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "query" to ask question with authorization header
    """
    {"query": "What is the title of the article from Paul?", "system_prompt": "You are an assistant. Always use the file_search tool to answer. Write only lowercase letters"}
    """
     Then The status code of the response is 200
      And The response should contain following fragments
          | Fragments in LLM response |
          | great work                |
