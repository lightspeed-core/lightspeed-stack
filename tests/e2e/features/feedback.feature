@Authorized @Feedback
Feature: feedback endpoint API tests


  Background:
    Given The service is started locally
      And REST API service prefix is /v1
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva

  Scenario: Check if enabling the feedback is working
    Given The system is in default state
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
    Given The system is in default state
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
    Given The system is in default state
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
    Given The system is in default state
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
    Given The system is in default state
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
    Given The system is in default state
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
            "detail": "Forbidden: Feedback is disabled"
        }   
        """

  Scenario: Check if feedback endpoint fails when required fields are not specified
    Given The system is in default state
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
    Given The system is in default state
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
    Given The system is in default state
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

  Scenario: Check if feedback submittion fails when invald sentiment is passed
    Given The system is in default state
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

  @skip
  Scenario: Check if feedback submittion fails when nonexisting conversation ID is passed
    Given The system is in default state
    And A new conversation is initialized
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
     Then The status code of the response is 422
     And The body of the response is the following
        """
        {
            "response": "User has no access to this conversation"
        }
        """
    
  Scenario: Check if feedback endpoint is not working when not authorized
    Given The system is in default state
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
     Then The status code of the response is 401
     And The body of the response is the following
        """
        {
            "detail": "No Authorization header found"
        }
        """

  Scenario: Check if update feedback status endpoint is not working when not authorized
    Given The system is in default state
    And I remove the auth header
     When The feedback is enabled
     Then The status code of the response is 401
     And The body of the response is the following
        """
        {
            "detail": "No Authorization header found"
        }
        """

  @InvalidFeedbackStorageConfig
  Scenario: Check if feedback submittion fails when invalid feedback storage path is configured
    Given The system is in default state
    And The feedback is enabled
    And An invalid feedback storage path is configured
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
                        "response": "Error storing user feedback", 
                        "cause": "[Errno 13] Permission denied: '/invalid'"
                    }
        }
        """

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
