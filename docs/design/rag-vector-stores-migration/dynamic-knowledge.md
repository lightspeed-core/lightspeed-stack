# Feature design for dynamic Knowledge (runtime vector stores)

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-10-22                                |
| **Component**      | lightspeed-stack                          |
| **Authors**        | @jboos                                    |
| **Feature**        | Follow-on to [UIESTRAT-215](https://redhat.atlassian.net/browse/UIESTRAT-215). JIRA not filed yet. |
| **Spike**          | [LCORE-4291](https://redhat.atlassian.net/browse/LCORE-4291) decision S1 left this out of the static epic |
| **Links**          | [Static spec](knowledge-capability.md), [Spike](rag-vector-stores-migration-spike.md), [RAG guide](../../user_doc/rag_guide.md) |

Sibling of the static Knowledge spec
([knowledge-capability.md](knowledge-capability.md), LCORE-4573). That
spec owns config-declared BYOK and OKP. This spec owns stores created
at runtime through `/v1/vector-stores` and `/v1/files`.

Target runtime:
`lightspeed-stack-pydantic/lightspeed/core/agent/knowledge`
(`FaissKnowledgeSource`, sqlite-faiss v3 keys,
`KnowledgeDocument` / `KnowledgeChunk`, Docling chunking, pydantic-ai
`Embedder.embed_documents`, document add/remove). Implement in
`src/pydantic_ai_lightspeed/capabilities/knowledge/`. Do not vendor
the prototype.

## What

`rag.dynamic` configures **one** writable FAISS knowledge source.
The block tells LCS where that database file lives and which
embedding model to use. `DynamicFaissKnowledgeSource` extends
`FaissKnowledgeSource` with create, delete, `add_document`, and
`remove_document`.

`POST /v1/vector-stores` does not register another source. It adds
an empty index in that same file, selected by `vector_store_id`
(sqlite-faiss key
`vector_io::faiss:faiss_index:v3::<vector_store_id>`). Attach and
delete write only that id. Search of named ids goes through this
one source.

Public routes stay the ones in `src/app/endpoints/vector_stores.py`.
Handlers stop proxying OGX. There is no `knowledge:` section and no
per-store provider list.

## Why

`POST /v1/vector-stores`, `POST /v1/files`, and
`POST /v1/vector-stores/{id}/files` are an OGX proxy, marked
deprecated because OGX is leaving. Static `rag.byok.stores` cannot
stand in for them: each BYOK store is a separate read-only corpus
declared before process start.

Runtime stores share one database. Deployers name that file once.
Clients then create many `vector_store_id`s inside it. A second
knowledge source per store would reload the same file and split
ingest from search.

## Requirements

- **R1:** When `rag.dynamic` is set, startup registers one
  `DynamicFaissKnowledgeSource` for `db_path`. `POST /v1/vector-stores`
  creates an empty `vector_store_id` in that file. It does not
  register another `KnowledgeSource`. No OGX client call.
- **R2:** `POST /v1/files` stores the upload in LCS and returns a file
  id. `POST /v1/vector-stores/{id}/files` builds a
  `KnowledgeDocument` and calls
  `add_document(vector_store_id, document)` on that one source.
- **R3:** `add_document` chunks with Docling's `HybridChunker`
  (markdown in, `contextualize` text embedded), embeds with
  `Embedder.embed_documents`, and writes each chunk into the index
  for that `vector_store_id`.
- **R4:** `DELETE /v1/vector-stores/{id}/files/{file_id}` removes
  every chunk for that document from that `vector_store_id`.
  `DELETE /v1/vector-stores/{id}` drops that id's index from the
  file. The source and the sqlite file stay.
- **R5:** Writes go only to `rag.dynamic.db_path`. Create rejects a
  `vector_store_id` equal to a static `rag_id`. BYOK sqlite files
  are not opened for write.
- **R6:** The dynamic source is searched only for `vector_store_id`s
  the request names (query `vector_store_ids`, or `file_search` on
  `/v1/responses`). Other ids in the same file are not searched.
  The source is not injected on every turn.
- **R7:** Hits use the same `KnowledgeMatch` → `RAGChunk` /
  `ReferencedDocument` mapping as static BYOK. Query, streaming
  query, and responses populate those fields. Match metadata
  includes the `vector_store_id`.
- **R8:** Every id in the file uses `rag.dynamic.embedding_model`.
  Document text goes through `embed_documents`. Queries go through
  `embed_query` on that same embedder.
- **R9:** Indexes are mutable. Search uses the live index, so a
  chunk added in this process is visible without a restart. Each id
  is persisted under the v3 kvstore key.
- **R10:** Upload and attach stay bounded by
  `max_concurrent_file_uploads` and
  `max_concurrent_vector_store_attaches`.
- **R11:** `chunking_strategy` on create and attach is accepted and
  ignored. Chunking is Docling hybrid only.

## Use Cases

- **U1:** As an API client, I want to create a vector store, upload a
  text file, and attach it, so that a later query against that
  `vector_store_id` returns the file's content in `rag_chunks`.
- **U2:** As an API client, I want to delete one file from a store,
  so that later searches of that id no longer return that file's
  chunks.
- **U3:** As a deployer, I want one `rag.dynamic` block that names
  the FAISS file and embedding model, so that every runtime store
  is written into that file.
- **U4:** As a deployer, I want static BYOK files to stay read-only
  when clients call the vector-store API, so that a runtime upload
  cannot rewrite `rag.byok` indexes.
- **U5:** As an API client, I want a `file_search` call that names
  one runtime id to search that index only, so that other ids in
  the same file are not pulled into the turn.

## Architecture

### Overview

```text
Startup:
  Configuration.rag.dynamic   (one block: db_path + embedder)
        │
        ▼
  DynamicFaissKnowledgeSource(db_path, embedding_model, ...)
        │  extends FaissKnowledgeSource
        │  registry name: "dynamic"
        ▼
  KnowledgeSourceRegistry
        │  also holds static BYOK / OKP sources
        ▼
  Knowledge capability

Create store:
  POST /v1/vector-stores
        │
        ▼
  source.create_store(vector_store_id)
        │  empty v3 row in the same sqlite file
        │  no registry.register

Attach file:
  POST /v1/files                         persist bytes, return file id
  POST /v1/vector-stores/{vector_store_id}/files
        │
        ▼
  KnowledgeDocument(content, url, id=file_id)
        │
        ▼
  source.add_document(vector_store_id, document)
        │
        ├─ chunk_document          Docling HybridChunker
        ├─ embed_chunks            Embedder.embed_documents
        └─ write chunks into that vector_store_id's index

Search (request names ids):
  /v1/query | /v1/streaming_query | /v1/responses
        │
        ▼
  Knowledge file_search tool
        │  static tool-mode sources for static rag_ids
        │  dynamic source, limited to the named vector_store_ids
        ▼
  KnowledgeMatch → RAGChunk / ReferencedDocument
```

Static search is unchanged when the request names no dynamic id.
Inline / auto retrieval still uses `rag.retrieval.inline.sources`
only. `rag.dynamic` is not a retrieval source id.

### Package layout

Same package as the static capability. The writable type lives next
to the read-only FAISS source so sqlite-faiss I/O stays in one
module.

```text
src/pydantic_ai_lightspeed/capabilities/knowledge/
  processing/
    __init__.py
    chunking.py            # chunk_document
    embedding.py           # embed_chunk / embed_chunks
  sources/
    faiss.py               # FaissKnowledgeSource
                           # DynamicFaissKnowledgeSource
```

`src/app/endpoints/vector_stores.py` calls the one dynamic source.
It does not chunk or embed itself, and it does not construct a
source per request.

### Types

`KnowledgeDocument` (frozen dataclass):

- `content: str` — file text, treated as Markdown
- `url: str` — citation string (the upload filename, or the file id
  when the upload has no name)
- `id: str` — the file id from `POST /v1/files`

`KnowledgeChunk` (frozen dataclass):

- `content: str` — Docling `contextualize` output; this is what is
  embedded
- `source: str` — `document.url`
- `metadata: dict` — includes `document_id` (`document.id`) and
  `vector_store_id`
- `id: str` — chunk id

`KnowledgeReadiness` stays `status` + `message`. The dynamic source
is `ready` when the file can be opened and the embedder loaded,
including when it holds zero `vector_store_id`s. It is `not_ready`
when the embedder or the sqlite file cannot be used.

### DynamicFaissKnowledgeSource

Subclass of `FaissKnowledgeSource`. One instance per process when
`rag.dynamic` is set. Registry name is the fixed string `dynamic`.

The static class loads a single `vector_store_id` once and only
searches it. The subclass keeps that read path (same kvstore key,
same L2 → `1 / (1 + distance)` score, same cutoff and
`score_multiplier`) and adds writes. It holds every id found in
`db_path`, not one id chosen at construction.

Methods:

- `create_store(vector_store_id) -> None` — empty index row. Raises
  if that id already exists.
- `delete_store(vector_store_id) -> None` — drop that id's row.
  Raises if missing. Does not delete the sqlite file or unregister
  the source.
- `add_document(vector_store_id, document) -> None`
- `remove_document(vector_store_id, document_id) -> None`
- `search_stores(query, vector_store_ids) -> list[KnowledgeMatch]`
  — search only those ids, merge, tag each match with
  `metadata["vector_store_id"]` and
  `metadata["knowledge_source"] = "dynamic"`.
- `list_store_ids() -> list[str]`
- `list_document_ids(vector_store_id) -> list[str]`

`KnowledgeSource.search(query)` on this subclass searches nothing.
The tool calls `search_stores` with the request's ids. That keeps
an unfiltered tool-source gather from scanning every runtime index.

Faiss mutation and `index.search` run off the event loop
(`asyncio.to_thread`). A lock serializes writes to the file so two
attaches do not rewrite the same sqlite database at once. Reads of
other ids can proceed against the in-memory indexes.

`add_document(vector_store_id, document)`:

1. The id must already exist (`create_store` ran). Otherwise raise.
2. `chunks = chunk_document(document)`. Blank content returns without
   writing. The file id is still recorded for that
   `vector_store_id` so list and delete have a row.
3. Stamp `metadata["document_id"]`, `metadata["vector_store_id"]`,
   and `source = document.url` on every chunk.
4. `embeddings = await embed_chunks(chunks, embedder)`. One
   `embed_documents` call. An empty chunk list does not call the
   model.
5. Append each chunk and vector to that id's index and rewrite its
   v3 row.
6. Remember `document.id` → chunk ids for that `vector_store_id`.

If a write fails after a partial update, remove the chunks already
added for this document from that id, then raise. The file id is not
recorded as attached.

`remove_document(vector_store_id, document_id)` deletes every chunk
id stored for that document in that index, then forgets the document
id. One document is many chunks. Deleting the document id as if it
were a single chunk id would leave the rest of the file in the
index.

### Chunking

`processing/chunking.py` — `chunk_document(document, *, chunker=None, converter=None)`:

- `document.content` is Markdown. Plain-text uploads are passed
  through as Markdown (the files API already stores parsed PDFs and
  URLs as text).
- Converter is a Docling `DocumentConverter` limited to
  `InputFormat.MD`, so the PDF/OCR pipeline is not loaded on attach.
- Chunker is Docling `HybridChunker`.
- Each chunk's `content` is `chunker.contextualize(chunk)`.
- Empty or whitespace-only content returns `[]`.

`chunking_strategy` on the HTTP body does not select a chunker
(R11).

### Embedding

`processing/embedding.py`:

- `embed_chunk` / `embed_chunks` call `Embedder.embed_documents`.
- Query search uses `Embedder.embed_query` on the same `Embedder`.

The embedder is built once from `rag.dynamic.embedding_model` when
the source is constructed. Every `vector_store_id` in the file uses
it. Static BYOK embedders stay on their own `RagStore.embedding_model`
and are not switched by this feature.

### Registry

`KnowledgeSourceRegistry` holds the one dynamic source under
`"dynamic"`, registered at startup from `rag.dynamic`. HTTP create
does not call `register`.

The handler loads that source and passes `vector_store_id` into
`create_store`, `delete_store`, `add_document`, and
`remove_document`. A missing `"dynamic"` registration means
`rag.dynamic` was not configured.

`unregister("dynamic")` is not used by `DELETE /v1/vector-stores/{id}`.
That route deletes one id inside the file.

### Search selection

The `file_search` tool (static spec S3: that public name) resolves
sources at call time:

1. Static sources whose mode includes `tool` are included when the
   request does not name `vector_store_ids`. That keeps static
   tool RAG.
2. When the request names ids, static tool-mode sources are included
   only for ids that are configured `rag_id`s. The dynamic source's
   `search_stores` is called with the ids that exist in its file.
   Ids in the file that were not named are omitted.
3. An id that is neither a static `rag_id` nor a dynamic
   `vector_store_id` contributes no matches. The turn continues.
4. Auto / `before_model_request` does not call the dynamic source.
   Inline eligibility stays `rag.retrieval.inline.sources`.

`no_tools=True` omits the toolset. Dynamic ids are then unsearchable
for that call.

Tool search does not run the cross-encoder. That matches the static
spec (rerank stays on inline). Ingest does not rerank.

### Trigger mechanism

- Store create, file upload, attach, list, get, update, and delete
  are the existing vector-store routes.
- Search runs when the model calls `file_search` with ids, or when
  query code asks the dynamic source for the named ids.
- There is no new route.

### Storage / data model

Two layers, one database file:

| Layer | Holds | Lifetime |
|-------|--------|----------|
| File record | bytes, filename, file id, purpose | until deleted, or until attach when `delete_file_after_vector_store_attach` is true |
| `vector_store_id` row in `rag.dynamic.db_path` | FAISS index, `chunk_by_index`, document id → chunk ids | until `DELETE /v1/vector-stores/{id}` |

The sqlite file is created on startup if `rag.dynamic` is set and
the path is missing. It is not deleted when the last id is removed.

File records are LCS-owned. They replace the OGX `POST /v1/files`
object. On restart, `vector_store_id`s are rebuilt by listing v3
keys in `db_path`. Document ids are rebuilt from `chunk_by_index`
(`document_id`). File bytes that were not yet attached are gone.

`PUT /v1/vector-stores/{id}` updates name, `expires_at`, and
metadata on the store record kept beside the index. It does not
reindex. This spec does not add a sweeper for `expires_at`.

`GET /v1/vector-stores` lists ids in the dynamic file. Static
`rag_id`s stay on `/v1/rags`.

`GET /v1/vector-stores/{id}/files` lists document ids recorded for
that `vector_store_id`.

Response JSON stays `VectorStoreResponse`, `FileResponse`, and
`VectorStoreFileResponse`. `status` is `completed` when the source
is `ready` and the id exists, and `failed` when the source is
`not_ready`. `usage_bytes` is the sum of stored chunk text sizes
for that id.

### Configuration

`rag.dynamic` is optional. When it is omitted, runtime create and
attach are unavailable. When it is set, it is one object, not a
list. `RagConfiguration` gains:

```yaml
rag:
  byok:
    stores:
      - rag_id: ocp-docs
        backend: faiss
        embedding_model: sentence-transformers/all-mpnet-base-v2
        vector_db_id: vs_ocp_docs
        db_path: /var/lib/rag/ocp.db
  dynamic:
    db_path: /var/lib/rag/dynamic.db
    embedding_model: sentence-transformers/all-mpnet-base-v2
    embedding_dimension: 768
    relevance_cutoff_score: 0.3
    score_multiplier: 1.0
  retrieval:
    inline:
      sources: [ocp-docs]
    tool:
      sources: [ocp-docs]
```

Fields follow the FAISS side of `RagStore`:

| Field | Required | Role |
|-------|----------|------|
| `db_path` | yes | Sqlite file that holds every runtime `vector_store_id` |
| `embedding_model` | no | Same default as `RagStore.embedding_model`. Used for ingest and query |
| `embedding_dimension` | no | Same default as `RagStore.embedding_dimension` |
| `relevance_cutoff_score` | no | Same default as `RagStore`. Applied per id on search |
| `score_multiplier` | no | Same default as `RagStore`. Applied to matches from this source |

There is no `rag_id`, `vector_db_id`, `backend`, or Postgres block.
Ids are created by the API. The backend is FAISS.

Validation:

- `db_path` is non-empty.
- `db_path` must not equal any `rag.byok.stores[].db_path`. The
  dynamic file and a static corpus do not share a sqlite file.
- `rag.dynamic` is not added to the retrieval-source id set.
  `validate_retrieval_sources` stays limited to BYOK `rag_id`s and
  `"okp"`.

`service.max_concurrent_file_uploads`,
`service.max_concurrent_vector_store_attaches`, and
`service.delete_file_after_vector_store_attach` stay as they are.

The existing top-level `vector_store:` provider list is the OGX
synthesis input. This source does not read it.

### API changes

No new routes and no new request fields.

Handlers in `src/app/endpoints/vector_stores.py` call
`DynamicFaissKnowledgeSource` and drop the OGX client. The
`@deprecated` marker comes off those routes in the same change: the
marker's reason is the OGX proxy. Auth actions stay
`MANAGE_VECTOR_STORES` and `MANAGE_FILES`.

`provider_id` on create is ignored. There is one database, from
`rag.dynamic`. `embedding_model` or `embedding_dimension` on the
create body, when set to a value other than `rag.dynamic`, returns
400. When omitted, the configured model is used.
`chunking_strategy` is ignored (R11).

### Error handling

| Case | Result |
|------|--------|
| Create, attach, or delete while `rag.dynamic` is unset | HTTP 503 |
| Create when `vector_store_id` already exists in the dynamic file | HTTP 409 |
| Create when `vector_store_id` equals a static `rag_id` | HTTP 409 |
| Create body embedding model or dimension disagrees with `rag.dynamic` | HTTP 400 |
| Attach, get, or delete-file when the `vector_store_id` is not in the dynamic file | HTTP 404 |
| File id on attach is unknown | HTTP 404 |
| Upload over `DEFAULT_MAX_FILE_UPLOAD_SIZE` | HTTP 413 (existing `FileTooLargeResponse`) |
| Upload or attach over the concurrency semaphore | HTTP 429 (existing responses) |
| Docling or embedder failure | HTTP 500, no partial chunks left on that id |
| Index write failure | roll back chunks for that document on that id, HTTP 500 |
| Search id not in the dynamic file and not a static `rag_id` | no matches from that id; the turn continues |
| Source `not_ready` | dynamic ids contribute no matches; log a warning |

Per-id search failure follows the static capability: log a warning,
contribute no matches, do not fail the user query with 500.

### Security considerations

- Uploaded text is untrusted. The dynamic source is not on the auto
  path, so that text is not concatenated into every model request.
- The `file_search` tool docstring keeps the static wording: results
  are reference data, not instructions.
- Do not log file bytes or chunk text at info.
- The dynamic source never opens a BYOK `db_path` for write.
- Auth stays the existing vector-store and file actions.

### Migration / backwards compatibility

- Route paths and response models stay.
- Deployers who want runtime stores set `rag.dynamic` (one FAISS
  file and one embedding model). A `vector_store.providers` list
  with several backends does not map onto this block. pgvector is
  not a dynamic backend here.
- Once the handlers are native, unified synthesis stops emitting
  OGX `vector_stores` / dynamic `providers.vector_io` entries from
  the top-level `vector_store:` section. Static BYOK synthesis
  follows the static spec.
- Existing clients that create a store, upload a file, and attach it
  keep that sequence. They receive chunks on a later query that
  names that `vector_store_id`.
- Each id is a v3 sqlite-faiss row, so the static reader can open
  one id in this file. Pointing `rag.byok` at `rag.dynamic.db_path`
  is rejected by config validation.
- `vector_stores.feature` today checks auth, list, and 422 bodies.
  Those scenarios stay. Native create/attach/search extends that
  feature (see acceptance). The static epic continues to skip it.

## Acceptance test surface

| Req | Observable behavior | Verified by |
|-----|---------------------|-------------|
| R1 | With `rag.dynamic` set, two creates produce two `vector_store_id`s and one registry source named `dynamic`. No OGX call | unit test; extend `vector_stores.feature` |
| R1 | Create while `rag.dynamic` is omitted returns 503 | unit test |
| R2, R3 | Upload a markdown file, attach it to one id, and `search_stores` of that id returns the chunk text. The other id in the same file does not | unit test with a fake embedder; e2e against a temp sqlite file |
| R4 | Delete the file, then search of that id returns no chunk from it. Delete the id, then get returns 404 and the other id still searches | unit test; e2e |
| R5 | `db_path` equal to a BYOK `db_path` fails config load. Create with a static `rag_id` returns 409 | config unit test; endpoint unit test |
| R6, R7 | Query or responses naming that `vector_store_id` on `file_search` returns `rag_chunks` / `referenced_documents`. A turn that does not name the id does not return those chunks | unit test on id filtering; one e2e scenario |
| R8 | Attach and the later query use `rag.dynamic.embedding_model` (`embed_documents` vs `embed_query`) | unit test |
| R9 | Search after `add_document` in-process returns the new chunk; the kvstore key is the v3 key for that id | unit test on a temp sqlite file |
| R10 | Over-cap upload and attach return 429 | existing semaphore tests; keep them on the native handlers |
| R11 | A body that sets `chunking_strategy` still chunks with Docling hybrid | unit test |
| — | Empty body and extra fields still return 422 | existing `vector_stores.feature` scenarios |

`inline_rag.feature`, `faiss.feature`, `byok_pdf.feature`, and
`okp_rag.feature` stay the static epic's gate. This feature must
not change their assertions.

## Aspect-specific concerns

### Latency and Cost

Attach is the expensive call: Docling convert + hybrid chunk +
`embed_documents` + index rewrite, off the event loop for Faiss and
for Docling's blocking convert. The attach semaphore bounds how many
run at once. A file lock bounds writers on the shared sqlite file.
Search of a named id is one `embed_query` plus one index search.

Docling's markdown converter still pulls model artifacts on first
use. Warm that on startup when `rag.dynamic` is set, so the first
attach is not the first download.

### Observability

Log create, attach, and delete at info with `vector_store_id`, file
id, and chunk count. Log chunk, embed, and write failures at warning
with the id and exception class. Do not log content. A span around
attach should carry chunk count and `vector_store_id`.

### Capacity planning

Each attach holds the upload (already capped) plus chunk embeddings
in memory until the rewrite returns. Every live `vector_store_id`
index in the one file stays in process memory. The file grows as v3
rows are rewritten. There is no cap on id count in this spec beyond
process memory and disk.

### Failure modes

- Docling or the embedder fails the attach. Other ids in the file
  stay searchable.
- A v3 rewrite fails: reload that id from the file before serving it
  again, and return 500. Do not keep serving an index that was not
  persisted.
- The sqlite file cannot be opened: the source is `not_ready`.
  Create and attach return 503. Search skips dynamic ids.
- Restart: list v3 keys in `rag.dynamic.db_path` and expose those
  ids. Unattached file bytes are not restored.

### Telemetry / data privacy

`rag_chunks` from dynamic hits use the same transcript and
Splunk/OTel shapes as static chunks. Chunk text can be customer
content, not only product docs. Info logs stay free of that text.
The existing transcript path will store it, which is the same as
today's OGX-backed `rag_chunks`.

### Runbook / oncall implications

Empty `rag_chunks` for an id the client just attached: confirm the
query names that `vector_store_id`, the attach returned 200, the
source is `ready`, and `rag.dynamic.db_path` is the file the process
opened. A 503 on create means `rag.dynamic` is unset or the file
cannot be opened. A 409 on an id that looks like a docs corpus means
that string is already a static `rag_id`.

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/models/config.py` | Add `DynamicRagConfiguration` and `RagConfiguration.dynamic` |
| `src/pydantic_ai_lightspeed/capabilities/knowledge/processing/chunking.py` | `chunk_document` as specified |
| `src/pydantic_ai_lightspeed/capabilities/knowledge/processing/embedding.py` | `embed_chunk` / `embed_chunks` |
| `src/pydantic_ai_lightspeed/capabilities/knowledge/sources/faiss.py` | `DynamicFaissKnowledgeSource` beside `FaissKnowledgeSource` |
| `src/pydantic_ai_lightspeed/capabilities/knowledge/factory.py` | When `rag.dynamic` is set, construct one dynamic source and `register("dynamic", source)` |
| `src/pydantic_ai_lightspeed/capabilities/knowledge/toolset.py` | Call `search_stores` with the request's dynamic ids. Do not scan the whole file |
| `src/app/endpoints/vector_stores.py` | Replace OGX calls with the one source; drop `@deprecated` |
| `src/ogx_configuration.py` | Stop emitting dynamic `vector_io` providers from top-level `vector_store:` once handlers are native |
| `pyproject.toml` | Add `docling>=2.0.0` (prototype pin). Reuse `pydantic-ai` and `sentence-transformers` already in the project |
| `docs/user_doc/rag_guide.md` | Document `rag.dynamic` and that `chunking_strategy` is ignored |

Depends on the static Knowledge package (`FaissKnowledgeSource`,
registry, `KnowledgeMatch`, `file_search` tool, RAGChunk mapper).
Can land behind that package. Does not depend on OKP MCP.

### Insertion point detail

Startup factory: if `config.rag.dynamic` is set, build
`DynamicFaissKnowledgeSource` from that block and register it as
`"dynamic"`. Do not build it from `vector_store.providers`.

File upload reads bytes the way the handler does today (size check,
semaphore) and writes a file record keyed by file id. Attach loads
that record, builds
`KnowledgeDocument(content=text, url=filename, id=file_id)`, and
calls `add_document(vector_store_id, document)` on the registered
dynamic source.

The toolset reads ids from the run's request context (the same ids
`extract_vector_store_ids_from_tools` / `resolve_vector_store_ids`
already see). Ids that match BYOK `rag_id`s stay on the static
sources. Remaining ids are passed to `search_stores`.

### Config pattern

New model `DynamicRagConfiguration` on `RagConfiguration`, field
name `dynamic`, default `None`. Same `ConfigurationBase` rules as
`RagStore` (`extra="forbid"`). Defaults for `embedding_model`,
`embedding_dimension`, `relevance_cutoff_score`, and
`score_multiplier` match `RagStore`.

### Test patterns

- Unit-test `chunk_document` with a fake converter/chunker. A live
  Docling model is an e2e concern, not a unit-test requirement.
- Unit-test `add_document` / `remove_document` with a fake embedder
  and a temp sqlite file. Assert two `vector_store_id`s share the
  file, `embed_documents` is used on ingest, and `document_id` is
  on chunk metadata.
- Unit-test config: missing `db_path` fails; `db_path` equal to a
  BYOK path fails; omitted `rag.dynamic` leaves the registry without
  `"dynamic"`.
- Endpoint tests: one source after two creates; 409, 404, 400, and
  503 from the error table; the OGX client is not called.
- E2E: extend `tests/e2e/features/vector_stores.feature` with one
  create → upload → attach → query path. The e2e config sets
  `rag.dynamic.db_path` to a temp file. Keep the existing 422
  scenarios.

## Open Questions for Future Work

- **Whether the routes stay public after they are native** — origin:
  spike S1 excluded them from the Q4 static epic and the handlers
  are deprecated as an OGX proxy. This spec re-homes them and removes
  the deprecation. Confirm with @sbunciak if product still wants the
  routes removed in a later release.
- **`expires_at` enforcement** — origin: the create/update models
  have the field; nothing in the FAISS source expires an id. Stored
  and returned only, until a later ticket.
- **Client `chunking_strategy`** — origin: R11. Docling hybrid is
  the only chunker because that is what `chunk_document` implements.
  Honor the request field only if a client depends on fixed-size
  chunks.
- **PDF/OCR on upload** — origin: `chunk_document` accepts Markdown
  strings and a Markdown-only converter. The files API already
  receives parsed text. Binary PDF conversion stays in rag-content
  (BYOK), not on this attach path.
- **Remote embedders** — origin: static spec open question,
  UIESTRAT-216. This spec uses `rag.dynamic.embedding_model` for
  every id in the file. A shared embedder registry can replace
  construction later without changing `add_document`.

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-10-22 | Initial version | Dynamic ingest from the knowledge prototype, on the existing vector-store HTTP API |
| 2026-10-22 | One `rag.dynamic` FAISS source; runtime stores are `vector_store_id`s in that file | Config stays under `rag`. One database, one source |

## Appendix A — What the prototype already does

Path:
`/Users/jboos/Code/me/lightspeed-stack-pydantic/lightspeed/core/agent/knowledge`

| Piece | In the prototype |
|-------|------------------|
| `FaissKnowledgeSource` / `FaissVectorStore` | One `vector_store_id` in a sqlite-faiss file. Read-only, loaded in the constructor. v3 key |
| `KnowledgeDocument` (`content`, `url`, `id`) | Done (`types.py`) |
| `KnowledgeChunk` | Done. `chunk_document` sets `content` and `source=document.url`. It does not set `document_id` |
| `chunk_document` | Done (`processing/chunking.py`). Docling `HybridChunker`, Markdown-only `DocumentConverter`, `contextualize` |
| `embed_chunks` | Done (`processing/embedding.py`). `Embedder.embed_documents` |
| `VectorStore.add` / `remove` | Declared on the ABC. `FaissVectorStore` does not implement them |
| `DynamicKnowledgeSource` | Separate type from FAISS. `add_document` is chunk → embed → `store.add`. `remove_document` calls `store.remove` once |
| Registry `add_document(name, document)` | `name` is a source name, not a `vector_store_id` |
| HTTP `/v1/vector-stores` and `/v1/files` | Not in that tree |

LCS shape this spec requires, because one shared file is the
product config:

- `DynamicFaissKnowledgeSource` subclasses `FaissKnowledgeSource`.
  There is one registered source. `vector_store_id` is an argument
  on create, delete, add, remove, and search, not a registry key.
- Chunk metadata includes `document_id` and `vector_store_id`.
  `remove_document` deletes every chunk for that document in that
  id.
- The sqlite-faiss write stays inside the FAISS module. This
  feature does not add a pgvector dynamic source.

## Appendix B — Out of scope

- Static BYOK and OKP search (knowledge-capability.md)
- A dynamic pgvector backend, or more than one dynamic database
- A `KnowledgeSource` per `vector_store_id`
- Changing rag-content writers (LCORE-3302)
- A new `knowledge:` YAML section, or reading top-level
  `vector_store.providers` as this source's config
- PDF, OCR, or HTML conversion on `POST /v1/files`
- Honoring client `chunking_strategy`
- An expiry sweeper
- Auto-injecting runtime uploads on every turn
