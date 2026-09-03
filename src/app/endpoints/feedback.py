"""Handler for REST API endpoint for user feedback."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from log import get_logger
from models.api.requests import FeedbackRequest, FeedbackStatusUpdateRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import (
    FeedbackResponse,
    FeedbackStatusUpdateResponse,
    StatusResponse,
)
from models.config import Action
from utils.endpoints import check_configuration_loaded, retrieve_conversation
from utils.otel_tracing import (
    SpanAttributes,
    SpanEvents,
    add_span_event,
    anonymize_value,
    set_span_attributes,
)
from utils.suid import get_suid

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])
feedback_status_lock = threading.Lock()


feedback_post_response: dict[int | str, dict[str, Any]] = {
    200: FeedbackResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "feedback"]),
    404: NotFoundResponse.openapi_response(examples=["conversation"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["feedback storage", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}

feedback_put_response: dict[int | str, dict[str, Any]] = {
    200: FeedbackStatusUpdateResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}

feedback_get_response: dict[int | str, dict[str, Any]] = {
    200: StatusResponse.openapi_response(),
}


def is_feedback_enabled() -> bool:
    """
    Check if feedback is enabled.

    Return whether user feedback collection is currently enabled
    based on configuration.

    Returns:
        bool: True if feedback collection is enabled; otherwise, False.
    """
    return configuration.user_data_collection_configuration.feedback_enabled


async def assert_feedback_enabled(_request: Request) -> None:
    """
    Ensure that feedback collection is enabled.

    Raises an HTTP 403 error if it is not.

    Args:
        request (Request): The FastAPI request object.

    Raises:
        HTTPException: If feedback collection is disabled.
    """
    feedback_enabled = is_feedback_enabled()
    if not feedback_enabled:
        response = ForbiddenResponse.feedback_disabled()
        raise HTTPException(**response.model_dump())


def _record_feedback_request_attributes(
    span: trace.Span, feedback_request: FeedbackRequest, user_id: str
) -> None:
    """Set high-level feedback attributes on the root span.

    User-generated free text (the question, LLM response, and comment) is
    anonymized before being recorded. Low-cardinality signals (rating and
    categories) are recorded as-is.

    Parameters:
        span: The root feedback span to annotate.
        feedback_request: The incoming feedback request.
        user_id: The authenticated user identifier (anonymized before recording).
    """
    set_span_attributes(
        span,
        {
            SpanAttributes.FEEDBACK_OPERATION: "submit",
            SpanAttributes.USER_ID: anonymize_value(user_id) if user_id else "",
            SpanAttributes.FEEDBACK_CONVERSATION: feedback_request.conversation_id,
            SpanAttributes.INPUT: anonymize_value(feedback_request.user_question),
            SpanAttributes.OUTPUT: anonymize_value(feedback_request.llm_response),
        },
    )
    if feedback_request.sentiment is not None:
        span.set_attribute(SpanAttributes.FEEDBACK_RATING, feedback_request.sentiment)
    if feedback_request.user_feedback:
        span.set_attribute(
            SpanAttributes.FEEDBACK_COMMENT,
            anonymize_value(feedback_request.user_feedback),
        )
    if feedback_request.categories:
        span.set_attribute(
            SpanAttributes.FEEDBACK_CATEGORIES,
            ",".join(
                getattr(category, "value", str(category))
                for category in feedback_request.categories
            ),
        )


@router.post("", responses=feedback_post_response)
@authorize(Action.FEEDBACK)
async def feedback_endpoint_handler(
    feedback_request: FeedbackRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    _ensure_feedback_enabled: Any = Depends(assert_feedback_enabled),
) -> FeedbackResponse:
    """Handle feedback requests.

    Processes a user feedback submission, storing the feedback and
    returning a confirmation response.

    ### Parameters:
    - feedback_request: The request containing feedback information.
    - ensure_feedback_enabled: The feedback handler (FastAPI Depends) that will
      handle feedback status checks.
    - auth: The Authentication handler (FastAPI Depends) that will handle
      authentication Logic.

    ### Returns:
    - Response indicating the status of the feedback storage request.

    ### Raises:
    - HTTPException: Returns HTTP 404 if conversation does not exist.
    - HTTPException: Returns HTTP 403 if conversation belongs to a different user.
    - HTTPException: Returns HTTP 500 if feedback storage fails.
    """
    logger.debug("Feedback received %s", str(feedback_request))

    user_id, _, _, _ = auth

    with tracer.start_as_current_span("feedback.submit") as span:
        _record_feedback_request_attributes(span, feedback_request, user_id)

        check_configuration_loaded(configuration)

        # Validate conversation exists and belongs to the user
        conversation_id = feedback_request.conversation_id
        conversation = retrieve_conversation(conversation_id)
        if conversation is None:
            span.set_attribute(
                SpanAttributes.FEEDBACK_STATUS_CODE, status.HTTP_404_NOT_FOUND
            )
            response = NotFoundResponse(
                resource="conversation", resource_id=conversation_id
            )
            raise HTTPException(**response.model_dump())

        if conversation.user_id != user_id:
            span.set_attribute(
                SpanAttributes.FEEDBACK_STATUS_CODE, status.HTTP_403_FORBIDDEN
            )
            response = ForbiddenResponse.conversation(
                action="submit feedback for",
                resource_id=conversation_id,
                user_id=user_id,
            )
            raise HTTPException(**response.model_dump())

        with tracer.start_as_current_span("feedback.storage") as storage_span:
            try:
                store_feedback(
                    user_id, feedback_request.model_dump(exclude={"model_config"})
                )
            except HTTPException:
                storage_span.set_attribute(
                    SpanAttributes.FEEDBACK_STORAGE_OUTCOME, "failure"
                )
                span.set_attribute(
                    SpanAttributes.FEEDBACK_STATUS_CODE,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
                raise
            storage_span.set_attribute(
                SpanAttributes.FEEDBACK_STORAGE_OUTCOME, "success"
            )

        span.set_attribute(SpanAttributes.FEEDBACK_STATUS_CODE, status.HTTP_200_OK)
        add_span_event(span, SpanEvents.FEEDBACK_SUBMITTED)

        return FeedbackResponse(response="feedback received")


def store_feedback(user_id: str, feedback: dict) -> None:
    """
    Store feedback in the local filesystem.

    Persist user feedback to a uniquely named JSON file in the
    configured local storage directory.

    Parameters:
    ----------
        user_id (str): Unique identifier of the user submitting feedback.
        feedback (dict): Feedback data to be stored, merged with user ID and timestamp.

    Raises:
    ------
        HTTPException: If writing the feedback file fails (HTTP 500).
    """
    logger.debug("Storing feedback for user %s", user_id)
    # Creates storage path only if it doesn't exist. The `exist_ok=True` prevents
    # race conditions in case of multiple server instances trying to set up storage
    # at the same location.
    storage_path = Path(
        configuration.user_data_collection_configuration.feedback_storage or ""
    )
    current_time = str(datetime.now(UTC))
    data_to_store = {"user_id": user_id, "timestamp": current_time, **feedback}
    # Stores feedback in a file under unique uuid
    feedback_file_path = storage_path / f"{get_suid()}.json"
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        with open(feedback_file_path, "w", encoding="utf-8") as feedback_file:
            json.dump(data_to_store, feedback_file)
    except OSError as e:
        logger.error("Failed to store feedback at %s: %s", feedback_file_path, e)
        response = InternalServerErrorResponse.feedback_path_invalid(str(storage_path))
        raise HTTPException(**response.model_dump()) from e


@router.get("/status", responses=feedback_get_response)
def feedback_status() -> StatusResponse:
    """
    Handle feedback status requests.

    Return the current enabled status of the feedback
    functionality.

    ### Parameters:
    - None

    ### Returns:
    - StatusResponse: Indicates whether feedback collection is enabled.
    """
    logger.debug("Feedback status requested")
    with tracer.start_as_current_span("feedback.get_status") as span:
        set_span_attributes(
            span,
            {
                SpanAttributes.FEEDBACK_OPERATION: "get_status",
                SpanAttributes.FEEDBACK_STATUS_CODE: status.HTTP_200_OK,
            },
        )
        feedback_status_enabled = is_feedback_enabled()
        return StatusResponse(
            functionality="feedback", status={"enabled": feedback_status_enabled}
        )


@router.put("/status", responses=feedback_put_response)
@authorize(Action.ADMIN)
async def update_feedback_status(
    feedback_update_request: FeedbackStatusUpdateRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> FeedbackStatusUpdateResponse:
    """
    Handle feedback status update requests.

    Takes a request with the desired state of the feedback status.
    Returns the updated state of the feedback status based on the request's value.
    These changes are for the life of the service and are on a per-worker basis.

    ### Parameters:
    - feedback_update_request: Structure containing desired state of the
      feedback status.
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Returns:
    - FeedbackStatusUpdateResponse: Indicates whether feedback is enabled.
    """
    user_id, _, _, _ = auth

    with tracer.start_as_current_span("feedback.update_status") as span:
        set_span_attributes(
            span,
            {
                SpanAttributes.FEEDBACK_OPERATION: "update_status",
                SpanAttributes.USER_ID: anonymize_value(user_id) if user_id else "",
            },
        )

        check_configuration_loaded(configuration)
        requested_status = feedback_update_request.get_value()

        with feedback_status_lock:
            previous_status = (
                configuration.user_data_collection_configuration.feedback_enabled
            )
            configuration.user_data_collection_configuration.feedback_enabled = (
                requested_status
            )
            updated_status = (
                configuration.user_data_collection_configuration.feedback_enabled
            )
            current_time = str(datetime.now(UTC))

        span.set_attribute(SpanAttributes.FEEDBACK_STATUS_CODE, status.HTTP_200_OK)

        return FeedbackStatusUpdateResponse(
            status={
                "previous_status": previous_status,
                "updated_status": updated_status,
                "updated_by": user_id,
                "timestamp": current_time,
            }
        )
