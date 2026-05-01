"""OpenAPI description strings and shared example-label lists for API responses."""

from typing import Final

SUCCESSFUL_RESPONSE_DESCRIPTION: Final[str] = "Successful response"
BAD_REQUEST_DESCRIPTION: Final[str] = "Invalid request format"
UNAUTHORIZED_DESCRIPTION: Final[str] = "Unauthorized"
FORBIDDEN_DESCRIPTION: Final[str] = "Permission denied"
NOT_FOUND_DESCRIPTION: Final[str] = "Resource not found"
UNPROCESSABLE_CONTENT_DESCRIPTION: Final[str] = "Request validation failed"
INVALID_FEEDBACK_PATH_DESCRIPTION: Final[str] = "Invalid feedback storage path"
SERVICE_UNAVAILABLE_DESCRIPTION: Final[str] = "Service unavailable"
QUOTA_EXCEEDED_DESCRIPTION: Final[str] = "Quota limit exceeded"
PROMPT_TOO_LONG_DESCRIPTION: Final[str] = "Prompt is too long"
INTERNAL_SERVER_ERROR_DESCRIPTION: Final[str] = "Internal server error"
CONFLICT_DESCRIPTION: Final[str] = "Resource already exists"
FILE_UPLOAD_EXCEEDS_SIZE_LIMIT_DESCRIPTION: Final[str] = (
    "File upload exceeds size limit"
)
UNAUTHORIZED_OPENAPI_EXAMPLES: Final[list[str]] = [
    "missing header",
    "missing token",
    "expired token",
    "invalid signature",
    "invalid key",
    "missing claim",
    "invalid k8s token",
    "invalid jwk token",
]

UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH: Final[list[str]] = [
    *UNAUTHORIZED_OPENAPI_EXAMPLES,
    "mcp oauth",
]
