"""Handler for REST API call to authorized endpoint."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from opentelemetry import trace

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from log import get_logger
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import AuthorizedResponse
from utils.otel_tracing import SpanAttributes, anonymize_value, set_span_attributes

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(tags=["authorized"])

authorized_responses: dict[int | str, dict[str, Any]] = {
    200: AuthorizedResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}


@router.post("/authorized", responses=authorized_responses)
async def authorized_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> AuthorizedResponse:
    """
    Handle request to the /authorized endpoint.

    Process POST requests to the /authorized endpoint, returning
    the authenticated user's ID and username.

    The response intentionally omits any authentication token.

    ### Parameters:
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Returns:
    - AuthorizedResponse: Contains the user ID and username of the authenticated user.
    """
    with tracer.start_as_current_span("authorized.handle_request") as span:
        # Ignore the user token, we should not return it in the response
        user_id, user_name, skip_userid_check, _ = auth
        set_span_attributes(span, {SpanAttributes.USER_ID: anonymize_value(user_id)})
        return AuthorizedResponse(
            user_id=user_id, username=user_name, skip_userid_check=skip_userid_check
        )
