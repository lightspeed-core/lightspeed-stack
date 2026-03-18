"""Handler for RHEL Lightspeed rlsapi v1 REST API endpoints.

This module provides the /infer endpoint for stateless inference requests
from the RHEL Lightspeed Command Line Assistant (CLA).
"""

import functools
import time
from datetime import datetime, UTC
from typing import Annotated, Any, Optional, cast

import jinja2
from jinja2.sandbox import SandboxedEnvironment
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import APIConnectionError, APIStatusError, RateLimitError
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

import constants
import metrics
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authentication.rh_identity import RHIdentityData
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.rlsapi.requests import RlsapiV1InferRequest, RlsapiV1SystemInfo
from models.rlsapi.responses import RlsapiV1InferData, RlsapiV1InferResponse
from observability import InferenceEventData, build_inference_event, send_splunk_event
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
)
from utils.responses import (
    build_turn_summary,
    extract_text_from_response_items,
    extract_token_usage,
    get_mcp_tools,
)
from utils.suid import get_suid
from log import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["rlsapi-v1"])


class TemplateRenderError(Exception):
    """Raised when the system prompt Jinja2 template cannot be compiled."""


# Default values when RH Identity auth is not configured
AUTH_DISABLED = "auth_disabled"
# Keep this tuple centralized so infer_endpoint can catch all expected backend
# failures in one place while preserving a single telemetry/error-mapping path.
_INFER_HANDLED_EXCEPTIONS = (
    TemplateRenderError,
    RuntimeError,
    APIConnectionError,
    RateLimitError,
    APIStatusError,
    OpenAIAPIStatusError,
)


def _get_rh_identity_context(request: Request) -> tuple[str, str]:
    """Extract org_id and system_id from RH Identity request state.

    When RH Identity authentication is configured, the auth dependency stores
    the RHIdentityData object in request.state.rh_identity_data. This function
    extracts the org_id and system_id for telemetry purposes.

    Args:
        request: The FastAPI request object.

    Returns:
        Tuple of (org_id, system_id). Returns ("auth_disabled", "auth_disabled")
        when RH Identity auth is not configured or data is unavailable.
    """
    rh_identity: Optional[RHIdentityData] = getattr(
        request.state, "rh_identity_data", None
    )
    if rh_identity is None:
        return AUTH_DISABLED, AUTH_DISABLED

    org_id = rh_identity.get_org_id() or AUTH_DISABLED
    system_id = rh_identity.get_user_id() or AUTH_DISABLED
    return org_id, system_id


