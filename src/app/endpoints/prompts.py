"""Handler for REST API calls to manage OGX stored prompt templates."""

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from ogx_api import PromptNotFoundError, PromptVersionNotFoundError
from ogx_client import ApiException, NotFoundError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client.ogx import AsyncOgxClientHolder
from configuration import configuration
from log import get_logger
from models.api.requests import PromptCreateRequest, PromptUpdateRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import (
    PromptDeleteResponse,
    PromptResourceResponse,
    PromptsListResponse,
)
from models.config import Action
from utils.endpoints import check_configuration_loaded
from utils.ogx_serialization import dump_ogx_model
from utils.query import handle_known_apistatus_errors
from utils.suid import check_suid_prompt

logger = get_logger(__name__)
router = APIRouter(tags=["prompts"])


# Response schemas for OpenAPI documentation
prompt_create_responses: dict[int | str, dict[str, Any]] = {
    200: PromptResourceResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt manage"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
}

prompt_list_responses: dict[int | str, dict[str, Any]] = {
    200: PromptsListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt read"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
}

prompt_get_responses: dict[int | str, dict[str, Any]] = {
    200: PromptResourceResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(examples=["prompt_id"]),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt read"]),
    404: NotFoundResponse.openapi_response(examples=["prompt"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
}

prompt_update_responses: dict[int | str, dict[str, Any]] = {
    200: PromptResourceResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(examples=["prompt_id"]),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt manage"]),
    404: NotFoundResponse.openapi_response(examples=["prompt"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
}

prompt_delete_responses: dict[int | str, dict[str, Any]] = {
    200: PromptDeleteResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(examples=["prompt_id"]),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "prompt manage"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
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

    Process requests to create a stored prompt template in OGX. The
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
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 422 if the request body is improper.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - PromptResourceResponse: The created prompt as returned by OGX.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncOgxClientHolder().get_client()
        payload = body.model_dump(exclude_none=True)
        created = await client.prompts.create(**payload)
        return PromptResourceResponse.model_validate(dump_ogx_model(created))
    except ApiException as e:
        if not e.status:
            logger.error("Unable to connect to OGX: %s", e)
            response = ServiceUnavailableResponse(backend_name="OGX")
            raise HTTPException(**response.model_dump()) from e

        logger.error("API status error while creating prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "ogx")
        raise HTTPException(**error_response.model_dump()) from e


@router.get("/prompts", responses=prompt_list_responses)
@authorize(Action.READ_PROMPTS)
async def list_prompts_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> PromptsListResponse:
    """
    Handle requests to the GET /prompts endpoint.

    Process GET requests that list all stored prompt templates from the OGX
    service. For example:

        curl http://localhost:8080/v1/prompts

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - PromptsListResponse: An object containing the list of prompts.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncOgxClientHolder().get_client()
        items = await client.prompts.list()
        data = [PromptResourceResponse.model_validate(dump_ogx_model(p)) for p in items]
        return PromptsListResponse(data=data)
    except ApiException as e:
        if not e.status:
            logger.error("Unable to connect to OGX: %s", e)
            response = ServiceUnavailableResponse(backend_name="OGX")
            raise HTTPException(**response.model_dump()) from e

        logger.error("API status error while listing prompts: %s", e)
        error_response = handle_known_apistatus_errors(e, "ogx")
        raise HTTPException(**error_response.model_dump()) from e


@router.get("/prompts/{prompt_id}", responses=prompt_get_responses)
@authorize(Action.READ_PROMPTS)
async def get_prompt_handler(
    request: Request,
    prompt_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    version: Optional[int] = None,
) -> PromptResourceResponse:
    """
    Handle requests to the GET /prompts/{prompt_id} endpoint.

    Process GET requests to retrieve a single prompt by identifier. The
    ``version`` query parameter is optional; when omitted, the latest version is
    returned. For example:

        curl http://localhost:8080/v1/prompts/pmpt_abc123?version=1

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - prompt_id: The OGX prompt identifier.
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - version: Optional version number (latest when omitted).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 404 if prompt is not found.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - PromptResourceResponse: The requested prompt object.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    if not check_suid_prompt(prompt_id):
        logger.error("Invalid prompt ID format: %s", prompt_id)
        response = BadRequestResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump())

    try:
        client = AsyncOgxClientHolder().get_client()
        retrieved = await client.prompts.retrieve(prompt_id, version=version)
        return PromptResourceResponse.model_validate(dump_ogx_model(retrieved))
    except (NotFoundError, PromptNotFoundError, PromptVersionNotFoundError) as e:
        logger.error("Prompt not found: %s", e)
        response = NotFoundResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump()) from e
    except ApiException as e:
        if not e.status:
            logger.error("Unable to connect to OGX: %s", e)
            response = ServiceUnavailableResponse(backend_name="OGX")
            raise HTTPException(**response.model_dump()) from e

        logger.error("API status error while retrieving prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "ogx")
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

    Process requests to update a stored prompt; OGX increments the
    version. The body includes the new text, the current version being
    replaced, and optional fields such as ``set_as_default`` and ``variables``.
    For example:

        curl -X PUT http://localhost:8080/v1/prompts/pmpt_abc123 \\
          -H 'Content-Type: application/json' \\
          -d '{"prompt": "Hi", "version": 1, "set_as_default": true}'

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - prompt_id: The OGX prompt identifier.
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - body: Prompt update parameters.

    ### Raises:
    - HTTPException: with status 400 when request format is not valid.
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 404 if prompt is not found.
    - HTTPException: with status 422 if request payload is corrupted.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - PromptResourceResponse: The updated prompt object returned by OGX.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    if not check_suid_prompt(prompt_id):
        logger.error("Invalid prompt ID format: %s", prompt_id)
        response = BadRequestResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump())

    try:
        client = AsyncOgxClientHolder().get_client()
        payload = body.model_dump(exclude_none=True, exclude_unset=True)
        updated = await client.prompts.update(prompt_id, **payload)
        return PromptResourceResponse.model_validate(dump_ogx_model(updated))
    except (NotFoundError, PromptNotFoundError) as e:
        logger.error("Prompt update failed: %s", e)
        response = NotFoundResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump()) from e
    except ApiException as e:
        if not e.status:
            logger.error("Unable to connect to OGX: %s", e)
            response = ServiceUnavailableResponse(backend_name="OGX")
            raise HTTPException(**response.model_dump()) from e

        logger.error("API status error while updating prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "ogx")
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

    Process requests to delete a stored prompt in OGX. The response
    always uses HTTP 200 with a JSON body indicating whether the deletion
    succeeded (same pattern as deleting a conversation in ``/v2``). For example:

        curl -X DELETE http://localhost:8080/v1/prompts/pmpt_abc123

    When the prompt does not exist, the response still returns 200 with
    ``deleted`` set to false in the body.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - prompt_id: The OGX prompt identifier.
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 422 if request payload is corrupted.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - PromptDeleteResponse: An object describing whether the prompt was
      deleted and a human-readable message.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    if not check_suid_prompt(prompt_id):
        logger.error("Invalid prompt ID format: %s", prompt_id)
        response = BadRequestResponse(resource="prompt", resource_id=prompt_id)
        raise HTTPException(**response.model_dump())

    try:
        client = AsyncOgxClientHolder().get_client()
        await client.prompts.delete(prompt_id)
        return PromptDeleteResponse(deleted=True, prompt_id=prompt_id)
    except (NotFoundError, PromptNotFoundError) as e:
        logger.error("Prompt delete failed: %s", e)
        return PromptDeleteResponse(deleted=False, prompt_id=prompt_id)
    except ApiException as e:
        if not e.status:
            logger.error("Unable to connect to OGX: %s", e)
            response = ServiceUnavailableResponse(backend_name="OGX")
            raise HTTPException(**response.model_dump()) from e

        logger.error("API status error while deleting prompt: %s", e)
        error_response = handle_known_apistatus_errors(e, "ogx")
        raise HTTPException(**error_response.model_dump()) from e
