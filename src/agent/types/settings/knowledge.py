"""Knowledge source settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from configuration import configuration
from constants import OKP_RAG_ID
from knowledge.sources.okp import OkpProductFilter
from models.api.requests import QueryRequest


def _enabled_for_request(requested: list[str] | None, item_id: str) -> bool:
    """Return whether one configured id stays enabled for this request.

    ``None`` leaves every configured id enabled. An empty list disables every
    id. Otherwise an id stays enabled when it appears in the request.

    Parameters:
        requested: Ids from the query, or ``None`` when the field was omitted.
        item_id: Configured id being considered.

    Returns:
        ``True`` when the id should stay enabled.

    """
    if requested is None:
        return True
    return item_id in requested


def _configured_knowledge_ids() -> list[str]:
    """Return knowledge source ids declared in the loaded RAG configuration.

    Returns:
        BYOK store ids, plus any retrieval source id that is not already a
        store, such as OKP.

    """
    rag = configuration.rag
    ids = [store.rag_id for store in rag.byok.stores]
    retrieval_ids = [
        *rag.retrieval.inline.sources,
        *rag.retrieval.tool.sources,
    ]
    for source_id in retrieval_ids:
        if source_id not in ids:
            ids.append(source_id)
    return ids


@dataclass
class KnowledgeSourceSettings:
    """Settings for a knowledge source."""

    id: str
    enabled: bool = True


@dataclass
class OKPKnowledgeSourceSettings(KnowledgeSourceSettings):
    """Settings for an OKP knowledge source.

    Attributes:
        products: Product restrictions from the query. ``None`` leaves the
            registered source unrestricted.

    """

    products: Optional[list[OkpProductFilter]] = None


@dataclass
class KnowledgeSettings:
    """Settings for a knowledge source."""

    sources: list[KnowledgeSourceSettings] = field(default_factory=list)

    @classmethod
    def from_query_request(cls, request: QueryRequest) -> KnowledgeSettings:
        """Build knowledge source settings for every configured source.

        Parameters:
            request: Incoming query. ``vector_store_ids`` of ``None`` leaves
                every source enabled. An empty list disables every source.
                Otherwise only the named sources stay enabled.

        Returns:
            One knowledge source setting per configured source, with
            ``enabled`` set from the request. The OKP setting also carries
            ``request.okp_products``.

        """
        sources: list[KnowledgeSourceSettings] = []
        for source_id in _configured_knowledge_ids():
            enabled = _enabled_for_request(request.vector_store_ids, source_id)
            if source_id == OKP_RAG_ID:
                sources.append(
                    OKPKnowledgeSourceSettings(
                        id=source_id,
                        enabled=enabled,
                        products=request.okp_products,
                    )
                )
            else:
                sources.append(KnowledgeSourceSettings(id=source_id, enabled=enabled))
        return cls(sources=sources)
