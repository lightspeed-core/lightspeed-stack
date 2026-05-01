# Feature design: BYOK PDF support

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-04-27                                |
| **Component**      | rag-content (primary), lightspeed-stack (docs only) |
| **Authors**        | Maxim Svistunov                           |
| **Feature**        | [LCORE-1471](https://issues.redhat.com/browse/LCORE-1471) |
| **Epic**           | [LCORE-2090](https://issues.redhat.com/browse/LCORE-2090) (covers LCORE-2091..2094) |
| **Spike**          | [LCORE-1471](https://issues.redhat.com/browse/LCORE-1471) — see [byok-pdf-spike.md](byok-pdf-spike.md) |
| **Precedent**      | [LCORE-1035](https://issues.redhat.com/browse/LCORE-1035) — HTML support (PR `7f688b0`) |

## What

Add native PDF input support to the BYOK content production tool (`rag-content`). After this feature, customers can drop `.pdf` files into the input directory of `custom_processor.py` alongside `.md`, `.txt`, and `.html` files, and get a functioning vector store without manual pre-conversion.

## Why

Today, customers with PDF content must convert it to Markdown themselves before feeding it to `rag-content`. The BYOK guide currently instructs them to use `docling` as a separate pre-processing step. This is friction — and ironic, because `rag-content` *already* depends on `docling` (it ships with HTML support). Wiring the existing dependency through to PDF removes the manual step at no cost in third-party deps.

## Requirements

- **R1**: `python -m lightspeed_rag_content.pdf convert -i input.pdf -o output.md` converts a single PDF to Markdown.
- **R2**: `python -m lightspeed_rag_content.pdf batch -i ./pdfs/ -o ./md/` converts a directory of PDFs.
- **R3**: `custom_processor.py` with `-f` pointing to a directory containing PDFs produces a vector store; PDFs are routed through `MarkdownNodeParser` after docling export.
- **R4**: No new entries in `pyproject.toml` (docling is already a dependency).
- **R5**: OCR is not invoked. Scanned/image-only PDFs are out of scope; their conversion may yield empty or near-empty Markdown without erroring.
- **R6**: The `lightspeed-stack/docs/byok_guide.md` no longer instructs users to pre-convert PDFs.
- **R7**: When `PDFReader.load_data` produces empty or near-empty Markdown (a likely indicator of a scanned/image-only PDF given R5), the reader emits a `logger.warning` with the file path and resulting length. This makes the silent-degradation case visible in `custom_processor.py` logs without raising. The empty-output threshold is a small module-level constant (e.g., `EMPTY_OUTPUT_THRESHOLD: Final[int] = 50`) so it is easy to find and tune.

## Use Cases

- **U1**: As a BYOK customer with product documentation PDFs, I want to feed the PDFs directly to `rag-content` so that I don't have to maintain a separate conversion step in my pipeline.
- **U2**: As an LCS operator, I want a vector store generated from a PDF to behave indistinguishably from one generated from Markdown when queried via `lightspeed-stack`, so that input-format choice does not affect retrieval semantics.

## Architecture

### Overview

```text
                 input/
                 ├── doc.md   ─┐
                 ├── note.txt ─┼─→ SimpleDirectoryReader
                 ├── page.html ┤        │
                 └── manual.pdf┘        │
                                        ▼
                          file_extractor lookup by ext:
                            .html ─→ HTMLReader (existing)
                            .pdf  ─→ PDFReader (new)            ←── this feature
                            .md, .txt ─→ default text reader
                                        │
                                        ▼
                              Document(text=markdown)
                                        │
                                        ▼
                          MarkdownNodeParser (existing path,
                            extended to recognize doc_type="pdf")
                                        │
                                        ▼
                              embedding + vector store
```

PDF support reuses the entire downstream pipeline. The only new code is the reader/CLI, plus a one-token addition (`"pdf"`) to two `doc_type` checks in `document_processor.py`.

### Reader

`PDFReader(BaseReader)` mirrors `HTMLReader` line-for-line with two differences:

1. The docling `DocumentConverter` is constructed with `allowed_formats=[InputFormat.PDF]` (not HTML).
2. The converter receives a `PdfFormatOption(pipeline_options=...)` argument with explicit pipeline knobs.

```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.pipeline_options import TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption

class PDFReader(BaseReader):
    def __init__(self) -> None:
        opts = PdfPipelineOptions()
        opts.do_ocr = False
        opts.do_table_structure = True
        opts.table_structure_options.mode = TableFormerMode.ACCURATE
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=opts),
            },
        )

    def load_data(self, file: Path, extra_info=None, **kwargs):
        # identical body to HTMLReader.load_data — see html_reader.py
        # Plus R7: warn-log when the resulting markdown is empty / very short.
        ...
```

Mirror `HTMLReader`'s `__init__` choice on whether to call `super().__init__()` — `BaseReader` from llama-index does not strictly require it, but matching the precedent keeps the two readers symmetric. Use `TableFormerMode.ACCURATE` (the enum), not the string literal `"accurate"`; docling's Pydantic coercion accepts both, but the enum is the idiomatic form and is type-checked.

### Pipeline configuration

| Option | Value | Why |
|--------|-------|-----|
| `do_ocr` | `False` | Out of scope (R5) |
| `do_table_structure` | `True` | Tables are common in customer docs |
| `table_structure_options.mode` | `"accurate"` | Offline indexing tolerates the perf cost |
| `do_picture_classification` | `False` (default) | Vector search does not use images |
| `do_picture_description` | `False` (default) | Heavy VLM call, no value |
| `generate_page_images` | `False` (default) | Wasted I/O |

These are baked into `PDFReader.__init__`. **No CLI flags expose them in v1.** If customer feedback calls for tuning, add flags later.

### Chunking

PDFs go through the same chunking path as HTML and Markdown. Two predicates in `document_processor.py` need to learn `"pdf"`:

- The `Settings.node_parser = MarkdownNodeParser()` branch in `_BaseDB.__init__`.
- The same branch in `_LlamaStackDB.__init__` (currently a separate copy of the predicate).

To prevent these two tuples from drifting, extract a single module-level constant and use it from both call sites:

```python
from typing import Final

# At module top
MARKDOWN_COMPATIBLE_DOC_TYPES: Final[tuple[str, ...]] = ("markdown", "html", "pdf")

# In _BaseDB.__init__ and _LlamaStackDB.__init__
if config.doc_type in MARKDOWN_COMPATIBLE_DOC_TYPES:
    Settings.node_parser = MarkdownNodeParser()
```

`MarkdownNodeParser` operates on the markdown that docling exports. It splits on heading boundaries, which works because docling produces well-formed `# ` / `## ` / `### ` headings for body content. Heading-text degradation in some PDFs (see "Known limitations") corrupts the heading *text* but does not break splitting.

### CLI module (`pdf/__main__.py`)

Mirror `html/__main__.py` exactly. Two subcommands:

- `convert -i input.pdf [-o output.md]` — single file
- `batch -i ./pdf_dir [-o ./md_dir]` — directory walk over `**/*.pdf`

Reuse `lightspeed_rag_content.utils.add_input_file_argument` and `run_cli_command`.

### Configuration

No YAML configuration changes. The reader's defaults are hard-coded; the CLI takes paths only; `custom_processor.py` already accepts the input directory as `-f`.

### API changes

No HTTP API changes. This feature is entirely offline (rag-content is a build-time tool).

### Error handling

Mirror HTMLReader exactly:

- `FileNotFoundError` if the input path does not exist.
- `RuntimeError` (with the underlying exception chained via `from exc`) if docling conversion fails.
- The CLI catches both, logs, and exits non-zero.

A scanned (image-only) PDF will produce empty or near-empty Markdown. This is not an error — the document parses fine; it just contains no extractable text. Customers will see a valid but empty-ish vector store entry. Per **R7**, the reader emits a `logger.warning` in this case (file path + resulting length) so the condition shows up in `custom_processor.py` logs. Document the same caveat in the rag-content README.

### Migration / backwards compatibility

None. This is purely additive: existing pipelines that don't pass PDFs are unaffected. No schema, no config, no API changes.

## Implementation Suggestions

### Key files and insertion points

| Repo | File | What to do |
|------|------|------------|
| rag-content | `src/lightspeed_rag_content/pdf/__init__.py` | New — minimal package init mirroring `html/__init__.py` |
| rag-content | `src/lightspeed_rag_content/pdf/__main__.py` | New — CLI mirroring `html/__main__.py` |
| rag-content | `src/lightspeed_rag_content/pdf/pdf_reader.py` | New — `PDFReader(BaseReader)` mirroring `html_reader.py` |
| rag-content | `src/lightspeed_rag_content/document_processor.py` | Add a module-level `MARKDOWN_COMPATIBLE_DOC_TYPES` constant (incl. `"pdf"`) and use it in both `_BaseDB.__init__` and `_LlamaStackDB.__init__` where the predicate `config.doc_type in (...)` currently appears |
| rag-content | `tests/pdf/__init__.py` | New |
| rag-content | `tests/pdf/test_pdf_reader.py` | New — mirror `tests/html/test_html_reader.py` |
| rag-content | `tests/pdf/test__main__.py` | New — mirror `tests/html/test__main__.py` |
| rag-content | `tests/pdf/fixture.pdf` | New — small text-extractable test PDF (< 50 KB) |
| rag-content | `README.md` | Edit — add PDF to the supported input formats list |
| lightspeed-stack | `docs/byok_guide.md` | In the "Knowledge Sources" subsection: add PDF to "Directly supported", remove it from "Requires conversion". In Step 1 ("Prepare Your Knowledge Sources"): drop the docling-as-pre-conversion example. |

### Insertion point detail

There are two predicates in `document_processor.py` that route by `doc_type`:

- One inside `_LlamaStackDB.__init__`.
- One inside `_BaseDB.__init__`.

Both look like:

```python
if config.doc_type in ("markdown", "html"):
    Settings.node_parser = MarkdownNodeParser()
```

Both should be replaced with the shared `MARKDOWN_COMPATIBLE_DOC_TYPES` constant introduced in the [Chunking](#chunking) section so the predicates cannot drift:

```python
if config.doc_type in MARKDOWN_COMPATIBLE_DOC_TYPES:
    Settings.node_parser = MarkdownNodeParser()
```

No other branches in the file route by `doc_type`.

### Config pattern

N/A — this feature has no Python config classes (it's a CLI tool, not a service).

### Test patterns

Mirror the HTML test layout exactly:

- `tests/pdf/test_pdf_reader.py`:
  - Test that `PDFReader().load_data(valid_path)` returns a list with one `Document`.
  - Test that the returned `Document.text` is non-empty for a real fixture PDF.
  - Test that `FileNotFoundError` is raised for a non-existent path.
  - Test that `RuntimeError` is raised when docling raises (mock the converter).
  - Test that `extra_info` is preserved in `Document.metadata`.
  - Test (per **R7**) that empty / sub-threshold docling output triggers a single `logger.warning` containing the file path (use `caplog` and assert `record.levelname == "WARNING"`).
- `tests/pdf/test__main__.py`:
  - Test argument parsing for `convert` and `batch`.
  - Test that `convert` writes output to the inferred path when `-o` is omitted.
  - Test that `batch` walks subdirectories and preserves structure.
  - Test that errors exit non-zero.

Use the existing `mocker` patterns from `tests/html/`. The PDF fixture should be small (< 50 KB) and committed to git — generate one from a known Markdown source so test assertions can match exact strings.

## Open Questions for Future Work

- **OCR support**: Scanned PDFs require docling's OCR engines (tesseract, easyocr, rapidocr). File a follow-up JIRA when there is customer demand. Implementation is mostly a flag toggle; the cost is in build/runtime size.
- **Hybrid (page-aware) chunking**: If retrieval quality on real customer PDFs is poor, switch from `MarkdownNodeParser` to docling's hybrid chunker. Requires a new branch in `_BaseDB.__init__`.
- **Heading-cleanup post-processor**: Confluence-export PDFs with letter-spaced headings yield `H e a d i n g` text. A small post-processor that collapses single-character runs in headings would mitigate. Not in scope for v1.
- **Shared `DoclingReader` base class**: If `PDFReader` and `HTMLReader` end up sharing significant logic beyond imports, refactor into a base. Not required by this feature.
- **DOCX, RTF, EPUB**: docling supports these. Add as separate readers when customer demand justifies.

## Known limitations

These are intentional v1 trade-offs documented for the rag-content README and the BYOK guide:

- **Scanned PDFs**: produce empty or near-empty Markdown. Per **R7** the reader emits a `logger.warning` so the condition is visible in `custom_processor.py` logs rather than silently degrading. Use a separate OCR step today; native OCR support tracked as a follow-up.
- **Letter-spaced display fonts**: typical of Confluence "Export to PDF" output. Headings may extract with spaces between letters (`H e a d i n g`). Body text is unaffected. The `## ` heading prefix is intact, so chunking still happens at heading boundaries; only the heading *text* is corrupted, which slightly degrades retrieval if a query mentions the heading literally.
- **Performance**: ~30-90 seconds per small/medium PDF on CPU after model warm-up. Acceptable for offline indexing; not suitable for interactive use.

## Changelog

| Date       | Change          | Reason                          |
|------------|-----------------|---------------------------------|
| 2026-04-27 | Initial version | Spike deliverable for LCORE-1471 |
| 2026-04-30 | Added R7 (warn-log empty output); switched chunking section to symbol anchors + shared `MARKDOWN_COMPATIBLE_DOC_TYPES` constant; switched code sketch to `TableFormerMode.ACCURATE` enum; added `super().__init__()` mirroring note | Reviewer feedback on PR #1598 (CodeRabbit) |
| 2026-04-30 | JIRAs filed under epic LCORE-2090 (LCORE-2091..2094); added Epic row to the metadata table | Step 9 of howto-run-a-spike.md |

## Appendix A: PoC evidence

The full PoC report, conversion logs, sample input PDFs, and converted Markdown samples were committed to PR #1598 under `docs/design/byok-pdf/poc/` and `docs/design/byok-pdf/poc-results/`, then removed before merge per `howto-run-a-spike.md` step 10. Refer to PR #1598's diff (commits `56be99cb` and `250881e2`) for the raw artifacts. The "PoC results" section of [`byok-pdf-spike.md`](byok-pdf-spike.md) summarises what the PoC proved and surfaces the heading-degradation limitation documented in "Known limitations".

## Appendix B: HTML precedent

The HTML implementation under [LCORE-1035](https://issues.redhat.com/browse/LCORE-1035) (commit `7f688b0`, 2026-01-15) established every pattern used here:

- `BaseReader` with docling-backed conversion
- `__main__.py` CLI structure with `convert` and `batch` subcommands
- `tests/html/` layout
- `document_processor.py` `doc_type` branching

Refer to the HTML files (`src/lightspeed_rag_content/html/`, `tests/html/`) when implementing this feature. Differences are limited to the `InputFormat` enum value and the addition of `PdfFormatOption(pipeline_options=...)` in the `DocumentConverter` constructor.
