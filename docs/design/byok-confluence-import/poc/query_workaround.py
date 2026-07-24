"""Query the PoC vector DB, working around the registered_resources conflict.

The store is already registered inside faiss_store.db's kv registry; we drop
the run.yaml re-registration and query the persisted registration directly.
"""

import os
import sys
import tempfile

import yaml

DB_DIR = os.path.dirname(os.path.abspath(__file__)) + "/vector_db"
QUERY = sys.argv[1]
TOP_K = int(sys.argv[2]) if len(sys.argv) > 2 else 3

tmp_dir = tempfile.TemporaryDirectory(prefix="ls-rag-")
os.environ["LLAMA_STACK_CONFIG_DIR"] = tmp_dir.name

with open(f"{DB_DIR}/llama-stack.yaml", encoding="utf-8") as fp:
    cfg = yaml.safe_load(fp)

vs_entries = cfg["registered_resources"].pop("vector_stores")
vector_store_id = vs_entries[0]["vector_store_id"]

cfg_file = os.path.join(tmp_dir.name, "llama-stack.yaml")
with open(cfg_file, "w", encoding="utf-8") as fp:
    yaml.safe_dump(cfg, fp)

from llama_stack.core.library_client import LlamaStackAsLibraryClient  # noqa: E402

with LlamaStackAsLibraryClient(cfg_file) as client:
    res = client.vector_io.query(
        vector_store_id=vector_store_id,
        query=QUERY,
        params={"max_chunks": TOP_K, "mode": "vector", "score_threshold": 0},
    )
    print(f"\nQUERY: {QUERY}")
    print(f"chunks retrieved: {len(res.chunks)}")
    for i, (chunk, score) in enumerate(zip(res.chunks, res.scores)):
        meta = chunk.metadata or {}
        text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
        print(f"\n--- chunk {i + 1} | score={score:.4f}")
        print(f"    title: {meta.get('title')}")
        print(f"    docs_url: {meta.get('docs_url')}")
        print(f"    text: {text[:300]!r}")
