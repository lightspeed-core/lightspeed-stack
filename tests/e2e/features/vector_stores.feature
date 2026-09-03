@e2e_group_3 @VectorStores
Feature: vector stores API endpoint tests


  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  Scenario: List vector stores returns 200
    When I access REST API endpoint "vector-stores" using HTTP GET method
    Then The status code of the response is 200
     And Content type of response is set to "application/json"

  Scenario: Create vector store with empty body returns 422
    When I access REST API endpoint "vector-stores" using HTTP POST method
         """
         {}
         """
    Then The status code of the response is 422

  Scenario: Create vector store with extra fields returns 422
    When I access REST API endpoint "vector-stores" using HTTP POST method
         """
         {"name": "test-store", "unknown_field": "value"}
         """
    Then The status code of the response is 422

  Scenario: Update vector store with empty body returns 422
    When I access REST API endpoint "vector-stores/nonexistent-id" using HTTP PUT method
         """
         {}
         """
    Then The status code of the response is 422

  Scenario: Add file to vector store with empty body returns 422
    When I access REST API endpoint "vector-stores/nonexistent-id/files" using HTTP POST method
         """
         {}
         """
    Then The status code of the response is 422
