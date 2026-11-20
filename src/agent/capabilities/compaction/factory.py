"""Factory for building compaction capabilities."""

from dataclasses import replace
from typing import Optional

from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

import constants
from agent.types.settings import CompactionSettings
from configuration import configuration
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)
from providers.inference.registry import ProviderRegistry
from utils.token_estimator import estimate_tokens


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

        keep_tokens = None
        if context_window is not None:
            keep_tokens = int(
                context_window * configuration.compaction.buffer_max_ratio
            )

        summarizer = SummarizingCompaction(
            model=model,
            max_messages=1,
            keep_messages=configuration.compaction.buffer_turns,
            keep_tokens=keep_tokens,
            tokenizer=estimate_tokens,
            incremental=True,
            preserve_first_user_message=True,
            keep_user_messages=True,
        )

        if configuration.compaction.summary_prompt is not None:
            summarizer = replace(
                summarizer, summary_prompt=configuration.compaction.summary_prompt
            )

        return TieredCompaction(
            tiers=[
                ClampOversizedMessages(
                    max_part_tokens=50000, tokenizer=estimate_tokens
                ),
                ClearToolResults(max_tokens=1, tokenizer=estimate_tokens),
                summarizer,
            ],
            target_fraction=configuration.compaction.threshold_ratio,
            context_window=context_window,
            fallback_context_window=constants.DEFAULT_CONTEXT_WINDOW,
            tokenizer=estimate_tokens,
        )
