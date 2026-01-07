"""Handler for RHEL Lightspeed rlsapi v1 REST API endpoints.

This module provides the /infer endpoint for stateless inference requests
from the RHEL Lightspeed Command Line Assistant (CLA).
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from llama_stack_client import APIConnectionError  # type: ignore
from llama_stack_client.types.chat.completion_create_params import (
    MessageOpenAISystemMessageParam,
    MessageOpenAIUserMessageParam,
)

import constants
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.rlsapi.requests import RlsapiV1InferRequest
from models.rlsapi.responses import RlsapiV1InferData, RlsapiV1InferResponse
from utils.suid import get_suid

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rlsapi-v1"])


infer_responses: dict[int | str, dict[str, Any]] = {
    200: RlsapiV1InferResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    422: UnprocessableEntityResponse.openapi_response(),
    503: ServiceUnavailableResponse.openapi_response(),
}


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


async def retrieve_simple_response(question: str) -> str:
    """Retrieve a simple response from the LLM for a stateless query.

    Uses direct chat completion API for simple stateless inference.

    Args:
        question: The combined user input (question + context).

    Returns:
        The LLM-generated response text.

    Raises:
        APIConnectionError: If the Llama Stack service is unreachable.
        HTTPException: 503 if no model is configured.
    """
    client = AsyncLlamaStackClientHolder().get_client()
    model_id = _get_default_model_id()

    logger.debug("Using model %s for rlsapi v1 inference", model_id)

    sys_msg: MessageOpenAISystemMessageParam = {
        "role": "system",
        "content": constants.DEFAULT_SYSTEM_PROMPT,
    }
    user_msg: MessageOpenAIUserMessageParam = {
        "role": "user",
        "content": question,
    }

    response = await client.chat.completions.create(
        model=model_id,
        messages=[sys_msg, user_msg],
    )

    if not response.choices:
        return ""

    choice = response.choices[0]
    message = getattr(choice, "message", None)
    if message is None:
        return ""

    content = getattr(message, "content", None)
    if content is None:
        return ""

    return str(content)


@router.post("/infer", responses=infer_responses)
@authorize(Action.RLSAPI_V1_INFER)
async def infer_endpoint(
    infer_request: RlsapiV1InferRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> RlsapiV1InferResponse:
    """Handle rlsapi v1 /infer requests for stateless inference.

    This endpoint serves requests from the RHEL Lightspeed Command Line Assistant (CLA).

    Accepts a question with optional context (stdin, attachments, terminal output,
    system info) and returns an LLM-generated response.

    Args:
        infer_request: The inference request containing question and context.
        auth: Authentication tuple from the configured auth provider.

    Returns:
        RlsapiV1InferResponse containing the generated response text and request ID.

    Raises:
        HTTPException: 503 if the LLM service is unavailable.
    """
    # Authentication enforced by get_auth_dependency(), authorization by @authorize decorator.
    _ = auth

    # Generate unique request ID
    request_id = get_suid()

    logger.info("Processing rlsapi v1 /infer request %s", request_id)

    # Combine all input sources (question, stdin, attachments, terminal)
    input_source = infer_request.get_input_source()
    logger.debug(
        "Request %s: Combined input source length: %d", request_id, len(input_source)
    )

    try:
        response_text = await retrieve_simple_response(input_source)
    except APIConnectionError as e:
        logger.error(
            "Unable to connect to Llama Stack for request %s: %s", request_id, e
        )
        response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e

    if not response_text:
        logger.warning("Empty response from LLM for request %s", request_id)
        response_text = constants.UNABLE_TO_PROCESS_RESPONSE

    logger.info("Completed rlsapi v1 /infer request %s", request_id)

    return RlsapiV1InferResponse(
        data=RlsapiV1InferData(
            text=response_text,
            request_id=request_id,
        )
    )
