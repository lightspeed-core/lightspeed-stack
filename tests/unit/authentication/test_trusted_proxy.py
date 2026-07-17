"""Unit tests for authentication/trusted_proxy module."""

from typing import Optional, cast

import pytest
from fastapi import HTTPException, Request
from pytest_mock import MockerFixture

from lightspeed_stack.authentication.trusted_proxy import TrustedProxyAuthDependency
from lightspeed_stack.configuration import AppConfig
from lightspeed_stack.constants import NO_USER_TOKEN
from lightspeed_stack.models.config import (
    TrustedProxyConfiguration,
    TrustedProxyServiceAccount,
)


def _make_config(
    user_header: str = "X-Forwarded-User",
    allowed_service_accounts: Optional[list[TrustedProxyServiceAccount]] = None,
) -> TrustedProxyConfiguration:
    """Create a TrustedProxyConfiguration for testing."""
    return TrustedProxyConfiguration(
        user_header=user_header,
        allowed_service_accounts=allowed_service_accounts,
    )


def _make_token_review_status(
    mocker: MockerFixture,
    username: str = "system:serviceaccount:konflux-ui:konflux-ui-proxy",
    uid: str = "sa-uid",
) -> object:
    """Create a mock V1TokenReviewStatus."""
    user = mocker.Mock()
    user.username = username
    user.uid = uid
    status = mocker.Mock()
    status.user = user
    status.authenticated = True
    return status


@pytest.mark.asyncio
async def test_valid_proxy_token_and_user_header(mocker: MockerFixture) -> None:
    """Test successful auth with valid proxy token and forwarded user header."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(mocker)

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    user_id, username, skip_userid_check, token = await dependency(request)

    assert user_id == "jane.doe@example.com"
    assert username == "jane.doe@example.com"
    assert skip_userid_check is True
    assert token == NO_USER_TOKEN


@pytest.mark.asyncio
async def test_missing_authorization_header() -> None:
    """Test that missing Authorization header raises 401."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["cause"] == "Missing Authorization header"


@pytest.mark.asyncio
async def test_invalid_token(mocker: MockerFixture) -> None:
    """Test that an invalid/expired proxy token raises 401."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = None

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer invalid-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["cause"] == "Invalid or expired proxy service account token"


@pytest.mark.asyncio
async def test_token_review_missing_user_info(mocker: MockerFixture) -> None:
    """Test that a token review response with no user info raises 401."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    status = mocker.Mock()
    status.authenticated = True
    status.user = None
    mock_get_user_info.return_value = status

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["cause"] == "Invalid service account token: missing user information"


@pytest.mark.asyncio
async def test_token_review_missing_username(mocker: MockerFixture) -> None:
    """Test that a token review response with empty username raises 401."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(mocker, username="")

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["cause"] == "Invalid service account token: missing username"


@pytest.mark.asyncio
async def test_sa_not_in_allowlist(mocker: MockerFixture) -> None:
    """Test that a valid token from an unlisted SA raises 403."""
    config = _make_config(
        allowed_service_accounts=[
            TrustedProxyServiceAccount(namespace="konflux-ui", name="konflux-ui-proxy"),
        ],
    )
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(
        mocker, username="system:serviceaccount:other-ns:other-sa"
    )

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer other-sa-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_sa_in_allowlist(mocker: MockerFixture) -> None:
    """Test that a valid token from an allowed SA succeeds."""
    config = _make_config(
        allowed_service_accounts=[
            TrustedProxyServiceAccount(namespace="konflux-ui", name="konflux-ui-proxy"),
        ],
    )
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(mocker)

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    user_id, username, skip_userid_check, token = await dependency(request)

    assert user_id == "jane.doe@example.com"
    assert username == "jane.doe@example.com"
    assert skip_userid_check is True
    assert token == NO_USER_TOKEN


@pytest.mark.asyncio
async def test_whitespace_only_user_header(mocker: MockerFixture) -> None:
    """Test that whitespace-only user identity header raises 401."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(mocker)

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
                (b"x-forwarded-user", b"   "),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["cause"] == "Missing required header 'X-Forwarded-User'"


