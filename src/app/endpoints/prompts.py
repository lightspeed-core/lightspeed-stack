"""Handler for REST API calls to manage Llama Stack stored prompt templates."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_client import APIConnectionError, BadRequestError
from llama_stack_client import APIStatusError as LLSApiStatusError
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.config import Action
from models.requests import PromptCreateRequest, PromptUpdateRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptDeleteResponse,
    PromptResourceResponse,
    PromptsListResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.query import handle_known_apistatus_errors

logger = get_logger(__name__)
router = APIRouter(tags=["prompts"])


# Response schemas for OpenAPI documentation
prompt_create_responses: dict[int | str, dict[str, Any]] = {
    200: PromptResourceResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt manage"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["llama stack"]),
}

prompt_list_responses: dict[int | str, dict[str, Any]] = {
    200: PromptsListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt read"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["llama stack"]),
}

prompt_get_responses: dict[int | str, dict[str, Any]] = {
    200: PromptResourceResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt read"]),
    404: NotFoundResponse.openapi_response(examples=["prompt"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["llama stack"]),
}

prompt_update_responses: dict[int | str, dict[str, Any]] = {
    200: PromptResourceResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt manage"]),
    404: NotFoundResponse.openapi_response(examples=["prompt"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["llama stack"]),
}

prompt_delete_responses: dict[int | str, dict[str, Any]] = {
    200: PromptDeleteResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt manage"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["llama stack"]),
}


@router.post("/prompts", responses=prompt_create_responses)
@authorize(Action.MANAGE_PROMPTS)
async def create_prompt_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    body: PromptCreateRequest,
) -> PromptResourceResponse:
    r"""
    Handle requests to the POST /prompts endpoint.

    Process requests to create a stored prompt template in Llama Stack. The
    body must include the prompt text and may include template variable names.
    For example:

        curl -X POST http://localhost:8080/v1/prompts \\
          -H 'Content-Type: application/json' \\
          -d '{"prompt": "Hello {{name}}", "variables": ["name"]}'

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - body: Prompt creation parameters.

    ### Raises:
    - HTTPException: If configuration is not loaded, if unable to connect to
      Llama Stack, or if the prompts API returns an error response.

    ### Returns:
    - PromptResourceResponse: The created prompt as returned by Llama Stack.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        payload = body.model_dump(exclude_none=True)
        created = await client.prompts.create(**payload)
        return PromptResourceResponse.model_validate(created.model_dump())
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while creating prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.get("/prompts", responses=prompt_list_responses)
@authorize(Action.READ_PROMPTS)
async def list_prompts_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> PromptsListResponse:
    """
    Handle requests to the GET /prompts endpoint.

    Process GET requests that list all stored prompt templates from the Llama
    Stack service. For example:

        curl http://localhost:8080/v1/prompts

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: If configuration is not loaded, if unable to connect to
      Llama Stack, or if the prompts API returns an error response.

    ### Returns:
    - PromptsListResponse: An object containing the list of prompts.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        items = await client.prompts.list()
        data = [PromptResourceResponse.model_validate(p.model_dump()) for p in items]
        return PromptsListResponse(data=data)
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while listing prompts: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.get("/prompts/{prompt_id}", responses=prompt_get_responses)
@authorize(Action.READ_PROMPTS)
async def get_prompt_handler(
    request: Request,
    prompt_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    version: int | None = None,
) -> PromptResourceResponse:
    """
    Handle requests to the GET /prompts/{prompt_id} endpoint.

    Process GET requests to retrieve a single prompt by identifier. The
    ``version`` query parameter is optional; when omitted, the latest version is
    returned. For example:

        curl http://localhost:8080/v1/prompts/pmpt_abc123?version=1

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - prompt_id: The Llama Stack prompt identifier.
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - version: Optional version number (latest when omitted).

    ### Raises:
    - HTTPException: If configuration is not loaded, if the prompt is not
      found, if unable to connect to Llama Stack, or if the prompts API returns
      an error response.

    ### Returns:
    - PromptResourceResponse: The requested prompt object.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        if version is not None:
            retrieved = await client.prompts.retrieve(prompt_id, version=version)
        else:
            retrieved = await client.prompts.retrieve(prompt_id)
        return PromptResourceResponse.model_validate(retrieved.model_dump())
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (BadRequestError, ValueError) as e:
        logger.error("Prompt not found: %s", e)
        response = NotFoundResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while retrieving prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.put("/prompts/{prompt_id}", responses=prompt_update_responses)
@authorize(Action.MANAGE_PROMPTS)
async def update_prompt_handler(
    request: Request,
    prompt_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    body: PromptUpdateRequest,
) -> PromptResourceResponse:
    r"""
    Handle requests to the PUT /prompts/{prompt_id} endpoint.

    Process requests to update a stored prompt; Llama Stack increments the
    version. The body includes the new text, the current version being
    replaced, and optional fields such as ``set_as_default`` and ``variables``.
    For example:

        curl -X PUT http://localhost:8080/v1/prompts/pmpt_abc123 \\
          -H 'Content-Type: application/json' \\
          -d '{"prompt": "Hi", "version": 1, "set_as_default": true}'

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - prompt_id: The Llama Stack prompt identifier.
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - body: Prompt update parameters.

    ### Raises:
    - HTTPException: If configuration is not loaded, if the prompt is not
      found, if unable to connect to Llama Stack, or if the prompts API returns
      an error response.

    ### Returns:
    - PromptResourceResponse: The updated prompt object returned by Llama Stack.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        payload = body.model_dump(exclude_none=True, exclude_unset=True)
        updated = await client.prompts.update(prompt_id, **payload)
        return PromptResourceResponse.model_validate(updated.model_dump())
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (BadRequestError, ValueError) as e:
        logger.error("Prompt update failed: %s", e)
        response = NotFoundResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while updating prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.delete("/prompts/{prompt_id}", responses=prompt_delete_responses)
@authorize(Action.MANAGE_PROMPTS)
async def delete_prompt_handler(
    request: Request,
    prompt_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> PromptDeleteResponse:
    """
    Handle requests to the DELETE /prompts/{prompt_id} endpoint.

    Process requests to delete a stored prompt in Llama Stack. The response
    always uses HTTP 200 with a JSON body indicating whether the deletion
    succeeded (same pattern as deleting a conversation in ``/v2``). For example:

        curl -X DELETE http://localhost:8080/v1/prompts/pmpt_abc123

    When the prompt does not exist, the response still returns 200 with
    ``deleted`` set to false in the body.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - prompt_id: The Llama Stack prompt identifier.
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: If configuration is not loaded, if unable to connect to
      Llama Stack, or if the prompts API returns an error response.

    ### Returns:
    - PromptDeleteResponse: An object describing whether the prompt was
      deleted and a human-readable message.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        await client.prompts.delete(prompt_id)
        return PromptDeleteResponse(deleted=True, prompt_id=prompt_id)
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (BadRequestError, ValueError) as e:
        logger.error("Prompt delete failed: %s", e)
        return PromptDeleteResponse(deleted=False, prompt_id=prompt_id)
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while deleting prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e
