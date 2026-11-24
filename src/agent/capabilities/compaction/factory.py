"""Factory for building compaction capabilities."""

from typing import Optional

from pydantic_ai_harness.compaction import TieredCompaction

from agent.types.settings import CompactionSettings
from configuration import configuration
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)
from providers.inference.registry import ProviderRegistry
from utils.tiered_compaction import build_tiered_compaction


class CompactionFactory:  # pylint: disable=too-few-public-methods
    """Factory for building compaction capabilities."""

    @staticmethod
    def build_capability(settings: CompactionSettings) -> Optional[TieredCompaction]:
        """Build a tiered compaction capability from compaction settings.

        Disabled settings and models that cannot be resolved produce no
        capability. The summarizer and tier thresholds come from the loaded
        compaction configuration.

        Parameters:
            settings: Compaction settings, including whether compaction is
                enabled and which provider and model summarize history.

        Returns:
            A tiered compaction capability, or ``None`` when compaction is
            disabled or the summarizer model cannot be resolved.

        """
        if not settings.enabled:
            return None

        try:
            model = ProviderRegistry().resolve_model_instance(
                "llm",
                settings.provider,
                settings.model,
            )
        except (
            ProviderNotFoundError,
            ModelNotAvailableError,
            ModelTypeNotSupportedError,
        ):
            return None

        # pylint: disable-next=fixme
        # TODO: Implement context window calculation from ProviderRegistry()
        context_window = None

        return build_tiered_compaction(configuration.compaction, model, context_window)