@pytest.mark.asyncio
async def test_missing_user_header(mocker: MockerFixture) -> None:
    """Test that missing user identity header raises 401."""
    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(mocker)

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["cause"] == "Missing required header 'X-Forwarded-User'"


@pytest.mark.asyncio
async def test_no_allowlist_accepts_any_sa(mocker: MockerFixture) -> None:
    """Test that without an allowlist, any authenticated SA is accepted."""
    config = _make_config(allowed_service_accounts=None)
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(
        mocker, username="system:serviceaccount:any-ns:any-sa"
    )

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer any-sa-token"),
                (b"x-forwarded-user", b"jane.doe@example.com"),
            ],
        }
    )

    user_id, username, skip_userid_check, token = await dependency(request)

    assert user_id == "jane.doe@example.com"
    assert username == "jane.doe@example.com"
    assert skip_userid_check is True
    assert token == NO_USER_TOKEN


@pytest.mark.asyncio
async def test_health_probe_skip_enabled(mocker: MockerFixture) -> None:
    """Test that health probes return NO_AUTH_TUPLE when skip is enabled."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "authentication": {
            "module": "trusted-proxy",
            "skip_for_health_probes": True,
            "trusted_proxy_config": {
                "user_header": "X-Forwarded-User",
            },
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": ".",
            "transcripts_enabled": False,
            "transcripts_storage": ".",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    mocker.patch("lightspeed_stack.authentication.trusted_proxy.configuration", cfg)

    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    for path in ("/readiness", "/liveness"):
        request = Request(
            scope={
                "type": "http",
                "headers": [],
                "path": path,
            }
        )

        user_id, username, skip_userid_check, token = await dependency(request)

        assert user_id == "00000000-0000-0000-0000-000"
        assert username == "lightspeed-user"
        assert skip_userid_check is True
        assert token == ""


@pytest.mark.asyncio
async def test_health_probe_skip_disabled(mocker: MockerFixture) -> None:
    """Test that health probes require auth when skip is disabled."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "authentication": {
            "module": "trusted-proxy",
            "skip_for_health_probes": False,
            "trusted_proxy_config": {
                "user_header": "X-Forwarded-User",
            },
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": ".",
            "transcripts_enabled": False,
            "transcripts_storage": ".",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    mocker.patch("lightspeed_stack.authentication.trusted_proxy.configuration", cfg)

    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    request = Request(
        scope={
            "type": "http",
            "headers": [],
            "path": "/readiness",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_metrics_skip_enabled(mocker: MockerFixture) -> None:
    """Test that metrics endpoint returns NO_AUTH_TUPLE when skip is enabled."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "authentication": {
            "module": "trusted-proxy",
            "skip_for_metrics": True,
            "trusted_proxy_config": {
                "user_header": "X-Forwarded-User",
            },
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": ".",
            "transcripts_enabled": False,
            "transcripts_storage": ".",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    mocker.patch("lightspeed_stack.authentication.trusted_proxy.configuration", cfg)

    config = _make_config()
    dependency = TrustedProxyAuthDependency(config=config)

    request = Request(
        scope={
            "type": "http",
            "headers": [],
            "path": "/metrics",
        }
    )

    user_id, username, skip_userid_check, token = await dependency(request)

    assert user_id == "00000000-0000-0000-0000-000"
    assert username == "lightspeed-user"
    assert skip_userid_check is True
    assert token == ""


@pytest.mark.asyncio
async def test_custom_user_header(mocker: MockerFixture) -> None:
    """Test that a custom user header name is respected."""
    config = _make_config(user_header="X-Auth-Request-User")
    dependency = TrustedProxyAuthDependency(config=config)

    mock_get_user_info = mocker.patch(
        "lightspeed_stack.authentication.trusted_proxy.get_user_info"
    )
    mock_get_user_info.return_value = _make_token_review_status(mocker)

    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer proxy-sa-token"),
                (b"x-auth-request-user", b"custom-user"),
            ],
        }
    )

    user_id, username, skip_userid_check, token = await dependency(request)

    assert user_id == "custom-user"
    assert username == "custom-user"
    assert skip_userid_check is True
    assert token == NO_USER_TOKEN
