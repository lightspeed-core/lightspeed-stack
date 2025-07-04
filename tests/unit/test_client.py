"""Unit tests for functions defined in src/client.py."""

import pytest

from client import LlamaStackClientHolder, AsyncLlamaStackClientHolder
from models.config import LLamaStackConfiguration


# [tisnik] Need to resolve dependencies on CI to be able to run this tests
def test_get_llama_stack_library_client() -> None:
    cfg = LLamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    client = LlamaStackClientHolder()
    client.load(cfg)
    assert client is not None


def test_get_llama_stack_remote_client() -> None:
    cfg = LLamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    client = LlamaStackClientHolder()
    client.load(cfg)
    assert client is not None


def test_get_llama_stack_wrong_configuration() -> None:
    cfg = LLamaStackConfiguration(
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
        client = LlamaStackClientHolder()
        client.load(cfg)


async def test_get_async_llama_stack_library_client() -> None:
    cfg = LLamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None


async def test_get_async_llama_stack_remote_client() -> None:
    cfg = LLamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None


async def test_get_async_llama_stack_wrong_configuration() -> None:
    cfg = LLamaStackConfiguration(
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
