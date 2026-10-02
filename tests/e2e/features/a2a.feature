@cfg_a2a
Feature: A2A protocol full-flow tests

  LCS is an A2A server. An external A2A client discovers this instance
  via the agent card and sends work to /a2a. These scenarios run that
  path through a live OGX. 

  Background:
    Given The service is started locally
      And The system is in default state
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-a2a.yaml configuration
      And The service is restarted

  Scenario: Discover the agent and complete one task
    And I authenticate as "user" user
    When I fetch the A2A agent card from "/.well-known/agent.json"
    Then The status code of the response is 200
      And The A2A agent card name is "E2E A2A Assistant"
      And The A2A agent card url ends with "/a2a"
      And The A2A agent card advertises streaming
      And The A2A agent card lists skill "general-qa"
    When I send an A2A "message/send" request
    """
    What is the capital of France? Reply with the city name.
    """
    Then The status code of the response is 200
      And Content type of response is set to "application/json"
      And The A2A task state is "completed"
      And The A2A artifact text contains "Paris"

  Scenario: Multi-turn conversation keeps context
    And I authenticate as "user" user
    When I send an A2A "message/send" request
    """
    What is the capital of France? Reply with the city name.
    """
    Then The status code of the response is 200
      And The A2A task state is "completed"
      And The A2A artifact text contains "Paris"
      And I store the A2A context id
    When I send an A2A "message/send" follow-up request
    """
    What is its population, roughly? Name the city in your answer.
    """
    Then The status code of the response is 200
      And Content type of response is set to "application/json"
      And The A2A task state is "completed"
      And The A2A context id is unchanged
      And The A2A artifact text contains "Paris"

  Scenario: Streaming message produces a completed task
    And I authenticate as "user" user
    When I send an A2A "message/stream" request
    """
    Explain how photosynthesis works in two short sentences.
    """
    Then The status code of the response is 200
      And Content type of response is set to "text/event-stream"
      And The A2A stream contains a submitted task
      And The A2A stream contains working status updates
      And The A2A stream ends with a completed task
      And The A2A artifact text contains "light"

    Scenario: Viewer views agent card but cannot send messages
    And I authenticate as "viewer" user
    When I fetch the A2A agent card from "/.well-known/agent-card.json"
    Then The status code of the response is 200
      And The A2A agent card name is "E2E A2A Assistant"
      And The A2A agent card url ends with "/a2a"
      And The A2A agent card advertises streaming
      And The A2A agent card lists skill "general-qa"
    When I send an A2A "message/send" request
    """
    What is the capital of France? Reply with the city name.
    """
    Then The status code of the response is 403