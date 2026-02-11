"""Unit tests for functions defined in src/client.py."""

# pylint: disable=protected-access

import json

import pytest
from client import AsyncLlamaStackClientHolder
from models.config import LlamaStackConfiguration
from utils.types import Singleton


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset singleton state between tests."""
    Singleton._instances = {}


def test_async_client_get_client_method() -> None:
    """Test how get_client method works for uninitialized client."""
    client = AsyncLlamaStackClientHolder()

    with pytest.raises(
        RuntimeError,
        match=(
            "AsyncLlamaStackClient has not been initialised. "
            "Ensure 'load\\(..\\)' has been called."
        ),
    ):
        client.get_client()


@pytest.mark.asyncio
async def test_get_async_llama_stack_library_client() -> None:
    """Test the initialization of asynchronous Llama Stack client in library mode."""
    cfg = LlamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
        timeout=60,
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None

    async with client.get_client() as ls_client:
        assert ls_client is not None
        assert not ls_client.is_closed()
        await ls_client.close()
        assert ls_client.is_closed()


async def test_get_async_llama_stack_remote_client() -> None:
    """Test the initialization of asynchronous Llama Stack client in server mode."""
    cfg = LlamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
        timeout=60,
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None

    ls_client = client.get_client()
    assert ls_client is not None


async def test_get_async_llama_stack_wrong_configuration() -> None:
    """Test if configuration is checked before Llama Stack is initialized."""
    cfg = LlamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
        timeout=60,
    )
    cfg.library_client_config_path = None
    with pytest.raises(
        ValueError,
        match="Configuration problem: library_client_config_path is not set",
    ):
        client = AsyncLlamaStackClientHolder()
        await client.load(cfg)


@pytest.mark.asyncio
async def test_update_provider_data_service_client() -> None:
    """Test that update_provider_data updates headers for service clients."""
    cfg = LlamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path=None,
        timeout=60,
    )
    holder = AsyncLlamaStackClientHolder()
    await holder.load(cfg)

    original_client = holder.get_client()
    assert not holder.is_library_client

    # Pre-populate with existing provider data via headers
    original_client._custom_headers["X-LlamaStack-Provider-Data"] = json.dumps(
        {
            "existing_field": "keep_this",
            "azure_api_key": "old_token",
        }
    )

    updated_client = holder.update_provider_data(
        {
            "azure_api_key": "new_token",
            "azure_api_base": "https://new.example.com",
        }
    )

    # Returns new client and updates holder
    assert updated_client is not original_client
    assert holder.get_client() is updated_client

    # Verify headers on updated client
    provider_data_json = updated_client.default_headers.get(
        "X-LlamaStack-Provider-Data"
    )
    assert provider_data_json is not None
    assert isinstance(provider_data_json, str)
    provider_data = json.loads(provider_data_json)

    # Existing fields preserved, new fields updated
    assert provider_data["existing_field"] == "keep_this"
    assert provider_data["azure_api_key"] == "new_token"
    assert provider_data["azure_api_base"] == "https://new.example.com"


@pytest.mark.asyncio
async def test_reload_library_client() -> None:
    """Test that reload_library_client reloads and returns new client."""
    cfg = LlamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
        timeout=60,
    )
    holder = AsyncLlamaStackClientHolder()
    await holder.load(cfg)

    original_client = holder.get_client()
    assert holder.is_library_client

    reloaded_client = await holder.reload_library_client()

    # Returns new client and updates holder
    assert reloaded_client is not original_client
    assert holder.get_client() is reloaded_client
