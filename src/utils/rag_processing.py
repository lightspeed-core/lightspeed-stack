"""Utility functions for processing RAG chunks and referenced documents in streaming responses."""

from typing import Optional, List, Dict, Set, Tuple, Any
from utils.types import TurnSummary


def process_rag_chunks_for_streaming(summary: TurnSummary) -> Optional[List[Dict[str, Any]]]:
    """
    Process RAG chunks from TurnSummary into streaming response format.

    Parameters:
        summary (TurnSummary): Summary containing RAG chunks data.

    Returns:
        Optional[List[Dict[str, Any]]]: List of RAG chunks in streaming format, or None if empty.
    """
    if not summary.rag_chunks:
        return None
    
    rag_chunks = [
        {
            "content": chunk.content,
            "source": chunk.source,
            "score": chunk.score
        }
        for chunk in summary.rag_chunks
    ]
    
    return rag_chunks if rag_chunks else None


def _extract_referenced_documents_from_rag_chunks(summary: TurnSummary) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """
    Extract referenced documents from RAG chunks for streaming format.

    Parameters:
        summary (TurnSummary): Summary containing RAG chunks data.

    Returns:
        Tuple[List[Dict[str, Any]], Set[str]]: A tuple containing the list of referenced documents
        and a set of document sources already processed.
    """
    referenced_docs = []
    doc_sources = set()
    
    for chunk in summary.rag_chunks:
        if chunk.source and chunk.source not in doc_sources:
            doc_sources.add(chunk.source)
            referenced_docs.append({
                "doc_url": chunk.source if chunk.source.startswith("http") else None,
                "doc_title": chunk.source,
                "chunk_count": sum(1 for c in summary.rag_chunks if c.source == chunk.source)
            })
    
    return referenced_docs, doc_sources


def _merge_legacy_referenced_documents(metadata_map: Dict[str, Any], doc_sources: Set[str]) -> List[Dict[str, Any]]:
    """
    Merge legacy referenced documents from metadata_map with existing document sources for streaming.

    Parameters:
        metadata_map (Dict[str, Any]): A mapping containing metadata about referenced documents.
        doc_sources (Set[str]): Set of document sources already processed.

    Returns:
        List[Dict[str, Any]]: List of additional referenced documents from legacy format.
    """
    legacy_docs = []
    
    for v in filter(
        lambda v: ("docs_url" in v) and ("title" in v),
        metadata_map.values(),
    ):
        if v["title"] not in doc_sources:
            doc_sources.add(v["title"])
            legacy_docs.append({
                "doc_url": v["docs_url"],
                "doc_title": v["title"],
            })
    
    return legacy_docs


def build_referenced_documents_list_for_streaming(summary: TurnSummary, metadata_map: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Build complete list of referenced documents from both RAG chunks and legacy metadata for streaming.

    Parameters:
        summary (TurnSummary): Summary containing RAG chunks data.
        metadata_map (Dict[str, Any]): A mapping containing metadata about referenced documents.

    Returns:
        Optional[List[Dict[str, Any]]]: Complete list of referenced documents, or None if empty.
    """
    # Extract documents from RAG chunks
    rag_docs, doc_sources = _extract_referenced_documents_from_rag_chunks(summary)
    
    # Merge with legacy documents
    legacy_docs = _merge_legacy_referenced_documents(metadata_map, doc_sources)
    
    # Combine all documents
    all_docs = rag_docs + legacy_docs
    
    return all_docs if all_docs else None
