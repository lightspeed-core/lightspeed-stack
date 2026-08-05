"""Profile that sets QV validation / invalid_resp to empty strings."""

PROFILE_CONFIG = {
    "system_prompts": {
        "default": "Default system prompt only.",
        "validation": "",
    },
    "query_responses": {"invalid_resp": ""},
}
