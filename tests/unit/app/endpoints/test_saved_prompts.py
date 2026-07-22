"""Unit tests for the /saved-prompts REST API endpoints."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

import constants
from app.endpoints.saved_prompts import (
    get_saved_prompts_config_handler,
    list_saved_prompts_handler,
    router,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.config import Action
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH: AuthTuple = ("test_user_id", "test_user", True, "test_token")
MOCK_LIST_AUTH: AuthTuple = ("user-1", "test_user", True, "test_token")

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
async def test_get_saved_prompts_config_incomplete_limits(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts/config returns 500 when a limit is unexpectedly None.

    The model validator on ``SavedPromptsConfiguration`` always fills in
    defaults, so this simulates the defensive branch that guards against a
    limit slipping through as ``None`` at runtime.
    """
    mock_authorization_resolvers(mocker)
    minimal_config.configuration.saved_prompts.max_prompts_per_user = None
    mocker.patch("app.endpoints.saved_prompts.configuration", minimal_config)

    with pytest.raises(HTTPException) as exc_info:
        await get_saved_prompts_config_handler(
            auth=MOCK_AUTH,
            request=saved_prompts_http_request,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Internal server error"  # type: ignore[index]


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


def _prompt_row(
    *,
    prompt_id: str,
    user_id: str,
    name: str,
    content: str,
    created_at: datetime,
    updated_at: datetime,
) -> SimpleNamespace:
    """Build a SavedPrompt-like object for handler mapping tests."""
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
async def test_list_saved_prompts_uses_list_saved_prompts_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts authorizes with Action.LIST_SAVED_PROMPTS."""
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
    assert await_args.args[0] == Action.LIST_SAVED_PROMPTS


@pytest.mark.asyncio
async def test_list_saved_prompts_forbidden_without_action(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    saved_prompts_http_request: Request,
) -> None:
    """GET /saved-prompts returns 403 when LIST_SAVED_PROMPTS is denied."""
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
