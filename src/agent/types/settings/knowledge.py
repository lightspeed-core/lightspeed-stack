"""Knowledge source settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass

from configuration import configuration
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

    @classmethod
    def from_query_request(cls, request: QueryRequest) -> list[KnowledgeSourceSettings]:
        """Build knowledge source settings for every configured source.

        Parameters:
            request: Incoming query. ``vector_store_ids`` of ``None`` leaves
                every source enabled. An empty list disables every source.
                Otherwise only the named sources stay enabled.

        Returns:
            One knowledge source setting per configured source, with
            ``enabled`` set from the request.

        """
        return [
            cls(
                id=source_id,
                enabled=_enabled_for_request(request.vector_store_ids, source_id),
            )
            for source_id in _configured_knowledge_ids()
        ]
