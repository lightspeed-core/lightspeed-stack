"""Handler for REST API call to list available models."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.params import Depends
from ogx_client import APIConnectionError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncOgxClientHolder
from configuration import configuration
from log import get_logger
from models.api.requests.catalog import ModelFilter
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import ModelsResponse
from models.config import Action
from utils.endpoints import check_configuration_loaded
from utils.model_list import parse_model_list_response

logger = get_logger(__name__)
router = APIRouter(tags=["models"])


models_responses: dict[int | str, dict[str, Any]] = {
    200: ModelsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["ogx", "kubernetes api"]
    ),
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
    models from the Llama Stack service. It is possible to specify "model_type"
    query parameter that is used as a filter. For example, if model type is set
    to "llm", only LLM models will be returned:

        curl http://localhost:8080/v1/models?model_type=llm

    The "model_type" query parameter is optional. When not specified, all models
    will be returned.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - model_type: Optional filter to return only models matching this type.

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 422 if model_type parameter is
      improper.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to Llama Stack.

    ### Returns:
    - ModelsResponse: An object containing the list of available models.
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    llama_stack_configuration = configuration.llama_stack_configuration
    logger.info("Llama Stack config: %s", llama_stack_configuration)

    try:
        # try to get Llama Stack client
        client = AsyncOgxClientHolder().get_client()
        # retrieve and normalize models across OpenAI/Anthropic/Google list shapes
        parsed_models = parse_model_list_response(await client.models.list())

        # optional filtering by model type
        if model_type.model_type is not None:
            parsed_models = [
                model
                for model in parsed_models
                if model.model_type == model_type.model_type
            ]

        return ModelsResponse(models=parsed_models)

    # Connection to Llama Stack server failed
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="OGX", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
