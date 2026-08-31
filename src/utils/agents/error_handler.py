"""Error mapping for agent inference failures to structured API error responses."""

from fastapi import status
from ogx_client import APIConnectionError, APIStatusError
from pydantic_ai.exceptions import (
    AgentRunError,
    ContentFilterError,
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)

from log import get_logger
from models.api.responses.error import (
    AbstractErrorResponse,
    InternalServerErrorResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
)
from utils.query import (
    handle_known_apistatus_errors,
    is_context_length_error,
    is_resource_exhausted_error,
)

type AgentInferenceError = (
    AgentRunError | APIStatusError | APIConnectionError | RuntimeError
)

logger = get_logger(__name__)


def map_agent_inference_error(
    exc: AgentInferenceError,
    model_id: str,
) -> AbstractErrorResponse:
    """Map agent run failures from pydantic-ai or OGX to an LCS error response.

    Args:
        exc: Agent, HTTP status, connection, or context-length runtime error.
        model_id: Model identifier in provider/model format.

    Returns:
        Structured error response for HTTP or SSE error events.

    Raises:
        RuntimeError: Re-raised when ``exc`` is a non-agent ``RuntimeError`` that is
            not a recognized context-length failure.
    """
    match exc:
        case AgentRunError() as agent_exc:
            response = map_pydantic_agent_run_error(agent_exc, model_id)
        case APIStatusError() as status_exc:
            response = handle_known_apistatus_errors(status_exc, model_id)
        case APIConnectionError() as connection_exc:
            response = ServiceUnavailableResponse(
                backend_name="OGX",
                cause=str(connection_exc),
            )
        case RuntimeError() as runtime_exc if is_context_length_error(str(runtime_exc)):
            response = PromptTooLongResponse(model=model_id)
        case _:
            response = InternalServerErrorResponse.generic()

    # The mapped HTTPException loses the original exception, and callers raise
    # it without logging — log here so failures are diagnosable (LCORE-3582).
    # Only unclassified failures are genuine service faults worth a traceback:
    # a mapped 4xx is caller-caused (413 over-long prompt, 429 rate limit) and
    # a 503 is an upstream outage, so logging those at error level with a stack
    # trace would bury the 500s this logging exists to surface.
    status_code = getattr(response, "status_code", None)
    caller_or_upstream = isinstance(status_code, int) and (
        status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
        or status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    )
    if caller_or_upstream:
        logger.warning("Agent inference returned %s: %s", status_code, exc)
    else:
        logger.error("Agent inference failed: %s", exc, exc_info=exc)
    return response


def map_pydantic_agent_run_error(  # pylint: disable=too-many-return-statements
    exc: AgentRunError, model_id: str
) -> AbstractErrorResponse:
    """Map pydantic-ai ``AgentRunError`` subclasses to LCS error responses.

    Args:
        exc: Agent exception to map.
        model_id: Model identifier in provider/model format.

    Returns:
        Structured error response for HTTP or SSE error events.
    """
    match exc:
        case ContentFilterError() as filter_exc:
            return InternalServerErrorResponse.query_failed(str(filter_exc))
        case IncompleteToolCall():
            return PromptTooLongResponse(model=model_id)
        case UnexpectedModelBehavior():
            logger.error("Unexpected model behavior: %s", exc, exc_info=True)
            return InternalServerErrorResponse.generic()
        case UsageLimitExceeded():
            return QuotaExceededResponse.model(model_id)
        case ModelHTTPError() as http_exc if is_context_length_error(str(http_exc)):
            return PromptTooLongResponse(model=model_id)
        case ModelHTTPError(status_code=429):
            return QuotaExceededResponse.model(model_id)
        case ModelHTTPError() as http_exc if is_resource_exhausted_error(str(http_exc)):
            logger.warning(
                "Detected RESOURCE_EXHAUSTED in ModelHTTPError with status %d; treating as "
                "429 (OGX wraps Vertex AI 429 as 500)",
                http_exc.status_code,
            )
            return QuotaExceededResponse.model(model_id)
        case ModelHTTPError():
            return InternalServerErrorResponse.generic()
        case ModelAPIError() as api_exc:
            return ServiceUnavailableResponse(
                backend_name="OGX",
                cause=str(api_exc),
            )
        case _:
            return InternalServerErrorResponse.query_failed(str(exc))
