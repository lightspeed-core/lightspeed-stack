"""Unit tests for functions defined in src/client.py."""

# pylint: disable=protected-access

import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import HTTPException
from ogx_client import APIConnectionError, APIStatusError
from pydantic import AnyHttpUrl, SecretStr
from pytest_mock import MockerFixture

from authorization.azure_token_manager import AzureEntraIDManager
from client import AsyncOgxClientHolder
from configuration import AzureEntraIdConfiguration
from models.config import LlamaStackConfiguration
from utils.types import Singleton


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset singleton state between tests."""
    Singleton._instances = {}


def test_async_client_get_client_method() -> None:
    """Test how get_client method works for uninitialized client."""
    client = AsyncOgxClientHolder()

    with pytest.raises(
        RuntimeError,
        match=(
            "AsyncOgxClient has not been initialised. "
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
    client = AsyncOgxClientHolder()
    await client.load(cfg)
    assert client is not None

    async with client.get_client() as ls_client:
        assert ls_client is not None
        assert not ls_client.is_closed()
        await ls_client.close()
        assert ls_client.is_closed()


@pytest.mark.asyncio
async def test_get_async_llama_stack_remote_client() -> None:
    """Test the initialization of asynchronous Llama Stack client in server mode."""
    cfg = LlamaStackConfiguration(
        url=AnyHttpUrl("http://localhost:8321"),
        api_key=None,
        use_as_library_client=False,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
        timeout=60,
    )
    client = AsyncOgxClientHolder()
    await client.load(cfg)
    assert client is not None

    ls_client = client.get_client()
    assert ls_client is not None


@pytest.mark.asyncio
async def test_get_async_llama_stack_wrong_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A library config with no legacy path routes to synthesis.

    With neither a legacy library_client_config_path nor a config block, the
    client treats the config as unified and attempts synthesis. Without the
    config-path env var pointing at the source lightspeed-stack.yaml, synthesis
    cannot proceed and raises a clear error. (The "library mode needs a run
    source" guarantee itself lives on the root Configuration validator.)
    """
    monkeypatch.delenv("LIGHTSPEED_STACK_CONFIG_PATH", raising=False)
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
        match="Cannot synthesize OGX config",
    ):
        client = AsyncOgxClientHolder()
        await client.load(cfg)


@pytest.mark.asyncio
async def test_update_azure_token_service_client() -> None:
    """Test update_azure_token replaces the service client with new provider headers."""
    AzureEntraIDManager._instances = {}  # type: ignore[attr-defined]
    manager = AzureEntraIDManager()
    manager.set_config(
        AzureEntraIdConfiguration(
            tenant_id=SecretStr("tenant"),
            client_id=SecretStr("client"),
            client_secret=SecretStr("secret"),
            scope="https://cognitiveservices.azure.com/.default",
        )
    )
    manager.set_base_url("https://api.example.com")
    manager._update_access_token("fresh-token", int(time.time()) + 3600)

    cfg = LlamaStackConfiguration(
        url=AnyHttpUrl("http://localhost:8321"),
        api_key=None,
        use_as_library_client=False,
        library_client_config_path=None,
        timeout=60,
    )
    holder = AsyncOgxClientHolder()
    await holder.load(cfg)
    original_client = holder.get_client()

    updated_client = await holder.update_azure_token()

    assert updated_client is not original_client
    assert holder.get_client() is updated_client
    provider_data_json = updated_client.default_headers.get(
        "X-OGX-Provider-Data"
    )
    provider_data = json.loads(provider_data_json)
    assert provider_data["azure_api_key"] == "fresh-token"
    assert provider_data["azure_api_base"] == "https://api.example.com"


@pytest.mark.asyncio
async def test_load_service_client_defers_azure_provider_data() -> None:
    """Test service client load does not set Azure headers until update_azure_token."""
    AzureEntraIDManager._instances = {}  # type: ignore[attr-defined]
    manager = AzureEntraIDManager()
    manager.set_config(
        AzureEntraIdConfiguration(
            tenant_id=SecretStr("tenant"),
            client_id=SecretStr("client"),
            client_secret=SecretStr("secret"),
            scope="https://cognitiveservices.azure.com/.default",
        )
    )
    manager.set_base_url("https://ols-test.openai.azure.com/openai/v1")
    manager._update_access_token("startup-token", int(time.time()) + 3600)

    cfg = LlamaStackConfiguration(
        url=AnyHttpUrl("http://localhost:8321"),
        api_key=None,
        use_as_library_client=False,
        library_client_config_path=None,
        timeout=60,
    )
    holder = AsyncOgxClientHolder()
    await holder.load(cfg)

    default_headers = holder.get_client().default_headers or {}
    assert "X-OGX-Provider-Data" not in default_headers

    updated_client = await holder.update_azure_token()
    provider_data_json = updated_client.default_headers.get(
        "X-OGX-Provider-Data"
    )
    assert provider_data_json is not None
    provider_data = json.loads(provider_data_json)
    assert provider_data["azure_api_key"] == "startup-token"
    assert (
        provider_data["azure_api_base"] == "https://ols-test.openai.azure.com/openai/v1"
    )


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
    holder = AsyncOgxClientHolder()
    await holder.load(cfg)

    original_client = holder.get_client()
    assert holder.is_library_client

    reloaded_client = await holder.reload_library_client()

    # Returns new client and updates holder
    assert reloaded_client is not original_client
    assert holder.get_client() is reloaded_client


