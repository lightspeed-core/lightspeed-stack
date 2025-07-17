"""Handler for REST API call to provide info."""

import logging
from typing import Any
from pathlib import Path
import json
from datetime import datetime, UTC

from fastapi import APIRouter, Request, HTTPException, Depends, status

from auth import get_auth_dependency
from configuration import configuration
from models.responses import (
    FeedbackResponse,
    StatusResponse,
    UnauthorizedResponse,
    ForbiddenResponse,
)
from models.requests import FeedbackRequest
from utils.suid import get_suid
from utils.common import retrieve_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])
auth_dependency = get_auth_dependency()

# Response for the feedback endpoint
feedback_response: dict[int | str, dict[str, Any]] = {
    200: {"response": "Feedback received and stored"},
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
}


def is_feedback_enabled() -> bool:
    """Check if feedback is enabled.

    Returns:
        bool: True if feedback is enabled, False otherwise.
    """
    return not configuration.user_data_collection_configuration.feedback_disabled


async def assert_feedback_enabled(_request: Request) -> None:
    """Check if feedback is enabled.

    Args:
        request (Request): The FastAPI request object.

    Raises:
        HTTPException: If feedback is disabled.
    """
    feedback_enabled = is_feedback_enabled()
    if not feedback_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Feedback is disabled",
        )


@router.post("", responses=feedback_response)
def feedback_endpoint_handler(
    _request: Request,
    feedback_request: FeedbackRequest,
    _ensure_feedback_enabled: Any = Depends(assert_feedback_enabled),
    auth: Any = Depends(auth_dependency),
) -> FeedbackResponse:
    """Handle feedback requests.

    Args:
        feedback_request: The request containing feedback information.
        ensure_feedback_enabled: The feedback handler (FastAPI Depends) that
            will handle feedback status checks.
        auth: The Authentication handler (FastAPI Depends) that will
            handle authentication Logic.

    Returns:
        Response indicating the status of the feedback storage request.
    """
    logger.debug("Feedback received %s", str(feedback_request))

    user_id = retrieve_user_id(auth)
    try:
        store_feedback(user_id, feedback_request.model_dump(exclude={"model_config"}))
    except Exception as e:
        logger.error("Error storing user feedback: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Error storing user feedback",
                "cause": str(e),
            },
        ) from e

    return FeedbackResponse(response="feedback received")


def store_feedback(user_id: str, feedback: dict) -> None:
    """Store feedback in the local filesystem.

    Args:
        user_id: The user ID (UUID).
        feedback: The feedback to store.
    """
    logger.debug("Storing feedback for user %s", user_id)
    # Creates storage path only if it doesn't exist. The `exist_ok=True` prevents
    # race conditions in case of multiple server instances trying to set up storage
    # at the same location.
    storage_path = Path(
        configuration.user_data_collection_configuration.feedback_storage or ""
    )
    storage_path.mkdir(parents=True, exist_ok=True)

    current_time = str(datetime.now(UTC))
    data_to_store = {"user_id": user_id, "timestamp": current_time, **feedback}

    # stores feedback in a file under unique uuid
    feedback_file_path = storage_path / f"{get_suid()}.json"
    with open(feedback_file_path, "w", encoding="utf-8") as feedback_file:
        json.dump(data_to_store, feedback_file)

    logger.info("Feedback stored sucessfully at %s", feedback_file_path)


@router.get("/status")
def feedback_status() -> StatusResponse:
    """Handle feedback status requests.

    Returns:
        Response indicating the status of the feedback.
    """
    logger.debug("Feedback status requested")
    feedback_status_enabled = is_feedback_enabled()
    return StatusResponse(
        functionality="feedback", status={"enabled": feedback_status_enabled}
    )
