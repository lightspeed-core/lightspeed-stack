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

- Input: `{"query": str, "rows": int}` (`rows` clamped server-side to 1..20),
  plus optional `product` / `product_version` scalars driven by the query-time
  `okp` request filter.
- Output: `{"response": {"numFound": int, "docs": [SolrDoc]}}` where each
  `SolrDoc` may carry `chunk` (text), `score`, `title`, `doc_id`,
  `online_source_url`, `source_path`, `product`, `product_version`.

## Configuration

There is no MCP-specific configuration block. The config is the same as the
pre-MCP OKP config; the MCP endpoint is always derived from `rhokp_url` (the
RHOKP MCP server is always served at its `/mcp` path):

```yaml
rag:
  okp:
    rhokp_url: ${env.RH_SERVER_OKP}      # base URL; MCP endpoint = rhokp_url/mcp
    offline: true
  retrieval:
    inline:
      sources: ["okp"]                    # "okp" activates OKP
```

Transport selection is automatic and per-request. The Solr `vector_io`
transport is always wired at launch; at query time the MCP transport is
preferred whenever `configuration.okp_mcp_available()` is True (the endpoint is
probed and TTL-cached so an upgraded RHOKP is adopted without a restart), and
the Solr path serves as the fallback when MCP is unavailable or hard-fails.
</content>