infer_responses: dict[int | str, dict[str, Any]] = {
    200: RlsapiV1InferResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    413: PromptTooLongResponse.openapi_response(),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["generic"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


def _build_instructions(systeminfo: RlsapiV1SystemInfo) -> str:
    """Build LLM instructions by rendering the system prompt as a Jinja2 template.

    The base prompt is rendered with the context variables ``date``, ``os``,
    ``version``, and ``arch``.  Prompts without template markers pass through
    unchanged.  The compiled template is cached after the first call.

    Args:
        systeminfo: System information from the client (OS, version, arch).

    Returns:
        The rendered instructions string for the LLM.
    """
    date_today = datetime.now(tz=UTC).strftime("%B %d, %Y")

    return _get_prompt_template().render(
        date=date_today,
        os=systeminfo.os or "",
        version=systeminfo.version or "",
        arch=systeminfo.arch or "",
    )


@functools.lru_cache(maxsize=8)
def _compile_prompt_template(prompt: str) -> jinja2.Template:
    """Compile a Jinja2 template string inside a SandboxedEnvironment.

    Results are cached by prompt text so that a configuration reload with
    a new system prompt produces a fresh compiled template.

    Args:
        prompt: The raw template source string.

    Returns:
        The compiled Jinja2 Template.

    Raises:
        TemplateRenderError: If the template contains invalid Jinja2 syntax.
    """
    env = SandboxedEnvironment()
    try:
        return env.from_string(prompt)
    except jinja2.TemplateSyntaxError as exc:
        raise TemplateRenderError(
            f"System prompt contains invalid Jinja2 syntax: {exc}"
        ) from exc


def _get_prompt_template() -> jinja2.Template:
    """Resolve the system prompt from configuration and return the compiled template.

    Delegates to the cached ``_compile_prompt_template`` so that identical
    prompt text is compiled only once, while configuration changes are
    picked up automatically.

    Returns:
        The compiled Jinja2 Template ready for rendering.
    """
    prompt = (
        configuration.customization.system_prompt
        if configuration.customization is not None
        and configuration.customization.system_prompt is not None
        else constants.DEFAULT_SYSTEM_PROMPT
    )
    return _compile_prompt_template(prompt)


async def _get_default_model_id() -> str:
    """Get the default model ID from configuration or auto-discovery.

    Model selection precedence:
    1. If default model and provider are configured, use them.
    2. Otherwise, query Llama Stack for available LLM models and select the first one.

    Returns:
        The model identifier string in "provider/model" format.

    Raises:
        HTTPException: If no model can be determined from configuration or discovery.
    """
    # 1. Try configured defaults
    if configuration.inference is not None:
        model_id = configuration.inference.default_model
        provider_id = configuration.inference.default_provider

        if model_id and provider_id:
            return f"{provider_id}/{model_id}"

    # 2. Auto-discover from Llama Stack
    client = AsyncLlamaStackClientHolder().get_client()
    try:
        models = await client.models.list()
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e

    llm_models = [
        m
        for m in models
        if m.custom_metadata and m.custom_metadata.get("model_type") == "llm"
    ]
    if not llm_models:
        msg = "No LLM model found in available models"
        logger.error(msg)
        error_response = ServiceUnavailableResponse(
            backend_name="inference service",
            cause=msg,
        )
        raise HTTPException(**error_response.model_dump())

    model = llm_models[0]
    logger.info("Auto-discovered LLM model for rlsapi v1: %s", model.id)
    return model.id


async def retrieve_simple_response(
    question: str,
    instructions: str,
    tools: Optional[list[Any]] = None,
    model_id: Optional[str] = None,
) -> str:
    """Retrieve a simple response from the LLM for a stateless query.

    Uses the Responses API for simple stateless inference, consistent with
    other endpoints (query, streaming_query).

    Args:
        question: The combined user input (question + context).
        instructions: System instructions for the LLM.
        tools: Optional list of MCP tool definitions for the LLM.
        model_id: Fully qualified model identifier in provider/model format.
            When omitted, the configured default model is used.

    Returns:
        The LLM-generated response text.

    Raises:
        APIConnectionError: If the Llama Stack service is unreachable.
        HTTPException: 503 if no default model is configured.
    """
    client = AsyncLlamaStackClientHolder().get_client()
    resolved_model_id = model_id or await _get_default_model_id()
    logger.debug("Using model %s for rlsapi v1 inference", resolved_model_id)

    response = await client.responses.create(
        input=question,
        model=resolved_model_id,
        instructions=instructions,
        tools=tools or [],
        stream=False,
        store=False,
    )
    response = cast(OpenAIResponseObject, response)
    extract_token_usage(response.usage, resolved_model_id)

    return extract_text_from_response_items(response.output)


def _get_cla_version(request: Request) -> str:
    """Extract CLA version from User-Agent header."""
    return request.headers.get("User-Agent", "")


def _get_configured_default_model_name() -> str:
    """Get configured default model name for telemetry payloads."""
    if configuration.inference is None:
        return ""
    return configuration.inference.default_model or ""


def _queue_splunk_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    background_tasks: BackgroundTasks,
    infer_request: RlsapiV1InferRequest,
    request: Request,
    request_id: str,
    response_text: str,
    inference_time: float,
    sourcetype: str,
) -> None:
    """Build and queue a Splunk telemetry event for background sending."""
    org_id, system_id = _get_rh_identity_context(request)
    systeminfo = infer_request.context.systeminfo

    event_data = InferenceEventData(
        question=infer_request.question,
        response=response_text,
        inference_time=inference_time,
        model=_get_configured_default_model_name(),
        org_id=org_id,
        system_id=system_id,
        request_id=request_id,
        cla_version=_get_cla_version(request),
        system_os=systeminfo.os,
        system_version=systeminfo.version,
        system_arch=systeminfo.arch,
    )

    event = build_inference_event(event_data)
    background_tasks.add_task(send_splunk_event, event, sourcetype)


def _record_inference_failure(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    background_tasks: BackgroundTasks,
    infer_request: RlsapiV1InferRequest,
    request: Request,
    request_id: str,
    error: Exception,
    start_time: float,
    model: str,
    provider: str,
) -> float:
    """Record metrics and queue Splunk event for an inference failure.

    Args:
        background_tasks: FastAPI background tasks for async event sending.
        infer_request: The original inference request.
        request: The FastAPI request object.
        request_id: Unique identifier for the request.
        error: The exception that caused the failure.
        start_time: Monotonic clock time when inference started.

    Returns:
        The total inference time in seconds.
    """
    inference_time = time.monotonic() - start_time
    metrics.llm_calls_failures_total.labels(provider, model).inc()
    _queue_splunk_event(
        background_tasks,
        infer_request,
        request,
        request_id,
        str(error),
        inference_time,
        "infer_error",
    )
    return inference_time


def _map_inference_error_to_http_exception(  # pylint: disable=too-many-return-statements
    error: Exception, model_id: str, request_id: str
) -> Optional[HTTPException]:
    """Map known inference errors to HTTPException.

    Returns None for RuntimeError values that are not context-length related,
    so callers can preserve existing re-raise behavior for unknown runtime
    errors.
    """
    if isinstance(error, TemplateRenderError):
        logger.error(
            "Invalid system prompt template for request %s: %s", request_id, error
        )
        error_response = InternalServerErrorResponse.generic()
        return HTTPException(**error_response.model_dump())

    if isinstance(error, RuntimeError):
        error_message = str(error).lower()
        if "context_length" in error_message or "context length" in error_message:
            logger.error("Prompt too long for request %s: %s", request_id, error)
            error_response = PromptTooLongResponse(model=model_id)
            return HTTPException(**error_response.model_dump())
        logger.error("Unexpected RuntimeError for request %s: %s", request_id, error)
        return None

    if isinstance(error, APIConnectionError):
        logger.error(
            "Unable to connect to Llama Stack for request %s: %s", request_id, error
        )
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause="Unable to connect to the inference backend",
        )
        return HTTPException(**error_response.model_dump())

    if isinstance(error, RateLimitError):
        logger.error("Rate limit exceeded for request %s: %s", request_id, error)
        error_response = QuotaExceededResponse(
            response="The quota has been exceeded",
            cause="Rate limit exceeded, please try again later",
        )
        return HTTPException(**error_response.model_dump())

    if isinstance(error, (APIStatusError, OpenAIAPIStatusError)):
        logger.exception("API error for request %s: %s", request_id, error)
        error_response = handle_known_apistatus_errors(error, model_id)
        return HTTPException(**error_response.model_dump())

    return None


