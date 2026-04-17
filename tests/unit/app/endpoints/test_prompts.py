"""Unit tests for the /prompts REST API endpoints."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, BadRequestError
from llama_stack_client.types.prompt import Prompt
from pytest_mock import MockerFixture

from app.endpoints.prompts import (
    create_prompt_handler,
    delete_prompt_handler,
    get_prompt_handler,
    list_prompts_handler,
    update_prompt_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.requests import PromptCreateRequest, PromptUpdateRequest
from models.responses import PromptDeleteResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


def _sample_prompt(
    prompt_id: str,
    version: int,
    *,
    is_default: bool | None = True,
    prompt: str | None = "hello",
    variables: list[str] | None = None,
) -> Prompt:
    """Build a Llama Stack SDK Prompt for test return values."""
    return Prompt(
        prompt_id=prompt_id,
        version=version,
        is_default=is_default,
        prompt=prompt,
        variables=variables,
    )


@pytest.fixture(autouse=True)
def _mock_prompts_authorization(mocker: MockerFixture) -> None:
    """Stub authorization resolvers for prompts endpoint tests."""
    mock_authorization_resolvers(mocker)


@pytest.fixture(name="prompts_http_request")
def prompts_http_request_fixture() -> Request:
    """Minimal ASGI Request; Authorization matches MOCK_AUTH token."""
    return Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer mock_token")],
        }
    )


@pytest.fixture(name="prompts_client_mocks")
def prompts_client_mocks_fixture(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> tuple[Any, Any]:
    """Patch loaded configuration and mocked Llama Stack client with ``.prompts`` API."""
    mocker.patch("app.endpoints.prompts.configuration", minimal_config)
    mock_prompts = mocker.AsyncMock()
    mock_client = mocker.AsyncMock()
    mock_client.prompts = mock_prompts
    mocker.patch(
        "app.endpoints.prompts.AsyncLlamaStackClientHolder.get_client",
        return_value=mock_client,
    )
    return mock_client, mock_prompts


@pytest.mark.asyncio
async def test_create_prompt_configuration_not_loaded(
    mocker: MockerFixture,
    prompts_http_request: Request,
) -> None:
    """create_prompt returns 500 when configuration is not loaded."""
    mock_config = AppConfig()
    mocker.patch("app.endpoints.prompts.configuration", mock_config)

    with pytest.raises(HTTPException) as exc_info:
        await create_prompt_handler(
            request=prompts_http_request,
            auth=MOCK_AUTH,
            body=PromptCreateRequest(prompt="x", variables=None),
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert detail["response"] == "Configuration is not loaded"  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_prompt_success(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """create_prompt delegates to client.prompts.create."""
    _, mock_prompts = prompts_client_mocks
    mock_prompts.create.return_value = _sample_prompt(
        "pmpt_abc", 1, prompt="Hi {{n}}", variables=["n"]
    )

    result = await create_prompt_handler(
        request=prompts_http_request,
        auth=MOCK_AUTH,
        body=PromptCreateRequest(prompt="Hi {{n}}", variables=["n"]),
    )

    assert result.prompt_id == "pmpt_abc"
    assert result.version == 1
    mock_prompts.create.assert_awaited_once_with(prompt="Hi {{n}}", variables=["n"])


@pytest.mark.asyncio
async def test_get_prompt_with_version(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """get_prompt passes version when provided."""
    _, mock_prompts = prompts_client_mocks
    mock_prompts.retrieve.return_value = _sample_prompt("pmpt_abc", 2)

    result = await get_prompt_handler(
        request=prompts_http_request,
        prompt_id="pmpt_abc",
        auth=MOCK_AUTH,
        version=2,
    )

    assert result.version == 2
    mock_prompts.retrieve.assert_awaited_once_with("pmpt_abc", version=2)


@pytest.mark.asyncio
async def test_get_prompt_without_version_omits_kwarg(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """get_prompt calls retrieve with prompt_id only when version is omitted."""
    _, mock_prompts = prompts_client_mocks
    mock_prompts.retrieve.return_value = _sample_prompt("pmpt_abc", 1)

    await get_prompt_handler(
        request=prompts_http_request,
        prompt_id="pmpt_abc",
        auth=MOCK_AUTH,
    )

    mock_prompts.retrieve.assert_awaited_once_with("pmpt_abc")


@pytest.mark.asyncio
async def test_update_prompt_success(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """update_prompt forwards body fields to the client."""
    _, mock_prompts = prompts_client_mocks
    mock_prompts.update.return_value = _sample_prompt("pmpt_abc", 2)

    body = PromptUpdateRequest(
        prompt="new", version=1, set_as_default=True, variables=None
    )
    result = await update_prompt_handler(
        request=prompts_http_request,
        prompt_id="pmpt_abc",
        auth=MOCK_AUTH,
        body=body,
    )

    assert result.version == 2
    mock_prompts.update.assert_awaited_once_with(
        "pmpt_abc", prompt="new", version=1, set_as_default=True
    )


@pytest.mark.asyncio
async def test_delete_prompt_success(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """delete_prompt calls client.prompts.delete and returns 200 body."""
    _, mock_prompts = prompts_client_mocks

    result = await delete_prompt_handler(
        request=prompts_http_request,
        prompt_id="pmpt_abc",
        auth=MOCK_AUTH,
    )

    assert isinstance(result, PromptDeleteResponse)
    assert result.success is True
    assert result.prompt_id == "pmpt_abc"
    mock_prompts.delete.assert_awaited_once_with("pmpt_abc")


@pytest.mark.asyncio
async def test_delete_prompt_not_found_returns_body(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
    mocker: MockerFixture,
) -> None:
    """delete_prompt returns success=False on Llama Stack BadRequestError (v2 style)."""
    _, mock_prompts = prompts_client_mocks
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_prompts.delete.side_effect = BadRequestError(
        message="not found", response=mock_response, body=None
    )

    result = await delete_prompt_handler(
        request=prompts_http_request,
        prompt_id="pmpt_missing",
        auth=MOCK_AUTH,
    )

    assert result.success is False
    assert result.prompt_id == "pmpt_missing"


@pytest.mark.asyncio
async def test_list_prompts_success(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """list_prompts maps client.prompts.list to PromptsListResponse."""
    _, mock_prompts = prompts_client_mocks
    mock_prompts.list.return_value = [
        _sample_prompt("pmpt_a", 1),
        _sample_prompt("pmpt_b", 2, is_default=False),
    ]

    out = await list_prompts_handler(request=prompts_http_request, auth=MOCK_AUTH)

    assert len(out.data) == 2
    assert out.data[0].prompt_id == "pmpt_a"
    mock_prompts.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_prompt_api_connection_error(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
) -> None:
    """get_prompt maps APIConnectionError to 503."""
    _, mock_prompts = prompts_client_mocks
    mock_prompts.retrieve.side_effect = APIConnectionError(request=None)  # type: ignore

    with pytest.raises(HTTPException) as exc_info:
        await get_prompt_handler(
            request=prompts_http_request,
            prompt_id="pmpt_abc",
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_get_prompt_bad_request_maps_to_404(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
    mocker: MockerFixture,
) -> None:
    """get_prompt maps Llama Stack BadRequestError to 404 NotFoundResponse."""
    _, mock_prompts = prompts_client_mocks
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_prompts.retrieve.side_effect = BadRequestError(
        message="not found", response=mock_response, body=None
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_prompt_handler(
            request=prompts_http_request,
            prompt_id="pmpt_missing",
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert detail["response"] == "Prompt not found"  # type: ignore[index]
    assert (
        detail["cause"]  # type: ignore[index]
        == "Prompt with ID pmpt_missing does not exist"
    )


@pytest.mark.asyncio
async def test_update_prompt_bad_request_maps_to_404(
    prompts_client_mocks: tuple[Any, Any],
    prompts_http_request: Request,
    mocker: MockerFixture,
) -> None:
    """update_prompt maps Llama Stack BadRequestError to 404 NotFoundResponse."""
    _, mock_prompts = prompts_client_mocks
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_prompts.update.side_effect = BadRequestError(
        message="invalid version", response=mock_response, body=None
    )

    body = PromptUpdateRequest(
        prompt="x", version=99, set_as_default=False, variables=None
    )
    with pytest.raises(HTTPException) as exc_info:
        await update_prompt_handler(
            request=prompts_http_request,
            prompt_id="pmpt_missing",
            auth=MOCK_AUTH,
            body=body,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert detail["response"] == "Prompt not found"  # type: ignore[index]
    assert (
        detail["cause"]  # type: ignore[index]
        == "Prompt with ID pmpt_missing does not exist"
    )
    mock_prompts.update.assert_awaited_once()
