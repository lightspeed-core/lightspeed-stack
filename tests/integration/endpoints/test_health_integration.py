"""Integration tests for the /health endpoint."""

from typing import Optional

import pytest
from fastapi import Response
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import SecretStr

from app.endpoints.health import (
    liveness_probe_get_method,
    readiness_probe_get_method,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.common.health import HealthStatus
from models.config import (
    AllowedModel,
    InferenceConfiguration,
    OpenAIInferenceProviderConfig,
    OpenAIInferenceProviderEntry,
)
from providers.inference.registry import ProviderRegistry
from utils.types import Singleton


@pytest.fixture(name="mock_registry", autouse=True)
def mock_registry():
    """Isolate the ProviderRegistry singleton per test."""
    Singleton._instances.pop(ProviderRegistry, None)  # pylint: disable=protected-access
    yield
    Singleton._instances.pop(ProviderRegistry, None)  # pylint: disable=protected-access


def _setup_inference(
    config: AppConfig,
    *,
    default_provider: Optional[str] = "openai",
    default_model: Optional[str] = "chat",
) -> None:
    """Configure inference with an OpenAI provider entry and default model settings.

    Args:
        config: Application configuration to mutate.
        default_provider: Provider ID to set as default.
        default_model: Model name to set as default.

    """
    assert config._configuration is not None  # pylint: disable=protected-access

    entry = OpenAIInferenceProviderEntry(
        type="openai",
        id="openai",
        skip_model_discovery=True,
        allowed_models=[
            AllowedModel(
                name="chat",
                provider_model_id="gpt-4o-mini",
                model_type="llm",
            ),
        ],
        model_profiles_path=None,
        api_key_env=None,
        extra=None,
        config=OpenAIInferenceProviderConfig(
            api_key=SecretStr("tasty"), base_url="https://example.com"
        ),
    )

    config._configuration.inference = (  # pylint: disable=protected-access
        InferenceConfiguration.model_validate(
            {
                "providers": [entry.model_dump()],
                "default_provider": default_provider,
                "default_model": default_model,
            }
        )
    )


@pytest.mark.asyncio
async def test_health_liveness(
    test_config: AppConfig,
    test_auth: AuthTuple,
) -> None:
    """Test that liveness probe endpoint is alive

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Real noop authentication is used
    - Response structure matches expected format

    Parameters:
    ----------
        test_config: Loads test configuration
        test_auth: noop authentication tuple

    Returns:
    -------
        None

    """
    _ = test_config

    response = await liveness_probe_get_method(auth=test_auth)

    # Verify that service is alive
    assert response.alive is True


@pytest.mark.asyncio
async def test_health_readiness_happy_path(
    test_config: AppConfig,
    test_response: Response,
    test_auth: AuthTuple,
) -> None:
    """Test readiness returns 200 when registry is initialized and default model is available.

    Args:
        test_config: Loaded test configuration.
        test_response: FastAPI response object.
        test_auth: Noop authentication tuple.

    """
    _setup_inference(test_config)

    registry = ProviderRegistry()
    await registry.initialize(test_config.inference)

    result = await readiness_probe_get_method(auth=test_auth, response=test_response)

    # Verify that service returns readiness response
    assert result.ready is True
    assert result.reason == "All providers are healthy"
    assert result.overall_status == HealthStatus.HEALTHY
    assert result.impacts is None


@pytest.mark.asyncio
async def test_health_readiness_without_default_provider_and_model(
    test_config: AppConfig,
    test_response: Response,
    test_auth: AuthTuple,
) -> None:
    """Test readiness returns 200 when registry is initialized and no defaults are configured.

    Args:
        test_config: Loaded test configuration.
        test_response: FastAPI response object.
        test_auth: Noop authentication tuple.

    """
    _setup_inference(test_config, default_provider=None, default_model=None)

    registry = ProviderRegistry()
    await registry.initialize(test_config.inference)

    result = await readiness_probe_get_method(auth=test_auth, response=test_response)

    # Verify that service returns readiness response
    assert result.ready is True
    assert result.reason == "All providers are healthy"
    assert result.overall_status == HealthStatus.HEALTHY
    assert result.impacts is None


@pytest.mark.asyncio
async def test_health_readiness_without_provider_registry_being_initialized(
    test_response: Response,
    test_auth: AuthTuple,
) -> None:
    """Test readiness returns 503 when provider registry has not been initialized.

    Args:
        test_response: FastAPI response object.
        test_auth: Noop authentication tuple.

    """
    result = await readiness_probe_get_method(auth=test_auth, response=test_response)

    # Verify that service returns readiness response
    assert result.ready is False
    assert result.reason == "Provider registry is not initialized"
    assert result.overall_status == HealthStatus.UNHEALTHY
    assert result.impacts is not None
    assert "LLM inference unavailable" in result.impacts


class TestHealthEndpointOtel:
    """OTEL instrumentation tests for health probe endpoints."""

    @pytest.mark.asyncio
    async def test_readiness_emits_span_on_healthy(
        self,
        test_config: AppConfig,
        test_response: Response,
        test_auth: AuthTuple,
        otel_collector: InMemorySpanExporter,
    ) -> None:
        """Test that a healthy readiness check emits a span with status 200."""
        otel_collector.clear()
        _setup_inference(test_config)

        registry = ProviderRegistry()
        await registry.initialize(test_config.inference)

        await readiness_probe_get_method(auth=test_auth, response=test_response)

        spans = otel_collector.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "readiness.handle_request"
        assert span.attributes is not None
        assert span.attributes["http.status_code"] == 200

    @pytest.mark.asyncio
    async def test_readiness_emits_span_on_registry_not_initialized(
        self,
        test_response: Response,
        test_auth: AuthTuple,
        otel_collector: InMemorySpanExporter,
    ) -> None:
        """Test that an uninitialized registry emits a span with status 503."""
        otel_collector.clear()

        await readiness_probe_get_method(auth=test_auth, response=test_response)

        spans = otel_collector.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "readiness.handle_request"
        assert span.attributes is not None
        assert span.attributes["http.status_code"] == 503

    @pytest.mark.asyncio
    async def test_liveness_emits_span(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        otel_collector: InMemorySpanExporter,
    ) -> None:
        """Test that the liveness probe emits a span with status 200."""
        _ = test_config
        otel_collector.clear()

        await liveness_probe_get_method(auth=test_auth)

        spans = otel_collector.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "liveness.handle_request"
        assert span.attributes is not None
        assert span.attributes["http.status_code"] == 200
