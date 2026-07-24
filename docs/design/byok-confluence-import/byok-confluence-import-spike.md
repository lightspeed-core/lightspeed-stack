# Spike for LCORE-788: Auto import of content for BYOK from Confluence

Spike ticket: LCORE-2664. Feature ticket: LCORE-788 (scope reduced 2026-06 to
Confluence only). Related epic: LCORE-256 (Alternative BYOK — frequent KB
updates without rebuild pain). Product context: OCPSTRAT-2278.

## Overview

**The problem**: Customers don't want to hand-build BYOK RAG databases. They
want to point Lightspeed at their Confluence and have the content imported —
and kept up to date — automatically. Today the BYOK workflow is entirely
manual and offline: an admin prepares Markdown/HTML/text files, runs the
`lightspeed-rag-content` tooling to build a faiss/pgvector store, and ships
the artifact to the service by hand. Nothing fetches from a remote source,
nothing refreshes, and the service cannot pick up a changed DB without a
restart.

**The recommendation**: Add a **Confluence fetch stage** to
`lightspeed-rag-content` (rendered-HTML export via the Confluence REST API →
existing docling/HTMLReader pipeline), plus a **documented Kubernetes
CronJob** that periodically re-crawls, rebuilds the vector-DB artifact, and
triggers a service rollout. Keep lightspeed-stack unchanged (existing
`byok_rag` config consumes the artifact as before). Incremental sync ships
as change *detection* (skip re-fetching/re-embedding unchanged pages) while
always producing a full rebuilt artifact; hot-reload of a live store is
explicitly out of scope.

