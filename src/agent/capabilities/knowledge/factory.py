"""Factory for building knowledge capabilities from knowledge source settings."""

from dataclasses import replace
from typing import Optional

from sentence_transformers import CrossEncoder

from agent.types.settings import KnowledgeSourceSettings
from agent.types.settings.knowledge import KnowledgeSettings, OKPKnowledgeSourceSettings
from configuration import configuration
from knowledge.capability import Knowledge
from knowledge.registry import KnowledgeSourceRegistry
from knowledge.sources.base import KnowledgeSource
from knowledge.sources.okp import OkpKnowledgeSource
from log import get_logger
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)
from providers.inference.registry import ProviderRegistry

logger = get_logger(__name__)


class KnowledgeFactory:  # pylint: disable=too-few-public-methods
    """Factory for building knowledge capabilities."""

    @staticmethod
    def build_capabilities(
        settings: KnowledgeSettings,
    ) -> Optional[Knowledge]:
        """Build a knowledge capability from knowledge source settings.

        Sources are resolved against the process knowledge-source registry.
        Disabled settings are skipped. The query only selects which sources
        are enabled. Inline and tool chunk caps are read from the loaded RAG
        configuration. Each source's score weight is applied after merged
        matches are ranked. When inline reranking is enabled, the
        cross-encoder is loaded from the inference provider registry and
        attached to the capability. OKP product filters from the request are
        applied on a copy of the registered OKP source.

        Parameters:
            settings: Per-request knowledge source selection.

        Returns:
            One knowledge capability covering every enabled, registered
            source, or ``None`` when no sources are built. The capability's
            reranker is ``None`` when reranking is disabled or the model
            cannot be resolved.

        """
        if sources := _get_enabled_sources(settings.sources):
            return Knowledge(
                sources=sources,
                reranker=_get_reranker(),
                auto_max_matches=configuration.rag.retrieval.inline.max_chunks,
                tool_max_matches=configuration.rag.retrieval.tool.max_chunks,
            )
        return None


def _get_enabled_sources(
    settings: list[KnowledgeSourceSettings],
) -> list[KnowledgeSource]:
    """Return registered sources for the given settings, in settings order.

    Parameters:
        settings: Knowledge source settings to resolve.

    Returns:
        Registered sources whose settings are enabled. Disabled settings and
        unknown ids are skipped. Unknown ids are logged. An OKP source with
        request product filters is a copy of the registered source.

    """
    registry = KnowledgeSourceRegistry()
    sources: list[KnowledgeSource] = []
    for setting in settings:
        if not setting.enabled:
            continue
        source = registry.find_source(setting.id)
        if source is None:
            logger.warning(
                "Knowledge source '%s' is not registered; skipping",
                setting.id,
            )
            continue
        if isinstance(setting, OKPKnowledgeSourceSettings) and setting.products:
            if isinstance(source, OkpKnowledgeSource):
                source = replace(source, products=tuple(setting.products))
            else:
                logger.warning(
                    "Knowledge source '%s' is not an OKP source; ignoring product filters",
                    setting.id,
                )
        sources.append(source)
    return sources


def _get_reranker() -> Optional[CrossEncoder]:
    """Resolve the inline reranker from the inference provider registry.

    Uses ``configuration.reranker.provider`` and ``configuration.reranker.model``
    with the typed rerank getter. The model is already loaded on the provider.

    Returns:
        Loaded cross-encoder, or ``None`` when reranking is disabled or the
        model cannot be resolved.

    """
    reranker = configuration.reranker
    if reranker is None or not reranker.enabled:
        logger.debug("Reranker is disabled, not loading cross-encoder model")
        return None

    try:
        model = ProviderRegistry().resolve_model_instance(
            "rerank",
            reranker.provider,
            reranker.model,
        )
    except (
        ProviderNotFoundError,
        ModelNotAvailableError,
        ModelTypeNotSupportedError,
    ) as exc:
        logger.warning(
            "Could not resolve cross-encoder for reranking "
            "(provider=%s model=%s): %s",
            reranker.provider,
            reranker.model,
            exc,
        )
        return None

    logger.info(
        "Resolved cross-encoder for knowledge reranking: provider=%s model=%s",
        reranker.provider,
        reranker.model,
    )
    return model
