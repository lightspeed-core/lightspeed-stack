@Authorized
Feature: Authorized endpoint API tests for the noop-with-token authentication module

  Background:
    Given The service is started locally
      And REST API service hostname is localhost
      And REST API service port is 8080
      And REST API service prefix is /v1

  Scenario: Check if the authorized endpoint fails when user_id and auth header are not provided 
    Given The system is in default state
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 400
      And The body of the response is the following
          """
            {"detail": "No Authorization header found"}
          """

  Scenario: Check if the authorized endpoint works when user_id is not provided 
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method without user_id
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "00000000-0000-0000-0000-000","username": "lightspeed-user","skip_userid_check": true}
          """

  Scenario: Check if the authorized endpoint works when providing empty user_id
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method with user_id ""
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "","username": "lightspeed-user","skip_userid_check": true}
          """

  Scenario: Check if the authorized endpoint works when providing proper user_id
    Given The system is in default state
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
     Then The status code of the response is 200
      And The body of the response is the following
          """
            {"user_id": "test_user","username": "lightspeed-user","skip_userid_check": true}
          """

   Scenario: Check if the authorized endpoint works with proper user_id but bearer token is not present
    Given The system is in default state
     When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
     Then The status code of the response is 400
      And The body of the response is the following
          """
            {"detail": "No Authorization header found"}
          """

  Scenario: Check if the authorized endpoint works when auth token is malformed
    Given The system is in default state
    And I set the Authorization header to BearereyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
     When I access endpoint "authorized" using HTTP POST method with user_id "test_user"
     Then The status code of the response is 400
      And The body of the response is the following
          """
            {"detail": "No token found in Authorization header"}
          """