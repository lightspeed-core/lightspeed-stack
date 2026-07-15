# pylint: disable=protected-access

"""Unit tests for Llama Stack file-search tool discovery."""

from typing import Any

import pytest
from fastapi import HTTPException
from llama_stack_client import APIConnectionError, APIStatusError
from llama_stack_client.types.shared.provider_info import ProviderInfo
from pytest_mock import MockerFixture

from models.common.tools import ListToolDefsResponse, ToolDef
from utils.builtin_tools import get_file_search_tools_from_lls


def _provider(
    *,
    provider_id: str,
    provider_type: str,
    api: str = "tool_runtime",
) -> ProviderInfo:
    """Build a ProviderInfo test fixture."""
    return ProviderInfo(
        api=api,
        provider_id=provider_id,
        provider_type=provider_type,
        config={},
        health={},
    )


@pytest.mark.asyncio
async def test_get_file_search_tools_returns_empty_when_not_configured(
    mocker: MockerFixture,
) -> None:
    """Return no tools when Llama Stack has no file-search provider."""
    client = mocker.AsyncMock()
    client.providers.list = mocker.AsyncMock(
        return_value=[
            _provider(
                provider_id="model-context-protocol",
                provider_type="remote::model-context-protocol",
            )
        ]
    )

    tools = await get_file_search_tools_from_lls(client)

    assert tools == []
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_file_search_tools_discovers_from_lls(
    mocker: MockerFixture,
) -> None:
    """Return file-search tools from Llama Stack when provider is configured."""
    client = mocker.AsyncMock()
    client.providers.list = mocker.AsyncMock(
        return_value=[
            _provider(
                provider_id="file-search",
                provider_type="inline::file-search",
            )
        ]
    )
    client.get = mocker.AsyncMock(
        return_value=ListToolDefsResponse(
            data=[
                ToolDef(
                    name="insert_into_memory",
                    description="Insert documents into memory",
                    toolgroup_id="builtin::file_search",
                ),
                ToolDef(
                    name="file_search",
                    description="Search files for relevant information",
                    toolgroup_id="builtin::file_search",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            }
                        },
                        "required": ["query"],
                    },
                ),
            ]
        )
    )

    tools = await get_file_search_tools_from_lls(client)

    assert len(tools) == 2
    identifiers = {tool.identifier for tool in tools}
    assert identifiers == {"insert_into_memory", "file_search"}
    assert all(tool.provider_id == "file-search" for tool in tools)
    assert all(tool.toolgroup_id == "builtin::file_search" for tool in tools)
    assert all(tool.server_source == "builtin" for tool in tools)

    client.get.assert_awaited_once()
    call_kwargs: dict[str, Any] = client.get.await_args.kwargs
    assert call_kwargs["cast_to"] is ListToolDefsResponse
    assert call_kwargs["options"]["params"] == {"toolgroup_id": "builtin::file_search"}


@pytest.mark.asyncio
async def test_get_file_search_tools_raises_503_on_provider_connection_error(
    mocker: MockerFixture,
) -> None:
    """Raise HTTP 503 when Llama Stack is unreachable during provider discovery."""
    client = mocker.AsyncMock()
    client.providers.list = mocker.AsyncMock(
        side_effect=APIConnectionError(message="down", request=mocker.Mock())
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_file_search_tools_from_lls(client)

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"


@pytest.mark.asyncio
async def test_get_file_search_tools_returns_empty_on_tools_api_error(
    mocker: MockerFixture,
) -> None:
    """Return no tools when file-search tool discovery fails with APIStatusError."""
    client = mocker.AsyncMock()
    client.providers.list = mocker.AsyncMock(
        return_value=[
            _provider(
                provider_id="file-search",
                provider_type="inline::file-search",
            )
        ]
    )
    client.get = mocker.AsyncMock(
        side_effect=APIStatusError(
            message="missing",
            response=mocker.Mock(request=None),
            body=None,
        )
    )

    tools = await get_file_search_tools_from_lls(client)

    assert tools == []


@pytest.mark.asyncio
async def test_get_file_search_tools_raises_503_on_tools_connection_error(
    mocker: MockerFixture,
) -> None:
    """Raise HTTP 503 when Llama Stack is unreachable during tools listing."""
    client = mocker.AsyncMock()
    client.providers.list = mocker.AsyncMock(
        return_value=[
            _provider(
                provider_id="file-search",
                provider_type="inline::file-search",
            )
        ]
    )
    client.get = mocker.AsyncMock(
        side_effect=APIConnectionError(message="down", request=mocker.Mock())
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_file_search_tools_from_lls(client)

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"
