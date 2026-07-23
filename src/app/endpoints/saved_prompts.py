"""Handler for REST API calls to manage saved prompts."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from log import get_logger
from models.api.requests import SavedPromptCreateRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ConflictResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.api.responses.successful import (
    SavedPromptResponse,
    SavedPromptsConfigResponse,
    SavedPromptsListResponse,
)
from models.config import Action
from models.database.saved_prompts import SavedPrompt
from utils.endpoints import check_configuration_loaded
from utils.saved_prompts import (
    SavedPromptConflictError,
    SavedPromptLimitExceededError,
    SavedPromptValidationError,
    create_saved_prompt,
    list_saved_prompts_by_user,
    validate_saved_prompt_content,
    validate_saved_prompt_name,
)

logger = get_logger(__name__)
router = APIRouter(tags=["saved-prompts"])


def _to_saved_prompt_response(row: SavedPrompt) -> SavedPromptResponse:
    """Map a persisted saved-prompt row to the API response model.

    Parameters:
        row: Saved prompt entity loaded from the database.

    Returns:
        API response for a single saved prompt (excludes ``user_id``).
    """
    return SavedPromptResponse(
        id=row.id,
        name=row.name,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


get_saved_prompts_config_responses: dict[int | str, dict[str, Any]] = {
    200: SavedPromptsConfigResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}

list_saved_prompts_responses: dict[int | str, dict[str, Any]] = {
    200: SavedPromptsListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["configuration", "database"]
    ),
}

create_saved_prompts_responses: dict[int | str, dict[str, Any]] = {
    201: SavedPromptResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    409: ConflictResponse.openapi_response(),
    422: UnprocessableEntityResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(
        examples=["configuration", "database"]
    ),
}


@router.get("/saved-prompts/config", responses=get_saved_prompts_config_responses)
@authorize(Action.GET_CONFIG)
async def get_saved_prompts_config_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    request: Request,
) -> SavedPromptsConfigResponse:
    """
    Handle requests to the GET /saved-prompts/config endpoint.

    Process GET requests that return saved prompts configuration limits so
    consuming services can provide limits consistent with what the server
    will enforce. For example:

        curl http://localhost:8080/v1/saved-prompts/config

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is not loaded.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to backend services.

    ### Returns:
    - SavedPromptsConfigResponse: Saved prompts configuration limits.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    saved_prompts_config = configuration.configuration.saved_prompts
    return SavedPromptsConfigResponse(
        max_prompts_per_user=saved_prompts_config.max_prompts_per_user,
        max_display_name_length=saved_prompts_config.max_display_name_length,
        max_content_length=saved_prompts_config.max_content_length,
    )


@router.get("/saved-prompts", responses=list_saved_prompts_responses)
@authorize(Action.MANAGE_SAVED_PROMPTS)
async def list_saved_prompts_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    request: Request,
) -> SavedPromptsListResponse:
    """
    Handle requests to the GET /saved-prompts endpoint.

    Process GET requests that return all saved prompts belonging to the
    authenticated user, ordered by creation timestamp descending. For example:

        curl http://localhost:8080/v1/saved-prompts

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency.

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 when configuration is not loaded or the
      database query fails.

    ### Returns:
    - SavedPromptsListResponse: Saved prompts for the authenticated user.
    """
    _ = request
    check_configuration_loaded(configuration)

    user_id = auth[0]
    logger.info("Retrieving saved prompts")

    try:
        rows = await run_in_threadpool(list_saved_prompts_by_user, user_id)
        prompts = [_to_saved_prompt_response(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.exception("Error retrieving saved prompts")
        error_response = InternalServerErrorResponse.database_error()
        raise HTTPException(**error_response.model_dump()) from exc

    logger.info("Retrieved %s saved prompts", len(prompts))
    return SavedPromptsListResponse(prompts=prompts)


@router.post(
    "/saved-prompts",
    responses=create_saved_prompts_responses,
    status_code=status.HTTP_201_CREATED,
)
@authorize(Action.MANAGE_SAVED_PROMPTS)
async def create_saved_prompts_handler(
    request: Request,
    body: SavedPromptCreateRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> SavedPromptResponse:
    r"""
    Handle requests to the POST /saved-prompts endpoint.

    Process POST requests that create a saved prompt for the authenticated
    user after validating name/content against configured limits. For example:

        curl -X POST http://localhost:8080/v1/saved-prompts \
          -H 'Content-Type: application/json' \
          -d '{"name":"Deploy to staging","content":"Help me write a checklist"}'

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - body: Saved prompt name and content.
    - auth: Authentication tuple from the auth dependency.

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 409 when a prompt with the same name exists.
    - HTTPException: with status 422 when validation fails or the per-user
      limit would be exceeded.
    - HTTPException: with status 500 when configuration is not loaded or the
      database write fails.

    ### Returns:
    - SavedPromptResponse: The created saved prompt.
    """
    _ = request
    check_configuration_loaded(configuration)

    saved_prompts_config = configuration.configuration.saved_prompts

    try:
        name = validate_saved_prompt_name(
            body.name,
            max_display_name_length=saved_prompts_config.max_display_name_length,
        )
        validate_saved_prompt_content(
            body.content,
            max_content_length=saved_prompts_config.max_content_length,
        )
    except SavedPromptValidationError as exc:
        error_response = UnprocessableEntityResponse(
            response="Invalid attribute value",
            cause=str(exc),
        )
        raise HTTPException(**error_response.model_dump()) from exc

    user_id = auth[0]
    logger.info("Creating saved prompt")

    try:
        row = await run_in_threadpool(
            create_saved_prompt,
            user_id,
            name,
            body.content,
            saved_prompts_config.max_prompts_per_user,
        )
    except SavedPromptLimitExceededError as exc:
        error_response = UnprocessableEntityResponse(
            response="Saved prompt limit exceeded",
            cause=str(exc),
        )
        raise HTTPException(**error_response.model_dump()) from exc
    except SavedPromptConflictError as exc:
        error_response = ConflictResponse(
            resource="Saved prompt",
            resource_id=name,
        )
        raise HTTPException(**error_response.model_dump()) from exc
    except SQLAlchemyError as exc:
        logger.exception("Error creating saved prompt")
        error_response = InternalServerErrorResponse.database_error()
        raise HTTPException(**error_response.model_dump()) from exc

    logger.info("Created saved prompt id=%s", row.id)
    return _to_saved_prompt_response(row)