**PoC validation**: A moderate PoC crawled a real space on
redhat.atlassian.net (Confluence Cloud, 20 pages, read-only API token),
built a `llamastack-faiss` store through the unmodified rag-content
pipeline, retrieved correct chunks with per-page Confluence URLs as
citations, and demonstrated incremental change detection (second run:
2 API calls instead of 21, zero re-embeds). See [PoC results](#poc-results).

## Settled decisions

Decided during the spike; recorded for context, **no reviewer
confirmation needed**.

### Decision S1: Where the importer lives — `rag-content` (settled)

The Confluence importer is build-time content tooling. The
[BYOK PDF spike](../byok-pdf/byok-pdf-spike.md) (Decision 3) already
established `lightspeed-core/rag-content` as the home for import tooling;
lightspeed-stack never opens vector DBs directly (all access goes through
the llama-stack client) and its config direction keeps ingestion out of the
serving path. The PoC needed zero changes to rag-content library code —
only a fetch script and a `MetadataProcessor` subclass. Alternatives
considered and rejected: lightspeed-stack (ingestion + crawler/docling
deps in the serving codebase) and a new repository (duplicated pipeline
internals, extra repo/release overhead). See
[Current BYOK state](#current-byok-state).

## Strategic decisions — for @sbunciak

High-level decisions that determine scope, approach, and cost. Each has a
recommendation — please confirm or override.

### Decision S2: Refresh architecture

LCORE-256's goal is frequent KB updates without pain. Today the service has
no hot-reload: a rebuilt DB requires a restart (no file-watching exists;
see [Current BYOK state](#current-byok-state)). See
[Refresh patterns on Kubernetes](#refresh-patterns-on-kubernetes).

| Option | Description |
|--------|-------------|
| A. Periodic full re-crawl → full rebuild → new artifact → rollout | Immutable artifact, deletions handled for free, zero service changes; staleness = cron period |
| B. Incremental sync into a live store | Fresher; requires net-new hot-reload plumbing in the service and mutates the artifact in place |
| C. Runtime ingestion inside lightspeed-stack | Service crawls Confluence itself; crawl+embed load in the serving path |

**Recommendation**: A as the epic baseline. Ship the cheap half of B as an
optional optimization (skip re-fetching/re-embedding unchanged pages via
CQL `lastmodified` + page-version cache — output is still a full rebuilt
artifact; validated in the PoC). Hot-reload stays out of scope as a
possible future epic.

**Confidence**: 85%

### Decision S3: Primary delivery artifact

Upstream Lightspeed Core Stack consumes a **file** (`byok_rag[].db_path`,
volume-mounted). Downstream OpenShift Lightspeed consumes a **BYOK OCI
image** (`/rag/vector_db`; see [Prior art](#prior-art-s2i-poc-and-ols-byok)).
rag-content already produces both (`--output-image`).

| Option | Description |
|--------|-------------|
| A. DB file primary, image optional | Filesystem artifact is the documented happy path; `--output-image` remains for image-based products |
| B. OCI image primary | Matches OLS contract; forces registry infra into the minimal upstream path |
| C. Both first-class | Double docs/test surface in this epic |

**Recommendation**: A.

**Confidence**: 80%

### Decision S4: Form of the deployable automation

LCORE-788 asks for "an automation Lightspeed admins can deploy".

| Option | Description |
|--------|-------------|
| A. Documented Kubernetes CronJob reference manifest | Wraps the importer container; portable to any k8s/OpenShift cluster |
| B. Shipwright BuildStrategy | Extends the s2i PoC; OCP-specific, assumes image contract + registry |
| C. Docs only | Ship the importer CLI/container; scheduling left entirely to admins |
| D. A + podman/systemd-timer reference | A, plus a Quadlet (`.container` + `.timer` systemd units) reference for podman-only hosts |

**Recommendation**: D — CronJob reference manifest + admin guide in
rag-content, documenting the DB-file flow (shared volume + rollout
trigger), **plus a podman-only reference**: Quadlet systemd units
(`.container` + `.timer`) running the same importer container on a
schedule, with a plain-cron one-liner noted as the minimal fallback.
Both references drive the identical container image and flags — the
automation layer is thin by design. Note B as the natural OLS
product-layer variant built on the same importer container.

*2026-07-21: extended from A to D per PM review on the spike PR
(non-Kubernetes deployments must be covered).*

**Confidence**: 88% (PM-confirmed with the podman amendment)

### Decision S5: Lightspeed-stack config surface

LCORE-788's scope list literally includes "provide configuration options in
Lightspeed stack config to enable this auto import". Under the recommended
design the importer is an offline tool: the existing `byok_rag` /
`rag.byok.stores` config already covers consumption of the produced
artifact, and importer configuration (Confluence URL, spaces, schedule,
credentials) belongs to the importer/CronJob, not the serving config.

| Option | Description |
|--------|-------------|
| A. No new lightspeed-stack config | Importer config lives with the importer; LCS docs point at it |
| B. Mirror importer settings in lightspeed-stack.yaml | Serving config describes an import the service itself never performs |

**Recommendation**: A. This deliberately reinterprets the ticket letter —
flagging for explicit PM confirmation.

**Confidence**: 82%

## Technical decisions — for @tisnik

### Decision T1: Fetch client library

See [Existing loaders](#existing-confluence-loaders). The PoC used raw
stdlib HTTP successfully; production needs pagination, retry/backoff, and
Cloud/DC parity without hand-rolling.

| Option | Description |
|--------|-------------|
| A. atlassian-python-api (Apache-2.0) | Thin, mature wrapper over Cloud+DC REST; we keep control of body format, CQL, state |
| B. llama-index-readers-confluence (MIT) | Highest-level; brings heavy attachment deps (pytesseract, pdf2image, docx2txt…); hides pagination/state |
| C. Raw REST (requests/httpx) | No new dep; we own retry/backoff/pagination/Cloud-DC differences |

**Recommendation**: A. B's attachment machinery is out of scope (T5) and
its abstraction hides the sync-state control we need; C re-implements what
A already does. A is also what B uses underneath.

**Confidence**: 70%

### Decision T2: Page body format

| Option | Description |
|--------|-------------|
| A. `body.export_view` (rendered HTML, v1 API) | Macros expanded; clean input for docling HTML→Markdown |
| B. `body.storage` (XHTML + `ac:`/`ri:` macros) | v2-native but macro tags mangle generic HTML→MD conversion |
| C. `atlas_doc_format` (ADF JSON) | Needs a dedicated renderer |

**Recommendation**: A. PoC evidence: headings, bold, links, nested lists,
and expand-macros all converted cleanly; the docling letter-spacing weakness
that affects Confluence "Export to PDF" does not apply to the HTML path.
Risk: `export_view` is not in the v2 API — Cloud requires v1 endpoints
(deprecation risk over the feature lifetime; DC keeps this surface).

**Confidence**: 88%

### Decision T3: Authentication modes

| Option | Description |
|--------|-------------|
| A. Cloud email+API-token (Basic) and DC PAT (Bearer) | Two single-secret headless modes, from env/K8s Secret |
| B. Also OAuth 2.0 3LO | Interactive consent + rotating refresh tokens; built for marketplace apps, poor fit for a CronJob |

**Recommendation**: A. Documentation must recommend a **service/bot
account** over personal tokens (Atlassian policies commonly require it —
Red Hat's own instance does; PoC finding 4) and must surface auth failures
loudly (Cloud tokens expire ≤ 1 year).

**Confidence**: 90%

### Decision T4: Content selection configuration

**Recommendation**: Space key list (required) + optional CQL filter and/or
label filter per space. CQL is the native server-side selection mechanism
and doubles as the incremental-sync primitive.

**Confidence**: 85%

### Decision T5: Attachments

**Recommendation**: Out of scope for the baseline epic — pages only.
PDF/Office attachments can later route through the byok-pdf pipeline
(LCORE-2090 line of work) as a follow-up; images/diagrams are dropped by
the HTML→Markdown conversion anyway.

**Confidence**: 75%

### Decision T6: Citation metadata plumbing

**Recommendation**: The fetch stage writes a `manifest.json`
(file → page id, title, canonical URL, version); a
`ConfluenceMetadataProcessor(MetadataProcessor)` resolves `url_function`
and `get_file_title` from it, with `hermetic_build=True` (page URLs are
auth-gated; reachability pings would mark every URL unreachable). Proven in
the PoC — every retrieved chunk carried title + canonical page URL.

**Confidence**: 90%

### Decision T7: Embedding-model pinning

A rebuilt DB is only queryable with the exact embedding model configured in
the consuming service; same-dimension model drift fails *silently*.

**Recommendation**: The importer requires an explicit model name; default to
HF-id resolution (`-md '' -mn <id>` convention) so the artifact is
path-portable; the admin guide states the runtime-match requirement in a
warning box. (PoC confirmed the absolute-model-path bake-in live.)

**Confidence**: 88%

### Decision T8: Change-detection mechanics

**Recommendation**: Sync state file (per-page version numbers + watermark)
kept next to the output. Delta = CQL `lastmodified >= watermark − overlap`
∪ pages absent from state; **deletions** = full ID enumeration diff (cheap,
no bodies; CQL alone cannot see deletions). Unchanged pages are neither
re-fetched nor re-embedded. Validated in the PoC for the no-change and
new-state cases; live update/delete exercised by the e2e tickets against a
mock Confluence.

**Confidence**: 85%

## Out of scope

- **Hot-reload of vector stores in lightspeed-stack** — no file-watching or
  re-registration path exists today; a restart/rollout picks up the new
  artifact. Deliberately deferred; candidate future epic under LCORE-256.
- **SharePoint, Git, generic web sources** — OCPSTRAT-2278 mentions them;
  LCORE-788 scope was explicitly reduced to Confluence (PM comment,
  2026-06-15). The fetch-stage/manifest seam is source-agnostic by design.
- **Attachments** (T5) — follow-up via the byok-pdf pipeline.
- **OAuth 2.0 3LO** (T3).
- **Operator/OLSConfig/Shipwright integration** — product-layer (OLS) work
  on top of the importer container; see
  [Prior art](#prior-art-s2i-poc-and-ols-byok).
- **Confluence permission mirroring** — imported content is served to all
  LCS users regardless of per-page Confluence restrictions; the admin guide
  must warn to import only spaces whose audience matches the assistant's.

## Proposed JIRAs

### Epic: BYOK auto-import from Confluence

Automation that builds and refreshes a BYOK vector store from Confluence,
per `docs/design/byok-confluence-import/byok-confluence-import.md`.

**Goals**:
- An admin can point the importer at Confluence spaces and get a BYOK
  vector-store artifact with per-page citations, with no manual document
  preparation.
- A documented CronJob keeps the artifact fresh (re-crawl, skip unchanged
  pages, rebuild, trigger rollout).
- Lightspeed Core Stack consumes the artifact with existing `byok_rag`
  configuration — no service changes.

**Scope**:
- In: rag-content fetch stage (Cloud + Data Center), incremental change
  detection, CronJob reference manifest, docs, unit/integration/e2e tests.
- Out: hot-reload, attachments, non-Confluence sources, operator
  integration (see spike doc Out-of-scope).

**Success criteria**:
- E2E: mock-Confluence → importer → artifact → lightspeed-stack answers
  with page-URL citations; a page edit followed by re-import updates
  answers after rollout.

<!-- type: Story -->
<!-- key: LCORE-???? -->
#### LCORE-???? E2E feature files for BYOK Confluence auto-import (no step implementation)

**User story**: As a Lightspeed Core e2e engineer, I want the behave
feature files for the Confluence auto-import scenarios written before the
implementation lands, so that the test shape reflects intended behavior
rather than the chosen implementation.

**Description**: Author behave `.feature` files under `tests/e2e/features/`
describing: import from a (mock) Confluence produces a queryable BYOK
store with page-URL citations; incremental re-import skips unchanged pages;
an edited page's content is served after re-import + restart; a deleted
page's content disappears after re-import + restart. Step definitions are
explicitly **not** part of this ticket (covered by LCORE-????).

**Scope**:
- `.feature` files covering R1..Rn from the spec doc
- Additions to `tests/e2e/test_list.txt`
- Author from spec doc requirements only; do not read implementation code

**Acceptance criteria**:
- behave parses every new `.feature` file without syntax errors
- behave marks all new scenario steps as `undefined`
- `uv run make test-e2e` remains green (new scenarios undefined, not failing)

**Blocks**: LCORE-???? (step-definitions counterpart)

**Agentic tool instruction**:

```text
Read "Requirements" and "Acceptance test surface" in
docs/design/byok-confluence-import/byok-confluence-import.md.
Do NOT read other JIRAs' scope sections or implementation code while
authoring. Key files to create:
tests/e2e/features/byok_confluence_import*.feature plus additions to
tests/e2e/test_list.txt. Do NOT create step definitions.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Implement behave step definitions for BYOK Confluence auto-import

**Description**: Implement Python step definitions under
`tests/e2e/features/steps/` for the feature files authored in the kickoff
ticket, including a mock Confluence REST fixture (v1 content listing,
`body.export_view`, CQL search) so scenarios run hermetically. Take the
Gherkin as-is; if a scenario cannot be implemented faithfully, raise it
against the spec doc rather than weakening the test.

**Blocked by**:
- LCORE-???? (E2E feature files kickoff)
- LCORE-???? (Confluence fetch stage)
- LCORE-???? (pipeline integration + packaging)

**Agentic tool instruction**:

```text
Read "Architecture" and "Requirements" in
docs/design/byok-confluence-import/byok-confluence-import.md.
Take feature files from tests/e2e/features/byok_confluence_import*.feature
as-is. To verify: `uv run make test-e2e` runs every new scenario green.
```

<!-- type: Story -->
<!-- key: LCORE-???? -->
#### LCORE-???? Implement Confluence fetch stage in rag-content

**User story**: As a Lightspeed admin, I want to fetch Confluence spaces as
pipeline-ready documents with one command, so that I don't prepare BYOK
content by hand.

**Description**: New `lightspeed_rag_content.confluence` module + CLI
(mirroring the `html`/`pdf` module pattern): crawl configured spaces via
the REST API (Cloud API-token and DC PAT auth), write per-page rendered
HTML + `manifest.json` + sync state; incremental mode per spike Decision
T8 (CQL delta, version skip, deletion diff). Includes
`ConfluenceMetadataProcessor` (manifest-driven URL/title,
`hermetic_build`). Unit tests against recorded API fixtures.

**Scope**:
- Full + incremental crawl, deletion handling, pagination, retry/backoff
  honoring 429 `Retry-After`
- Auth from env vars; no secrets in CLI args or logs
- Loud, actionable failure on auth errors (expired token) and permission
  denials

**Acceptance criteria**:
- One command produces a directory consumable by the existing pipeline
  with correct per-page metadata
- Second run against unchanged spaces performs no body fetches and no
  re-embeds
- Deleting a page removes it from the next build
- Works against Confluence Cloud and Data Center API shapes (fixtures)

**Agentic tool instruction**:

```text
Read "Architecture" and "Implementation Suggestions" in
docs/design/byok-confluence-import/byok-confluence-import.md.
Key files: src/lightspeed_rag_content/confluence/ (new),
tests/confluence/ (new), following the html/ and pdf/ module patterns
in lightspeed-core/rag-content.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? End-to-end importer command and container packaging

**Description**: A single `import-confluence` entrypoint that runs
fetch → build → (optional) image packaging in one invocation, wired into
the rag-content tool image; integration test covering
fetch-dir → `llamastack-faiss` artifact with citation metadata.

**Blocked by**: LCORE-???? (Confluence fetch stage)

**Scope**:
- CLI orchestration (fetch stage + DocumentProcessor + optional
  `--output-image`)
- Embedding-model pinning per spike Decision T7 (explicit model, HF-id
  resolution default, mismatch warning in output)
- Tool-image (Containerfile) inclusion + smoke test

**Acceptance criteria**:
- `podman run … import-confluence …` with env-provided credentials
  produces the artifact end-to-end
- Integration test builds from fixture HTML and asserts chunk metadata
  (title, canonical URL)

**Agentic tool instruction**:

```text
Read "Architecture" and "Implementation Suggestions" in
docs/design/byok-confluence-import/byok-confluence-import.md.
Key files: scripts/, Containerfile, src/lightspeed_rag_content/confluence/
in lightspeed-core/rag-content.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Scheduled-refresh references (CronJob, podman/systemd) and admin automation guide

**Description**: Reference automation for scheduled refresh in two
deployment shapes, both driving the same importer container: a Kubernetes
CronJob manifest (shared volume for the artifact + state; rollout trigger
for lightspeed-stack) and a podman-only Quadlet reference (`.container` +
`.timer` systemd units, plain-cron fallback noted). Plus the admin guide
covering credentials (Secret / podman secret; service-account
recommendation), scheduling, staleness expectations, and the security
warning about permission flattening.

**Blocked by**: LCORE-???? (end-to-end importer command)

**Acceptance criteria**:
- Manifest applies cleanly on a stock OpenShift/k8s cluster
- Quadlet units run the same refresh on a podman-only RHEL-family host
  (systemd timer fires, artifact refreshed, restart documented)
- Guide walks an admin from zero to scheduled refresh with the DB-file
  contract in both shapes (image variant referenced)

**Agentic tool instruction**:

```text
Read "Architecture" and "Rollout / deployment plan" in
docs/design/byok-confluence-import/byok-confluence-import.md.
Key files: examples/ and docs/ in lightspeed-core/rag-content.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Update lightspeed-stack BYOK documentation for Confluence auto-import

**Description**: Extend `docs/byok_guide.md` with the Confluence source:
point at the rag-content importer + CronJob guide, document the
embedding-model-match requirement, the restart-to-pick-up-changes
behavior, and the permission-flattening warning. Per spike Decision S5, no
lightspeed-stack config changes.

**Blocked by**: LCORE-???? (CronJob reference manifest and admin guide)

**Acceptance criteria**:
- byok_guide has an end-to-end "from Confluence" walkthrough consistent
  with the rag-content docs

**Agentic tool instruction**:

```text
Read "What" and "Architecture" in
docs/design/byok-confluence-import/byok-confluence-import.md.
Key files: docs/byok_guide.md, docs/rag_guide.md in
lightspeed-core/lightspeed-stack.
```

## Proposed incidental JIRAs

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? rag-content: generated llama-stack.yaml conflicts with registration persisted in faiss_store.db

**Description**: A freshly built `llamastack-faiss` store cannot be opened
with its own generated `llama-stack.yaml`: the
`registered_resources.vector_stores` entry re-registers the vector store
with fewer fields than the registration already persisted inside
`faiss_store.db`, and llama-stack raises
`ValueError: Object of type 'vector_store' … already exists with
conflicting field values: {'provider_resource_id': (None, 'vs_…'),
'vector_store_name': (None, '<index>')}`. This breaks
`scripts/query_rag.py` out of the box (observed during the LCORE-2664 PoC;
worked around by dropping the `registered_resources.vector_stores` entry
and querying the persisted registration). Likely a llama-stack
version-bump regression: either the generated yaml should carry the full
field set, or query_rag should not re-register.

## PoC results

### What the PoC does

Moderate-ambition PoC (three small scripts +
`ConfluenceMetadataProcessor`), run against **real Confluence Cloud**
(redhat.atlassian.net, space RHAT, 20 pages, regular user's read-only API
token):

1. Full crawl: v1 REST `body.export_view` → 20 HTML files +
   `manifest.json` + `state.json`.
2. Build: unmodified rag-content pipeline (docling `HTMLReader`,
   `MarkdownNodeParser`, `all-mpnet-base-v2`, `llamastack-faiss`) →
   `faiss_store.db` (3.8 MB).
3. Verify: `vector_io.query` via the llama-stack library client.
4. Incremental: second crawl with CQL `lastmodified` + version comparison.

**Important**: The PoC diverges from the production design in these ways:
- Raw stdlib HTTP instead of atlassian-python-api; no retry/backoff.
- Credentials read from the developer's Jira CLI credentials file.
- No CLI/config surface, no container, no CronJob.
- Update/delete sync paths implemented but not exercised live (no writable
  space available — see finding 3); covered logically and deferred to the
  e2e tickets (mock Confluence).

### Results

| Step | Outcome |
|---|---|
| Full crawl | 20/20 pages, ~1 API call/page + 1 listing call |
| Build | All pages converted; no letter-spacing artifacts (HTML path) |
| Retrieval | Top-3 chunks for a policy question: correct pages, scores 2.25/1.65/1.60 |
| Citations | Title + canonical page URL on every chunk |
| Incremental | `fetched=0 unchanged=20 deleted=0`; 2 API calls vs 21 |

Evidence: `poc-results/` (sanitized — crawled content is Red Hat-internal;
removed before merge).

### Findings discovered during the PoC

- **Zero rag-content changes needed** for the mechanism — the
  `file_extractor`/`MetadataProcessor` seams suffice. Implication: the
  implementation is fetch-stage + glue, low architectural risk.
- **`hermetic_build=True` is mandatory** for auth-gated sources, else every
  URL is flagged unreachable (or worse, `drop` mode empties the corpus).
- **Read-only tokens are the realistic baseline**: even space creation was
  403-forbidden for a regular corporate user. The importer must require
  nothing beyond read.
- **Governance**: Atlassian-instance policies (including Red Hat's own)
  require registered bot/service accounts for team integrations —
  the admin guide must say so (T3).
- **`doc_type="html"` does not auto-wire the HTMLReader** — the caller must
  pass `file_extractor={".html": HTMLReader()}`; `required_exts` is also
  needed to keep `manifest.json`/`state.json` out of the corpus.
- **Incidental bug**: generated `llama-stack.yaml` + `query_rag.py`
  registration conflict (see Proposed incidental JIRAs).
- **Absolute embedding-model path** is baked into the generated config and
  kv registry unless HF-id resolution is used (T7).
- **Incomplete git-LFS model checkout** fails late with an obscure
  `model.safetensors not found` — a preflight check in the importer command
  would save admins a full crawl.

## External input needed

- Whether OpenShift Lightspeed plans to consume this importer for its BYOK
  image flow (affects how much weight the image-packaging path gets) — ask
  the OLS PM via @sbunciak.

## Background sections

### Current BYOK state

lightspeed-stack: operators declare stores under `byok_rag:`
(`src/models/config.py` `ByokRag`; faiss `db_path` or pgvector);
`src/llama_stack_configuration.py` enriches them into llama-stack
`run.yaml` (`VECTOR_IO_TEMPLATES` supports `inline::faiss` and
`remote::pgvector` only); retrieval fans out in
`src/utils/vector_search.py`. All vector access is mediated by the
llama-stack client — the service never opens DBs directly, and the
config-merge design (LCORE-836) keeps operator config backend-agnostic.
**No hot-reload**: nothing watches `db_path`; a changed DB needs a
restart. The customer workflow today is fully manual
(`docs/byok_guide.md`): prepare files → run rag-content → mount the
artifact.

rag-content: a local-files framework — `SimpleDirectoryReader` +
per-extension readers (docling `HTMLReader` on main, `PDFReader` on the
LCORE-2091 branch) → `MarkdownNodeParser` (380/0) → embed → faiss/pgvector
in llama-index or llama-stack flavor → optional OCI packaging
(`--output-image`, artifact at `/rag/vector_db`). Chunk metadata carries
`docs_url`/`title` via `MetadataProcessor` (frontmatter `url` or
`url_function`). **No remote-source concept, no crawler, no scheduler
anywhere** — the fetch stage is greenfield, but everything downstream of
local files is reusable as-is (proven by the PoC).

### Confluence API landscape

- **Cloud**: v2 API for fast cursor-paginated listing; **CQL search and
  `body.export_view` are v1-only** — a Cloud importer necessarily uses
  both. DC: the v1-shaped surface + PATs.
- **CQL**: `space in (…) and type=page and lastmodified >= "yyyy/MM/dd
  HH:mm"` is the delta primitive; minute granularity and user-timezone
  interpretation ⇒ use an overlap buffer + version comparison
  (deduplicates re-fetches). `content/search` caps result windows (50 with
  body expand) ⇒ search for IDs, fetch bodies individually.
- **Deletions are invisible to CQL** ⇒ full ID enumeration diff each run
  (cheap: no body expands).
- **Rate limits**: Cloud is points-based per tenant with 429 +
  `Retry-After` (API-token Basic traffic currently exempt but unpublished
  burst limits apply); DC limits are admin-configurable. Importer must
  honor `Retry-After`.

### Existing Confluence loaders

| Tool | License | Fit |
|---|---|---|
| atlassian-python-api 4.x | Apache-2.0 | Recommended (T1): thin Cloud+DC client, CQL, attachment APIs |
| llama-index-readers-confluence | MIT | Full loader; heavy attachment deps; hides sync state |
| langchain-community ConfluenceLoader | MIT | Same underlying client; no incremental state; langchain dep |
| unstructured-ingest / Airbyte / RAGFlow / Elastic connectors | various | Platform-scale connectors; useful as sync-pattern references (Elastic's version-skip + ID-diff informs T8), not as dependencies |

### Prior art: s2i PoC and OLS BYOK

- **syedriko s2i PoC** (lightspeed-rag-content fork, `syedriko-s2i`
  branch): Git-hosted Markdown → Shipwright BuildRun on OCP runs
  `generate_embeddings_tool.py` → UBI9 image containing `/rag/vector_db` →
  registry → OLS picks it up. The Confluence importer slots in as the
  *document producer* upstream of exactly this build — which is why S4
  keeps Shipwright as the OLS-layer variant.
- **OLS BYOK today**: customer Markdown → `lightspeed-rag-tool` container →
  `byok-image.tar` → registry → `OLSConfig.spec.ols.rag`
  (`indexPath: /rag/vector_db`). Tech Preview.

### Refresh patterns on Kubernetes

| Pattern | Pros | Cons |
|---|---|---|
| CronJob → rebuild artifact → rollout (**recommended**) | Immutable, auditable; matches both LCS file and OLS image contracts; no service changes | Staleness = cron period; full-rebuild embed cost (mitigated by version-skip) |
| CronJob → live store on shared PVC | No restart | Needs hot-reload the service doesn't have; RWX storage; mutable artifact |
| Sidecar sync | Freshest | Embedding workload inside serving pods; per-replica duplication |
| Init container | Simple | Refresh only on restart; slow pod starts |

## Glossary

- **BYOK** — Bring Your Own Knowledge: customer-supplied RAG content
  served alongside product docs.
- **export_view** — Confluence REST body representation: fully rendered
  HTML with macros expanded.
- **CQL** — Confluence Query Language; server-side content search
  (selection + delta detection).
- **Sync state** — per-page version numbers + last-sync watermark kept
  between importer runs.
