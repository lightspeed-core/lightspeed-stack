@e2e_group_3 @RHIdentity
Feature: Authorized endpoint API tests for the rh-identity authentication module

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-rh-identity.yaml configuration
      And The service is restarted

  Scenario: Request fails when identity field is missing
      And I set the x-rh-identity header with JSON
      """
      {"entitlements": {"rhel": {"is_entitled": true}}}
      """
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 400
      And The body of the response contains Invalid identity data

  Scenario: Request succeeds with valid User identity and required entitlements
      And I set the x-rh-identity header with valid User identity
          | field        | value               |
          | user_id      | test-user-123       |
          | username     | testuser@redhat.com |
          | org_id       | 321                 |
          | entitlements | rhel                |
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 200
      And The body of the response is the following
          """
          {"user_id": "test-user-123", "username": "testuser@redhat.com", "skip_userid_check": false}
          """

  Scenario: Request succeeds with valid System identity and required entitlements
      And I set the x-rh-identity header with valid System identity
          | field          | value                                |
          | cn             | c87dcb4c-8af1-40dd-878e-60c744edddd0 |
          | account_number | 456                                  |
          | org_id         | 654                                  |
          | entitlements   | rhel                                 |
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 200
      And The body of the response is the following
          """
          {"user_id": "c87dcb4c-8af1-40dd-878e-60c744edddd0", "username": "456", "skip_userid_check": false}
          """

  Scenario: Request fails when required entitlement is missing
      And I set the x-rh-identity header with valid User identity
          | field        | value               |
          | user_id      | test-user-123       |
          | username     | testuser@redhat.com |
          | org_id       | 321                 |
          | entitlements | ansible             |
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 403
      And The body of the response contains Insufficient entitlements

  Scenario: Request fails when entitlement exists but is_entitled is false
      And I set the x-rh-identity header with JSON
      """
      {
        "identity": {
          "type": "User",
          "org_id": "321",
          "user": {"user_id": "test-user-123", "username": "testuser@redhat.com"}
        },
        "entitlements": {"rhel": {"is_entitled": false, "is_trial": true}}
      }
      """
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 403
      And The body of the response contains Insufficient entitlements

  Scenario: Request fails when User identity is missing user_id
      And I set the x-rh-identity header with JSON
      """
      {
        "identity": {
          "type": "User",
          "org_id": "321",
          "user": {"username": "testuser@redhat.com"}
        },
        "entitlements": {"rhel": {"is_entitled": true}}
      }
      """
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 400
      And The body of the response contains Invalid identity data

  Scenario: Request fails when User identity is missing username
      And I set the x-rh-identity header with JSON
      """
      {
        "identity": {
          "type": "User",
          "org_id": "321",
          "user": {"user_id": "test-user-123"}
        },
        "entitlements": {"rhel": {"is_entitled": true}}
      }
      """
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 400
      And The body of the response contains Invalid identity data

  Scenario: Request fails when System identity is missing cn
      And I set the x-rh-identity header with JSON
      """
      {
        "identity": {
          "type": "System",
          "account_number": "456",
          "org_id": "654",
          "system": {}
        },
        "entitlements": {"rhel": {"is_entitled": true}}
      }
      """
     When I access endpoint "authorized" using HTTP POST method
     """
     {"placeholder":"abc"}
     """
     Then The status code of the response is 400
      And The body of the response contains Invalid identity data
