# PoC: BYOK auto-import from Confluence (LCORE-2664 spike)

Validates the core mechanism recommended by the spike doc: fetch Confluence
pages as rendered HTML via the REST API, feed them to the existing
`lightspeed-rag-content` pipeline (docling `HTMLReader` → Markdown →
`MarkdownNodeParser` → embeddings), produce a `llamastack-faiss` vector DB,
and query it with correct per-page citations. Also validates incremental
change detection (CQL `lastmodified` + page-version comparison).

Not production code: credentials come from the developer's Jira CLI
credentials file, there is no retry/backoff, no attachments, no config
surface.

## Files

| File | Purpose |
|---|---|
| `confluence_fetch.py` | Fetch stage: full + incremental crawl, manifest, state |
| `confluence_processor.py` | `custom_processor.py`-pattern build driver with `ConfluenceMetadataProcessor` |
| `confluence_test_page.py` | Test-space/page helper (unused in the end: space creation is 403-forbidden on redhat.atlassian.net; kept as evidence of the read-only constraint) |

## Repro

Prereqs: `~/.config/jira/credentials.json` (email + API token for
redhat.atlassian.net), a checkout of `lightspeed-rag-content` with its uv
venv, and a *complete* local copy of the embedding model
(`model.safetensors` present — an LFS-less clone will fail).

```bash
RUN_DIR=/tmp/poc-run   # fetched content is Red Hat internal; keep out of the repo
POC_DIR=docs/design/byok-confluence-import/poc

# 1. Full crawl (run 1)
python3 $POC_DIR/confluence_fetch.py --spaces RHAT --out $RUN_DIR/pages

# 2. Build the vector DB (from the rag-content repo root)
cd ../rag-content
uv run python $POC_DIR/confluence_processor.py \
  -f $RUN_DIR/pages -o $RUN_DIR/vector_db -i byok-confluence-poc \
  -md embeddings_model -mn sentence-transformers/all-mpnet-base-v2 \
  --vector-store-type llamastack-faiss

# 3. Query (workaround script; scripts/query_rag.py hits a
#    registered_resources conflict — see incidental findings in the spike doc)
uv run python query_workaround.py "your question here" 3

# 4. Incremental crawl (run 2) — re-uses state.json, fetches only changes
python3 $POC_DIR/confluence_fetch.py --spaces RHAT --out $RUN_DIR/pages --incremental
```

Results and evidence: see `../poc-results/`.
