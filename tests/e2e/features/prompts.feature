@e2e_group_2 @Authorized
Feature: Prompts API endpoint tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  # --- 200 OK ---

  Scenario: Create prompt returns 200 with prompt_id and version 1
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    And The prompt version in the response is 1

  Scenario: List prompts includes a newly created prompt
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API endpoint "prompts" using HTTP GET method
    Then The status code of the response is 200
    And The prompts list contains the stored prompt id

  Scenario: Get prompt by id returns latest version
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP GET method
    Then The status code of the response is 200
    And The prompt_id in the response matches the stored prompt id
    And The prompt version in the response is 1

  Scenario: Update prompt increments version
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 1, "set_as_default": true, "variables": ["text"]}
    """
    Then The status code of the response is 200
    And The prompt_id in the response matches the stored prompt id
    And The prompt version in the response is 2

  Scenario: Get prompt by id with version query returns that version
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 1, "set_as_default": true, "variables": ["text"]}
    """
    Then The status code of the response is 200
    And The prompt version in the response is 2
    When I access REST API prompts endpoint with stored prompt id and version 1 using HTTP GET method
    Then The status code of the response is 200
    And The prompt_id in the response matches the stored prompt id
    And The prompt version in the response is 1

  Scenario: Delete prompt returns deleted then not found on second delete
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP DELETE method
    Then The status code of the response is 200
    And The prompt_id in the response matches the stored prompt id
    And The body of the response contains deleted successfully
    When I access REST API prompts endpoint with stored prompt id using HTTP DELETE method
    Then The status code of the response is 200
    And The prompt_id in the response matches the stored prompt id
    And The body of the response contains Prompt not found

  # --- 400 Bad Request ---

  Scenario: Get prompt with invalid prompt_id returns bad request
    When I access REST API endpoint "prompts/not_a_prompt_id" using HTTP GET method
    Then The status code of the response is 400
    And The body of the response contains Invalid prompt ID format

  Scenario: Update prompt with invalid prompt_id returns bad request
    When I access REST API endpoint "prompts/not_a_prompt_id" using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 1, "variables": ["text"]}
    """
    Then The status code of the response is 400
    And The body of the response contains Invalid prompt ID format

  Scenario: Delete prompt with invalid prompt_id returns bad request
    When I access REST API endpoint "prompts/not_a_prompt_id" using HTTP DELETE method
    Then The status code of the response is 400
    And The body of the response contains Invalid prompt ID format

  # --- 404 Not Found ---

  Scenario: Get non-existent prompt returns not found
    When I access REST API endpoint "prompts/pmpt_ffffffffffffffffffffffffffffffffffffffffffffffff" using HTTP GET method
    Then The status code of the response is 404
    And The body of the response contains Prompt not found

  Scenario: Get prompt by id with unknown version returns not found
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id and version 99 using HTTP GET method
    Then The status code of the response is 404
    And The body of the response contains Prompt not found

  Scenario: Update non-existent prompt returns not found
    When I access REST API endpoint "prompts/pmpt_ffffffffffffffffffffffffffffffffffffffffffffffff" using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 1, "set_as_default": true, "variables": ["text"]}
    """
    Then The status code of the response is 404
    And The body of the response contains Prompt not found

  # --- 422 Unprocessable Entity ---

  Scenario: Create prompt with missing required field returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"variables": ["text"]}
    """
    Then The status code of the response is 422
    And The body of the response contains prompt

  Scenario: Create prompt with empty prompt returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "", "variables": ["text"]}
    """
    Then The status code of the response is 422
    And The body of the response contains prompt

  Scenario: Create prompt with unknown field returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"], "extra_field": true}
    """
    Then The status code of the response is 422
    And The body of the response contains Extra inputs are not permitted

  Scenario: Get prompt with invalid version query returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id and version query "not-a-version" using HTTP GET method
    Then The status code of the response is 422
    And The body of the response contains version

  Scenario: Update prompt with empty prompt returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP PUT method
    """
    {"prompt": "", "version": 1}
    """
    Then The status code of the response is 422
    And The body of the response contains prompt

  Scenario: Update prompt with missing version returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 422
    And The body of the response contains version

  Scenario: Update prompt with invalid version returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 0, "variables": ["text"]}
    """
    Then The status code of the response is 422
    And The body of the response contains version

  Scenario: Update prompt with unknown field returns unprocessable entity
    When I access REST API endpoint "prompts" using HTTP POST method
    """
    {"prompt": "Summarize: {{text}}", "variables": ["text"]}
    """
    Then The status code of the response is 200
    And I store the prompt_id from the last response
    When I access REST API prompts endpoint with stored prompt id using HTTP PUT method
    """
    {"prompt": "Summarize in bullets: {{text}}", "version": 1, "extra_field": true}
    """
    Then The status code of the response is 422
    And The body of the response contains Extra inputs are not permitted
