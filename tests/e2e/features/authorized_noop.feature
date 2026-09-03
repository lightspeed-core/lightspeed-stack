@e2e_group_1
Feature: Authorized endpoint API tests for the noop authentication module

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack.yaml configuration
      And The service is restarted

  Scenario: Check if the authorized endpoint works fine when user_id and auth header are not provided 
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "00000000-0000-0000-0000-000","username": "lightspeed-user","skip_userid_check": true}
          """

  Scenario: Check if the authorized endpoint works when auth token is not provided 
     When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "test_user","username": "lightspeed-user","skip_userid_check": true}
          """

  Scenario: Check if the authorized endpoint works when user_id is not provided 
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method without user_id
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "00000000-0000-0000-0000-000","username": "lightspeed-user","skip_userid_check": true}
          """

  Scenario: Check if the authorized endpoint rejects empty user_id
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method with user_id ""
     Then The status code of the response is 400
      And The body of the response is the following
          """
            {"detail": "user_id cannot be empty"}
          """

  Scenario: Check if the authorized endpoint works when providing proper user_id
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "test_user","username": "lightspeed-user","skip_userid_check": true}
          """