"""Handler for REST API call to provide metrics."""

from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request
from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint_handler(_request: Request) -> PlainTextResponse:
    """Handle request to the /metrics endpoint."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