@router.post("/infer", responses=infer_responses, response_model_exclude_none=True)
@authorize(Action.RLSAPI_V1_INFER)
async def infer_endpoint(  # pylint: disable=R0914
    infer_request: RlsapiV1InferRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> RlsapiV1InferResponse:
    """Handle rlsapi v1 /infer requests for stateless inference.

    This endpoint serves requests from the RHEL Lightspeed Command Line Assistant (CLA).

    Accepts a question with optional context (stdin, attachments, terminal output,
    system info) and returns an LLM-generated response.

    Args:
        infer_request: The inference request containing question and context.
        request: The FastAPI request object for accessing headers and state.
        background_tasks: FastAPI background tasks for async Splunk event sending.
        auth: Authentication tuple from the configured auth provider.

    Returns:
        RlsapiV1InferResponse containing the generated response text and request ID.

    Raises:
        HTTPException: 503 if the LLM service is unavailable.
    """
    # Authentication enforced by get_auth_dependency(), authorization by @authorize decorator.
    _ = auth

    request_id = get_suid()

    logger.info("Processing rlsapi v1 /infer request %s", request_id)

    input_source = infer_request.get_input_source()
    model_id = await _get_default_model_id()
    provider, model = extract_provider_and_model_from_model_id(model_id)
    mcp_tools: list[Any] = await get_mcp_tools(request_headers=request.headers)
    logger.debug(
        "Request %s: Combined input source length: %d", request_id, len(input_source)
    )

    start_time = time.monotonic()

    # Check if verbose metadata should be returned
    verbose_enabled = (
        configuration.customization is not None
        and configuration.customization.allow_verbose_infer
        and infer_request.include_metadata
    )

    try:
        instructions = _build_instructions(infer_request.context.systeminfo)

        # For verbose mode, retrieve the full response object instead of just text
        if verbose_enabled:
            client = AsyncLlamaStackClientHolder().get_client()
            response = await client.responses.create(
                input=input_source,
                model=model_id,
                instructions=instructions,
                tools=mcp_tools or [],
                stream=False,
                store=False,
            )
            response = cast(OpenAIResponseObject, response)
            response_text = extract_text_from_response_items(response.output)
        else:
            response = None
            response_text = await retrieve_simple_response(
                input_source,
                instructions,
                tools=cast(list[Any], mcp_tools),
                model_id=model_id,
            )
        inference_time = time.monotonic() - start_time
    except _INFER_HANDLED_EXCEPTIONS as error:
        _record_inference_failure(
            background_tasks,
            infer_request,
            request,
            request_id,
            error,
            start_time,
            model,
            provider,
        )
        mapped_error = _map_inference_error_to_http_exception(
            error,
            model_id,
            request_id,
        )
        if mapped_error is not None:
            raise mapped_error from error
        raise

    if not response_text:
        logger.warning("Empty response from LLM for request %s", request_id)
        response_text = constants.UNABLE_TO_PROCESS_RESPONSE

    _queue_splunk_event(
        background_tasks,
        infer_request,
        request,
        request_id,
        response_text,
        inference_time,
        "infer_with_llm",
    )

    logger.info("Completed rlsapi v1 /infer request %s", request_id)

    # Build response with optional extended metadata
    if verbose_enabled and response is not None:
        # Extract metadata from full response object
        turn_summary = build_turn_summary(
            response, model_id, vector_store_ids=None, rag_id_mapping=None
        )

        return RlsapiV1InferResponse(
            data=RlsapiV1InferData(
                text=response_text,
                request_id=request_id,
                tool_calls=turn_summary.tool_calls,
                tool_results=turn_summary.tool_results,
                rag_chunks=turn_summary.rag_chunks,
                referenced_documents=turn_summary.referenced_documents,
                input_tokens=turn_summary.token_usage.input_tokens,
                output_tokens=turn_summary.token_usage.output_tokens,
            )
        )

    # Standard minimal response
    return RlsapiV1InferResponse(
        data=RlsapiV1InferData(
            text=response_text,
            request_id=request_id,
            tool_calls=None,
            tool_results=None,
            rag_chunks=None,
            referenced_documents=None,
            input_tokens=None,
            output_tokens=None,
        )
    )
