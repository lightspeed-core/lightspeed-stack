# Spike for LCORE-1471: BYOK PDF support

## Overview

This document is the deliverable for [LCORE-1471](https://issues.redhat.com/browse/LCORE-1471). It proposes the design for adding PDF support to the BYOK content production tool (`rag-content`), with a recommendation and a proof-of-concept validation.

**The problem**: The BYOK pipeline only accepts Markdown and plain-text input. Customers typically have content in PDF or HTML and must convert it themselves before indexing. HTML support shipped under [LCORE-1035](https://issues.redhat.com/browse/LCORE-1035) (Jan 2026); PDF support is still missing.

**The recommendation**: Add a `PDFReader` to `rag-content` mirroring the existing `HTMLReader`, configured to use the `docling` library that is already a dependency. No new third-party dependencies. Reuse the existing `MarkdownNodeParser` for chunking — `docling` exports clean Markdown for body content. Scope is text-extractable PDFs only; OCR is deferred.

**PoC validation**: A 60-line PoC script converted two real-world PDFs (Lightspeed JIRA exports, 217 KB and 372 KB) using docling's PDF pipeline with the recommended defaults. Body text quality is high; tables are preserved as Markdown tables. Headings degrade on letter-spaced Confluence-export PDFs (cosmetic noise that survives into the markdown but is stripped during chunking). See [PoC results](#poc-results).

## Decisions for @maxrubyonrails (and product owner of choice)

These determine scope and approach.

### Decision 1: Library choice for PDF → Markdown conversion

| Option | Description | New deps? | Quality |
|--------|-------------|-----------|---------|
| A | `docling` (already a dep) | None | High; ML-based layout + table detection |
| B | `pymupdf4llm` | New dep | Medium; faster but weaker on tables/structure |
| C | `marker` (datalab-to / marker) | New dep + heavy | Highest; but huge model download, GPU-friendly |
| D | `pypdf` + custom heuristics | New dep | Low; we'd be reinventing layout parsing |

**Recommendation**: **A** (docling). It is *already* a dependency (added by [LCORE-1035](#html-precedent-lcore-1035) for HTML), the `BaseReader` plumbing exists, and PoC quality is good. Confidence: 95%.

### Decision 2: OCR for scanned PDFs

| Option | Description |
|--------|-------------|
| A | Out of scope for v1 — text-extractable PDFs only |
| B | Add `--ocr` opt-in flag, default off |
| C | Enable OCR by default |

**Recommendation**: **A**. Already discussed and confirmed during scope clarification. OCR adds tesseract / easyocr as runtime deps, multiplies conversion time, and the typical BYOK customer ships text PDFs. Track as a follow-up JIRA. Confidence: 90%.

### Decision 3: Repository placement

| Option | Description |
|--------|-------------|
| A | Implementation in `rag-content`, docs update in `lightspeed-stack` |
| B | All in `rag-content` (skip stack docs update) |
| C | All in `lightspeed-stack` (move BYOK pipeline) |

**Recommendation**: **A**. The "existing tool for producing BYOK vector store" *is* `rag-content`. `lightspeed-stack/docs/byok_guide.md` currently lists PDF under "Requires conversion" and tells customers PDFs must be converted to Markdown first — that needs to change to reflect native support. Confidence: 95%.

## Technical decisions for @maxrubyonrails

Architecture- and implementation-level decisions.

### Decision 4: Pipeline configuration knobs

`docling`'s `PdfPipelineOptions` exposes ~15 toggles. We need to pick defaults and decide which (if any) become CLI flags.

| Knob | Recommended default | Expose as CLI flag? | Rationale |
|------|---------------------|---------------------|-----------|
| `do_ocr` | `False` | No | Decision 2: OCR out of scope |
| `do_table_structure` | `True` | No | Tables are common; cheap quality win |
| `table_structure_options.mode` | `accurate` | No | Accuracy over speed for offline indexing |
| `do_picture_classification` | `False` | No | Vector search doesn't use pictures |
| `do_picture_description` | `False` | No | Heavy (VLM call), no vector-search value |
| `generate_page_images` | `False` | No | Wasted I/O |

**Recommendation**: ship the defaults above; **no CLI flags in v1**. This mirrors `HTMLReader`, which exposes nothing. Add flags later if customer feedback requires. Confidence: 80%.

### Decision 5: Chunking strategy

After docling exports to Markdown, how is the content chunked into vector-store nodes?

| Option | Description |
|--------|-------------|
| A | Reuse the existing `MarkdownNodeParser`. Add `"pdf"` to the `doc_type` branches in `_BaseDB.__init__` and `_LlamaStackDB.__init__` (extracted to a shared `MARKDOWN_COMPATIBLE_DOC_TYPES` constant — see spec doc). |
| B | Use docling's hybrid chunker (PDF-aware, page-boundary-aware). Different node parser path. |

**Recommendation**: **A**. docling already exports clean Markdown for body content (PoC evidence: tables, lists, paragraphs all preserved). The `MarkdownNodeParser` we use for HTML and Markdown is well-tested and handles the output. **B** adds a parallel chunking pipeline and complicates `document_processor.py`. If retrieval quality on PDFs is poor in practice, **B** is a clean follow-up. Confidence: 85%.

### Decision 6: Code organization

| Option | Description |
|--------|-------------|
| A | New `src/lightspeed_rag_content/pdf/` package (mirrors `html/`). Standalone `__main__.py`, separate `pdf_reader.py`. |
| B | Add PDF as a third format inside `html/` (rename module to `docling/`). |
| C | Refactor `HTMLReader` and `PDFReader` into a shared `DoclingReader` base. |

**Recommendation**: **A**. Mirrors the established pattern. **B** mixes concerns and renames a public module. **C** is a defensible cleanup but it's not in scope for LCORE-1471 — file it as a follow-up if both readers prove to share enough non-trivial logic to justify a base class. Confidence: 80%.

### Decision 7: Test coverage scope

| Option | Description |
|--------|-------------|
| A | Unit tests for the reader + CLI; integration test that builds a small Faiss index from a PDF and runs `query_rag.py`. |
| B | A only — no e2e through `lightspeed-stack`. |
| C | Full e2e — generate vector DB from PDF in rag-content, deploy via stack, run a real query against the stack endpoint. |

**Recommendation**: **A** for the test JIRA, **C** as a separate e2e JIRA. The `tests/html/` precedent gives us the unit-test pattern; e2e is real work that needs the full local stack running. Confidence: 80%.

## Filed JIRAs

Filed 2026-04-30 via `dev-tools/file-jiras.sh`, all under epic [LCORE-2090](https://issues.redhat.com/browse/LCORE-2090) which itself sits under feature ticket [LCORE-1471](https://issues.redhat.com/browse/LCORE-1471):

- [LCORE-2091](https://issues.redhat.com/browse/LCORE-2091) — Implement PDF support in rag-content
- [LCORE-2092](https://issues.redhat.com/browse/LCORE-2092) — Unit and integration tests for PDF support
- [LCORE-2093](https://issues.redhat.com/browse/LCORE-2093) — End-to-end test (PDF-built vector store consumed by lightspeed-stack)
- [LCORE-2094](https://issues.redhat.com/browse/LCORE-2094) — Update lightspeed-stack BYOK guide for native PDF support

Each `agentic tool instruction` points to the spec doc, not this spike doc.

<!-- type: Task -->
<!-- key: LCORE-2091 -->
### LCORE-2091: Implement PDF support in rag-content

**Description**: Add a `PDFReader` to `rag-content` mirroring the existing `HTMLReader`. Use `docling` (already a dependency) configured for `InputFormat.PDF`. Wire it into `document_processor.py` so PDFs are recognized and parsed via `MarkdownNodeParser`. Update the `rag-content` README to list PDF as supported.

**Scope**:

- New package `src/lightspeed_rag_content/pdf/` with `__init__.py`, `__main__.py`, `pdf_reader.py`.
- `PDFReader(BaseReader)` exposing `load_data(file: Path) -> list[Document]`. Use `TableFormerMode.ACCURATE` (enum), not the string `"accurate"`. Match `HTMLReader` on whether to invoke `super().__init__()`.
- `convert_pdf_file_to_markdown` and `convert_pdf_string_to_markdown` convenience helpers (mirror HTML).
- CLI subcommands `convert` and `batch` (mirror `html/__main__.py`).
- Per **R7**, `PDFReader.load_data` emits a `logger.warning` when the resulting Markdown is empty / under a small threshold (likely a scanned PDF). Threshold is a module-level `Final[int]` constant.
- Extract the `("markdown", "html", "pdf")` predicate in `document_processor.py` to a single module-level `MARKDOWN_COMPATIBLE_DOC_TYPES: Final[tuple[str, ...]]` constant and reference it from both `_BaseDB.__init__` and `_LlamaStackDB.__init__` (do not duplicate the tuple).
- Update `rag-content/README.md`: list PDF as a directly supported input format.
- Pass `uv run make format && uv run make verify` (or rag-content equivalent).
- No new entries in `pyproject.toml` — docling is already there.

**Acceptance criteria**:

- `python -m lightspeed_rag_content.pdf convert -i sample.pdf -o sample.md` succeeds.
- `python -m lightspeed_rag_content.pdf batch -i ./pdfs/ -o ./md/` converts a directory.
- Running `custom_processor.py` with `-f` pointing to a directory of PDFs produces a vector store the same way HTML and Markdown do.
- `rag-content/README.md` includes PDF in the supported-formats list.

**Agentic tool instruction**:

```text
Read the "Architecture", "Chunking", and "Implementation Suggestions"
sections in docs/design/byok-pdf/byok-pdf.md (in the lightspeed-stack
repo). R7 (warn on empty output) is in the "Requirements" section.
Key files in rag-content:
  src/lightspeed_rag_content/html/                       (precedent — mirror this)
  src/lightspeed_rag_content/document_processor.py       (extract MARKDOWN_COMPATIBLE_DOC_TYPES, use it in _BaseDB.__init__ and _LlamaStackDB.__init__)
  README.md
Mirror html/ into pdf/ with InputFormat.PDF and the pipeline options
listed in the spec doc's "Pipeline configuration" section.
```

<!-- type: Task -->
<!-- key: LCORE-2092 -->
### LCORE-2092: Unit and integration tests for PDF support

**Description**: Add unit tests for `PDFReader` and the CLI module mirroring the HTML test layout. Add an integration test that builds a small Faiss vector store from a real PDF and runs a query that returns expected content.

**Scope**:

- Create `tests/pdf/` directory with `__init__.py`.
- `tests/pdf/test_pdf_reader.py` mirroring `tests/html/test_html_reader.py` (load, error paths, missing file, conversion failure).
- `tests/pdf/test__main__.py` mirroring `tests/html/test__main__.py` (CLI argument parsing, convert and batch subcommands).
- Integration test: feed a small text PDF to `DocumentProcessor`, verify the resulting Faiss index contains a chunk whose text matches a known string from the source PDF.
- Commit a small (< 50 KB) text-extractable test PDF for fixtures.

**Acceptance criteria**:

- `pytest tests/pdf/` passes.
- Test coverage for `pdf/` matches the existing `html/` coverage threshold.
- Integration test runs in under 60 seconds on CI (cold model load excluded — pre-cache models in CI image).

**Agentic tool instruction**:

```text
Read the "Testing" section in docs/design/byok-pdf/byok-pdf.md.
Key files in rag-content:
  tests/html/test_html_reader.py     (mirror this)
  tests/html/test__main__.py         (mirror this)
  tests/conftest.py
Use docling's mock-friendly seam from the HTML tests.
```

<!-- type: Task -->
<!-- key: LCORE-2093 -->
### LCORE-2093: End-to-end test — PDF-built vector store consumed by lightspeed-stack

**Description**: Verify that a vector store generated from a PDF (via the new `pdf` module) is consumed correctly by `lightspeed-stack` end-to-end: the stack starts up, the BYOK source is registered, and a query that should retrieve content from the PDF actually returns it.

**Scope**:

- Add an e2e feature file under `tests/e2e/features/` (BDD style).
- Step definitions that (1) generate a vector store from a sample PDF, (2) start the stack pointed at it, (3) issue a query, (4) assert retrieved content matches PDF source.
- Add the new feature to `tests/e2e/test_list.txt`.

**Acceptance criteria**:

- The e2e feature passes locally with the full stack (Llama Stack + MCP Mock + lightspeed-stack).
- The feature is added to CI's e2e suite if/when CI supports the rag-content cross-repo dependency.

**Agentic tool instruction**:

```text
Read the "End-to-end validation" section in docs/design/byok-pdf/byok-pdf.md.
Key files:
  tests/e2e/features/                  (existing BDD features for pattern)
  tests/integration/endpoints/test_query_byok_integration.py  (similar pattern)
Generate the vector store ahead of stack startup using the rag-content
custom_processor.py invocation documented in the spec doc.
```

<!-- type: Task -->
<!-- key: LCORE-2094 -->
### LCORE-2094: Update lightspeed-stack BYOK guide for native PDF support

**Description**: Update `docs/byok_guide.md` to reflect that PDF is a directly supported input format, removing the "convert PDFs to Markdown first" instruction.

**Scope**:

- Edit `docs/byok_guide.md`:
  - "Knowledge Sources" subsection (under Prerequisites): move PDF from "Requires conversion" to "Directly supported"; clarify which formats still require conversion (e.g., AsciiDoc).
  - "Step 1: Prepare Your Knowledge Sources": remove the docling-as-pre-conversion example for PDFs, replace with a note that PDFs can be passed directly to `custom_processor.py`.
- Sanity-check no other parts of `docs/` give stale conversion advice (search for `docling` and `convert.*PDF`).

**Acceptance criteria**:

- `docs/byok_guide.md` no longer says PDFs require pre-conversion.
- A pointer to the rag-content README's PDF section is included.

**Agentic tool instruction**:

```text
Read the "Documentation impact" section in docs/design/byok-pdf/byok-pdf.md.
Key files:
  docs/byok_guide.md                          (Knowledge Sources subsection
                                                + Step 1)
  examples/lightspeed-stack-byok-okp-rag.yaml  (no change, but verify still
                                                accurate after PDF support)
```

## PoC results

A 60-line PoC script implementing `PDFReader` was committed to PR #1598 (commit `56be99cb`) under `docs/design/byok-pdf/poc/` along with two sample PDFs, then removed from the merged tree per [`howto-run-a-spike.md`](../../contributing/howto-run-a-spike.md) step 10. The PoC was run against both samples to validate that docling's PDF pipeline produces usable Markdown.

### What the PoC does

The PoC mirrors the production `HTMLReader` but configures docling for PDF (`InputFormat.PDF`, `PdfPipelineOptions` with the recommended defaults). It does *not* integrate with `document_processor.py` or implement a CLI — it is the minimum code needed to validate that docling's PDF pipeline produces usable Markdown.

**Important**: The PoC diverges from the production design in these ways:

- No CLI module (the production design has `__main__.py` with `convert` and `batch` subcommands).
- No `BaseReader` interface compliance (the PoC is a free function; production is a class).
- No `extra_info`/metadata passthrough (production handles `extra_info` like HTMLReader).
- No batch mode.
- No tests.

### Results

| PDF | Size | Wall-clock | Output | Quality |
|-----|------|-----------|--------|---------|
| sample_jira_1311.pdf | 217 KB | 332 s (incl. ~290 s model load) | 7,608 chars / 288 lines | High — clean headings, body, tables |
| sample_jira_836.pdf | 372 KB | ~70 s (warm) | 3,084 chars / 165 lines | Body clean; **headings degraded** (letter-spaced font) |

**What the PoC proved (validated against both samples)**:

1. **No new dependencies are needed.** docling, already in `pyproject.toml` for HTML, handles PDF via the same `DocumentConverter` API with `InputFormat.PDF` and `PdfFormatOption(pipeline_options=...)`.
2. **Body text and tables convert cleanly.** The 1311 sample produced two well-formed GitHub-flavored Markdown tables (Component/Behavior, Area/Impact) with correct headers and cell boundaries. Body paragraphs were free of hyphenation artifacts and broken sentences.
3. **`MarkdownNodeParser` will work for chunking.** Heading prefixes (`## `, `### `) survive intact, so the existing chunker splits on heading boundaries without modification.
4. **No parallel chunking pipeline needed.** A single `doc_type` branch addition is sufficient.

**Honest limitation surfaced by sample 836** (Confluence "Export to PDF"): letter-spaced display fonts cause docling to extract heading text with spaces between letters (e.g., `S t r e a m l i n e   l i g h t s p e e d - s t a c k   c o n f i g`). The `## ` prefix remains intact so chunking still happens at heading boundaries; only the heading *text* is corrupted. Body content under the heading is unaffected. This is a docling extraction limitation, not a `PdfPipelineOptions` knob. Documented as a known v1 caveat in the spec doc; no production fix in v1. A heading-cleanup post-processor is noted as a follow-up.

> The full PoC report, conversion logs, sample input PDFs, and converted Markdown outputs were committed to PR #1598 under `docs/design/byok-pdf/poc/` and `docs/design/byok-pdf/poc-results/` for review purposes, then removed before merge per [`howto-run-a-spike.md`](../../contributing/howto-run-a-spike.md) step 10. Their content is summarised above so the spike doc stays self-contained in the merged history. PR #1598's diff (commits `56be99cb` and `250881e2`) is the canonical reference if the raw artifacts are needed later.

## Background sections

### Current state of `rag-content`

The BYOK content tool lives at https://github.com/lightspeed-core/rag-content (sibling repo). Relevant structure:

```
rag-content/
├── pyproject.toml                # already has docling>=2.68.0
├── README.md                     # documents Markdown / text / HTML inputs
└── src/lightspeed_rag_content/
    ├── document_processor.py     # main pipeline; doc_type branches at L75, L87
    ├── metadata_processor.py
    ├── utils.py                  # CLI helpers (add_input_file_argument, etc.)
    ├── asciidoc/                 # AsciiDoc converter (Ruby-based, separate path)
    └── html/                     # HTML support — added by LCORE-1035
        ├── __init__.py
        ├── __main__.py           # `convert` and `batch` CLI
        └── html_reader.py        # 165 LoC, BaseReader, uses docling
```

The `document_processor.py` file already routes by `doc_type` inside both `_BaseDB.__init__` and `_LlamaStackDB.__init__`:

```python
if config.doc_type in ("markdown", "html"):
    Settings.node_parser = MarkdownNodeParser()
```

These are the only two predicates that need to grow `"pdf"` for chunking to work. The implementation ticket extracts the tuple to a shared `MARKDOWN_COMPATIBLE_DOC_TYPES` constant so the predicate cannot drift between the two call sites.

### HTML precedent (LCORE-1035)

PR `7f688b0` ("Add HTML support for BYOK", 2026-01-15) introduced the docling integration. Stats:

```
pyproject.toml                                   |   2 +
scripts/query_rag.py                             |   2 +-
src/lightspeed_rag_content/document_processor.py |   5 +-
src/lightspeed_rag_content/html/__init__.py      |  19 +
src/lightspeed_rag_content/html/__main__.py      | 153 +++++
src/lightspeed_rag_content/html/html_reader.py   | 163 +++++
src/lightspeed_rag_content/utils.py              |   3 +-
tests/html/__init__.py                           |  15 +
tests/html/test_html_reader.py                   | 147 +++++
uv.lock                                          | 799 ++++++++++++++++++++++-
```

PDF support follows the same shape minus the `uv.lock` blast (no new deps). Estimated PR size: ~400 LoC (vs LCORE-1035's 470 LoC excluding `uv.lock`).

### Why docling and not an alternative

The decision was effectively pre-made by LCORE-1035: docling is already vendored. But here is a brief comparison for completeness:

| Library | Strengths | Weaknesses for our use case |
|---------|-----------|------------------------------|
| **docling** | Already dep; layout + table ML; multi-format (PDF/HTML/DOCX); active dev | CPU-only is slow; large model downloads (already paid for HTML) |
| pymupdf4llm | Fast; small dep | Weaker on tables; no integrated CLI we already use |
| marker | Best quality on academic PDFs | Huge model download; GPU-friendly; overkill |
| pypdf + heuristics | Tiny dep | We'd reinvent layout parsing badly |

There is no compelling reason to add a second PDF library when docling is already paid for.

### Why MarkdownNodeParser and not docling's hybrid chunker

The PoC output for body content is clean Markdown — paragraph breaks where you'd expect, headings as `## `, tables as `|...|`. `MarkdownNodeParser` is what `MarkdownReader` uses internally and what we already use for HTML (which goes through the same docling → markdown → MarkdownNodeParser path). Using a different chunker for PDFs would create two parallel pipelines for what is essentially the same intermediate representation.

Docling's hybrid chunker is page-aware and could improve retrieval if PDF pagination conveys semantic structure (it usually doesn't for the BYOK use case — customer content is typically continuous prose). If we see retrieval quality issues on real customer PDFs, switching to the hybrid chunker is a self-contained follow-up.

### Documentation impact

In `lightspeed-stack`, `docs/byok_guide.md` currently states (line 106-107):

```
- **Directly supported**: Markdown (.md) and plain text (.txt) files
- **Requires conversion**: PDFs, AsciiDoc, HTML, and other formats must be
  converted to markdown or TXT
```

This claim is already stale (HTML is supported via LCORE-1035). LCORE-1471 should make it correct, listing PDF *and* HTML as directly supported and removing the docling-as-pre-conversion example in Step 1.

### Out of scope (follow-ups)

- **OCR for scanned PDFs** — docling supports OCR via tesseract or easyocr. Track as a separate feature.
- **DOCX, RTF, EPUB** — docling supports these; if customer demand emerges, add as separate readers.
- **Refactor HTMLReader + PDFReader into a shared base** — defensible but not required by LCORE-1471.
- **Hybrid (page-aware) chunking** — switch from MarkdownNodeParser if retrieval quality is poor on real PDFs.
- **Heading-cleanup post-processor** — collapse single-character runs in headings extracted from letter-spaced fonts.
