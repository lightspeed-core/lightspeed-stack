"""OKP RAG retriever over the RHOKP MCP server.

The RHOKP container ships an MCP server that encapsulates embeddings and Solr
querying server-side. This retriever connects to that server over streamable
HTTP (via pydantic-ai's :class:`~pydantic_ai.mcp.MCPToolset`), calls its search
tool with the raw user query, and maps the returned documents to the
backend-neutral :class:`~models.common.turn_summary.RAGChunk` /
:class:`~models.common.turn_summary.ReferencedDocument` models.

Unlike the OGX/Solr OKP path, this retriever needs no client-side embedding
model and does no OGX ``run.yaml`` enrichment: the MCP server does the work. The
Solr transport is always wired at launch and serves as the query-time fallback,
selected whenever :func:`configuration.okp_mcp_available` returns False (the
RHOKP endpoint is not MCP-capable or was unreachable).
"""

from pydantic_ai_lightspeed.retrieval.okp_mcp._provider import OkpMcpRetriever

__all__ = ["OkpMcpRetriever"]
