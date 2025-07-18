"""Utility functions for metrics handling."""

from client import LlamaStackClientHolder
from log import get_logger
import metrics

logger = get_logger(__name__)


# TODO(lucasagomes): Change this metric once we are allowed to set the the
# default model/provider via the configuration.The default provider/model
# will be set to 1, and the rest will be set to 0.
def setup_model_metrics() -> None:
    """Perform setup of all metrics related to LLM model and provider."""
    client = LlamaStackClientHolder().get_client()
    models = [
        model
        for model in client.models.list()
        if model.model_type == "llm"  # pyright: ignore[reportAttributeAccessIssue]
    ]

    for model in models:
        provider = model.provider_id
        model_name = model.identifier
        if provider and model_name:
            label_key = (provider, model_name)
            metrics.provider_model_configuration.labels(*label_key).set(1)
            logger.debug(
                "Set provider/model configuration for %s/%s to 1",
                provider,
                model_name,
            )
