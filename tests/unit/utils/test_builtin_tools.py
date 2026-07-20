# pylint: disable=protected-access

"""Unit tests for Llama Stack file-search tool discovery."""

import pytest
from fastapi import HTTPException
from ogx_client import APIConnectionError
from ogx_client.types.shared.provider_info import ProviderInfo
from pytest_mock import MockerFixture

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
async def test_get_file_search_tools_returns_static_catalog_when_provider_present(
    mocker: MockerFixture,
) -> None:
    """Return the known file-search catalog when the provider is configured."""
    client = mocker.AsyncMock()
    client.providers.list = mocker.AsyncMock(
        return_value=[
            _provider(
                provider_id="file-search",
                provider_type="inline::file-search",
            )
        ]
    )

    tools = await get_file_search_tools_from_lls(client)

    assert len(tools) == 2
    by_id = {tool.identifier: tool for tool in tools}
    assert set(by_id) == {"insert_into_memory", "file_search"}

    memory_tool = by_id["insert_into_memory"]
    assert memory_tool.description == "Insert documents into memory"
    assert memory_tool.parameters == []
    assert memory_tool.provider_id == "file-search"
    assert memory_tool.toolgroup_id == "builtin::file_search"
    assert memory_tool.server_source == "builtin"
    assert memory_tool.type == "tool"

    search_tool = by_id["file_search"]
    assert search_tool.description == "Search files for relevant information"
    assert len(search_tool.parameters) == 1
    query_param = search_tool.parameters[0]
    assert query_param.name == "query"
    assert query_param.parameter_type == "string"
    assert query_param.required is True
    assert query_param.default is None
    assert all(tool.provider_id == "file-search" for tool in tools)
    assert all(tool.toolgroup_id == "builtin::file_search" for tool in tools)
    assert all(tool.server_source == "builtin" for tool in tools)

    client.get.assert_not_called()


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
    assert detail["response"] == "Unable to connect to OGX"
