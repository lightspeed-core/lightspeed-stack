"""OKP RAG retriever over the RHOKP MCP server.

The RHOKP container ships an MCP server that encapsulates embeddings and Solr
querying server-side. This retriever connects to that server over streamable
HTTP (via pydantic-ai's :class:`~pydantic_ai.mcp.MCPToolset`), calls its search
tool with the raw user query, and maps the returned documents to the
backend-neutral :class:`~models.common.turn_summary.RAGChunk` /
:class:`~models.common.turn_summary.ReferencedDocument` models.

Unlike the OGX/Solr OKP path, there is no client-side embedding model, no
``vector_io`` provider, and no OGX ``run.yaml`` enrichment: the MCP server does
the work. The Solr transport remains intact and is selected whenever
:func:`configuration.okp_rag_mcp_enabled` returns False.
"""

from pydantic_ai_lightspeed.retrieval.okp_mcp._provider import OkpMcpRetriever

__all__ = ["OkpMcpRetriever"]