class TestCheckModelAvailable:
    """Test cases for the check_model_available method."""

    EXPECTED_MODEL_ID = "google-vertex/publishers/google/models/gemini-2.5-flash"

    @pytest.fixture
    def holder_with_mock_client(
        self, mocker: MockerFixture
    ) -> tuple[AsyncOgxClientHolder, Any]:
        """Create a holder with a mocked async client."""
        holder = AsyncOgxClientHolder()
        mock_client = mocker.AsyncMock()
        holder._lsc = mock_client
        return holder, mock_client

    def _make_model(self, mocker: MockerFixture, model_id: str) -> Any:
        """Create a mock model with the given ID."""
        model = mocker.Mock()
        model.id = model_id
        return model

    @pytest.mark.asyncio
    async def test_model_available(
        self,
        mocker: MockerFixture,
        holder_with_mock_client: tuple[AsyncOgxClientHolder, Any],
    ) -> None:
        """Test returns True when the model is found in the registry."""
        holder, mock_client = holder_with_mock_client
        mock_client.models.list.return_value = [
            self._make_model(mocker, self.EXPECTED_MODEL_ID)
        ]

        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is True
        assert "is available" in reason

    @pytest.mark.asyncio
    async def test_model_not_found_service_client(
        self,
        mocker: MockerFixture,
        holder_with_mock_client: tuple[AsyncOgxClientHolder, Any],
    ) -> None:
        """Test returns False and skips reload for non-library (service) clients."""
        holder, mock_client = holder_with_mock_client
        mock_client.models.list.return_value = [self._make_model(mocker, "other/model")]

        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is False
        assert "not found in model registry" in reason

    @pytest.mark.asyncio
    async def test_client_not_initialized(self) -> None:
        """Test returns False when the client has not been initialized."""
        holder = AsyncOgxClientHolder()

        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is False
        assert "Client not initialized" in reason

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_factory",
        [
            pytest.param(
                lambda m: APIConnectionError(request=m.Mock()),
                id="connection_error",
            ),
            pytest.param(
                lambda m: APIStatusError(
                    message="Internal error",
                    response=m.Mock(status_code=500, headers={}),
                    body=None,
                ),
                id="api_status_error",
            ),
        ],
    )
    async def test_api_error(
        self,
        mocker: MockerFixture,
        holder_with_mock_client: tuple[AsyncOgxClientHolder, Any],
        exception_factory: Callable,
    ) -> None:
        """Test returns False when model list fails with API errors."""
        _, mock_client = holder_with_mock_client
        mock_client.models.list.side_effect = exception_factory(mocker)

        holder = AsyncOgxClientHolder()
        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is False
        assert "Error checking model availability" in reason

    @pytest.mark.asyncio
    async def test_model_found_after_reload(
        self,
        mocker: MockerFixture,
        holder_with_mock_client: tuple[AsyncOgxClientHolder, Any],
    ) -> None:
        """Test returns True when model is missing initially but found after reload."""
        holder, mock_client = holder_with_mock_client
        mocker.patch.object(
            AsyncOgxClientHolder,
            "is_library_client",
            new_callable=mocker.PropertyMock,
            return_value=True,
        )
        holder.reload_library_client = mocker.AsyncMock()

        wrong_model = self._make_model(mocker, "other/model")
        correct_model = self._make_model(mocker, self.EXPECTED_MODEL_ID)
        mock_client.models.list.side_effect = [[wrong_model], [correct_model]]

        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is True
        assert "after reload" in reason
        holder.reload_library_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reload_fails_returns_not_found(
        self,
        mocker: MockerFixture,
        holder_with_mock_client: tuple[AsyncOgxClientHolder, Any],
    ) -> None:
        """Test returns False when model is missing and client reload fails."""
        holder, mock_client = holder_with_mock_client
        mocker.patch.object(
            AsyncOgxClientHolder,
            "is_library_client",
            new_callable=mocker.PropertyMock,
            return_value=True,
        )
        holder.reload_library_client = mocker.AsyncMock(
            side_effect=RuntimeError("Cannot reload: config path not set")
        )
        mock_client.models.list.return_value = [self._make_model(mocker, "other/model")]

        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is False
        assert "not found in model registry" in reason

    @pytest.mark.asyncio
    async def test_reload_http_exception_returns_not_found(
        self,
        mocker: MockerFixture,
        holder_with_mock_client: tuple[AsyncOgxClientHolder, Any],
    ) -> None:
        """Test returns False when reload raises HTTPException."""
        holder, mock_client = holder_with_mock_client
        mocker.patch.object(
            AsyncOgxClientHolder,
            "is_library_client",
            new_callable=mocker.PropertyMock,
            return_value=True,
        )
        holder.reload_library_client = mocker.AsyncMock(
            side_effect=HTTPException(status_code=503, detail="Llama Stack unavailable")
        )
        mock_client.models.list.return_value = [self._make_model(mocker, "other/model")]

        available, reason = await holder.check_model_available(self.EXPECTED_MODEL_ID)

        assert available is False
        assert "not found in model registry" in reason
