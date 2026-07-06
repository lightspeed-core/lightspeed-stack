# Vector stores in `tests/e2e/rag`

This directory holds committed BYOK vector stores used by the e2e suite.

## `kv_store.db`

Faiss BYOK store used by `faiss.feature` and `inline_rag.feature` (the
`e2e-test-docs` source). Consumed via the `FAISS_VECTOR_STORE_ID` /
`KV_RAG_PATH` environment variables.

## `pdf_kv_store.db` (+ `sources/lightspeed-field-notes.pdf`)

Faiss BYOK store used by `byok_pdf.feature` (the `pdf-field-notes` source).
It is **built from a PDF** by `rag-content`'s `pdf` module (LCORE-2091) to prove
that a PDF-sourced vector store is consumed correctly by lightspeed-stack.

- Source PDF: `sources/lightspeed-field-notes.pdf` — a tiny document containing a
  single deliberately-fabricated fact (a "purple penguin named Zephyr"), so a
  correct query answer can only come from the store, not the LLM's knowledge.
- Embedding model: `sentence-transformers/all-mpnet-base-v2` (dimension 768).
- Baked-in `vector_db_id`: `vs_4a27375c-b8da-4134-96fc-b8198d111015`
  (hardcoded in `lightspeed-stack-byok-pdf.yaml`, so the feature is
  self-contained and needs no externally-provisioned store id).

### Reproduce

From a `rag-content` checkout with PDF support (LCORE-2091):

```bash
python scripts/generate_embeddings.py \
  -f <dir containing the PDF> \
  -o <out dir> \
  -i pdf-field-notes \
  -m sentence-transformers/all-mpnet-base-v2 \
  -d <embeddings model dir> \
  -s llamastack-faiss \
  -t pdf
# -> <out dir>/faiss_store.db   (copied here as pdf_kv_store.db)
```

> Note: docling (used by the PDF reader) loads its own models from the Hugging
> Face cache, but `DocumentProcessor` forces `HF_HOME` to the embeddings-model
> dir. Until that is fixed (tracked separately), make docling's models reachable
> by symlinking a populated `hub` into the embeddings-model dir
> (`ln -s ~/.cache/huggingface/hub <embeddings model dir>/hub`).
