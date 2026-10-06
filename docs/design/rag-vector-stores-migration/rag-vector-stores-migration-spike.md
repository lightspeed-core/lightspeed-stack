# Spike for UIESTRAT-215: RAG & vector stores migration

This document is the deliverable for
[LCORE-4291](https://redhat.atlassian.net/browse/LCORE-4291) — finalize
scope of [UIESTRAT-215](https://redhat.atlassian.net/browse/UIESTRAT-215).
It is epic-level scoping: designs, pros/cons, and the decisions that
determine cost. Implementation details that are not load-bearing for
scope are left to the child tickets.

**Reviewed at**: epic readout (acceptance criterion for LCORE-4291).

**Spec**: [knowledge-capability.md](knowledge-capability.md) (LCORE-4573).

**Target prototype**:
`lightspeed-stack-pydantic/lightspeed/core/agent/knowledge`
(local working tree used as the intended runtime shape).

---

## Overview

**The problem**: BYOK RAG still goes through OGX. `rag-content` builds
indexes with `AsyncOGXAsLibraryClient`. Lightspeed Core Stack (LCS)
queries those indexes with `client.vector_io.query`, and tool RAG is
OGX's `file_search`. Inference is already moving onto pydantic-ai
agents; knowledge retrieval is still an OGX-shaped side path.

**The recommendation**: Two parallel workstreams, matching the two open
epics under UIESTRAT-215:

1. **[LCORE-3302](https://redhat.atlassian.net/browse/LCORE-3302)** —
   native FAISS and pgvector writers in `rag-content`, producing the
   same on-disk format existing deployments already serve.
2. **[LCORE-4573](https://redhat.atlassian.net/browse/LCORE-4573)** —
   a pydantic-ai `Knowledge` capability in LCS for **static** (config-
   declared) BYOK sources plus an OKP `KnowledgeSource` that wraps the
   upcoming OKP MCP server: pluggable `KnowledgeSource`s, per-source
   `tool` / `auto` mode, one `search_knowledge` tool, optional
   cross-encoder rerank.

**PoC validation**: The prototype already implements the capability
surface, FAISS sqlite-faiss read path, toolset, auto injection, and
reranker blend. It does **not** yet build stores from YAML, implement
pgvector, or wire into LCS query/responses. Treat it as the target
shape, not drop-in production code.

---

## Strategic decisions — for @sbunciak and @ptisnovs

High-level decisions that determine scope, approach, and cost. Each has
a recommendation — please confirm or override.

### Decision S1: What is in Q4 scope for UIESTRAT-215?

| Option | Description |
|--------|-------------|
| A | The two open epics only: native `rag-content` writers (LCORE-3302) and a static Knowledge capability in LCS (LCORE-4573) |
| B | Also re-home dynamic OpenAI-compatible vector-store APIs (`POST /v1/vector-stores`, live file ingest) |
| C | Also reimplement OKP/Solr `vector_io` as a native Knowledge source |

**Recommendation**: **A**, plus an OKP **MCP** `KnowledgeSource` under
LCORE-4573 (not a third epic). Do not reimplement Solr/`vector_io`.
OKP becomes another `KnowledgeSource` that calls the upcoming OKP MCP
server. Dynamic vector-store APIs stay out.

**Confidence**: 85%.

### Decision S2: YAML config — keep `rag:` or move to `knowledge:`?

Product configs today:

```yaml
rag:
  byok:
    stores:
      - rag_id: ocp-docs
        backend: faiss
        embedding_model: sentence-transformers/all-mpnet-base-v2
        vector_db_id: vs_...
        db_path: /path/faiss_store.db
  retrieval:
    inline:
      sources: [ocp-docs]
    tool:
      sources: [ocp-docs]
```

Prototype:

```yaml
knowledge:
  sources:
    - name: ocp-docs
      type: faiss
      mode: [tool, auto]
      config: { db_path: /path/faiss_store.db, vector_store_id: vs_... }
      embedding_model: openai:text-embedding-3-small
      top_k: 5
```

| Option | Description |
|--------|-------------|
| A | New `knowledge:` section only. Breaking YAML change for every BYOK deployment. |
| B | Keep `rag:` as the public schema. Factory maps `rag.byok.stores` + `rag.retrieval.*.sources` onto `KnowledgeSource`s (`inline` → `auto`, `tool` → `tool`). |
| C | Accept both during 0.8; document `knowledge:` as the target; drop `rag:` later. |

**Recommendation**: **B** for Q4. Zero forced YAML churn, and
`rag.retrieval.inline/tool.sources` already encodes per-source mode.
Move to `knowledge:` only if we want a clean break in a later release.

**Confidence**: 70% — this is the main product-facing call.

### Decision S3: Public tool name for tool RAG

| Option | Description |
|--------|-------------|
| A | `search_knowledge` (prototype). Clean pydantic-ai tool. Breaks clients that send OpenAI `file_search` tools or parse `file_search_call` items. |
| B | Keep exposing `file_search` on the Responses API surface (request tools, output items, `rag_chunks` extraction). Internally the capability still owns search. |
| C | Native `search_knowledge` for `/v1/query` and `/v1/streaming_query`; keep `file_search` translation only on `/v1/responses`. |

**Recommendation**: **B** if Responses-API compatibility is still a
0.8 requirement; **C** if query and responses can diverge. This is a
compatibility question more than an architecture question — please
confirm which clients still send `file_search`.

**Confidence**: 60%.

---

## Technical decisions — for @ptisnovs

Architecture-level decisions. They do not change Q4 cost much, but they
lock the code shape.

### Decision T1: How are sources constructed at startup?

The prototype's factory looks up names in a process-wide
`KnowledgeSourceRegistry` and **cannot** build a FAISS/pgvector
backend from YAML yet (`pgvector.py` and `okp.py` are empty;
registry errors tell you to `register()` by hand).

| Option | Description |
|--------|-------------|
| A | Factory builds the concrete `KnowledgeSource` from `backend` / `db_path` / `vector_db_id` / embedder fields. No hand registration in production. |
| B | Keep the prototype registry. Application startup registers each configured store. |

**Recommendation**: **A**. Hand registration is a prototype shortcut.
Production config already has every field needed to construct FAISS and
pgvector sources.

**Confidence**: 90%.

### Decision T2: Preserve the sqlite-faiss on-disk format?

The prototype `FaissVectorStore` already reads the layout `rag-content`
writes via OGX:

- SQLite table `kvstore`
- Key `vector_io::faiss:faiss_index:v3::<vector_store_id>`
- JSON value: base64 `faiss.Index` + `chunk_by_index` map

| Option | Description |
|--------|-------------|
| A | Native writers emit that same schema/key prefix. Existing `faiss_store.db` files keep working. |
| B | New native format; migrate or rebuild every index. |

**Recommendation**: **A**. This is the whole point of LCORE-3302's
"output DB format is preserved" language. Native writers are a
replacement for `AsyncOGXAsLibraryClient`, not a new corpus format.

**Confidence**: 95%.

### Decision T3: Reranker behavior

Current LCS (`src/utils/reranker.py`):

- Lazy-loaded `sentence-transformers` `CrossEncoder`
- Min-max normalize CE scores and original scores
- Combine **30% CE / 70% original** so `score_multiplier` still matters
- Optional BYOK boost vs OKP (still applies when both BYOK and OKP
  matches are merged)

The prototype `reranker.py` already uses the same 30/70 mix.

| Option | Description |
|--------|-------------|
| A | Port the current LCS reranker into the capability (including `score_multiplier` and `relevance_cutoff_score` per store). |
| B | Prototype-minimal: CE only, drop per-store weights. |

**Recommendation**: **A**. Product configs already set
`score_multiplier` and `relevance_cutoff_score`. Dropping them is a
behavior change, not a simplification.

**Confidence**: 90%.

---

## Out of scope

- **Dynamic vector stores** (`src/app/endpoints/vector_stores.py`) —
  already deprecated; not "static".
- **Native Solr / OGX `vector_io` OKP provider** — Solr is deprecated.
  OKP is in scope only as an MCP-backed `KnowledgeSource` (see ticket
  below), not as a reimplemented Solr client.
- **Live document ingest** (`POST /files`, attach-to-store) — dynamic,
  not static.
- **New e2e feature files or step definitions for Knowledge** — static
  BYOK is already covered by the existing RAG suite. LCORE-4573 must
  keep those scenarios green; it must not add a parallel Knowledge e2e
  suite. See [Existing RAG e2e](#existing-rag-e2e).
- **Changing how documents are chunked** in `rag-content` — writers
  change; LlamaIndex chunking can stay until a later cleanup.
- **Inference provider registry / chat backends** — UIESTRAT-216, not
  this feature. Query embeddings stay local `sentence-transformers`.

---

## Proposed JIRAs

File under LCORE, parented to the existing epics, **after** readout
consensus. Do not file until S1–S3 are confirmed.

LCORE-4571 and LCORE-4572 already exist as empty stories; the text
below is what should land on them. LCORE-4573 has no children yet.

No new e2e Stories/Tasks. Team default (`require_e2e_kickoff_jira`)
does not apply here: static RAG already has behave coverage.

### Epic: Native RAG generation pipeline — remove OGX dependency

[LCORE-3302](https://redhat.atlassian.net/browse/LCORE-3302) · component
`rag-content` · assignee Sergey Yedrikov · fix version Q4CY26

**Goals**:

- `rag-content` can build FAISS and pgvector stores without importing
  OGX.
- Output remains readable by today's LCS BYOK path **and** by the new
  Knowledge capability (same sqlite-faiss keys / pgvector table shape).
- `ogx` / `ogx-api` / `ogx-client` leave `rag-content`'s
  `pyproject.toml`.

**Scope**: writers + generated LCS YAML snippets. Not the LCS query
path.

<!-- type: Story -->
<!-- key: LCORE-4571 -->
#### LCORE-4571 Native FAISS DB builder

**User story**: As a rag-content maintainer, I want a native FAISS
writer, so that we can produce `faiss_store.db` without
`AsyncOGXAsLibraryClient`.

**Description**: Replace `_LlamaStackDB` FAISS write path in
`src/lightspeed_rag_content/document_processor.py`. Keep chunking
(`_split_and_filter`) as-is. Embed with `SentenceTransformer` (already
used). Serialize:

- numpy vectors → `faiss.serialize_index` → base64 → JSON
- `chunk_by_index` map with `content`, `chunk_id`, `metadata`
- SQLite `kvstore` key
  `vector_io::faiss:faiss_index:v3::<vector_store_id>`

**Acceptance criteria**:

- [ ] `llamastack-faiss` (or its replacement name) no longer constructs
      `AsyncOGXAsLibraryClient`
- [ ] Produced `faiss_store.db` remains readable by current LCS BYOK
      and by the native FAISS reader in LCORE-4573 (same sqlite-faiss
      schema and key prefix)
- [ ] Generated `lightspeed-stack.yaml` snippet still declares
      `rag.byok.stores` with `backend: faiss`, `vector_db_id`, `db_path`
- [ ] Unit tests cover serialize/deserialize round-trip

**Depends on**: none.

<!-- type: Story -->
<!-- key: LCORE-4572 -->
#### LCORE-4572 Native pgvector DB builder

**User story**: As a rag-content maintainer, I want a native pgvector
writer, so that we can populate `vector_store_<id>` tables without OGX.

**Description**: Same epic, pgvector write path. Preserve table shape
LCS already documents (`id`, `document jsonb`, `embedding vector(n)`).
Use env `POSTGRES_*` the same way current templates do.

**Acceptance criteria**:

- [ ] No OGX client on the pgvector write path
- [ ] Table/index shape matches what current LCS BYOK expects
- [ ] Unit tests cover insert + a native query smoke check

**Depends on**: none (can proceed in parallel with LCORE-4571).

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Remove OGX from rag-content packaging and CLI

**Description**: After both writers land, delete `_LlamaStackDB`'s OGX
imports, drop `llamastack-faiss` / `llamastack-pgvector` as the only
supported LCS-compatible types (or make them aliases of the native
writers), remove `ogx` / `ogx-api` / `ogx-client` from
`pyproject.toml`, and stop emitting `llama-stack.yaml` as a required
artifact (LCS snippet is enough).

**Acceptance criteria**:

- [ ] `uv tree` / lockfile has no OGX packages
- [ ] `generate_embeddings` docs list native FAISS/pgvector only
- [ ] CI for rag-content does not install OGX

**Blocked by**: LCORE-4571, LCORE-4572.

---

### Epic: Native RAG agent capability — static

[LCORE-4573](https://redhat.atlassian.net/browse/LCORE-4573) · component
`lightspeed-stack`

**Spec**: [knowledge-capability.md](knowledge-capability.md). Child tickets
implement that spec.

**Goals**:

- Static BYOK sources (FAISS file, pgvector table) are searched by LCS
  with no OGX `vector_io` / `file_search`.
- OKP can be attached as a `KnowledgeSource` that wraps the OKP MCP
  server (not Solr `vector_io`).
- Retrieval is a pydantic-ai `Knowledge` capability attached in
  `build_agent`.
- Inline (`auto`) and tool (`tool`) modes remain independently
  selectable per source.
- **E2E gate is the existing RAG suite**, not a new Knowledge-specific
  behave feature. See [Existing RAG e2e](#existing-rag-e2e).

**Suggested epic description** (current Jira body is a placeholder):

```markdown
## Description

As an LCS deployer, I want config-declared BYOK stores and OKP searched
natively by the pydantic-ai agent, so that RAG keeps working after OGX
vector_io is removed.

Today inline RAG goes through `client.vector_io.query` and tool RAG
through OGX `file_search`. This epic adds a pydantic-ai `Knowledge`
capability in Lightspeed Core Stack for **static** (config-declared)
sources:

- FAISS sqlite-faiss BYOK stores
- pgvector BYOK stores
- OKP as a `KnowledgeSource` wrapping the upcoming OKP MCP server
  (not Solr / OGX `vector_io`)

Public YAML stays `rag:`. `rag.retrieval.inline.sources` maps to mode
`auto`; `rag.retrieval.tool.sources` maps to mode `tool`. The
capability is attached in `build_agent`.

### Target / PoC architecture

https://github.com/jrobertboos/lightspeed-stack-pydantic/tree/feature-knowledge/lightspeed/core/agent/knowledge

That tree is the intended runtime shape (`KnowledgeSource`, per-source
`auto` / `tool` mode, combined search tool, auto inject via
`before_model_request`, cross-encoder reranker,
`KnowledgeSourceRegistry`). Implement from scratch in
`src/pydantic_ai_lightspeed/capabilities/knowledge/`. Do not vendor or
copy the PoC into LCS.

### Spec

`docs/design/rag-vector-stores-migration/knowledge-capability.md`
(spike [LCORE-4291](https://redhat.atlassian.net/browse/LCORE-4291)).

Sibling epic [LCORE-3302](https://redhat.atlassian.net/browse/LCORE-3302)
owns native rag-content writers. Shared contract is the on-disk store
format.

## Acceptance Criteria

* Static BYOK FAISS and pgvector stores are searchable with OGX
  vector_io disabled
* `"okp"` in retrieval sources is served by an OKP MCP
  `KnowledgeSource` (no Solr client)
* Inline-only sources inject context; tool-only sources expose a
  search tool; sources listed in both do both
* `/v1/query`, `/v1/streaming_query`, and `/v1/responses` still
  populate `rag_chunks` and `referenced_documents`
* Existing RAG e2e stays green (`inline_rag.feature`,
  `faiss.feature`, `byok_pdf.feature`, `okp_rag.feature`, and
  `file_search` scenarios in `responses.feature`); do not add a new
  Knowledge e2e suite
* Dynamic `/v1/vector-stores` and a native Solr reimplementation are
  out of scope
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Knowledge match and source interfaces

**Description**: Add the types a Knowledge capability will search
against: a scored match (`content`, `score`, `id`, optional citation
`source`, `metadata`) and an abstract knowledge source with `name`,
`mode` (`tool` and/or `auto`), and `async search(query) -> list[match]`.

Live under `src/pydantic_ai_lightspeed/capabilities/knowledge/`. No
backends, no agent hook, no config factory.

**Scope**:

- `KnowledgeMatch` dataclass / model
- `KnowledgeSource` ABC
- Package layout and module docstrings

**Acceptance criteria**:

- [ ] A source can declare `mode` as `{tool}`, `{auto}`, or both
- [ ] `search` is abstract; no concrete backend in this ticket
- [ ] Unit tests cover match defaults and mode typing

**Agentic tool instruction**:

```text
Read "Target runtime" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Implement from scratch in
src/pydantic_ai_lightspeed/capabilities/knowledge/.
Do not copy from an external tree. Follow existing capability packages
(redaction, question_validity) for layout and docstring style.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? VectorStore interface and VectorStoreKnowledgeSource

**Description**: Shared layer for backends that search by embedding
vector: a `VectorStore` ABC
(`search(embeddings, limit, threshold)`) and a
`VectorStoreKnowledgeSource` that embeds the query locally then calls
that store. FAISS must not use this layer.

**Acceptance criteria**:

- [ ] `VectorStoreKnowledgeSource` is a `KnowledgeSource`
- [ ] Query text in → embedding → `VectorStore.search` → matches
- [ ] `top_k` and cutoff are applied
- [ ] Unit tests with a fake `VectorStore` (no FAISS, no Postgres)

**Depends on**: Knowledge match and source interfaces.

**Agentic tool instruction**:

```text
Implement VectorStore and VectorStoreKnowledgeSource from scratch in
src/pydantic_ai_lightspeed/capabilities/knowledge/sources/base.py
(same module as KnowledgeSource). Do not add vector_store.py. Do not
import FAISS types. pgvector will use this; FAISS KnowledgeSource
stays separate.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Rerank Knowledge matches with cross-encoder

**Description**: Rerank a list of knowledge matches with a
`sentence-transformers` CrossEncoder. Preserve current LCS scoring
(T3): min-max normalize CE and original scores, combine **30% CE /
70% original** so per-store `score_multiplier` still matters. Lazy-load
and cache the model. On load or predict failure, log a warning and
return the original order.

**Scope**:

- Function that takes query + matches + model id, returns reranked
  matches
- Reuse the algorithm in `src/utils/reranker.py`; do not change
  product scoring. May extract shared helpers, or call into that
  module after adapting `RAGChunk` ↔ match.

**Acceptance criteria**:

- [ ] Combined score is 30/70 as in `rerank_chunks_with_cross_encoder`
- [ ] Failure path returns unranked/original-score order
- [ ] Unit tests for blend, identical-score edge case, and failure
      fallback (mock CrossEncoder)

**Depends on**: Knowledge match type.

**Agentic tool instruction**:

```text
Read src/utils/reranker.py and "Decision T3" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Keep 30/70 mix and score_multiplier influence. Implement against
Knowledge matches, from scratch relative to any external tree.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Knowledge capability auto-mode injection

**Description**: pydantic-ai `AbstractCapability` that, in
`before_model_request`, searches every source whose `mode` includes
`auto` using the latest user prompt, optionally reranks, and injects
matches as delimited context on the current request. Skip when there
are no auto sources or no prompt text. Do not expose a tool in this
ticket.

**Acceptance criteria**:

- [ ] Injected context includes source id, match id, content, and
      scores in metadata
- [ ] Sources with only `tool` mode are not searched here
- [ ] Empty match lists add no message
- [ ] Unit tests for mode filtering and no-op when prompt is missing

**Depends on**: Knowledge source interfaces; reranker.

**Agentic tool instruction**:

```text
Read "Target runtime" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Hook: pydantic_ai AbstractCapability.before_model_request, same package
as other LCS capabilities. Implement from scratch. Look at how
question_validity / redaction hook the request, not an external
Knowledge tree.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Knowledge search tool for tool-mode sources

**Description**: Function toolset on the Knowledge capability:
one `search_knowledge` tool that searches every source whose `mode`
includes `tool`, concurrently, tags each match with the originating
source name, optionally reranks, and returns highest-score-first.
`get_toolset()` returns `None` when no tool-mode sources exist.

**Acceptance criteria**:

- [ ] One tool spans all tool-mode sources (not one tool per source)
- [ ] Auto-only sources are not included
- [ ] Unit tests for gather/merge, source tagging, empty toolset

**Depends on**: Knowledge capability auto-mode injection (capability
class) or land the capability shell here if that ticket only added the
hook; coordinate so there is a single `Knowledge` class.

**Agentic tool instruction**:

```text
Read "Decision S3" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Internal tool name is search_knowledge. Responses API file_search
compatibility is a later cut-over ticket. Implement from scratch using
pydantic-ai FunctionToolset, same pattern as skills tools.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? FAISS KnowledgeSource

**Description**: Concrete `KnowledgeSource` for a static FAISS BYOK
store. `search(query)` embeds the query with the store's configured
local `sentence-transformers` model and returns scored matches
from an existing sqlite-faiss file (T2). Constructor takes `name`,
`mode`, `db_path`, `vector_db_id`, `embedding_model`, `top_k`, and
cutoff (`RagStore`).

How the file is opened and searched is an implementation detail of
this source (SQLite `kvstore`, key
`vector_io::faiss:faiss_index:v3::<vector_store_id>`, JSON payload
with base64-serialized `faiss.Index` and `chunk_by_index`, L2 →
`1 / (1 + distance)`, load-once, FAISS call off the event loop). Do
not use `VectorStore` or `VectorStoreKnowledgeSource`; sqlite-faiss
I/O stays private to this class.

**Acceptance criteria**:

- [ ] Query text in → local embed → sqlite-faiss search → list of
      matches
- [ ] Search against `tests/e2e/rag/kv_store.db` works with no OGX
      import
- [ ] Missing `vector_store_id` raises a clear error
- [ ] `top_k` and `relevance_cutoff_score` are applied
- [ ] Embedding model is `RagStore.embedding_model`, not a remote
      chat-provider embedder
- [ ] Class hierarchy is `KnowledgeSource` only
- [ ] Unit tests for L2→score conversion, threshold, and a fixture
      search

**Depends on**: Knowledge match and source interfaces.

**Agentic tool instruction**:

```text
Read "Decision T2" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Implement FaissKnowledgeSource from scratch as a KnowledgeSource.
sqlite-faiss I/O stays private to that class. Fixture:
tests/e2e/rag/kv_store.db. Use sentence-transformers locally.
RagStore fields: embedding_model, relevance_cutoff_score, db_path,
vector_db_id in src/models/config.py. Do not use VectorStore,
VectorStoreKnowledgeSource, or a public index-loader type.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? pgvector KnowledgeSource

**Description**: `VectorStore` that queries PostgreSQL pgvector with
`ORDER BY embedding <=> %s::vector` (cosine, current OGX default),
`LIMIT`, and score threshold. Wrap it with `VectorStoreKnowledgeSource`
for embed-then-search. Connection fields from `RagStore`
(`host`/`port`/`db`/`user`/`password`, `${env.POSTGRES_*}` defaults).
Table name follows current LCS convention
(`vector_store_<vector_db_id>`). Return the same chunk metadata LCS
already maps into `RAGChunk` / `ReferencedDocument` (`content`,
document id, URLs in metadata).

**Acceptance criteria**:

- [ ] Native search with no OGX import
- [ ] Connection defaults match `RagStore` pgvector validation
- [ ] Unit tests with a fake cursor or testcontainer

**Depends on**: VectorStore interface and VectorStoreKnowledgeSource.
Does **not** depend on FAISS KnowledgeSource.

**Agentic tool instruction**:

```text
Read RagStore pgvector fields and docs/user_doc/rag_guide.md pgvector
schema (id, document jsonb, embedding vector(n)). Implement from
scratch. Do not add an OKP/Solr source.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? OKP KnowledgeSource (MCP)

**Description**: Concrete `KnowledgeSource` for OKP. `search(query)`
calls the upcoming OKP MCP server and maps tool results into
`KnowledgeMatch`es so OKP can be listed in
`rag.retrieval.inline.sources` / `rag.retrieval.tool.sources` like any
other Knowledge source (`mode` `auto` / `tool` / both).

This wraps the MCP server as a retrieval backend. Do **not**
reimplement Solr, use OGX `vector_io`, or subclass `VectorStore` /
`VectorStoreKnowledgeSource`. Do **not** also attach OKP's MCP tools
as extra agent tools — the model sees OKP only through Knowledge
(auto inject and/or `search_knowledge`). Wiring into YAML/factory is
the factory ticket.

Use existing `OkpConfiguration` where it still applies (`max_chunks`,
`offline` URL shaping, `chunk_filter_query`, `search_mode`) if the MCP
tool accepts equivalents; add the MCP server URL (or a named entry in
`mcp_servers`) as needed once the OKP team publishes the tool
contract.

**Acceptance criteria**:

- [ ] `OkpKnowledgeSource` implements `KnowledgeSource` only
- [ ] `search` talks to the OKP MCP server; no OGX Solr client
- [ ] Matches carry content, score, and citation metadata needed for
      `RAGChunk` / `ReferencedDocument` (including offline vs online
      URL behavior)
- [ ] Unit tests with a fake MCP client (OKP server need not run in
      unit tests)

**Depends on**: Knowledge match and source interfaces. **Blocked by**:
OKP MCP server tool contract from the OKP team.

**Agentic tool instruction**:

```text
Read OkpConfiguration in src/models/config.py, _fetch_okp_rag in
src/utils/vector_search.py, and docs/user_doc/okp_guide.md for
current OKP behavior to preserve. Implement OkpKnowledgeSource from
scratch as a KnowledgeSource that calls the OKP MCP search tool and
maps results to KnowledgeMatch. Do not add a Solr client or
VectorStore. Do not wire the factory. Confirm the MCP tool schema
with the OKP team before coding.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Construct Knowledge sources from rag configuration

**Description**: Factory that, given `Configuration.rag`, constructs
every configured BYOK store and OKP (T1=A) and registers them on the
`KnowledgeSourceRegistry` singleton. Map
`rag.retrieval.inline.sources` → `auto` and
`rag.retrieval.tool.sources` → `tool` on each source (S2=B). Apply
`score_multiplier`, `top_k`/`max_chunks`, cutoff, embedder, and
reranker config. Reject duplicate `rag_id` and unknown retrieval
source IDs the same way `RagConfiguration` already does. Deployers do
not call `register()` by hand.

**Acceptance criteria**:

- [ ] FAISS stores get a FAISS-backed source from `db_path` +
      `vector_db_id`
- [ ] pgvector stores get a pgvector-backed source from connection
      fields
- [ ] `"okp"` in inline and/or tool retrieval sources gets
      `OkpKnowledgeSource`
- [ ] A store listed in both inline and tool sources has both modes
- [ ] Sources live on `KnowledgeSourceRegistry` (lookup by name;
      duplicates rejected; resettable in tests)
- [ ] Unit tests for mapping, duplicates, and missing backend fields

**Depends on**: FAISS KnowledgeSource; pgvector KnowledgeSource; OKP
KnowledgeSource; Knowledge capability.

**Agentic tool instruction**:

```text
Read RagStore, ByokConfiguration, OkpConfiguration,
RetrievalConfiguration in src/models/config.py and "Decision S2" /
"Decision T1" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Keep public YAML as rag:. Implement factory.py and registry.py from
scratch. Factory constructs sources from config and registers them on
KnowledgeSourceRegistry. Do not require hand-registration in
production. Include OkpKnowledgeSource when "okp" is in retrieval
sources. Spec: docs/design/rag-vector-stores-migration/knowledge-capability.md.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Attach Knowledge capability when building LCS agents

**Description**: Include the constructed `Knowledge` capability in
`_agent_capabilities()` / `build_agent()` in
`src/utils/pydantic_ai_helpers.py`. Honor `no_tools=True` the same way
skills are omitted (drop the capability's toolset, keep auto injection
unless product decides otherwise — default: omit toolset only).

**Acceptance criteria**:

- [ ] Agents used by query / streaming_query / responses include
      Knowledge when `rag.byok.stores` is non-empty or `"okp"` is in
      retrieval sources
- [ ] `no_tools=True` omits the Knowledge toolset
- [ ] Unit tests for capability list with/without stores and no_tools

**Depends on**: Construct Knowledge sources from rag configuration.

**Agentic tool instruction**:

```text
Read _agent_capabilities and build_agent in
src/utils/pydantic_ai_helpers.py. Attach Knowledge next to skills and
shields. Implement from scratch; do not introduce a second agent
factory.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Map Knowledge matches to RAGChunk and ReferencedDocument

**Description**: Convert knowledge matches into the types query,
streaming, responses, transcripts, and telemetry already consume:
`RAGChunk` and `ReferencedDocument` in
`src/models/common/turn_summary.py`. Preserve document URL / id
extraction used today in `src/utils/vector_search.py`
(`_process_byok_rag_chunks_for_documents` and related helpers).

**Acceptance criteria**:

- [ ] Match content, score, source, and metadata round-trip into
      `RAGChunk`
- [ ] Referenced documents dedupe with the same keys as current BYOK
- [ ] Unit tests against fixtures shaped like current BYOK metadata
      (`document_id`, `docs_url` / `reference_url`)

**Depends on**: Knowledge match type.

**Agentic tool instruction**:

```text
Read RAGChunk / ReferencedDocument and the BYOK document extraction in
src/utils/vector_search.py. Implement a pure mapper. Do not change
response JSON shapes. Implement from scratch.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Remove OGX RAG from the static BYOK and OKP path

**Description**: Delete the OGX-backed retrieval path once Knowledge
is attached to agents. Inline and tool RAG both go through the
Knowledge capability; LCS must not call OGX for BYOK or OKP search.

Rip out, at least:

- `client.vector_io.query` / `_fetch_byok_rag` / `_fetch_okp_rag` /
  `build_rag_context` in `src/utils/vector_search.py`
- OGX builtin `file_search` attachment for BYOK and OKP tool sources
  (`src/utils/responses.py`, `src/utils/builtin_tools.py`,
  `file_search` extra_body tools)
- BYOK `providers.vector_io` synthesis used only to make OGX serve
  those stores (`src/ogx_configuration.py` BYOK helpers), unless still
  required for deprecated dynamic vector-store routes

`rag_chunks` and `referenced_documents` stay populated via the
Knowledge mapper. If S3=B, translate Knowledge tool results to
Responses `file_search` / `file_search_call` so existing clients keep
working.

**Acceptance criteria**:

- [ ] No BYOK or OKP `vector_io.query` on query, streaming_query, or
      responses
- [ ] No OGX `inline::file-search` provider required for tool RAG
- [ ] `/tools` lists the Knowledge search tool when tool sources exist
- [ ] `inline_rag.feature`, `byok_pdf.feature`, `faiss.feature`,
      `okp_rag.feature`, and `file_search` scenarios in
      `responses.feature` stay green
- [ ] Do not add new Knowledge `.feature` files or step definitions
      (touch existing steps only if S3 requires a contract change)

**Depends on**: Attach Knowledge capability; map matches to RAGChunk;
auto-mode injection; Knowledge search tool.

**Agentic tool instruction**:

```text
Rip OGX out of static BYOK and OKP RAG. Read src/utils/vector_search.py
(build_rag_context, _fetch_byok_rag, _fetch_okp_rag),
src/utils/responses.py file_search helpers, src/utils/builtin_tools.py,
BYOK helpers in src/ogx_configuration.py, and call sites in query.py /
streaming_query.py / responses.py. "Decision S3" in
docs/design/rag-vector-stores-migration/rag-vector-stores-migration-spike.md.
Existing RAG e2e (including okp_rag.feature) is the gate.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Docs and examples for static native BYOK

**Description**: Update `docs/user_doc/rag_guide.md`,
`docs/user_doc/okp_guide.md`,
`examples/lightspeed-stack-byok-okp-rag.yaml`, and rag-content's
generated LCS snippet if the public schema changes. Document OKP as
an MCP-backed Knowledge source (not Solr `vector_io`). State that
dynamic `/v1/vector-stores` remains deprecated.

---

## Suggested implementation order

```text
LCORE-3302 writers (rag-content)     LCORE-4573 capability (LCS)
──────────────────────────────       ──────────────────────────
4571 FAISS writer ─┐                 match + source interfaces
4572 pgvector writer ─┤             VectorStore + VectorKnowledgeSource
                 drop OGX deps       reranker
                                     auto injection
                                     search tool
                                     FAISS KnowledgeSource
                                     pgvector KnowledgeSource
                                     OKP KnowledgeSource (MCP)  ← blocked on OKP MCP contract
                                     RAGChunk mapper
                                     factory from rag: config
                                     attach on build_agent
                                     remove OGX RAG (existing e2e)
                                     docs
```

The two epics are **not** strictly sequential. LCS can read DBs that
OGX already wrote. rag-content can emit DBs before LCS knows how to
search them natively. Cross-epic contract is T2 (on-disk format).

---

## PoC results

Path:
`/Users/jboos/Code/me/lightspeed-stack-pydantic/lightspeed/core/agent/knowledge`

### What the prototype proves

| Piece | Status in prototype |
|-------|---------------------|
| `KnowledgeSource` + `KnowledgeMatch` | Done (`sources/base.py`) |
| `VectorStore` + embed-then-search wrapper | Done (`sources/vector_store.py`) |
| FAISS sqlite-faiss reader | Done (`sources/faiss.py`) — v3 kvstore keys, L2→`1/(1+d)` |
| pgvector source | Empty file |
| OKP source | Empty file — LCS ticket wraps the OKP MCP server, not this stub |
| Single `Knowledge` capability, per-source `mode` | Done (`capability.py`) |
| Combined `search_knowledge` tool | Done (`toolset.py`) |
| Auto inject via `before_model_request` | Done (XML `<knowledge>` / `<match>` blocks + metadata) |
| Cross-encoder rerank 30/70 | Done (`reranker.py`) |
| YAML `knowledge.sources` models | Done (`app/models/config.py`) |
| Factory builds backends from `type`/`config` | **Not done** — registry lookup only |
| LCS query/responses/telemetry wiring | Not in this tree |

### How the prototype should **not** be copied blindly

- `factory.py` constructs a `CrossEncoder` while `capability.py` types
  `reranker` as `Optional[str]` — internals are mid-refactor.
- Registry docstring still mentions a `CrossEncoderRegistry` that was
  removed.
- `embedding_model: openai:text-embedding-3-small` does not match how
  LCS BYOK indexes are built (local sentence-transformers).
- No mapping to `RAGChunk`, referenced documents, Splunk/OTel, or
  `file_search_call` output items.
- Tests in that tree are not a usable LCS suite (compiled artifacts
  only).

Implementation tickets under LCORE-4573 are from scratch in
`src/pydantic_ai_lightspeed/capabilities/knowledge/`. This PoC is
spike evidence only — do not vendor or copy it into LCS.

---

## External input needed

- **@sbunciak**: S2 (keep `rag:` vs new `knowledge:`) and S3 (keep
  `file_search` on Responses API?). Product teams own YAML and client
  contracts.
- **OKP team**: MCP search tool schema, auth, and score/metadata
  fields for the OKP KnowledgeSource ticket. Required before that
  ticket can start.

---

## Background

### Current LCS retrieval (OGX-shaped)

```text
/v1/query  or  /v1/streaming_query  or  /v1/responses
        │
        ├─ inline: build_rag_context()
        │     ├─ _fetch_byok_rag()  →  client.vector_io.query (per store)
        │     ├─ _fetch_okp_rag()   →  client.vector_io.query (Solr)
        │     ├─ merge, optional CrossEncoder, cap max_chunks
        │     └─ prepend formatted "file_search found N chunks" text
        │
        └─ tool: OGX Responses extra_body tools: [{type: file_search, ...}]
              OGX runs file_search; LCS parses file_search_call items
              into rag_chunks / referenced_documents
```

Agents already exist (`build_agent`) but Knowledge is not one of the
capabilities. Shields and skills are.

Config types: `RagStore`, `ByokConfiguration`,
`RetrievalConfiguration` in `src/models/config.py`. Supported backends:
`faiss`, `pgvector`.

### Current rag-content write path (OGX-shaped)

`DocumentProcessor._get_db()`:

- `faiss` / `postgres` → `_LlamaIndexDB` (LlamaIndex, **not** the
  LCS-compatible sqlite-faiss layout)
- `llamastack-faiss` / `llamastack-pgvector` → `_LlamaStackDB` →
  writes a temp OGX `run.yaml`, then
  `async with AsyncOGXAsLibraryClient(cfg_file)` to create the store
  and insert chunks

LCS-compatible indexes therefore **require OGX as a library** today.
That is LCORE-3302.

### Target runtime

```text
Configuration.rag.byok.stores  (+ rag.okp + retrieval.inline / retrieval.tool)
        │
        ▼
KnowledgeCapabilityFactory  →  Knowledge(sources=[...], reranker=...)
        │                         FAISS / pgvector / OkpKnowledgeSource (MCP)
        │
        ├─ source.mode includes "auto"
        │     before_model_request → source.search(prompt) → inject
        │
        └─ source.mode includes "tool"
              KnowledgeToolset.search_knowledge(query)
              → gather all tool sources → rerank → list[KnowledgeMatch]
```

FAISS search (already written): load index once in the constructor,
`asyncio.to_thread(index.search)`, convert L2 distance to
`1/(1+distance)`, apply threshold, cap `top_k`.

---

## Existing RAG e2e

LCORE-4573 does **not** get new behave features or step definitions.
The Knowledge capability must preserve the behavior those files already
assert. Implementation tickets treat this suite as the e2e gate:

| File | What it already covers |
|------|------------------------|
| `tests/e2e/features/inline_rag.feature` | BYOK source registered; inline RAG on `/v1/query`, `/v1/streaming_query`, `/v1/responses` (sync + stream); `rag_chunks` and `referenced_documents` |
| `tests/e2e/features/faiss.feature` | Tool RAG via `file_search` on `/v1/query` |
| `tests/e2e/features/byok_pdf.feature` | PDF-built static FAISS store (`tests/e2e/rag/pdf_kv_store.db`) |
| `tests/e2e/features/responses.feature` | Responses API `file_search` / `file_search_call` (including `tool_choice` and client-supplied tools) |
| `tests/e2e/features/okp_rag.feature` | OKP inline and tool RAG (gate for the OKP MCP KnowledgeSource) |

Fixtures such as `tests/e2e/rag/kv_store.db` stay the corpus. Skip
`vector_stores.feature` — dynamic vector-store APIs are out of this
epic.

If S3 keeps the `file_search` Responses contract, those scenarios
should pass without Gherkin or step changes.

## Requirements (for readout)

Testable, epic-level. Not an exhaustive spec. R1–R5, R8, and R9 are
already exercised by the table above.

- **R1:** A FAISS BYOK store declared in config is searchable with OGX
  vector_io disabled.
- **R2:** A pgvector BYOK store declared in config is searchable the
  same way.
- **R3:** A source listed only under inline/`auto` injects context
  without exposing a search tool.
- **R4:** A source listed only under tool/`tool` does not inject
  automatically; the model may call the search tool.
- **R5:** A source listed in both modes does both.
- **R6:** Existing sqlite-faiss files produced before this work remain
  readable (format unchanged).
- **R7:** `rag-content` can produce those files without OGX installed.
- **R8:** Query/streaming_query/responses still populate `rag_chunks`
  and referenced documents for static BYOK.
- **R9:** `"okp"` in retrieval sources is served by an OKP MCP
  `KnowledgeSource`, with no Solr/`vector_io` client.

---

## Glossary

| Term | Meaning |
|------|---------|
| Static BYOK | Vector corpus declared in `lightspeed-stack.yaml` at startup. Not created through `POST /v1/vector-stores`. |
| Inline / auto | Retrieval runs on every turn; matches are injected into the model request. |
| Tool / tool | Retrieval is a model-callable tool. |
| sqlite-faiss | SQLite kvstore file holding a serialized FAISS index plus chunk text. |
| Knowledge capability | pydantic-ai `AbstractCapability` that owns retrieval for one agent run. |

---

## Sources

**Jira (open only):**

- [UIESTRAT-215](https://redhat.atlassian.net/browse/UIESTRAT-215) —
  Feature: RAG & vector stores migration
- [LCORE-4291](https://redhat.atlassian.net/browse/LCORE-4291) — this
  spike
- [LCORE-3302](https://redhat.atlassian.net/browse/LCORE-3302) — epic:
  native rag-content pipeline
- [LCORE-4571](https://redhat.atlassian.net/browse/LCORE-4571) —
  Native FAISS DB builder
- [LCORE-4572](https://redhat.atlassian.net/browse/LCORE-4572) —
  Native pgvector DB builder
- [LCORE-4573](https://redhat.atlassian.net/browse/LCORE-4573) — epic:
  native RAG agent capability (static)

**Code:**

- Prototype:
  `lightspeed-stack-pydantic/lightspeed/core/agent/knowledge`
- LCS retrieval: `src/utils/vector_search.py`,
  `src/utils/pydantic_ai_helpers.py`, `src/utils/reranker.py`
- rag-content write path:
  `rag-content/src/lightspeed_rag_content/document_processor.py`
  (`_LlamaStackDB`)
