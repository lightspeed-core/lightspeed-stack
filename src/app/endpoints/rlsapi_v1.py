"""Handler for RHEL Lightspeed rlsapi v1 REST API endpoints.

This module provides the /infer endpoint for stateless inference requests
from the RHEL Lightspeed Command Line Assistant (CLA).
"""

import functools
import time
from datetime import UTC, datetime
from typing import Annotated, Any, Optional, cast

import jinja2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from jinja2.sandbox import SandboxedEnvironment
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import APIConnectionError, APIStatusError, RateLimitError
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

import constants
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import ENDPOINT_PATH_INFER
from log import get_logger
from metrics import recording
from models.api.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.config import Action
from models.rlsapi.requests import RlsapiV1InferRequest, RlsapiV1SystemInfo
from models.rlsapi.responses import RlsapiV1InferData, RlsapiV1InferResponse
from observability import InferenceEventData, build_inference_event, send_splunk_event
from utils.endpoints import check_configuration_loaded
from utils.query import (
    consume_query_tokens,
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_context_length_error,
)
from utils.quota import check_tokens_available
from utils.responses import (
    build_turn_summary,
    check_model_configured,
    extract_text_from_response_items,
    extract_token_usage,
    get_mcp_tools,
)
from utils.rh_identity import AUTH_DISABLED, get_rh_identity_context
from utils.shields import run_shield_moderation
from utils.suid import get_suid

logger = get_logger(__name__)
router = APIRouter(tags=["rlsapi-v1"])


class TemplateRenderError(Exception):
    """Raised when the system prompt Jinja2 template cannot be compiled."""


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


infer_responses: dict[int | str, dict[str, Any]] = {
    200: RlsapiV1InferResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["model"]),
    413: PromptTooLongResponse.openapi_response(examples=["context window exceeded"]),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
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


async def _resolve_validated_model_id() -> str:
    """Resolve and validate the default model against Llama Stack.

    Combines model resolution with existence validation so callers get
    either a known-good model ID or a clear 404 error.

    Returns:
        The validated model identifier string in "provider/model" format.

    Raises:
        HTTPException: 404 if the resolved model does not exist in Llama Stack.
        HTTPException: 503 if Llama Stack is unreachable during resolution or validation.
    """
    model_id = await _get_default_model_id()
    client = AsyncLlamaStackClientHolder().get_client()
    if not await check_model_configured(client, model_id):
        _, model_name = extract_provider_and_model_from_model_id(model_id)
        error_response = NotFoundResponse(resource="model", resource_id=model_name)
        raise HTTPException(**error_response.model_dump())
    return model_id


async def retrieve_simple_response(
    question: str,
    instructions: str,
    tools: Optional[list[Any]] = None,
    model_id: Optional[str] = None,
    endpoint_path: str = ENDPOINT_PATH_INFER,
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
    resolved_model_id = model_id or await _get_default_model_id()
    response = await _call_llm(question, instructions, tools, resolved_model_id)
    extract_token_usage(response.usage, resolved_model_id, endpoint_path)
    return extract_text_from_response_items(response.output)


async def _call_llm(
    question: str,
    instructions: str,
    tools: Optional[list[Any]] = None,
    model_id: Optional[str] = None,
) -> OpenAIResponseObject:
    """Call the LLM via the Responses API and return the full response object.

    This is a transport-only function: it calls the LLM and returns the raw
    response. Callers are responsible for token usage extraction and metrics.

    Args:
        question: The combined user input (question + context).
        instructions: System instructions for the LLM.
        tools: Optional list of MCP tool definitions for the LLM.
        model_id: Fully qualified model identifier in provider/model format.
            When omitted, the configured default model is used.

    Returns:
        The full OpenAIResponseObject from the LLM.

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
    return cast(OpenAIResponseObject, response)


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
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Build and queue a Splunk telemetry event for background sending.

    Args:
        background_tasks: FastAPI background task manager.
        infer_request: Original rlsapi v1 inference request.
        request: FastAPI request object used to resolve identity context.
        request_id: Unique identifier for the request.
        response_text: Response text to include in the telemetry event.
        inference_time: Request processing duration in seconds.
        sourcetype: Splunk sourcetype to use when sending the event.
        input_tokens: Number of prompt tokens consumed by the LLM call.
        output_tokens: Number of completion tokens produced by the LLM call.
    """
    org_id, system_id = get_rh_identity_context(request)
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
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    event = build_inference_event(event_data)
    background_tasks.add_task(send_splunk_event, event, sourcetype)


async def _check_shield_moderation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    input_text: str,
    request_id: str,
    background_tasks: BackgroundTasks,
    infer_request: RlsapiV1InferRequest,
    request: Request,
    endpoint_path: str,
) -> Optional[RlsapiV1InferResponse]:
    """Run shield moderation and return a refusal response if blocked.

    Uses all configured shields in Llama Stack. When no shields are
    registered, moderation is a no-op and returns None immediately.

    Args:
        input_text: The combined user input to moderate.
        request_id: Unique identifier for the request.
        background_tasks: FastAPI background tasks for async Splunk event sending.
        infer_request: The original inference request (for Splunk event context).
        request: The FastAPI request object (for Splunk event context).
        endpoint_path: The API endpoint path for metric labeling.

    Returns:
        An RlsapiV1InferResponse containing the refusal message if the input
        was blocked, or None if moderation passed.
    """
    client = AsyncLlamaStackClientHolder().get_client()
    moderation_result = await run_shield_moderation(client, input_text, endpoint_path)

    if moderation_result.decision != "blocked":
        return None

    logger.info(
        "Request %s blocked by shield moderation: %s",
        request_id,
        moderation_result.message,
    )
    _queue_splunk_event(
        background_tasks,
        infer_request,
        request,
        request_id,
        moderation_result.message,
        0.0,
        "infer_shield_blocked",
    )
    return RlsapiV1InferResponse(
        data=RlsapiV1InferData(
            text=moderation_result.message,
            request_id=request_id,
            tool_calls=None,
            tool_results=None,
            rag_chunks=None,
            referenced_documents=None,
            input_tokens=None,
            output_tokens=None,
        )
    )


