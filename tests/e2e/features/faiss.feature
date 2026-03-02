@Authorized
Feature: FAISS support tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: check if vector store is registered
    Given The system is in default state
     And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I access REST API endpoint rags using HTTP GET method
    Then The status code of the response is 200
     And the body of the response has the following structure
    """
    {
      "rags": [
        "{VECTOR_STORE_ID}"
      ]
    }
    """

  @skip-in-library-mode
  Scenario: Check if rags endpoint fails when llama-stack is unavailable
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    And The llama-stack connection is disrupted
     When I access REST API endpoint rags using HTTP GET method
     Then The status code of the response is 503
     And The body of the response contains Unable to connect to Llama Stack

  Scenario: Check if rags endpoints responds with error when not authenticated
    Given The system is in default state
     When I access REST API endpoint rags using HTTP GET method
      Then The status code of the response is 401
      And The body of the response is the following
      """
      {
        "detail": {
          "response": "Missing or invalid credentials provided by client",
          "cause": "No Authorization header found"
        }
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
