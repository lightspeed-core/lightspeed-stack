#!/usr/bin/env python3
"""PoC: build a BYOK vector DB from Confluence-fetched HTML pages.

Follows the documented `custom_processor.py` pattern from
lightspeed-rag-content: a Confluence-aware ``MetadataProcessor`` that
resolves each page's canonical URL and title from the ``manifest.json``
written by ``confluence_fetch.py``, driving the existing
``DocumentProcessor`` with ``doc_type="html"`` (docling HTMLReader ->
Markdown -> MarkdownNodeParser chunks).

Run from the rag-content repo root so its venv and embeddings model resolve:

    uv run python <this file> -f <pages-dir> -o <out-dir> -i <index-id> \
        -md embeddings_model -mn sentence-transformers/all-mpnet-base-v2
"""

import json
import os

from lightspeed_rag_content import utils
from lightspeed_rag_content.document_processor import DocumentProcessor
from lightspeed_rag_content.html.html_reader import HTMLReader
from lightspeed_rag_content.metadata_processor import MetadataProcessor


class ConfluenceMetadataProcessor(MetadataProcessor):
    """Resolve per-page URL and title from the fetch-stage manifest.

    ``hermetic_build=True`` because Confluence page URLs are auth-gated:
    an unauthenticated reachability ping would mark every URL unreachable.
    """

    def __init__(self, manifest_path: str):
        super().__init__(hermetic_build=True)
        with open(manifest_path, encoding="utf-8") as fp:
            self.manifest = json.load(fp)

    def _entry(self, file_path: str) -> dict:
        return self.manifest.get(os.path.basename(file_path), {})

    def url_function(self, file_path: str) -> str:
        return self._entry(file_path).get("url", os.path.basename(file_path))

    def get_file_title(self, file_path: str) -> str:
        # HTML files have no frontmatter; first-line extraction would return
        # raw markup. The manifest carries the real Confluence page title.
        return self._entry(file_path).get("title", os.path.basename(file_path))


if __name__ == "__main__":
    parser = utils.get_common_arg_parser()
    args = parser.parse_args()

    metadata_processor = ConfluenceMetadataProcessor(
        os.path.join(args.folder, "manifest.json")
    )
    document_processor = DocumentProcessor(
        chunk_size=args.chunk,
        chunk_overlap=args.overlap,
        model_name=args.model_name,
        embeddings_model_dir=args.model_dir,
        num_workers=args.workers,
        vector_store_type=args.vector_store_type,
        doc_type="html",
    )
    document_processor.process(
        args.folder,
        metadata=metadata_processor,
        required_exts=[".html"],
        file_extractor={".html": HTMLReader()},
    )
    document_processor.save(args.index, args.output)
