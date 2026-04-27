"""Handler for REST API calls to list and retrieve available providers."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.params import Depends
from llama_stack_client import APIConnectionError, BadRequestError
from llama_stack_client.types import ProviderListResponse

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.config import Action
from models.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ProviderResponse,
    ProvidersListResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(tags=["providers"])


providers_list_responses: dict[int | str, dict[str, Any]] = {
    200: ProvidersListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

provider_get_responses: dict[int | str, dict[str, Any]] = {
    200: ProviderResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["provider"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}


@router.get("/providers", responses=providers_list_responses)
@authorize(Action.LIST_PROVIDERS)
async def providers_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> ProvidersListResponse:
    """
    List all available providers grouped by API type.

    ### Parameters:
    - request: The incoming HTTP request.
    - auth: Authentication tuple from the auth dependency.

    ### Returns:
    - ProvidersListResponse: Mapping from API type to list of providers.

    ### Raises:
    - HTTPException:
    - 401: Authentication failed
    - 403: Authorization failed
    - 500: Lightspeed Stack configuration not loaded
    - 503: Unable to connect to Llama Stack
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    llama_stack_configuration = configuration.llama_stack_configuration
    logger.info("Llama stack config: %s", llama_stack_configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        providers: ProviderListResponse = await client.providers.list()
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e

    return ProvidersListResponse(providers=group_providers(providers))


def group_providers(providers: ProviderListResponse) -> dict[str, list[dict[str, Any]]]:
    """Group a list of ProviderInfo objects by their API type.

    Args:
        providers: List of ProviderInfo objects.

    Returns:
        Mapping from API type to list of providers containing
        only 'provider_id' and 'provider_type'.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for provider in providers:
        result.setdefault(provider.api, []).append(
            {
                "provider_id": provider.provider_id,
                "provider_type": provider.provider_type,
            }
        )
    return result


@router.get("/providers/{provider_id}", responses=provider_get_responses)
@authorize(Action.GET_PROVIDER)
async def get_provider_endpoint_handler(
    request: Request,
    provider_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> ProviderResponse:
    """
    Retrieve a single provider identified by its unique ID.

    ### Parameters:
    - request: The incoming HTTP request.
    - provider_id: Provider identification string
    - auth: Authentication tuple from the auth dependency.

    ### Returns:
    - ProviderResponse: Provider details.

    ### Raises:
    - HTTPException:
    - 401: Authentication failed
    - 403: Authorization failed
    - 404: Provider not found
    - 500: Lightspeed Stack configuration not loaded
    - 503: Unable to connect to Llama Stack
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    llama_stack_configuration = configuration.llama_stack_configuration
    logger.info("Llama stack config: %s", llama_stack_configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        provider = await client.providers.retrieve(provider_id)
        return ProviderResponse(**provider.model_dump())

    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e

    except BadRequestError as e:
        response = NotFoundResponse(resource="provider", resource_id=provider_id)
        raise HTTPException(**response.model_dump()) from e
