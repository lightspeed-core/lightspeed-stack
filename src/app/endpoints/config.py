"""Handler for REST API call to configuration."""

import logging
from typing import Any

from fastapi import APIRouter, Request

from version import __version__
from models.config import ClientConfig
from configuration import configuration

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


get_config_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "name": "foo bar baz",
        "llama_stack": {"url": "http://localhost:8321", "api_key": "xyzzy"},
    },
}


@router.get("/config", responses=get_config_responses)
def config_endpoint_handler(request: Request) -> ClientConfig:
    return configuration.configuration
