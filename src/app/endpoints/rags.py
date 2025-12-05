"""Handler for REST API calls to list and retrieve available RAGs."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.params import Depends
from llama_stack_client import APIConnectionError, BadRequestError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    RAGInfoResponse,
    RAGListResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rags"])


rags_responses: dict[int | str, dict[str, Any]] = {
    200: RAGListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}

rag_responses: dict[int | str, dict[str, Any]] = {
    200: RAGInfoResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["rag"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


@router.get("/rags", responses=rags_responses)
@authorize(Action.LIST_RAGS)
async def rags_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> RAGListResponse:
    """
    List all available RAGs.

    Returns:
        RAGListResponse: List of RAG identifiers.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    # make sure that the configuration is loaded
    check_configuration_loaded(configuration)

    llama_stack_configuration = configuration.llama_stack_configuration
    logger.info("Llama stack config: %s", llama_stack_configuration)

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        # retrieve list of RAGs
        rags = await client.vector_stores.list()
        logger.info("List of rags: %d", len(rags.data))

        # convert into the proper response object
        return RAGListResponse(rags=[rag.id for rag in rags.data])

    # connection to Llama Stack server
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e


@router.get("/rags/{rag_id}", responses=rag_responses)
@authorize(Action.GET_RAG)
async def get_rag_endpoint_handler(
    request: Request,
    rag_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> RAGInfoResponse:
    """Retrieve a single RAG by its unique ID.

    Returns:
        RAGInfoResponse: A single RAG's details.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 404: RAG with the given ID not found
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
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        # retrieve info about RAG
        rag_info = await client.vector_stores.retrieve(rag_id)
        return RAGInfoResponse(
            id=rag_info.id,
            name=rag_info.name,
            created_at=rag_info.created_at,
            last_active_at=rag_info.last_active_at,
            expires_at=rag_info.expires_at,
            object=rag_info.object,
            status=rag_info.status,
            usage_bytes=rag_info.usage_bytes,
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("RAG not found: %s", e)
        response = NotFoundResponse(resource="rag", resource_id=rag_id)
        raise HTTPException(**response.model_dump()) from e
