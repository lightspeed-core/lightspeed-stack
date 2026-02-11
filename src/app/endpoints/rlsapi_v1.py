"""Handler for RHEL Lightspeed rlsapi v1 REST API endpoints.

This module provides the /infer endpoint for stateless inference requests
from the RHEL Lightspeed Command Line Assistant (CLA).
"""

import logging
import time
from typing import Annotated, Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import APIConnectionError, APIStatusError, RateLimitError

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
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.rlsapi.requests import RlsapiV1InferRequest, RlsapiV1SystemInfo
from models.rlsapi.responses import RlsapiV1InferData, RlsapiV1InferResponse
from observability import InferenceEventData, build_inference_event, send_splunk_event
from utils.responses import extract_text_from_response_output_item, get_mcp_tools
from utils.suid import get_suid

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rlsapi-v1"])

# Default values when RH Identity auth is not configured
AUTH_DISABLED = "auth_disabled"


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
    rh_identity: RHIdentityData | None = getattr(
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
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["generic"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


def _build_instructions(systeminfo: RlsapiV1SystemInfo) -> str:
    """Build LLM instructions incorporating system context when available.

    Enhances the default system prompt with RHEL system information to provide
    the LLM with relevant context about the user's environment.

    Args:
        systeminfo: System information from the client (OS, version, arch).

    Returns:
        Instructions string for the LLM, with system context if available.
    """
    if (
        configuration.customization is not None
        and configuration.customization.system_prompt is not None
    ):
        base_prompt = configuration.customization.system_prompt
    else:
        base_prompt = constants.DEFAULT_SYSTEM_PROMPT

    context_parts = []
    if systeminfo.os:
        context_parts.append(f"OS: {systeminfo.os}")
    if systeminfo.version:
        context_parts.append(f"Version: {systeminfo.version}")
    if systeminfo.arch:
        context_parts.append(f"Architecture: {systeminfo.arch}")

    if not context_parts:
        return base_prompt

    system_context = ", ".join(context_parts)
    return f"{base_prompt}\n\nUser's system: {system_context}"


def _get_default_model_id() -> str:
    """Get the default model ID from configuration.

    Returns the model identifier in Llama Stack format (provider/model).

    Returns:
        The model identifier string.

    Raises:
        HTTPException: If no model can be determined from configuration.
    """
    if configuration.inference is None:
        msg = "No inference configuration available"
        logger.error(msg)
        raise HTTPException(
            status_code=503,
            detail={"response": "Service configuration error", "cause": msg},
        )

    model_id = configuration.inference.default_model
    provider_id = configuration.inference.default_provider

    if model_id and provider_id:
        return f"{provider_id}/{model_id}"

    msg = "No default model configured for rlsapi v1 inference"
    logger.error(msg)
    raise HTTPException(
        status_code=503,
        detail={"response": "Service configuration error", "cause": msg},
    )


async def retrieve_simple_response(
    question: str, instructions: str, tools: list | None = None
) -> str:
    """Retrieve a simple response from the LLM for a stateless query.

    Uses the Responses API for simple stateless inference, consistent with
    other endpoints (query, streaming_query).

    Args:
        question: The combined user input (question + context).
        instructions: System instructions for the LLM.
        tools: Optional list of MCP tool definitions for the LLM.

    Returns:
        The LLM-generated response text.

    Raises:
        APIConnectionError: If the Llama Stack service is unreachable.
        HTTPException: 503 if no model is configured.
    """
    client = AsyncLlamaStackClientHolder().get_client()
    model_id = _get_default_model_id()

    logger.debug("Using model %s for rlsapi v1 inference", model_id)

    response = await client.responses.create(
        input=question,
        model=model_id,
        instructions=instructions,
        tools=tools or [],
        stream=False,
        store=False,
    )
    response = cast(OpenAIResponseObject, response)

    return "".join(
        extract_text_from_response_output_item(output_item)
        for output_item in response.output
    )


def _get_cla_version(request: Request) -> str:
    """Extract CLA version from User-Agent header."""
    return request.headers.get("User-Agent", "")


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
        model=(
            (configuration.inference.default_model or "")
            if configuration.inference
            else ""
        ),
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


@router.post("/infer", responses=infer_responses)
@authorize(Action.RLSAPI_V1_INFER)
async def infer_endpoint(
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
    instructions = _build_instructions(infer_request.context.systeminfo)
    mcp_tools = get_mcp_tools(configuration.mcp_servers)
    logger.debug(
        "Request %s: Combined input source length: %d", request_id, len(input_source)
    )

    start_time = time.monotonic()
    try:
        response_text = await retrieve_simple_response(
            input_source, instructions, tools=mcp_tools
        )
        inference_time = time.monotonic() - start_time
    except APIConnectionError as e:
        inference_time = time.monotonic() - start_time
        metrics.llm_calls_failures_total.inc()
        logger.error(
            "Unable to connect to Llama Stack for request %s: %s", request_id, e
        )
        _queue_splunk_event(
            background_tasks,
            infer_request,
            request,
            request_id,
            str(e),
            inference_time,
            "infer_error",
        )
        response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e
    except RateLimitError as e:
        inference_time = time.monotonic() - start_time
        metrics.llm_calls_failures_total.inc()
        logger.error("Rate limit exceeded for request %s: %s", request_id, e)
        _queue_splunk_event(
            background_tasks,
            infer_request,
            request,
            request_id,
            str(e),
            inference_time,
            "infer_error",
        )
        response = QuotaExceededResponse(
            response="The quota has been exceeded", cause=str(e)
        )
        raise HTTPException(**response.model_dump()) from e
    except APIStatusError as e:
        inference_time = time.monotonic() - start_time
        metrics.llm_calls_failures_total.inc()
        logger.exception("API error for request %s: %s", request_id, e)
        _queue_splunk_event(
            background_tasks,
            infer_request,
            request,
            request_id,
            str(e),
            inference_time,
            "infer_error",
        )
        response = InternalServerErrorResponse.generic()
        raise HTTPException(**response.model_dump()) from e

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

    return RlsapiV1InferResponse(
        data=RlsapiV1InferData(
            text=response_text,
            request_id=request_id,
        )
    )
