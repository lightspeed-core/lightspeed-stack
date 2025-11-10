"""Unit tests for functions defined in src/client.py."""

# pylint: disable=protected-access

import json
import pytest
from client import AsyncLlamaStackClientHolder
from models.config import LlamaStackConfiguration


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
    )
    cfg.library_client_config_path = None
    with pytest.raises(
        Exception,
        match="Configuration problem: library_client_config_path option is not set",
    ):
        client = AsyncLlamaStackClientHolder()
        await client.load(cfg)


@pytest.mark.asyncio
async def test_get_client_with_updated_azure_headers_preserves_existing_data() -> None:
    """Test that update preserves unrelated headers and overwrites Azure headers."""
    cfg = LlamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path=None,
    )
    holder = AsyncLlamaStackClientHolder()
    await holder.load(cfg)

    original_client = holder.get_client()

    # Pre-populate client with custom headers and provider data
    original_client._custom_headers["X-Custom-Header"] = "custom_value"
    original_provider_data = {
        "existing_field": "keep_this",
        "azure_api_key": "old_token",
        "azure_api_base": "https://old.example.com",
        "azure_api_version": "v0",
    }
    original_client._custom_headers["X-LlamaStack-Provider-Data"] = json.dumps(
        original_provider_data
    )

    access_token = "new_token"
    api_base = "https://new.example.com"
    api_version = "v1"

    new_client = holder.get_client_with_updated_azure_headers(
        access_token=access_token,
        api_base=api_base,
        api_version=api_version,
    )

    assert new_client is not original_client

    # Verify non-provider headers are preserved
    assert new_client.default_headers["X-Custom-Header"] == "custom_value"

    # Verify provider data headers are updated correctly
    provider_data_json = new_client.default_headers.get("X-LlamaStack-Provider-Data")
    assert provider_data_json is not None
    provider_data = json.loads(provider_data_json)

    # Existing unrelated fields are preserved
    assert provider_data["existing_field"] == "keep_this"

    # Azure fields are overwritten
    assert provider_data["azure_api_key"] == access_token
    assert provider_data["azure_api_base"] == api_base
    assert provider_data["azure_api_version"] == api_version
    assert provider_data.get("azure_api_type") is None
