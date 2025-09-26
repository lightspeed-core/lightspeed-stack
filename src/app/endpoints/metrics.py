"""Handler for REST API call to provide metrics."""

from typing import Annotated
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request, Depends
from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from authentication.interface import AuthTuple
from authentication import get_auth_dependency
from authorization.middleware import authorize
from models.config import Action
from metrics.utils import setup_model_metrics

router = APIRouter(tags=["metrics"])
auth_dependency = get_auth_dependency()



@router.get("/metrics", response_class=PlainTextResponse)
@authorize(Action.GET_METRICS)
async def metrics_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    request: Request,
) -> PlainTextResponse:
    """
    Handle request to the /metrics endpoint.

    Process GET requests to the /metrics endpoint, returning the
    latest Prometheus metrics in form of a plain text.

    Initializes model metrics on the first request if not already
    set up, then responds with the current metrics snapshot in
    Prometheus format.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    # Setup the model metrics if not already done. This is a one-time setup
    # and will not be run again on subsequent calls to this endpoint
    await setup_model_metrics()
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
