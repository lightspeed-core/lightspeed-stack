# Feature design for Knowledge capability (static RAG)

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-10-06                                |
| **Component**      | lightspeed-stack                          |
| **Authors**        | @jboos                                    |
| **Feature**        | [LCORE-4573](https://redhat.atlassian.net/browse/LCORE-4573) |
| **Epic / Feature** | [UIESTRAT-215](https://redhat.atlassian.net/browse/UIESTRAT-215) |
| **Spike**          | [LCORE-4291](https://redhat.atlassian.net/browse/LCORE-4291) |
| **Links**          | [Spike doc](rag-vector-stores-migration-spike.md), [RAG guide](../../user_doc/rag_guide.md), [OKP guide](../../user_doc/okp_guide.md) |

This is the spec for the LCS Knowledge capability. Native `rag-content`
writers (LCORE-3302) are a sibling epic; the shared contract is the
on-disk store format (spike T2).

## What

A pydantic-ai `Knowledge` capability on LCS agents that searches
config-declared knowledge sources without OGX `vector_io` or OGX
`file_search`.

Public YAML stays `rag:`. The factory maps
`rag.byok.stores` plus `rag.okp` onto `KnowledgeSource`s, and maps
`rag.retrieval.inline.sources` → mode `auto` and
`rag.retrieval.tool.sources` → mode `tool`.

Sources:

- **FAISS** — `KnowledgeSource` that embeds locally and searches an
  existing sqlite-faiss file. Does not use `VectorStore`.
- **pgvector** — `VectorStore` wrapped by `VectorStoreKnowledgeSource`.
- **OKP** — `KnowledgeSource` that calls the upcoming OKP MCP server.
  Not Solr, not OGX `vector_io`, not `VectorStore`.

Inline RAG is auto-mode injection in `before_model_request`. Tool RAG
is one model-visible search tool spanning all tool-mode sources. After
the turn, matches map to the existing `rag_chunks` /
`referenced_documents` response fields.

## Why

BYOK and OKP retrieval still go through OGX. Inline RAG calls
`client.vector_io.query` in `src/utils/vector_search.py`. Tool RAG
attaches OGX `file_search`. Agents already run with capabilities
(skills, question validity, redaction, Granite Guardian) in
`build_agent`; retrieval is an OGX-shaped side path.

When OGX vector_io leaves, static RAG stops working unless LCS owns
search. This capability is that owner.

## Requirements

- **R1:** A FAISS BYOK store declared in `rag.byok.stores` is
  searchable with OGX `vector_io` disabled.
- **R2:** A pgvector BYOK store declared in `rag.byok.stores` is
  searchable the same way.
- **R3:** A source listed only under `rag.retrieval.inline.sources`
  injects context (`auto`) and does not expose a search tool.
- **R4:** A source listed only under `rag.retrieval.tool.sources` does
  not inject automatically; the model may call the search tool.
- **R5:** A source listed in both inline and tool sources does both.
- **R6:** Existing sqlite-faiss files remain readable (kvstore key
  `vector_io::faiss:faiss_index:v3::<vector_store_id>`).
- **R7:** Query embeddings use the store's configured local
  `sentence-transformers` model (`RagStore.embedding_model`), not a
  chat-provider embedder.
- **R8:** `/v1/query`, `/v1/streaming_query`, and `/v1/responses` still
  populate `rag_chunks` and `referenced_documents` for static BYOK.
- **R9:** `"okp"` in retrieval sources is served by an OKP MCP
  `KnowledgeSource`, with no Solr/`vector_io` client.
- **R10:** Cross-encoder rerank on auto/inline keeps the current 30%
  CE / 70% original mix so `score_multiplier` still matters. Load or
  predict failure logs a warning and keeps original order.
- **R11:** Public config schema remains `rag:` (spike S2=B). No
  `knowledge:` YAML in this feature.
- **R12:** Existing RAG e2e stays the gate. Do not add Knowledge
  `.feature` files or step definitions.

## Use Cases

- **U1:** As a deployer, I want config-declared FAISS and pgvector
  stores searched by the agent, so that BYOK RAG keeps working after
  OGX vector_io is removed.
- **U2:** As a deployer, I want a source listed only under inline RAG
  to inject context every turn, so that the model does not have to
  call a tool.
- **U3:** As a deployer, I want a source listed only under tool RAG to
  be model-callable, so that retrieval happens only when the model
  needs it.
- **U4:** As a deployer, I want `"okp"` in retrieval sources to use
  the OKP MCP server, so that OKP is another Knowledge source rather
  than a Solr client.
- **U5:** As an API client, I want `rag_chunks` and
  `referenced_documents` unchanged, so that existing UIs keep working.

## Architecture

### Overview

```text
Startup:
  Configuration.rag
        │
        ▼
  KnowledgeCapabilityFactory
        │  FAISS / pgvector / OkpKnowledgeSource
        ▼
  KnowledgeSourceRegistry  (process singleton; sources stay in memory)
        │
        ▼
  Knowledge  (reads sources from the registry)
        │
        ▼
  _agent_capabilities() / build_agent()

Request:
  /v1/query  |  /v1/streaming_query  |  /v1/responses
        │
        ▼
  Agent.run (or stream)
        │
        ├─ auto sources: Knowledge.before_model_request
        │     latest user prompt → source.search → optional rerank
        │     inject delimited context on this request
        │
        └─ tool sources: model-visible search tool
              gather tool-mode sources → optional rerank
              → list[KnowledgeMatch]
        │
        ▼
  Knowledge.turn_matches() → RAGChunk / ReferencedDocument
        │
        ▼
  HTTP response (rag_chunks, referenced_documents)
```

Endpoints stop calling `build_rag_context` for static BYOK and OKP
once this capability is attached. Matches for the JSON response come
from the capability after the turn, not from a pre-agent helper.

### Package layout

Live under `src/pydantic_ai_lightspeed/capabilities/knowledge/`, next
to redaction, question validity, and Granite Guardian.

```text
src/pydantic_ai_lightspeed/capabilities/knowledge/
  __init__.py
  capability.py     # Knowledge(AbstractCapability)
  toolset.py        # FunctionToolset for tool-mode sources
  factory.py        # Configuration.rag → register sources
  registry.py       # KnowledgeSourceRegistry singleton
  reranker.py       # CE blend against KnowledgeMatch (or adapters on utils/reranker.py)
  types.py          # KnowledgeMatch
  sources/
    __init__.py
    base.py          # KnowledgeSource, VectorStore, VectorStoreKnowledgeSource
    faiss.py         # FaissKnowledgeSource
    pgvector.py      # PgvectorVectorStore
    okp.py           # OkpKnowledgeSource
```

### Types

`KnowledgeMatch` holds at least:

- `content: str`
- `score: float`
- `id: str`
- `source: str` — `rag_id` or `"okp"`
- `metadata: dict` — citation fields used today (`document_id`,
  `docs_url` / `reference_url` / `doc_url`, `title`, …)

`KnowledgeSource` is an ABC:

- `name: str`
- `mode: frozenset[{"auto", "tool"}]` — `{auto}`, `{tool}`, or both
- `async search(query: str) -> list[KnowledgeMatch]`

`VectorStore` is an ABC used only by embed-then-search backends
(same `base.py`):

- `search(embeddings, limit, threshold) -> list[KnowledgeMatch]`

`VectorStoreKnowledgeSource` is a `KnowledgeSource` that embeds the
query with the store's local sentence-transformers model, then calls
`VectorStore.search`. FAISS must not use this layer.

### Source implementations

**FAISS (`FaissKnowledgeSource`)**

Implements `KnowledgeSource` only. Constructor takes `name`, `mode`,
and the FAISS fields from `RagStore` (`db_path`, `vector_db_id`,
`embedding_model`, `relevance_cutoff_score`, `score_multiplier`,
`top_k`).

sqlite-faiss I/O is private to this class:

- SQLite table `kvstore`
- Key `vector_io::faiss:faiss_index:v3::<vector_store_id>`
- JSON: base64 `faiss.Index` + `chunk_by_index`
- Load once in the constructor
- `index.search` off the event loop (`asyncio.to_thread`)
- L2 distance → `1 / (1 + distance)`
- Apply cutoff on that raw score, then `score_multiplier`
- Missing `vector_store_id` raises a clear error

**pgvector**

`PgvectorVectorStore` implements `VectorStore` with
`ORDER BY embedding <=> %s::vector` (cosine, current OGX default),
`LIMIT`, and score threshold. Wrap with `VectorStoreKnowledgeSource`.
Connection fields and `${env.POSTGRES_*}` defaults match `RagStore`.
Table name stays `vector_store_<vector_db_id>`. Return the same chunk
metadata LCS already maps into `RAGChunk` / `ReferencedDocument`.

**OKP (`OkpKnowledgeSource`)**

Implements `KnowledgeSource` only. `search` calls the OKP MCP search
tool and maps results to `KnowledgeMatch`. Do not add a Solr client,
use OGX `vector_io`, or subclass `VectorStore`. Do not also attach
OKP MCP tools as extra agent tools — the model sees OKP only through
Knowledge (auto inject and/or the search tool).

Preserve current `OkpConfiguration` behavior where the MCP tool has
equivalents: `max_chunks`, `offline` URL shaping (`parent_id` vs
`reference_url`), `chunk_filter_query`, `search_mode`. MCP server URL
is a named `mcp_servers` entry or an `okp` URL field once the OKP
team publishes the tool contract. This source is blocked on that
contract.

### Capability behavior

One `Knowledge` class reads configured sources from
`KnowledgeSourceRegistry` and owns the optional reranker plus
per-turn match state.

**Auto (`before_model_request`)**

1. If there are no auto-mode sources, or no latest user prompt text,
   return the request unchanged.
2. `asyncio.gather` `source.search(prompt)` on every auto source.
3. A source that raises logs a warning and contributes no matches
   (same as today's per-store `vector_io` failure).
4. Merge matches, apply inline rerank when
   `rag.retrieval.inline.reranker.enabled`, then cap at
   `rag.retrieval.inline.max_chunks`.
5. Inject delimited context on the current request (source id, match
   id, content, scores in metadata). Empty match lists add no message.
6. Record matches on the capability for the endpoint to map after
   the turn.

**Tool**

One FunctionToolset. `get_toolset()` returns `None` when no source
has `tool` mode.

Until spike S3 says otherwise, the **model-visible** tool name is
`file_search`, because existing e2e (`faiss.feature` and
`responses.feature`) instruct the model to call `file_search`. The
Python implementation may be named `search_knowledge`. Do not expose
one tool per source.

The tool gathers all tool-mode sources concurrently, tags each match
with the originating source name, sorts highest-score-first, and caps
at `rag.retrieval.tool.max_chunks`. Record matches on the capability.

`no_tools=True` on `build_agent` omits this toolset and keeps auto
injection (same pattern as skills).

**Turn matches**

`Knowledge` keeps the auto-injected and tool-returned matches for the
current turn and exposes them as `KnowledgeMatch`es. Mapping those
into `RAGChunk` / `ReferencedDocument` is LCS response plumbing, not
part of the capability package. It lives next to the existing BYOK
document extraction in `src/utils/vector_search.py` (or a sibling
helper in `src/utils/`), using the same URL / id keys as
`_process_byok_rag_chunks_for_documents` (`document_id`, `docs_url` /
`reference_url` / `doc_url`, `title`). Dedup keys stay the same.
Query, streaming_query, and responses call that helper after the
turn.

If Responses clients still parse `file_search_call` output items
(spike S3=B), translate Knowledge tool results into that shape so
`responses.feature` stays green.

### Reranker

Reuse the algorithm in `src/utils/reranker.py`. Do not change product
scoring.

- Lazy-load and cache `sentence-transformers` `CrossEncoder`
  (default `cross-encoder/ms-marco-MiniLM-L6-v2`)
- Min-max normalize CE scores and original scores
- Combine **30% CE / 70% original**
- After CE, apply `BYOK_RAG_RERANK_BOOST` (1.2) to non-OKP matches
  when BYOK and OKP matches are merged
- On load or predict failure: log a warning, sort by original score

Reranker config stays on `rag.retrieval.inline.reranker`. Auto
injection uses it. Tool-mode search does not run the cross-encoder
unless `rag.retrieval.tool.reranker` is added later (today it is
inline-only).

### Factory and registry

`KnowledgeSourceRegistry` is a process-wide singleton in
`registry.py`. It holds the configured `KnowledgeSource` instances in
memory (FAISS indexes stay loaded; pgvector/OKP clients stay reused).
Lookup is by source name (`rag_id` / `"okp"`). Duplicate names are
rejected. Unit tests must be able to reset the singleton.

The factory (spike T1=A) still **constructs** sources from
`Configuration.rag` — deployers do not call `register()` by hand.
At startup it builds each source and registers it on the singleton.
`Knowledge` and `build_agent` read from the registry; they do not
rebuild sources per request or per agent.

| Config | Source |
|--------|--------|
| `rag.byok.stores[]` with `backend: faiss` | `FaissKnowledgeSource` |
| `rag.byok.stores[]` with `backend: pgvector` | `VectorStoreKnowledgeSource(PgvectorVectorStore)` |
| `"okp"` in inline and/or tool `sources` | `OkpKnowledgeSource` |

Mode: union of membership in `rag.retrieval.inline.sources` (`auto`)
and `rag.retrieval.tool.sources` (`tool`). Duplicate `rag_id` and
unknown retrieval source IDs are already rejected by
`RagConfiguration`.

Attach `Knowledge` in `_agent_capabilities()` / `build_agent()` when
the registry is non-empty.

### Trigger mechanism

The capability is attached at agent construction. Auto search runs on
every model request when auto sources exist. Tool search runs when
the model calls `file_search`. There is no new HTTP endpoint.

### Configuration

Public schema does not change:

```yaml
rag:
  byok:
    max_chunks: 10
    stores:
      - rag_id: ocp-docs
        backend: faiss
        embedding_model: sentence-transformers/all-mpnet-base-v2
        vector_db_id: vs_ocp_docs
        db_path: /path/faiss_store.db
        score_multiplier: 1.0
        relevance_cutoff_score: 0.3
      - rag_id: rh-docs
        backend: pgvector
        embedding_model: sentence-transformers/all-mpnet-base-v2
        vector_db_id: vs_rh_docs
        # host/port/db/user/password default to ${env.POSTGRES_*}
  okp:
    rhokp_url: ${env.RH_SERVER_OKP}
    offline: true
    max_chunks: 10
  retrieval:
    inline:
      sources: [ocp-docs, okp]
      max_chunks: 10
      reranker:
        enabled: true
        model: cross-encoder/ms-marco-MiniLM-L6-v2
    tool:
      sources: [ocp-docs]
      max_chunks: 10
```

OKP MCP server location (named `mcp_servers` entry vs `rag.okp`
field) is decided when the OKP team publishes the tool contract.

### API changes

No new routes. No new request/response fields.

`/v1/rags` continues to list configured `rag_id`s from YAML.

`/tools` lists the Knowledge search tool when tool-mode sources exist.
Until S3 changes it, that tool is `file_search`.

`rag_chunks` and `referenced_documents` keep their current JSON
shapes.

### Error handling

- Per-source search failure: log a warning, contribute no matches,
  continue the turn.
- Missing FAISS `vector_store_id` / unreadable kvstore: fail
  construction or that source's search with a clear error (startup
  for missing file is preferable).
- Reranker failure: original-score order (R10).
- OKP MCP unreachable: same as per-source failure (empty OKP
  matches), not HTTP 500 for the user query.

### Security considerations

- OKP MCP credentials follow existing MCP server auth. Knowledge must
  not log chunk text at info level.
- Do not register OKP MCP tools on the agent in addition to the
  Knowledge source (avoids a second, unmoderated retrieval path).
- Dynamic `/v1/vector-stores` stays deprecated and is not this
  feature.

### Migration / backwards compatibility

- YAML: keep `rag:` (R11).
- On-disk FAISS: keep sqlite-faiss v3 keys (R6). Native rag-content
  writers (LCORE-3302) emit the same format.
- After Knowledge is attached, delete
  `_fetch_byok_rag` / `_fetch_okp_rag` / BYOK `file_search` extra_body
  tools / BYOK `providers.vector_io` synthesis used only so OGX can
  serve those stores, unless still required for deprecated dynamic
  vector-store routes.

## Acceptance test surface

No new behave features. Implementation tickets treat the existing RAG
suite as the e2e gate.

| Req | Observable behavior | Verified by |
|-----|---------------------|-------------|
| R1, R6, R8 | FAISS BYOK on `/v1/query`, `/v1/streaming_query`, `/v1/responses` returns content plus non-empty `rag_chunks` / `referenced_documents` with OGX vector_io disabled | `inline_rag.feature`, `byok_pdf.feature` |
| R4 | Tool RAG on `/v1/query` still works when the model is told to use `file_search` | `faiss.feature` |
| R4, R8 | Responses API `file_search` / `file_search_call` (including `tool_choice` and client-supplied tools) | `responses.feature` |
| R2 | pgvector store declared in config is searchable natively | unit / testcontainer; no dedicated e2e store in-tree today |
| R3, R5 | Inline-only vs both modes | `inline_rag.feature` (inline); unit tests for mode filtering |
| R9 | OKP inline and tool RAG with no Solr client | `okp_rag.feature` (blocked on OKP MCP) |
| R7, R10, R11 | Local embedder, 30/70 rerank, `rag:` YAML | unit tests |
| R12 | No new Knowledge `.feature` files | review of the e2e tree |

Skip `vector_stores.feature` — dynamic APIs are out of this epic.

## Aspect-specific concerns

### Latency and Cost

Auto mode searches every auto source on every turn before the model
call. Keep per-source search concurrent (`asyncio.gather`). FAISS
`index.search` and CrossEncoder `predict` stay off the event loop.
Query embeddings are local CPU (same as index build), not a remote
embedding API.

Tool mode adds a model round-trip only when the model calls the tool.

### Observability

Keep the `rag.retrieve` span semantics for auto retrieval (query,
chunk count, sources). Tool retrieval stays associated with the
inference/tool span. Log reranker enable/disable and per-source
search failures at warning. Do not log full chunk text at info.

### Failure modes

- Empty FAISS file or wrong `vector_db_id`: that source returns
  nothing or errors at load; other sources still run.
- CrossEncoder OOM / missing model: fall back to original scores.
- OKP MCP down: OKP matches empty; BYOK still serves.
- `no_tools=True`: tool RAG silent; auto RAG still injects.

### Telemetry / data privacy

`rag_chunks` already flow into transcripts and Splunk/OTel. The
utils mapping from `KnowledgeMatch` must not change those payload
shapes. Chunk content is product
documentation, not end-user PII, but still must not be dumped in info
logs.

### Runbook / oncall implications

If inline RAG returns empty `rag_chunks`, check: store paths /
Postgres connectivity, `vector_db_id` vs kvstore key, embedding model
name vs how the index was built, reranker load warnings, OKP MCP
health.

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/pydantic_ai_lightspeed/capabilities/knowledge/` | New package (layout above) |
| `src/utils/pydantic_ai_helpers.py` | Attach `Knowledge` in `_agent_capabilities` / `build_agent` |
| `src/app/endpoints/query.py` | Stop `build_rag_context` for static sources; map `Knowledge.turn_matches()` |
| `src/app/endpoints/streaming_query.py` | Same |
| `src/app/endpoints/responses.py` | Same; keep `file_search_call` translation if S3=B |
| `src/utils/vector_search.py` | Map `KnowledgeMatch` → `RAGChunk` / `ReferencedDocument` (same keys as `_process_byok_rag_chunks_for_documents`). Delete `_fetch_byok_rag` / `_fetch_okp_rag` / BYOK branch of `build_rag_context` once endpoints no longer call them |
| `src/utils/responses.py`, `src/utils/builtin_tools.py` | Stop attaching OGX builtin `file_search` for BYOK/OKP tool sources |
| `src/ogx_configuration.py` | Drop BYOK `providers.vector_io` synthesis unless dynamic vector-store routes still need it |
| `src/utils/reranker.py` | Reuse 30/70 + BYOK boost; Knowledge reranker may call into this after adapting match ↔ `RAGChunk` |
| `docs/user_doc/rag_guide.md`, `docs/user_doc/okp_guide.md` | Document native search and OKP-as-MCP; dynamic `/v1/vector-stores` remains deprecated |

### Insertion point detail

`build_agent` already takes `config: AppConfig`. Populate
`KnowledgeSourceRegistry` once at startup from `config.rag` (factory).
`_agent_capabilities` constructs `Knowledge` that reads that registry.
Do not rebuild FAISS indexes per request or per agent. Pass `no_tools`
through so the toolset is dropped when query already omits tools.

After `agent.run` / stream completion, read matches from the same
`Knowledge` instance that was passed into `Agent(..., capabilities=)`.
Do not parse injected prompt text back into chunks.

### Config pattern

No new Pydantic config classes. Factory reads `RagStore`,
`ByokConfiguration`, `OkpConfiguration`, `RetrievalConfiguration` in
`src/models/config.py`.

### Test patterns

- Unit tests with a fake `VectorStore` and a fake OKP MCP client.
  The real OKP server is not required in unit tests.
- FAISS fixture: `tests/e2e/rag/kv_store.db` (and
  `tests/e2e/rag/pdf_kv_store.db` for PDF-built stores).
- pgvector: fake cursor or testcontainer.
- Capability unit tests: mode filtering, empty prompt no-op, empty
  toolset when no tool sources, `no_tools` omits toolset.
- Registry unit tests: register/lookup by name, duplicate name
  rejected, reset between tests.
- Unit tests for `KnowledgeMatch` → `RAGChunk` mapping against
  BYOK-shaped metadata (in `src/utils/`, not the capability package).
- E2E: existing RAG suite only (R12).

## Open Questions for Future Work

- **Public YAML `rag:` vs `knowledge:`** — origin: spike S2.
  This spec ships S2=B (`rag:`). A later release can introduce
  `knowledge:` if product wants a clean break.
- **Model-visible tool name** — origin: spike S3. This spec keeps
  `file_search` so existing e2e stays green. Confirm with @sbunciak
  which clients still send or require `file_search` /
  `file_search_call`.
- **OKP MCP tool schema, auth, and score/metadata fields** — origin:
  spike external input. Blocks the OKP KnowledgeSource ticket.
- **Remote/provider embedders** — origin: UIESTRAT-216 is out of
  scope. Query embeddings stay local sentence-transformers. Revisit
  if a shared embedder registry appears later.
- **Dynamic vector stores** (`POST /v1/vector-stores`, live ingest) —
  origin: spike S1=B rejected. Remains deprecated.

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-10-06 | Initial version | Spec for LCORE-4573 from LCORE-4291 spike |

## Appendix A — Out of scope

- Dynamic `/v1/vector-stores` and live file ingest
- Native Solr / OGX `vector_io` OKP provider
- New Knowledge e2e feature files
- Changing rag-content chunking (LlamaIndex splitters)
- Inference provider registry / chat backends (UIESTRAT-216)
- rag-content native writers (LCORE-3302), except consuming the same
  sqlite-faiss / pgvector table shape they emit
