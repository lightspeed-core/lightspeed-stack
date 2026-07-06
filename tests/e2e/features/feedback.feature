@e2e_group_3 @Feedback
Feature: feedback endpoint API tests


  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"
      And The service uses the lightspeed-stack-auth-noop-token.yaml configuration
      And The service is restarted

  Scenario: Check if enabling the feedback is working
    When The feedback is enabled
     Then The status code of the response is 200
     And the body of the response has the following structure
        """
        {
            "status": 
                {
                    "updated_status": true
                }
        }
        """
    
  Scenario: Check if disabling the feedback is working
    When The feedback is disabled
     Then The status code of the response is 200
     And the body of the response has the following structure
        """
        {
            "status": 
                {
                    "updated_status": false
                }
        }
        """

  Scenario: Check if toggling the feedback with incorrect attribute name fails
     When I update feedback status with
        """
            {
                "no_status": true
            }
        """
     Then The status code of the response is 422
     And the body of the response has the following structure
        """
        {
        "detail": [
            {
            "type": "extra_forbidden",
            "loc": [
                "body",
                "no_status"
            ],
            "msg": "Extra inputs are not permitted",
            "input": true
            }
        ]
        }
        """

  Scenario: Check if getting feedback status returns true when feedback is enabled
    And The feedback is enabled
     When I retreive the current feedback status
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "functionality": "feedback",
            "status": { 
                        "enabled": true
                        }
        }
        """

  Scenario: Check if getting feedback status returns false when feedback is disabled
    And The feedback is disabled
     When I retreive the current feedback status
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "functionality": "feedback",
            "status": { 
                        "enabled": false
                        }
        }
        """

  Scenario: Check if feedback endpoint is not working when feedback is disabled
    And A new conversation is initialized
    And The feedback is disabled
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "bar",
            "sentiment": -1,
            "user_feedback": "Not satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 403
     And The body of the response is the following
        """
        {
            "detail": {
                "response": "Storing feedback is disabled",
                "cause": "Storing feedback is disabled."
            }
        }  
        """

  Scenario: Check if feedback endpoint fails when required fields are not specified
    And The feedback is enabled
     When I submit the following feedback without specifying conversation ID
        """
        {
        }
        """
     Then The status code of the response is 422
     And the body of the response has the following structure
        """
        {
        "detail": [
            {
            "type": "missing",
            "loc": [
                "body",
                "conversation_id"
            ],
            "msg": "Field required"
            },
            {
            "type": "missing",
            "loc": [
                "body",
                "user_question"
            ],
            "msg": "Field required"
            },
            {
            "type": "missing",
            "loc": [
                "body",
                "llm_response"
            ],
            "msg": "Field required"
            }
        ]
        }
        """

  Scenario: Check if feedback endpoint is working when sentiment is negative
    And A new conversation is initialized
    And The feedback is enabled
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "bar",
            "sentiment": -1,
            "user_feedback": "Not satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "response": "feedback received"
        }
        """

  Scenario: Check if feedback endpoint is working when sentiment is positive
    And A new conversation is initialized
    And The feedback is enabled
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "bar",
            "sentiment": 1,
            "user_feedback": "Satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "response": "feedback received"
        }
        """

  Scenario: Check if feedback submission fails when invalid sentiment is passed
    And A new conversation is initialized
    And The feedback is enabled
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "Sample Response",
            "sentiment": 0,
            "user_feedback": "Not satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 422
     And the body of the response has the following structure
        """
        {
            "detail": [{
                        "type": "value_error", 
                        "loc": ["body", "sentiment"], 
                        "msg": "Value error, Improper sentiment value of 0, needs to be -1 or 1",
                        "input": 0
                    }]           
        }
        """

  Scenario: Check if feedback submission fails when nonexisting conversation ID is passed
    And The feedback is enabled
     When I submit the following feedback for nonexisting conversation "12345678-abcd-0000-0123-456789abcdef"
        """
        {
            "llm_response": "Sample Response",
            "sentiment": -1,
            "user_feedback": "Not satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 404
     And The body of the response is the following
        """
        {
            "detail": {
                "response": "Conversation not found",
                "cause": "Conversation with ID 12345678-abcd-0000-0123-456789abcdef does not exist"
            }
        }
        """

  Scenario: Check if feedback submission fails when conversation belongs to a different user
    And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
    # Create a conversation as a different user (via user_id query param for noop_with_token)
    And A new conversation is initialized with user_id "different_user_id"
    # Feedback submission will use the default user from the auth header
    And The feedback is enabled
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "Sample Response",
            "sentiment": -1,
            "user_feedback": "Not satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 403
     And The body of the response contains User does not have permission to perform this action

  Scenario: Check if feedback endpoint fails when only empty string user_feedback is provided
    Given The system is in default state
    And A new conversation is initialized
    And The feedback is enabled
     When I submit the following feedback for the conversation created before
        """
        {
            "user_question": "Sample Question",
            "llm_response": "Sample Response",
            "user_feedback": ""
        }
        """
     Then The status code of the response is 422
     And the body of the response has the following structure
        """
        {
            "detail": [{
                        "type": "value_error", 
                        "loc": ["body"], 
                        "msg": "Value error, At least one form of feedback must be provided: 'sentiment', 'user_feedback', or 'categories'",
                        "input": {
                            "user_feedback": ""
                        }
                    }]           
        }
        """

@InvalidFeedbackStorageConfig
  Scenario: Check if feedback submittion fails when invalid feedback storage path is configured
    Given The service uses the lightspeed-stack-invalid-feedback-storage.yaml configuration
      And The service is restarted
      And The system is in default state
      And The feedback is enabled
    And A new conversation is initialized
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "Sample Response",
            "sentiment": -1,
            "user_feedback": "Not satisfied with the response quality",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 500
     And The body of the response is the following
        """
        {
            "detail": {
                        "response": "Failed to store feedback",
                        "cause": "Failed to store feedback at directory: /invalid"
                    }
        }
        """

  Scenario: Check if sequential feedback status toggling maintains consistency
    When The feedback is enabled
     Then The status code of the response is 200
    When The feedback is disabled
     Then The status code of the response is 200
    When The feedback is enabled
     Then The status code of the response is 200
    When I retreive the current feedback status
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "functionality": "feedback",
            "status": {
                        "enabled": true
                        }
        }
        """

  Scenario: Check if submitting duplicate feedback succeeds
    And A new conversation is initialized
    And The feedback is enabled
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "bar",
            "sentiment": -1,
            "user_feedback": "Not satisfied",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "response": "feedback received"
        }
        """
     When I submit the following feedback for the conversation created before
        """
        {
            "llm_response": "bar",
            "sentiment": -1,
            "user_feedback": "Not satisfied",
            "user_question": "Sample Question"
        }
        """
     Then The status code of the response is 200
     And The body of the response is the following
        """
        {
            "response": "feedback received"
        }
        """
