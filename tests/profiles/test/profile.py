"""Custom profile for test profile."""

SUBJECT_ALLOWED = "ALLOWED"
SUBJECT_REJECTED = "REJECTED"

# Default responses
INVALID_QUERY_RESP = (
    "Hi, I'm the Red Hat Developer Hub Lightspeed assistant, I can help you with questions about Red Hat Developer Hub or Backstage. "
    "Please ensure your question is about these topics, and feel free to ask again!"
)

QUERY_SYSTEM_INSTRUCTION = """
1. Test
This is a test system instruction

You achieve this by offering:
- testing
"""

USE_CONTEXT_INSTRUCTION = """
Use the retrieved document to answer the question.
"""

USE_HISTORY_INSTRUCTION = """
Use the previous chat history to interact and help the user.
"""

QUESTION_VALIDATOR_PROMPT_TEMPLATE = f"""
Instructions:
- You provide validation for testing
Example Question:
How can I integrate GitOps into my pipeline?
Example Response:
{SUBJECT_ALLOWED}
"""

TOPIC_SUMMARY_PROMPT_TEMPLATE = """
Instructions:
- You are a topic summarizer
- For testing
- Your job is to extract precise topic summary from user input

Example Input:
Testing placeholder
Example Output:
Proper response test.
"""

PROFILE_CONFIG = {
    "system_prompts": {
        "default": QUERY_SYSTEM_INSTRUCTION,
        "validation": QUESTION_VALIDATOR_PROMPT_TEMPLATE,
        "topic_summary": TOPIC_SUMMARY_PROMPT_TEMPLATE,
    },
    "query_responses": {"invalid_resp": INVALID_QUERY_RESP},
    "instructions": {
        "context": USE_CONTEXT_INSTRUCTION,
        "history": USE_HISTORY_INSTRUCTION,
    },
}
