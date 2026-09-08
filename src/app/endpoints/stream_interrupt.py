"""Endpoint for interrupting in-progress streaming query requests."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from models.api.requests import StreamingInterruptRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import StreamingInterruptResponse
from models.config import Action
from utils.otel_tracing import SpanAttributes
from utils.stream_interrupts import (
    CancelStreamResult,
    StreamInterruptRegistry,
    get_stream_interrupt_registry,
)

router = APIRouter(tags=["streaming_query_interrupt"])
tracer = trace.get_tracer(__name__)

stream_interrupt_responses: dict[int | str, dict[str, Any]] = {
    200: StreamingInterruptResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["streaming request"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
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

    ### Parameters:
    - interrupt_request: Request payload containing the stream request ID.
    - auth: Auth context tuple resolved from the authentication dependency.
    - registry: Stream interrupt registry dependency used to cancel streams.

    ### Returns:
    - StreamingInterruptResponse: Confirmation payload when interruption succeeds.

    ### Raises:
    - HTTPException: If no active stream for the given request ID can be interrupted.
    """
    user_id, _, _, _ = auth
    request_id = interrupt_request.request_id

    with tracer.start_as_current_span("stream.interrupt") as span:
        span.set_attribute(SpanAttributes.INTERRUPT_REQUEST_ID, request_id)

        # Surface the conversation id when the caller owns the stream. The
        # conversation id is looked up before cancellation so it is available
        # for the span regardless of the cancel outcome. It is only recorded
        # for streams owned by the requesting user to avoid exposing another
        # user's conversation identifier.
        existing_stream = registry.get_stream(request_id)
        if (
            existing_stream is not None
            and existing_stream.user_id == user_id
            and existing_stream.conversation_id
        ):
            span.set_attribute(
                SpanAttributes.STREAM_CONVERSATION_ID,
                existing_stream.conversation_id,
            )

        cancel_result = registry.cancel_stream(request_id, user_id)
        span.set_attribute(SpanAttributes.INTERRUPT_RESULT, cancel_result.value)

        if cancel_result == CancelStreamResult.NOT_FOUND:
            span.set_status(Status(StatusCode.ERROR, "streaming request not found"))
            response = NotFoundResponse(
                resource="streaming request",
                resource_id=request_id,
            )
            raise HTTPException(**response.model_dump())
        if cancel_result == CancelStreamResult.FORBIDDEN:
            span.set_status(
                Status(StatusCode.ERROR, "caller does not own streaming request")
            )
            response = ForbiddenResponse(
                response=(
                    "User does not have permission to interrupt this "
                    "streaming request"
                ),
                cause=(
                    f"User {user_id} does not own streaming request "
                    f"with ID {request_id}"
                ),
            )
            raise HTTPException(**response.model_dump())
        if cancel_result == CancelStreamResult.ALREADY_DONE:
            span.set_status(Status(StatusCode.OK))
            return StreamingInterruptResponse(
                request_id=request_id,
                interrupted=False,
                message="Streaming request already completed; nothing to interrupt",
            )

        span.set_status(Status(StatusCode.OK))
        return StreamingInterruptResponse(
            request_id=request_id,
            interrupted=True,
            message="Streaming request interrupted",
        )
