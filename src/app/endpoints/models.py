"""Handler for REST API call to list available models."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.params import Depends
from llama_stack_client import APIConnectionError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.requests import ModelFilter
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ModelsResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["models"])


def parse_llama_stack_model(model: Any) -> dict[str, Any]:
    """
    Parse llama-stack model.

    Converting the new llama-stack model format (0.4.x) with custom_metadata.

    Args:
        model: Model object from llama-stack (has id, custom_metadata, object fields)

    Returns:
        dict: Model in legacy format with identifier, provider_id, model_type, etc.
    """
    custom_metadata = getattr(model, "custom_metadata", {}) or {}

    model_type = str(custom_metadata.get("model_type", "unknown"))

    metadata = {
        k: v
        for k, v in custom_metadata.items()
        if k not in ("provider_id", "provider_resource_id", "model_type")
    }

    legacy_model = {
        "identifier": getattr(model, "id", ""),
        "metadata": metadata,
        "api_model_type": model_type,
        "provider_id": str(custom_metadata.get("provider_id", "")),
        "type": getattr(model, "object", "model"),
        "provider_resource_id": str(custom_metadata.get("provider_resource_id", "")),
        "model_type": model_type,
    }
    return legacy_model


models_responses: dict[int | str, dict[str, Any]] = {
    200: ModelsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


@router.get("/models", responses=models_responses)
@authorize(Action.GET_MODELS)
async def models_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    model_type: Annotated[ModelFilter, Query()],
) -> ModelsResponse:
    """
    Handle requests to the /models endpoint.

    Process GET requests to the /models endpoint, returning a list of available
    models from the Llama Stack service.

    Parameters:
        request: The incoming HTTP request.
        auth: Authentication tuple from the auth dependency.
        model_type: Optional filter to return only models matching this type.

    Raises:
        HTTPException: If unable to connect to the Llama Stack server or if
        model retrieval fails for any reason.

    Returns:
        ModelsResponse: An object containing the list of available models.
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    llama_stack_configuration = configuration.llama_stack_configuration
    logger.info("Llama stack config: %s", llama_stack_configuration)

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        # retrieve models
        models = await client.models.list()

        # parse models to legacy format
        parsed_models = [parse_llama_stack_model(model) for model in models]

        # optional filtering by model type
        if model_type.model_type is not None:
            parsed_models = [
                model
                for model in parsed_models
                if model["model_type"] == model_type.model_type
            ]

        return ModelsResponse(models=parsed_models)

    # Connection to Llama Stack server failed
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
