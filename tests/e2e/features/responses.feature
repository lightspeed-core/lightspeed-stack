@Authorized
Feature: Responses endpoint API tests

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  Scenario: Check if responses endpoint returns 200 for minimal request
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": false}
    """
    Then The status code of the response is 200

  Scenario: Check if responses endpoint returns 200 for minimal streaming request
    Given The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    When I use "responses" to ask question with authorization header
    """
    {"input": "Say hello", "model": "{PROVIDER}/{MODEL}", "stream": true}
    """
    Then The status code of the response is 200
