@JWKAuth
Feature: JWK authorization enforcement

  Background:
    Given The service is started locally
      And REST API service hostname is localhost
      And REST API service port is 8080
      And REST API service prefix is /v1

  Scenario: A user with the admin role can access the info endpoint
    Given I have a valid JWT token with the admin role
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: A user with the admin role can access the config endpoint
    Given I have a valid JWT token with the admin role
     When I access REST API endpoint "config" using HTTP GET method
     Then The status code of the response is 200

  Scenario: A user with the config role can access the config endpoint
    Given I have a valid JWT token with the config role
     When I access REST API endpoint "config" using HTTP GET method
     Then The status code of the response is 200

  Scenario: A user with the config role can access the info endpoint
    Given I have a valid JWT token with the config role
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: A user with the readonly role can access the info endpoint
    Given I have a valid JWT token with the readonly role
     When I access REST API endpoint "info" using HTTP GET method
     Then The status code of the response is 200

  Scenario: A user with the readonly role can't access the config endpoint
    Given I have a valid JWT token with the readonly role
     When I access REST API endpoint "config" using HTTP GET method
     Then The status code of the response is 403
      And The body of the response contains Insufficient permissions
