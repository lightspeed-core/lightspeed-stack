@e2e_group_1 @RBAC
Feature: rlsapi v1 /infer endpoint error response tests

  Tests for error conditions on the rlsapi v1 /infer endpoint including
  authorization failures (403).

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-rbac.yaml configuration
      And The service is restarted

  # ============================================
  # Authorization - 403 Forbidden
  # ============================================

  Scenario: User without rlsapi_v1_infer permission returns 403
      And I authenticate as "viewer" user
     When I use "infer" to ask question with authorization header
      """
      {"question": "How do I list files?"}
      """
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  Scenario: User with rlsapi_v1_infer permission can access endpoint
      And I authenticate as "user" user
     When I use "infer" to ask question with authorization header
      """
      {"question": "How do I list files?"}
      """
     Then The status code of the response is 200
      And The rlsapi response has valid structure

