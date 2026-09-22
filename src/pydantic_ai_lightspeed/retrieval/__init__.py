"""Pydantic-AI-side RAG context retrievers.

This package holds retrievers that fetch RAG context on the Pydantic-AI side of
the stack (i.e. without going through the OGX ``vector_io`` client). Retrievers
emit the backend-neutral chunk/document models
(:class:`models.common.turn_summary.RAGChunk` /
:class:`models.common.turn_summary.ReferencedDocument`) so any retriever feeds
the same response/transcript shape.

Currently exposes:
    - :mod:`pydantic_ai_lightspeed.retrieval.okp_mcp`: OKP RAG over the RHOKP
      MCP server (the Pydantic-AI analog of the OGX/Solr OKP ``vector_io``
      path).
"""
