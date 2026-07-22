"""Utility functions for metrics handling."""

from lightspeed_stack import metrics
from lightspeed_stack.client import AsyncLlamaStackClientHolder
from lightspeed_stack.configuration import configuration
from lightspeed_stack.log import get_logger
from lightspeed_stack.utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)


async def setup_model_metrics() -> None:
    """Perform setup of all metrics related to LLM model and provider.

    Should be called during startup when service is in healthy mode.
    Skipped in degraded mode to avoid blocking on unavailable llama-stack.
    """
    logger.info("Setting up model metrics")
    check_configuration_loaded(configuration)
    model_list = await AsyncLlamaStackClientHolder().get_client().models.list()

    models = [
        model
        for model in model_list
        if model.custom_metadata and model.custom_metadata.get("model_type") == "llm"
    ]

    default_model_label = (
        configuration.inference.default_provider,
        configuration.inference.default_model,
    )

    for model in models:
        provider = (
            str(model.custom_metadata.get("provider_id", ""))
            if model.custom_metadata
            else ""
        )
        model_name = model.id
        if provider and model_name:
            # If the model/provider combination is the default, set the metric value to 1
            # Otherwise, set it to 0
            default_model_value = 0
            label_key = (provider, model_name)
            if label_key == default_model_label:
                default_model_value = 1

            # Set the metric for the provider/model configuration
            metrics.provider_model_configuration.labels(*label_key).set(
                default_model_value
            )
            logger.debug(
                "Set provider/model configuration for %s/%s to %d",
                provider,
                model_name,
                default_model_value,
            )
    logger.info("Model metrics setup complete")
