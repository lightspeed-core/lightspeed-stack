"""Endpoint for interrupting in-progress streaming query requests."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from models.config import Action
from models.requests import StreamingInterruptRequest
from models.responses import (
    ForbiddenResponse,
    NotFoundResponse,
    StreamingInterruptResponse,
    UnauthorizedResponse,
)
from utils.stream_interrupts import (
    CancelStreamResult,
    StreamInterruptRegistry,
    get_stream_interrupt_registry,
)

router = APIRouter(tags=["streaming_query_interrupt"])

stream_interrupt_responses: dict[int | str, dict[str, Any]] = {
    200: StreamingInterruptResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["streaming request"]),
}


@router.post(
    "/streaming_query/interrupt",
    responses=stream_interrupt_responses,
    summary="Streaming Query Interrupt Endpoint Handler",
)
@authorize(Action.STREAMING_QUERY)
async def stream_interrupt_endpoint_handler(
    interrupt_request: StreamingInterruptRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    registry: Annotated[
        StreamInterruptRegistry, Depends(get_stream_interrupt_registry)
    ],
) -> StreamingInterruptResponse:
    """Interrupt an in-progress streaming query by request identifier.

    Parameters:
        interrupt_request: Request payload containing the stream request ID.
        auth: Auth context tuple resolved from the authentication dependency.
        registry: Stream interrupt registry dependency used to cancel streams.

    Returns:
        StreamingInterruptResponse: Confirmation payload when interruption succeeds.

    Raises:
        HTTPException: If no active stream for the given request ID can be interrupted.
    """
    user_id, _, _, _ = auth
    request_id = interrupt_request.request_id
    cancel_result = registry.cancel_stream(request_id, user_id)
    if cancel_result == CancelStreamResult.NOT_FOUND:
        response = NotFoundResponse(
            resource="streaming request",
            resource_id=request_id,
        )
        raise HTTPException(**response.model_dump())
    if cancel_result == CancelStreamResult.FORBIDDEN:
        response = ForbiddenResponse(
            response="User does not have permission to interrupt this streaming request",
            cause=(
                f"User {user_id} does not own streaming request "
                f"with ID {request_id}"
            ),
        )
        raise HTTPException(**response.model_dump())
    if cancel_result == CancelStreamResult.ALREADY_DONE:
        return StreamingInterruptResponse(
            request_id=request_id,
            interrupted=False,
            message="Streaming request already completed; nothing to interrupt",
        )

    return StreamingInterruptResponse(
        request_id=request_id,
        interrupted=True,
        message="Streaming request interrupted",
    )