def _record_inference_failure(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    background_tasks: BackgroundTasks,
    infer_request: RlsapiV1InferRequest,
    request: Request,
    request_id: str,
    error: Exception,
    start_time: float,
    model: str,
    provider: str,
    endpoint_path: str,
) -> float:
    """Record metrics and queue Splunk event for an inference failure.

    Args:
        background_tasks: FastAPI background tasks for async event sending.
        infer_request: The original inference request.
        request: The FastAPI request object.
        request_id: Unique identifier for the request.
        error: The exception that caused the failure.
        start_time: Monotonic clock time when inference started.
        model: The model name.
        provider: The provider name.
        endpoint_path: The API endpoint path for metric labeling.

    Returns:
        The total inference time in seconds.
    """
    inference_time = time.monotonic() - start_time
    recording.record_llm_failure(provider, model, endpoint_path)
    recording.record_llm_inference_duration(
        provider, model, endpoint_path, "failure", inference_time
    )
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


def _is_verbose_enabled(infer_request: RlsapiV1InferRequest) -> bool:
    """Check whether verbose metadata should be included in the response.

    Verbose mode requires dual opt-in: the server configuration must allow it
    via ``allow_verbose_infer``, and the client must request it via the
    ``include_metadata`` field.

    Args:
        infer_request: The inference request to check.

    Returns:
        True if both server config and client request enable verbose mode.
    """
    return (
        configuration.rlsapi_v1.allow_verbose_infer and infer_request.include_metadata
    )


def _resolve_quota_subject(request: Request, auth: AuthTuple) -> Optional[str]:
    """Resolve the quota subject identifier based on rlsapi_v1 configuration.

    Returns None when quota enforcement is disabled (quota_subject not set),
    signaling the caller to skip quota checks entirely.

    When the configured subject source (org_id or system_id) is unavailable
    (e.g., rh-identity auth is not active), falls back to user_id from the
    auth tuple so quota enforcement still applies.

    Args:
        request: The FastAPI request object (for accessing rh-identity state).
        auth: Authentication tuple from the configured auth provider.

    Returns:
        The resolved subject identifier string, or None if quota is disabled.
    """
    quota_subject = configuration.rlsapi_v1.quota_subject
    if quota_subject is None:
        return None

    user_id = auth[0]

    if quota_subject == "user_id":
        return user_id

    org_id, system_id = get_rh_identity_context(request)

    if quota_subject == "org_id":
        if org_id == AUTH_DISABLED:
            logger.warning(
                "quota_subject is 'org_id' but rh-identity data is unavailable, "
                "falling back to user_id"
            )
            return user_id
        return org_id

    # quota_subject == "system_id"
    if system_id == AUTH_DISABLED:
        logger.warning(
            "quota_subject is 'system_id' but rh-identity data is unavailable, "
            "falling back to user_id"
        )
        return user_id
    return system_id


