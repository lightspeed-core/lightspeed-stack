"""Exceptions raised by inference providers."""

from providers.inference.types import ModelType, ProviderId


class ModelNotAvailableError(Exception):
    """Raised when a requested model is not in the provider catalog."""

    def __init__(self, name: str, model_type: str, provider_id: str) -> None:
        """Initialize with the unavailable model identity.

        Args:
            name: Local catalog model name that was requested.
            model_type: Requested model type (llm, embedding, or rerank).
            provider_id: Provider that rejected the request.

        """
        super().__init__(
            f"Model {name!r} of type {model_type!r} is not available "
            f"for provider {provider_id!r}"
        )
        self.name = name
        self.model_type = model_type
        self.provider_id = provider_id


class ModelTypeNotSupportedError(Exception):
    """Raised when a provider cannot serve the requested model type."""

    def __init__(self, model_type: ModelType, provider_id: ProviderId) -> None:
        """Initialize with the unsupported capability and provider.

        Args:
            model_type: Model type the provider does not support.
            provider_id: Provider that rejected the request.

        """
        super().__init__(
            f"Model type {model_type!r} is not supported by provider {provider_id!r}"
        )
        self.model_type = model_type
        self.provider_id = provider_id


class ProviderNotFoundError(Exception):
    """Raised when no provider is registered for the requested ID."""

    def __init__(self, provider_id: ProviderId) -> None:
        """Initialize with the unknown provider ID.

        Args:
            provider_id: Local provider identifier from configuration.

        """
        super().__init__(f"Inference provider {provider_id!r} is not registered")
        self.provider_id = provider_id


class NoModelConfiguredError(Exception):
    """Raised when no model can be resolved after soft fallbacks."""

    def __init__(self, model_type: ModelType) -> None:
        """Initialize with the unresolved model capability.

        Args:
            model_type: Model type that could not be resolved.

        """
        super().__init__(
            f"No {model_type!r} model is configured or available in the catalog"
        )
        self.model_type = model_type
