"""Unit tests for functions defined in src/client.py."""

import pytest

from client import LlamaStackClientHolder, AsyncLlamaStackClientHolder
from models.config import LLamaStackConfiguration


def test_get_llama_stack_library_client() -> None:
    """
    Tests initialization of the Llama Stack client in library client mode using a valid configuration file.
    """
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
    """
    Test initialization of Llama Stack in remote (server) client mode.
    
    Verifies that a Llama Stack client can be successfully created using a configuration with `use_as_library_client` set to False and a valid server URL.
    """
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
    """
    Test that initializing a Llama Stack client in library mode without a configuration path raises an exception.
    
    Verifies that an exception with the expected error message is raised if `library_client_config_path` is not set when `use_as_library_client` is True.
    """
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
    """
    Test asynchronous initialization of a Llama Stack client in library mode.
    
    Verifies that the AsyncLlamaStackClientHolder can be successfully loaded with a configuration specifying library client mode and a valid configuration path.
    """
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
    """
    Test asynchronous initialization of a Llama Stack client in remote (server) mode.
    
    Verifies that the AsyncLlamaStackClientHolder can be successfully loaded with a configuration specifying remote server mode.
    """
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
    """
    Test that initializing AsyncLlamaStackClientHolder with missing library_client_config_path raises an exception.
    
    Verifies that an exception with the expected error message is raised when attempting to load the client in library client mode without specifying the required configuration path.
    """
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