def _check_infer_quota(
    request: Request, auth: AuthTuple, endpoint_path: str
) -> Optional[str]:
    """Check infer quota availability and record bounded quota metrics."""
    quota_id = _resolve_quota_subject(request, auth)
    quota_type = configuration.rlsapi_v1.quota_subject or "disabled"
    if quota_id is None:
        recording.record_quota_check(
            endpoint_path, quota_type, recording.QUOTA_RESULT_SKIPPED, 0.0
        )
        return None

    quota_start_time = time.monotonic()
    try:
        check_tokens_available(configuration.quota_limiters, quota_id)
    except HTTPException:
        recording.record_quota_check(
            endpoint_path,
            quota_type,
            recording.QUOTA_RESULT_FAILURE,
            time.monotonic() - quota_start_time,
        )
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        recording.record_quota_check(
            endpoint_path,
            quota_type,
            recording.QUOTA_RESULT_ERROR,
            time.monotonic() - quota_start_time,
        )
        raise
    recording.record_quota_check(
        endpoint_path,
        quota_type,
        recording.QUOTA_RESULT_SUCCESS,
        time.monotonic() - quota_start_time,
    )
    return quota_id


def _build_infer_response(
    response_text: str,
    request_id: str,
    response: Optional[OpenAIResponseObject],
    model_id: str,
    endpoint_path: str,
) -> RlsapiV1InferResponse:
    """Build the final inference response, with optional verbose metadata.

    When ``response`` is provided, verbose metadata (tool calls, RAG chunks,
    token counts) is extracted via ``build_turn_summary`` and included.
    When ``response`` is None, a minimal response with only text is returned.

    Args:
        response_text: The LLM-generated response text.
        request_id: Unique identifier for the request.
        response: The full LLM response object. Pass None for non-verbose
            responses; pass the object to include extended metadata.
        model_id: The model identifier used for inference.

    Returns:
        The assembled RlsapiV1InferResponse.
    """
    if response is not None:
        turn_summary = build_turn_summary(
            response,
            model_id,
            endpoint_path,
            vector_store_ids=None,
            rag_id_mapping=None,
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
        if is_context_length_error(str(error)):
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
    check_configuration_loaded(configuration)
    endpoint_path = ENDPOINT_PATH_INFER

    # Quota enforcement: resolve subject and check availability before any work.
    # No-op when quota_subject is not configured or no quota limiters exist.
    quota_id = _check_infer_quota(request, auth, endpoint_path)

    request_id = get_suid()

    logger.info("Processing rlsapi v1 /infer request %s", request_id)

    input_source = infer_request.get_input_source()
    logger.debug(
        "Request %s: Combined input source length: %d", request_id, len(input_source)
    )

    # Run shield moderation on user input before inference.
    # Uses all configured shields; no-op when no shields are registered.
    # Runs before model/tool discovery so blocked requests short-circuit
    # without incurring external I/O.
    blocked_response = await _check_shield_moderation(
        input_source,
        request_id,
        background_tasks,
        infer_request,
        request,
        endpoint_path,
    )
    if blocked_response is not None:
        return blocked_response

    model_id = await _resolve_validated_model_id()
    provider, model = extract_provider_and_model_from_model_id(model_id)
    mcp_tools: list[Any] = await get_mcp_tools(request_headers=request.headers)

    start_time = time.monotonic()
    verbose_enabled = _is_verbose_enabled(infer_request)

    response = None
    try:
        instructions = _build_instructions(infer_request.context.systeminfo)
        response = await _call_llm(
            input_source,
            instructions,
            tools=cast(list[Any], mcp_tools),
            model_id=model_id,
        )
        response_text = extract_text_from_response_items(response.output)
        token_usage = extract_token_usage(response.usage, model_id, endpoint_path)
        inference_time = time.monotonic() - start_time
        recording.record_llm_inference_duration(
            provider, model, endpoint_path, "success", inference_time
        )
    except _INFER_HANDLED_EXCEPTIONS as error:
        if response is not None:
            extract_token_usage(response.usage, model_id, endpoint_path)  # type: ignore[arg-type]
        _record_inference_failure(
            background_tasks,
            infer_request,
            request,
            request_id,
            error,
            start_time,
            model,
            provider,
            endpoint_path,
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

    # Consume quota tokens after successful inference.
    if quota_id is not None:
        consume_query_tokens(
            user_id=quota_id,
            model_id=model_id,
            token_usage=token_usage,
        )

    _queue_splunk_event(
        background_tasks,
        infer_request,
        request,
        request_id,
        response_text,
        inference_time,
        "infer_with_llm",
        input_tokens=token_usage.input_tokens,
        output_tokens=token_usage.output_tokens,
    )

    logger.info("Completed rlsapi v1 /infer request %s", request_id)

    return _build_infer_response(
        response_text,
        request_id,
        response if verbose_enabled else None,
        model_id,
        endpoint_path,
    )
