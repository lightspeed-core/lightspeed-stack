"""Handler for REST API calls to list and retrieve available providers."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.params import Depends
from llama_stack_client import APIConnectionError, BadRequestError
from llama_stack_client.types import ProviderListResponse

from lightspeed_stack.authentication import get_auth_dependency
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.authorization.middleware import authorize
from lightspeed_stack.client import AsyncLlamaStackClientHolder
from lightspeed_stack.configuration import configuration
from lightspeed_stack.log import get_logger
from lightspeed_stack.models.api.responses.constants import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
)
from lightspeed_stack.models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from lightspeed_stack.models.api.responses.successful import (
    ProviderResponse,
    ProvidersListResponse,
)
from lightspeed_stack.models.config import Action
from lightspeed_stack.utils.endpoints import check_configuration_loaded

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

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to Llama Stack.

    ### Returns:
    - ProvidersListResponse: Mapping from API type to list of providers.
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

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 404 if provider is not found.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to Llama Stack.

    ### Returns:
    - ProviderResponse: Provider details.
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
