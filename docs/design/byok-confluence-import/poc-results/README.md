# PoC results: BYOK auto-import from Confluence (LCORE-2664)

Evidence for the spike doc's PoC findings. Raw crawled content is **not**
included: the PoC ran against the RHAT space on redhat.atlassian.net
(Red Hat-internal content); this directory carries sanitized stats and
excerpts only.

## Design

- **Target**: Confluence Cloud (redhat.atlassian.net), space `RHAT`
  (20 pages), read-only API token of a regular user.
- **Fetch**: v1 REST `body.export_view` (rendered HTML), one HTML file per
  page + `manifest.json` (id → title, canonical URL, version) +
  `state.json` (sync watermark, per-page versions).
- **Build**: existing rag-content pipeline — docling `HTMLReader`,
  `MarkdownNodeParser`, chunk 380/0, `all-mpnet-base-v2` (768-dim),
  `llamastack-faiss` output.
- **Verify**: `vector_io.query` via llama-stack library client, top-3.
- **Incremental**: run 2 with `--incremental` — CQL
  `lastmodified >= watermark − 10min` + full ID enumeration (deletion diff)
  + version comparison to skip unchanged pages.

## Results

| Step | Outcome |
|---|---|
| Full crawl (run 1) | 20/20 pages fetched, ~1 API call/page + 1 listing call |
| DB build | `faiss_store.db` 3.8 MB, no page failed conversion |
| Retrieval | Top-3 chunks on a policy question: correct pages, scores 2.25/1.65/1.60 |
| Citations | `title` + canonical page URL present on every chunk (see `retrieval-evidence.txt`) |
| Incremental (run 2) | `fetched=0 unchanged=20 deleted=0` — 2 API calls total instead of 21 |
| Conversion quality | Headings/bold/nested lists/expand-macros clean (see `conversion-sample.md` excerpt) |

## Findings (carried into the spike doc)

1. **The mechanism works end-to-end** with zero changes to rag-content
   library code — only a fetch stage and a `MetadataProcessor` subclass.
2. **Citations flow**: per-page Confluence URLs land in chunk metadata via
   `url_function`; `hermetic_build=True` is required (page URLs are
   auth-gated, reachability pings would mark all unreachable).
3. **Read-only is all you get**: space creation 403-forbidden for regular
   users on redhat.atlassian.net; the importer must not assume any write
   permission. Update/delete sync paths are therefore implemented but
   validated logically, not live (no writable page available).
4. **Governance**: Red Hat's own Atlassian policy (retrieved by the PoC
   itself) requires team integrations to use registered bot/service
   accounts, not personal tokens — auth docs must say so.
5. **Incidental bug**: the generated `llama-stack.yaml` +
   `scripts/query_rag.py` fail out-of-the-box — re-registering the
   vector store conflicts with the registration persisted inside
   `faiss_store.db` (`provider_resource_id`/`vector_store_name`: None vs
   set). Worked around by dropping `registered_resources.vector_stores`
   and querying the persisted registration.
6. **Portability gotcha confirmed live**: the built DB bakes the absolute
   embedding-model path into `llama-stack.yaml` and the kv registry.
7. **Incomplete-LFS gotcha**: an embeddings-model directory without
   `model.safetensors` fails only at build time with an obscure error.

## Implications

- Recommended design (fetch stage + existing pipeline) is validated;
  no design change needed.
- Incremental sync as "skip unchanged re-embeds, full rebuild output"
  is cheap and works; live update/delete validation moves to the e2e
  test ticket (needs a writable test instance/mock).
- Finding 5 becomes a proposed incidental JIRA.
