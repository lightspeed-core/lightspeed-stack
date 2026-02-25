@RBAC
Feature: rlsapi v1 /infer endpoint error response tests

  Tests for error conditions on the rlsapi v1 /infer endpoint including
  authorization failures (403) and service unavailability (503).

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  # ============================================
  # Authorization - 403 Forbidden
  # ============================================

  Scenario: User without rlsapi_v1_infer permission returns 403
    Given The system is in default state
      And I authenticate as "viewer" user
     When I use "infer" to ask question with authorization header
      """
      {"question": "How do I list files?"}
      """
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  Scenario: User with rlsapi_v1_infer permission can access endpoint
    Given The system is in default state
      And I authenticate as "user" user
     When I use "infer" to ask question with authorization header
      """
      {"question": "How do I list files?"}
      """
     Then The status code of the response is 200
      And The rlsapi response should have valid structure

  # ============================================
  # Service Unavailable - 503
  # ============================================

  @skip-in-library-mode
  Scenario: Returns 503 when llama-stack connection is broken
    Given The system is in default state
      And I authenticate as "user" user
      And The llama-stack connection is disrupted
     When I use "infer" to ask question with authorization header
      """
      {"question": "How do I list files?"}
      """
     Then The status code of the response is 503
      And The body of the response contains Llama Stack
