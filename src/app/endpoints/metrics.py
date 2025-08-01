"""Handler for REST API call to provide metrics."""

from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request
from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from metrics.utils import setup_model_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint_handler(_request: Request) -> PlainTextResponse:
    """Handle request to the /metrics endpoint."""
    # Setup the model metrics if not already done. This is a one-time setup
    # and will not be run again on subsequent calls to this endpoint
    await setup_model_metrics()
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
