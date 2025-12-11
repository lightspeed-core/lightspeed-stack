"""Handler for RHEL Lightspeed rlsapi v1 REST API endpoints.

This module provides the /infer endpoint for stateless inference requests
from the RHEL Lightspeed Command Line Assistant (CLA).
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from models.config import Action
from models.responses import (
    ForbiddenResponse,
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
}


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
    """
    # Authentication enforced by get_auth_dependency(), authorization by @authorize decorator.
    _ = auth

    # Generate unique request ID
    request_id = get_suid()

    logger.info("Processing rlsapi v1 /infer request %s", request_id)

    # Combine all input sources (question, stdin, attachments, terminal)
    input_source = infer_request.get_input_source()
    logger.debug("Combined input source length: %d", len(input_source))

    # NOTE(major): Placeholder until we wire up the LLM integration.
    response_text = (
        "Inference endpoint is functional. "
        "LLM integration will be added in a subsequent update."
    )

    return RlsapiV1InferResponse(
        data=RlsapiV1InferData(
            text=response_text,
            request_id=request_id,
        )
    )
