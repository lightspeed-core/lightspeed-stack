# okp_mcp

OKP RAG retriever over the RHOKP MCP server.

The RHOKP container ships an MCP server that encapsulates embeddings and Solr
querying server-side. This retriever connects to it over streamable HTTP,
calls its search tool with the raw user query, and maps the returned documents
to `RAGChunk` / `ReferencedDocument`.

Compared to the OGX/Solr OKP `vector_io` path, there is **no** local embedding
model, **no** `vector_io` provider, and **no** OGX `run.yaml` enrichment — the
MCP server does that work.

## Files

- `_client.py` — thin wrapper over pydantic-ai's `MCPToolset`
  (`direct_call_tool`) that performs a single, programmatic search call. No
  agent/LLM is involved.
- `_provider.py` — `OkpMcpRetriever`: `fetch(query) -> (list[RAGChunk],
  list[ReferencedDocument])`. Builds itself from configuration via
  `OkpMcpRetriever.from_configuration()`.

## RHOKP MCP `search` tool contract

- Input: `{"query": str, "rows": int}` (`rows` clamped server-side to 1..20).
- Output: `{"response": {"numFound": int, "docs": [SolrDoc]}}` where each
  `SolrDoc` may carry `chunk` (text), `score`, `title`, `doc_id`,
  `online_source_url`, `source_path`, `product`, `product_version`.

## Configuration

Enabled via `rag.okp.mcp` (see `models.config.OkpMcpConfiguration`):

```yaml
rag:
  okp:
    rhokp_url: ${env.RH_SERVER_OKP}      # base URL for offline document links
    offline: true
    mcp:
      enabled: true
      url: ${env.RH_SERVER_OKP_MCP}      # defaults to http://localhost:8080/mcp
      tool_name: search
      max_chunks: 5
  retrieval:
    inline:
      sources: ["okp"]                    # "okp" still activates OKP
```

When `mcp.enabled` is false, the Solr `vector_io` transport is used instead.
</content>
