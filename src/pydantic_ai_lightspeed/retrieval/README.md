# retrieval

Pydantic-AI-side RAG context retrievers. Retrievers here fetch RAG context
without going through the OGX `vector_io` client, and emit the backend-neutral
`RAGChunk` / `ReferencedDocument` models from
`models.common.turn_summary` so any retriever produces the same
response/transcript shape.

## Subpackages

- `okp_mcp/` — OKP RAG over the RHOKP MCP server. The Pydantic-AI analog of the
  OGX/Solr OKP `vector_io` path.

## Relationship to the Solr OKP path

The Solr OKP retriever (`utils/vector_search.py:_fetch_okp_rag`) and the MCP
retriever are two transports for the same `"okp"` RAG source, selected per
request by `utils/vector_search.py:_fetch_okp`. The Solr `vector_io` provider is
always wired at launch; at query time the RHOKP MCP transport is preferred
whenever `configuration.okp_mcp_available()` is True (the endpoint, always at
`rhokp_url/mcp`, is probed and cached with a TTL so an upgraded RHOKP is adopted
without restart), and the Solr path serves as the fallback. Both return
`tuple[list[RAGChunk], list[ReferencedDocument]]` and plug into the same
`build_rag_context` merge/rerank/format pipeline (Option A in the design doc).
</content>
