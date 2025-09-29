"""Handler for REST API call to list available models."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.params import Depends
from llama_stack_client import APIConnectionError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from authorization.middleware import authorize
from models.config import Action
from models.responses import ModelsResponse
from utils.endpoints import check_configuration_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["models"])
auth_dependency = get_auth_dependency()



models_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "models": [
            {
                "identifier": "all-MiniLM-L6-v2",
                "metadata": {"embedding_dimension": 384},
                "api_model_type": "embedding",
                "provider_id": "ollama",
                "provider_resource_id": "all-minilm:latest",
                "type": "model",
                "model_type": "embedding",
            },
            {
                "identifier": "llama3.2:3b-instruct-fp16",
                "metadata": {},
                "api_model_type": "llm",
                "provider_id": "ollama",
                "provider_resource_id": "llama3.2:3b-instruct-fp16",
                "type": "model",
                "model_type": "llm",
            },
        ]
    },
    500: {"description": "Connection to Llama Stack is broken"},
}


@router.get("/models", responses=models_responses)
@authorize(Action.GET_MODELS)
async def models_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
) -> ModelsResponse:
    """
    Handle requests to the /models endpoint.

    Process GET requests to the /models endpoint, returning a list of available
    models from the Llama Stack service.

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
        m = [dict(m) for m in models]
        return ModelsResponse(models=m)

    # connection to Llama Stack server
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unable to connect to Llama Stack",
                "cause": str(e),
            },
        ) from e
    # any other exception that can occur during model listing
    except Exception as e:
        logger.error("Unable to retrieve list of models: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unable to retrieve list of models",
                "cause": str(e),
            },
        ) from e
