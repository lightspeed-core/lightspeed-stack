"""Unit tests for the /saved-prompts REST API endpoints."""

# pylint: disable=too-many-lines

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Final

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlalchemy.exc import SQLAlchemyError

import constants
from app.endpoints.saved_prompts import (
    create_saved_prompts_handler,
    delete_saved_prompts_handler,
    get_saved_prompts_config_handler,
    list_saved_prompts_handler,
    router,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import SavedPromptCreateRequest
from models.config import Action
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from utils.saved_prompts import (
    SavedPromptAccessDeniedError,
    SavedPromptConflictError,
    SavedPromptLimitExceededError,
    SavedPromptNotFoundError,
)

MOCK_AUTH: AuthTuple = ("test_user_id", "test_user", True, "test_token")
MOCK_LIST_AUTH: Final[AuthTuple] = ("user-1", "test_user", True, "test_token")
MOCK_CREATE_AUTH: Final[AuthTuple] = ("user-1", "test_user", True, "test_token")
MOCK_DELETE_AUTH: Final[AuthTuple] = ("user-1", "test_user", True, "test_token")
MOCK_DELETE_AUTH_OTHER: Final[AuthTuple] = ("user-2", "other_user", True, "test_token")
VALID_PROMPT_ID: Final[str] = "123e4567-e89b-12d3-a456-426614174000"
INVALID_PROMPT_ID: Final[str] = "not-a-valid-id"

CUSTOM_MAX_PROMPTS_PER_USER = 100
CUSTOM_MAX_DISPLAY_NAME_LENGTH = 128
CUSTOM_MAX_CONTENT_LENGTH = 5000


@pytest.fixture(name="saved_prompts_http_request")
def saved_prompts_http_request_fixture() -> Request:
    """Minimal ASGI Request for saved prompts endpoint tests."""
    return Request(scope={"type": "http"})


@pytest.fixture(name="config_with_custom_saved_prompts")
def config_with_custom_saved_prompts_fixture() -> AppConfig:
    """AppConfig with explicit saved prompts configuration values."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "test-key",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "authorization": {"access_rules": []},
            "saved_prompts": {
                "max_prompts_per_user": CUSTOM_MAX_PROMPTS_PER_USER,
                "max_display_name_length": CUSTOM_MAX_DISPLAY_NAME_LENGTH,
                "max_content_length": CUSTOM_MAX_CONTENT_LENGTH,
            },
        }
    )
    return cfg


@pytest.mark.asyncio
async def test_get_saved_prompts_config_returns_default_values(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts/config returns default saved prompts limits."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    response = await get_saved_prompts_config_handler(
        auth=MOCK_AUTH,
        request=saved_prompts_http_request,
    )

    assert response.max_prompts_per_user == constants.SAVED_PROMPTS_DEFAULT_MAX_PER_USER
    assert (
        response.max_display_name_length
        == constants.SAVED_PROMPTS_DEFAULT_MAX_DISPLAY_NAME_LENGTH
    )
    assert (
        response.max_content_length
        == constants.SAVED_PROMPTS_DEFAULT_MAX_CONTENT_LENGTH
    )


@pytest.mark.asyncio
async def test_get_saved_prompts_config_returns_configured_values(
    mocker: MockerFixture,
    config_with_custom_saved_prompts: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts/config returns configured saved prompts limits."""
    mock_authorization_resolvers(mocker)
    mocker.patch(
        "app.endpoints.saved_prompts.configuration",
        config_with_custom_saved_prompts,
    )

    response = await get_saved_prompts_config_handler(
        auth=MOCK_AUTH,
        request=saved_prompts_http_request,
    )

    assert response.max_prompts_per_user == CUSTOM_MAX_PROMPTS_PER_USER
    assert response.max_display_name_length == CUSTOM_MAX_DISPLAY_NAME_LENGTH
    assert response.max_content_length == CUSTOM_MAX_CONTENT_LENGTH


@pytest.mark.asyncio
async def test_get_saved_prompts_config_configuration_not_loaded(
    mocker: MockerFixture,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts/config returns 500 when configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.saved_prompts.configuration", mock_config)

    with pytest.raises(HTTPException) as exc_info:
        await get_saved_prompts_config_handler(
            auth=MOCK_AUTH,
            request=saved_prompts_http_request,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Configuration is not loaded"  # type: ignore[index]
    assert detail["cause"] == (  # type: ignore[index]
        "Lightspeed Stack configuration has not been initialized."
    )


@pytest.mark.asyncio
async def test_get_saved_prompts_config_forbidden_without_get_config_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts/config returns 403 when user lacks GET_CONFIG permission."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    mock_role_resolver = mocker.AsyncMock()
    mock_role_resolver.resolve_roles.return_value = set()

    mock_access_resolver = mocker.Mock()
    mock_access_resolver.check_access.return_value = False

    mocker.patch(
        "authorization.middleware.get_authorization_resolvers",
        return_value=(mock_role_resolver, mock_access_resolver),
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_saved_prompts_config_handler(
            auth=MOCK_AUTH,
            request=saved_prompts_http_request,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == (  # type: ignore[index]
        "User does not have permission to access this endpoint"
    )
    assert "not authorized to access this endpoint" in detail["cause"]  # type: ignore[index]


def test_get_saved_prompts_config_returns_401_when_auth_rejects(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> None:
    """GET /v1/saved-prompts/config returns 401 when auth dependency rejects.

    Verifies the route is actually wired with the auth dependency by
    hitting it via TestClient rather than calling the handler directly.
    """
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_authorization_resolvers(mocker)

    async def _reject(_self: object, _request: Request) -> None:
        """Simulate auth rejection."""
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "response": "Missing or invalid credentials provided by client",
                "cause": "No Authorization header found",
            },
        )

    mocker.patch(
        "authentication.noop.NoopAuthDependency.__call__",
        _reject,
    )

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    client = TestClient(app)
    response = client.get("/v1/saved-prompts/config")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    detail = response.json()["detail"]
    assert detail["response"] == "Missing or invalid credentials provided by client"
    assert detail["cause"] == "No Authorization header found"


@pytest.mark.asyncio
async def test_get_saved_prompts_config_uses_get_config_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts/config authorizes with Action.GET_CONFIG."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    perform_check = mocker.patch(
        "authorization.middleware._perform_authorization_check",
        return_value=None,
    )

    await get_saved_prompts_config_handler(
        auth=MOCK_AUTH,
        request=saved_prompts_http_request,
    )

    perform_check.assert_awaited_once()
    await_args = perform_check.await_args
    assert await_args is not None
    assert await_args.args[0] == Action.GET_CONFIG


# Test helper; explicit fields keep call sites readable.
def _prompt_row(  # pylint: disable=too-many-arguments
    *,
    prompt_id: str,
    user_id: str,
    name: str,
    content: str,
    created_at: datetime,
    updated_at: datetime,
) -> SimpleNamespace:
    """Build a SavedPrompt-like object for handler mapping tests.

    Parameters:
        prompt_id: Saved prompt identifier mapped to ``id``.
        user_id: Owning user identifier (not exposed in API responses).
        name: Prompt display name.
        content: Prompt body text.
        created_at: Creation timestamp.
        updated_at: Last-update timestamp.

    Returns:
        A ``SimpleNamespace`` with attributes matching a ``SavedPrompt`` row.
    """
    return SimpleNamespace(
        id=prompt_id,
        user_id=user_id,
        name=name,
        content=content,
        created_at=created_at,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_list_saved_prompts_happy_path(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts maps DAL rows and preserves order without user_id."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    newer_ts = datetime(2026, 7, 22, 16, 5, 0, tzinfo=UTC)
    older_ts = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    mock_list = mocker.patch(
        "app.endpoints.saved_prompts.list_saved_prompts_by_user",
        return_value=[
            _prompt_row(
                prompt_id="p-newer",
                user_id="user-1",
                name="second",
                content="c2",
                created_at=newer_ts,
                updated_at=newer_ts,
            ),
            _prompt_row(
                prompt_id="p-older",
                user_id="user-1",
                name="first",
                content="c1",
                created_at=older_ts,
                updated_at=older_ts,
            ),
        ],
    )

    response = await list_saved_prompts_handler(
        auth=MOCK_LIST_AUTH,
        request=saved_prompts_http_request,
    )

    mock_list.assert_called_once_with("user-1")
    payload = response.model_dump(mode="json")
    assert [item["id"] for item in payload["prompts"]] == ["p-newer", "p-older"]
    assert payload["prompts"][0]["name"] == "second"
    assert payload["prompts"][0]["content"] == "c2"
    assert "user_id" not in payload["prompts"][0]
    assert "user_id" not in payload


@pytest.mark.asyncio
async def test_list_saved_prompts_empty(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts returns an empty prompts list when DAL is empty."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.list_saved_prompts_by_user",
        return_value=[],
    )

    response = await list_saved_prompts_handler(
        auth=MOCK_LIST_AUTH,
        request=saved_prompts_http_request,
    )

    assert response.model_dump() == {"prompts": []}


@pytest.mark.asyncio
async def test_list_saved_prompts_isolates_near_collision_users(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """Handler only asks DAL for auth user_id; response stays that user's rows."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    ts = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    mock_list = mocker.patch(
        "app.endpoints.saved_prompts.list_saved_prompts_by_user",
        return_value=[
            _prompt_row(
                prompt_id="owned",
                user_id="user-1",
                name="deploy",
                content="owned-body",
                created_at=ts,
                updated_at=ts,
            )
        ],
    )

    response = await list_saved_prompts_handler(
        auth=MOCK_LIST_AUTH,
        request=saved_prompts_http_request,
    )

    mock_list.assert_called_once_with("user-1")
    assert mock_list.call_args.args[0] not in {"user-11", "user-1a"}
    payload = response.model_dump(mode="json")
    assert len(payload["prompts"]) == 1
    assert payload["prompts"][0]["id"] == "owned"
    assert payload["prompts"][0]["name"] == "deploy"
    assert payload["prompts"][0]["content"] == "owned-body"


@pytest.mark.asyncio
async def test_list_saved_prompts_uses_manage_saved_prompts_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts authorizes with Action.MANAGE_SAVED_PROMPTS."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.list_saved_prompts_by_user",
        return_value=[],
    )
    perform_check = mocker.patch(
        "authorization.middleware._perform_authorization_check",
        return_value=None,
    )

    await list_saved_prompts_handler(
        auth=MOCK_LIST_AUTH,
        request=saved_prompts_http_request,
    )

    perform_check.assert_awaited_once()
    await_args = perform_check.await_args
    assert await_args is not None
    assert await_args.args[0] == Action.MANAGE_SAVED_PROMPTS


@pytest.mark.asyncio
async def test_list_saved_prompts_forbidden_without_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts returns 403 when MANAGE_SAVED_PROMPTS is denied."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    mock_role_resolver = mocker.AsyncMock()
    mock_role_resolver.resolve_roles.return_value = set()
    mock_access_resolver = mocker.Mock()
    mock_access_resolver.check_access.return_value = False
    mocker.patch(
        "authorization.middleware.get_authorization_resolvers",
        return_value=(mock_role_resolver, mock_access_resolver),
    )

    with pytest.raises(HTTPException) as exc_info:
        await list_saved_prompts_handler(
            auth=MOCK_LIST_AUTH,
            request=saved_prompts_http_request,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_list_saved_prompts_returns_401_when_auth_rejects(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> None:
    """GET /v1/saved-prompts returns 401 when auth dependency rejects."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_authorization_resolvers(mocker)

    async def _reject(_self: object, _request: Request) -> None:
        """Simulate auth rejection."""
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "response": "Missing or invalid credentials provided by client",
                "cause": "No Authorization header found",
            },
        )

    mocker.patch(
        "authentication.noop.NoopAuthDependency.__call__",
        _reject,
    )

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    client = TestClient(app)
    response = client.get("/v1/saved-prompts")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_list_saved_prompts_configuration_not_loaded(
    mocker: MockerFixture,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts returns 500 when configuration is not loaded."""
    mock_authorization_resolvers(mocker)
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.saved_prompts.configuration", mock_config)

    with pytest.raises(HTTPException) as exc_info:
        await list_saved_prompts_handler(
            auth=MOCK_LIST_AUTH,
            request=saved_prompts_http_request,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_list_saved_prompts_database_error(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts returns 500 when the database query fails."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.list_saved_prompts_by_user",
        side_effect=SQLAlchemyError("db down"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await list_saved_prompts_handler(
            auth=MOCK_LIST_AUTH,
            request=saved_prompts_http_request,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Database query failed"  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_saved_prompts_happy_path(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns mapped prompt without user_id."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    created_at = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    mock_create = mocker.patch(
        "app.endpoints.saved_prompts.create_saved_prompt",
        return_value=_prompt_row(
            prompt_id="prompt-1",
            user_id="user-1",
            name="Deploy to staging",
            content="Help me write a checklist",
            created_at=created_at,
            updated_at=created_at,
        ),
    )

    response = await create_saved_prompts_handler(
        request=saved_prompts_http_request,
        body=SavedPromptCreateRequest(
            name="Deploy to staging",
            content="Help me write a checklist",
        ),
        auth=MOCK_CREATE_AUTH,
    )

    mock_create.assert_called_once_with(
        "user-1",
        "Deploy to staging",
        "Help me write a checklist",
        constants.SAVED_PROMPTS_DEFAULT_MAX_PER_USER,
    )
    payload = response.model_dump(mode="json")
    assert set(payload.keys()) == {
        "id",
        "name",
        "content",
        "created_at",
        "updated_at",
    }
    assert payload["id"] == "prompt-1"
    assert payload["name"] == "Deploy to staging"
    assert payload["content"] == "Help me write a checklist"
    assert "user_id" not in payload


@pytest.mark.asyncio
async def test_create_saved_prompts_normalizes_name_before_dal(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts strips name whitespace before calling DAL."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    created_at = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    mock_create = mocker.patch(
        "app.endpoints.saved_prompts.create_saved_prompt",
        return_value=_prompt_row(
            prompt_id="prompt-1",
            user_id="user-1",
            name="Deploy",
            content="body",
            created_at=created_at,
            updated_at=created_at,
        ),
    )

    await create_saved_prompts_handler(
        request=saved_prompts_http_request,
        body=SavedPromptCreateRequest(name="  Deploy  ", content="body"),
        auth=MOCK_CREATE_AUTH,
    )

    mock_create.assert_called_once_with(
        "user-1",
        "Deploy",
        "body",
        constants.SAVED_PROMPTS_DEFAULT_MAX_PER_USER,
    )


@pytest.mark.asyncio
async def test_create_saved_prompts_uses_manage_saved_prompts_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts authorizes with Action.MANAGE_SAVED_PROMPTS."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    created_at = datetime(2026, 7, 22, 16, 0, 0, tzinfo=UTC)
    mocker.patch(
        "app.endpoints.saved_prompts.create_saved_prompt",
        return_value=_prompt_row(
            prompt_id="prompt-1",
            user_id="user-1",
            name="Deploy",
            content="body",
            created_at=created_at,
            updated_at=created_at,
        ),
    )
    perform_check = mocker.patch(
        "authorization.middleware._perform_authorization_check",
        return_value=None,
    )

    await create_saved_prompts_handler(
        request=saved_prompts_http_request,
        body=SavedPromptCreateRequest(name="Deploy", content="body"),
        auth=MOCK_CREATE_AUTH,
    )

    perform_check.assert_awaited_once()
    await_args = perform_check.await_args
    assert await_args is not None
    assert await_args.args[0] == Action.MANAGE_SAVED_PROMPTS


@pytest.mark.asyncio
async def test_create_saved_prompts_quota_exceeded(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns 422 when the per-user quota is exceeded."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.create_saved_prompt",
        side_effect=SavedPromptLimitExceededError(
            "Saved prompt limit exceeded: 50 existing prompts, maximum is 50"
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_saved_prompts_handler(
            request=saved_prompts_http_request,
            body=SavedPromptCreateRequest(name="Deploy", content="body"),
            auth=MOCK_CREATE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Saved prompt limit exceeded"  # type: ignore[index]
    assert "maximum is 50" in detail["cause"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_saved_prompts_validation_error(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns 422 for empty/invalid name or content."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_create = mocker.patch("app.endpoints.saved_prompts.create_saved_prompt")

    with pytest.raises(HTTPException) as exc_info:
        await create_saved_prompts_handler(
            request=saved_prompts_http_request,
            body=SavedPromptCreateRequest(name="   ", content="body"),
            auth=MOCK_CREATE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Invalid attribute value"  # type: ignore[index]
    assert "must not be empty" in detail["cause"]  # type: ignore[index]
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_saved_prompts_duplicate_name_conflict(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns 409 when the prompt name already exists."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.create_saved_prompt",
        side_effect=SavedPromptConflictError("Saved prompt name already exists"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_saved_prompts_handler(
            request=saved_prompts_http_request,
            body=SavedPromptCreateRequest(name="Deploy", content="body"),
            auth=MOCK_CREATE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Saved Prompt already exists"  # type: ignore[index]
    assert "Deploy" in detail["cause"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_saved_prompts_database_error(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns 500 when the database write fails."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.create_saved_prompt",
        side_effect=SQLAlchemyError("db down"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_saved_prompts_handler(
            request=saved_prompts_http_request,
            body=SavedPromptCreateRequest(name="Deploy", content="body"),
            auth=MOCK_CREATE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Database query failed"  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_saved_prompts_configuration_not_loaded(
    mocker: MockerFixture,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns 500 when configuration is not loaded."""
    mock_authorization_resolvers(mocker)
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.saved_prompts.configuration", mock_config)

    with pytest.raises(HTTPException) as exc_info:
        await create_saved_prompts_handler(
            request=saved_prompts_http_request,
            body=SavedPromptCreateRequest(name="Deploy", content="body"),
            auth=MOCK_CREATE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_create_saved_prompts_forbidden_without_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """POST /saved-prompts returns 403 when MANAGE_SAVED_PROMPTS is denied."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    mock_role_resolver = mocker.AsyncMock()
    mock_role_resolver.resolve_roles.return_value = set()
    mock_access_resolver = mocker.Mock()
    mock_access_resolver.check_access.return_value = False
    mocker.patch(
        "authorization.middleware.get_authorization_resolvers",
        return_value=(mock_role_resolver, mock_access_resolver),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_saved_prompts_handler(
            request=saved_prompts_http_request,
            body=SavedPromptCreateRequest(name="Deploy", content="body"),
            auth=MOCK_CREATE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_create_saved_prompts_returns_401_when_auth_rejects(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> None:
    """POST /v1/saved-prompts returns 401 when auth dependency rejects."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_authorization_resolvers(mocker)

    async def _reject(_self: object, _request: Request) -> None:
        """Simulate auth rejection."""
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "response": "Missing or invalid credentials provided by client",
                "cause": "No Authorization header found",
            },
        )

    mocker.patch(
        "authentication.noop.NoopAuthDependency.__call__",
        _reject,
    )

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    client = TestClient(app)
    response = client.post(
        "/v1/saved-prompts",
        json={"name": "Deploy", "content": "body"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_delete_saved_prompts_happy_path(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE /saved-prompts/{prompt_id} returns 204 and scopes DAL to auth user."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_delete = mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user",
        return_value=None,
    )

    response = await delete_saved_prompts_handler(
        request=saved_prompts_http_request,
        prompt_id=VALID_PROMPT_ID,
        auth=MOCK_DELETE_AUTH,
    )

    mock_delete.assert_called_once_with(VALID_PROMPT_ID, "user-1")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.body == b""


@pytest.mark.asyncio
async def test_delete_saved_prompts_uses_authenticated_user_id(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE passes the authenticated user_id into DAL, not another user's."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_delete = mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user",
        return_value=None,
    )

    await delete_saved_prompts_handler(
        request=saved_prompts_http_request,
        prompt_id=VALID_PROMPT_ID,
        auth=MOCK_DELETE_AUTH_OTHER,
    )

    mock_delete.assert_called_once_with(VALID_PROMPT_ID, "user-2")
    assert mock_delete.call_args.args[1] != "user-1"


@pytest.mark.asyncio
async def test_delete_saved_prompts_invalid_id_format(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE returns 400 for invalid prompt_id and does not call DAL."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_delete = mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user"
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=saved_prompts_http_request,
            prompt_id=INVALID_PROMPT_ID,
            auth=MOCK_DELETE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Invalid saved prompt ID format"  # type: ignore[index]
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_saved_prompts_not_found(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE returns 404 when the prompt does not exist."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user",
        side_effect=SavedPromptNotFoundError("Saved prompt not found"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=saved_prompts_http_request,
            prompt_id=VALID_PROMPT_ID,
            auth=MOCK_DELETE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Saved Prompt not found"  # type: ignore[index]
    assert VALID_PROMPT_ID in detail["cause"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_delete_saved_prompts_access_denied_as_not_found(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE maps non-owner access denied to 404 (same as missing)."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user",
        side_effect=SavedPromptAccessDeniedError("Saved prompt access denied"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=saved_prompts_http_request,
            prompt_id=VALID_PROMPT_ID,
            auth=MOCK_DELETE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Saved Prompt not found"  # type: ignore[index]


@pytest.mark.asyncio
async def test_delete_saved_prompts_uses_manage_saved_prompts_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE /saved-prompts/{prompt_id} authorizes with MANAGE_SAVED_PROMPTS."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user",
        return_value=None,
    )
    perform_check = mocker.patch(
        "authorization.middleware._perform_authorization_check",
        return_value=None,
    )

    await delete_saved_prompts_handler(
        request=saved_prompts_http_request,
        prompt_id=VALID_PROMPT_ID,
        auth=MOCK_DELETE_AUTH,
    )

    perform_check.assert_awaited_once()
    await_args = perform_check.await_args
    assert await_args is not None
    assert await_args.args[0] == Action.MANAGE_SAVED_PROMPTS


@pytest.mark.asyncio
async def test_delete_saved_prompts_database_error(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE returns 500 when the database delete fails."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mocker.patch(
        "app.endpoints.saved_prompts.delete_saved_prompt_by_id_and_user",
        side_effect=SQLAlchemyError("db down"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=saved_prompts_http_request,
            prompt_id=VALID_PROMPT_ID,
            auth=MOCK_DELETE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Database query failed"  # type: ignore[index]


@pytest.mark.asyncio
async def test_delete_saved_prompts_configuration_not_loaded(
    mocker: MockerFixture,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE returns 500 when configuration is not loaded."""
    mock_authorization_resolvers(mocker)
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.saved_prompts.configuration", mock_config)

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=saved_prompts_http_request,
            prompt_id=VALID_PROMPT_ID,
            auth=MOCK_DELETE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_delete_saved_prompts_forbidden_without_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """DELETE returns 403 when MANAGE_SAVED_PROMPTS is denied."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    mock_role_resolver = mocker.AsyncMock()
    mock_role_resolver.resolve_roles.return_value = set()
    mock_access_resolver = mocker.Mock()
    mock_access_resolver.check_access.return_value = False
    mocker.patch(
        "authorization.middleware.get_authorization_resolvers",
        return_value=(mock_role_resolver, mock_access_resolver),
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=saved_prompts_http_request,
            prompt_id=VALID_PROMPT_ID,
            auth=MOCK_DELETE_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_delete_saved_prompts_returns_401_when_auth_rejects(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> None:
    """DELETE /v1/saved-prompts/{prompt_id} returns 401 when auth rejects."""
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)
    mock_authorization_resolvers(mocker)

    async def _reject(_self: object, _request: Request) -> None:
        """Simulate auth rejection."""
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "response": "Missing or invalid credentials provided by client",
                "cause": "No Authorization header found",
            },
        )

    mocker.patch(
        "authentication.noop.NoopAuthDependency.__call__",
        _reject,
    )

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    client = TestClient(app)
    response = client.delete(f"/v1/saved-prompts/{VALID_PROMPT_ID}")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
