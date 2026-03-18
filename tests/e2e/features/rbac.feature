@RBAC
Feature: Role-Based Access Control (RBAC)

  Comprehensive tests for role-based access control to ensure
  authentication and authorization work correctly.

  Background:
    Given The service is started locally
      And REST API service prefix is /v1

  # ============================================
  # Authentication - Token Validation
  # ============================================

  Scenario: Request without token returns 401
    Given The system is in default state
      And I remove the auth header
     When I access REST API endpoint "models" using HTTP GET method
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

  Scenario: Request with malformed Authorization header returns 401
    Given The system is in default state
      And I set the Authorization header to NotBearer sometoken
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 401

  # ============================================
  # Admin Role - Full Access
  # ============================================

  Scenario: Admin can access query endpoint
    Given The system is in default state
      And I authenticate as "admin" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 200

  Scenario: Admin can access models endpoint
    Given The system is in default state
      And I authenticate as "admin" user
     When I access REST API endpoint "models" using HTTP GET method
     Then The status code of the response is 200

  Scenario: Admin can list conversations
    Given The system is in default state
      And I authenticate as "admin" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200

  # ============================================
  # User Role - Standard Access
  # ============================================

  Scenario: User can access query endpoint
    Given The system is in default state
      And I authenticate as "user" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 200

  Scenario: User can list conversations
    Given The system is in default state
      And I authenticate as "user" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200

  # ============================================
  # Viewer Role - Read Only
  # ============================================

  Scenario: Viewer can list conversations
    Given The system is in default state
      And I authenticate as "viewer" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 200

  Scenario: Viewer can access info endpoint
    Given The system is in default state
      And I authenticate as "viewer" user
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: Viewer cannot query - returns 403
    Given The system is in default state
      And I authenticate as "viewer" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  # ============================================
  # Query-Only Role - Limited Access (no model_override)
  # ============================================

  Scenario: Query-only user can query without specifying model
    Given The system is in default state
      And I authenticate as "query_only" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi"}
      """
     Then The status code of the response is 200

  Scenario: Query-only user cannot override model - returns 403
    Given The system is in default state
      And I authenticate as "query_only" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 403
      And The body of the response contains model_override

  Scenario: Query-only user cannot list conversations - returns 403
    Given The system is in default state
      And I authenticate as "query_only" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  # ============================================
  # No Role - Minimal Access (everyone role only)
  # ============================================

  Scenario: No-role user can access info endpoint (everyone role)
    Given The system is in default state
      And I authenticate as "no_role" user
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: No-role user cannot query - returns 403
    Given The system is in default state
      And I authenticate as "no_role" user
     When I use "query" to ask question with authorization header
      """
      {"query": "Say hi", "model": "{MODEL}", "provider": "{PROVIDER}"}
      """
     Then The status code of the response is 403
      And The body of the response contains does not have permission

  Scenario: No-role user cannot list conversations - returns 403
    Given The system is in default state
      And I authenticate as "no_role" user
     When I access REST API endpoint "conversations" using HTTP GET method
     Then The status code of the response is 403
      And The body of the response contains does not have permission
