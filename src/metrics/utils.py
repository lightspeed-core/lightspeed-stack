"""Utility functions for metrics handling."""

import metrics
from configuration import configuration
from log import get_logger
from providers.inference.registry import ProviderRegistry

logger = get_logger(__name__)


async def setup_model_metrics() -> None:
    """Perform setup of all metrics related to LLM model and provider.

    Reads the provider registry catalog instead of calling OGX, so no
    remote calls are required.  Should be called during startup after
    the registry has been initialized.
    """
    logger.info("Setting up model metrics")

    default_model_label = (
        configuration.inference.default_provider,
        configuration.inference.default_model,
    )

    registry = ProviderRegistry()
    for provider in registry.list_providers():
        provider_id = provider.provider_id
        for model in provider.list_catalog_models(model_type="llm"):
            model_name = model.name
            if provider_id and model_name:
                default_model_value = (
                    1 if (provider_id, model_name) == default_model_label else 0
                )
                metrics.provider_model_configuration.labels(
                    provider_id, model_name
                ).set(default_model_value)
                logger.debug(
                    "Set provider/model configuration for %s/%s to %d",
                    provider_id,
                    model_name,
                    default_model_value,
                )
    logger.info("Model metrics setup complete")
