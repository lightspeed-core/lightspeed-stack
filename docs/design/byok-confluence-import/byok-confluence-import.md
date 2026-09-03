# Feature design for LCORE-788: BYOK auto-import from Confluence

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-07-09                                |
| **Component**      | lightspeed-core/rag-content (primary), lightspeed-core/lightspeed-stack (docs only) |
| **Authors**        | Maxim Svistunov                           |
| **Feature**        | [LCORE-788](https://redhat.atlassian.net/browse/LCORE-788) |
| **Spike**          | [LCORE-2664](https://redhat.atlassian.net/browse/LCORE-2664) — [spike doc](byok-confluence-import-spike.md) |
| **Links**          | [LCORE-256](https://redhat.atlassian.net/browse/LCORE-256) (Alternative BYOK), OCPSTRAT-2278 |

## What

An importer in `lightspeed-rag-content` that builds — and periodically
refreshes — a BYOK vector-store artifact directly from Confluence: it
crawls configured spaces via the Confluence REST API (Cloud and Data
Center), converts rendered page HTML to Markdown through the existing
docling pipeline, embeds and packages the store exactly like today's
manual flow, and preserves per-page Confluence URLs as citation metadata.
A documented Kubernetes CronJob wraps the importer for scheduled refresh;
Lightspeed Core Stack consumes the artifact through its existing
`byok_rag` configuration, unchanged.

## Why

Customers store their private documentation predominantly in Confluence.
Today's BYOK flow requires them to export/prepare files by hand, run the
rag-content tooling manually, and re-do all of it whenever content
changes. That is enough friction that BYOK content goes stale or never
gets built. This feature removes the manual preparation (point at spaces,
get a store) and the manual refresh (CronJob keeps it current, skipping
unchanged pages).

## Requirements

- **R1:** The importer fetches all pages of one or more configured
  Confluence spaces and produces a directory of documents consumable by
  the existing rag-content pipeline, with no manual preparation.
- **R2:** Confluence Cloud (email + API token, Basic) and Data Center
  (Personal Access Token, Bearer) are both supported; credentials come
  from environment variables (Kubernetes Secret), never CLI args or logs.
- **R3:** Selection is configurable: space keys (required), optional CQL
  and/or label filter.
- **R4:** Every chunk in the built store carries the source page's title
  and canonical Confluence URL, so answers can cite the page.
- **R5:** A single command performs fetch → build → artifact
  (`llamastack-faiss` file by default; optional OCI image via the existing
  `--output-image`).
- **R6:** Incremental refresh: a re-run against unchanged spaces performs
  no page-body fetches and no re-embeddings; changed pages are re-imported;
  deleted pages disappear from the rebuilt artifact.
- **R7:** The importer requires an explicit embedding model and produces a
  path-portable artifact by default (HF-id resolution); the docs state the
  build/runtime model-match requirement.
- **R8:** Failures are loud and actionable: auth errors (expired token),
  permission denials, and rate limiting (429 honoring `Retry-After`) are
  reported distinctly; a partial crawl never silently produces a truncated
  store.
- **R9:** Reference automation and an admin guide document the
  scheduled-refresh deployment in two shapes driving the same importer
  container: a Kubernetes CronJob manifest (shared volume + rollout
  trigger) and a podman-only Quadlet reference (`.container` + `.timer`
  systemd units) for non-Kubernetes hosts.
- **R10:** lightspeed-stack requires no code or config-schema changes; its
  BYOK guide documents the Confluence flow (spike Decision S5).

## Use Cases

- **U1:** As a Lightspeed admin, I want to point the importer at my
  Confluence spaces and get a ready BYOK store, so that I don't prepare
  documents by hand.
- **U2:** As a Lightspeed admin, I want a scheduled job to keep the store
  current with Confluence edits and deletions, so that answers don't go
  stale.
- **U3:** As a Lightspeed user, I want answers grounded in my company's
  Confluence with links to the exact pages, so that I can verify and read
  more.
- **U4:** As an OpenShift Lightspeed engineer, I want the importer usable
  as a container step, so that the product's BYOK-image build (Shipwright)
  can adopt it.

## Architecture

### Overview

```text
                    lightspeed-rag-content (importer, offline)
┌──────────────────────────────────────────────────────────────────┐
│  fetch stage (new)                    build stage (existing)     │
│  Confluence REST ──► pages/*.html ──► docling HTMLReader         │
│   Cloud v1+v2 / DC     manifest.json    │ Markdown               │
│   CQL delta, version   state.json       ▼                        │
│   skip, deletion diff              MarkdownNodeParser (380/0)    │
│                                         │ embed (pinned model)   │
│                                         ▼                        │
│                              faiss_store.db (+ llama-stack.yaml) │
│                              [optional --output-image OCI tar]   │
└──────────────────────────────────────────────────────────────────┘
        ▲ CronJob (scheduled)                  │ artifact on shared
        │ credentials from Secret              ▼ volume / registry
   Confluence                     lightspeed-stack (unchanged)
   (customer)                     byok_rag: db_path → rollout restart
                                  → answers with page-URL citations
```

### Trigger mechanism

Manual invocation (one-shot CLI / `podman run`) or the reference CronJob
on a schedule. There is no in-service trigger: the service picks up a new
artifact on restart/rollout (spike Decision S2; hot-reload deferred).

### Storage / data model changes

None to lightspeed-stack. New importer-side files kept next to the
output artifact:

- `manifest.json` — per fetched file: page id, title, canonical URL,
  version, space.
- `state.json` — last-sync watermark (UTC) + page-id → version map,
  enabling incremental runs and deletion detection.

### Configuration

Importer configuration (CLI flags / env; no lightspeed-stack schema):

```yaml
# conceptual shape; concrete form is CLI flags + env vars
confluence:
  url: https://example.atlassian.net      # or DC base URL
  auth: cloud_token | dc_pat              # secrets via env: CONFLUENCE_EMAIL / CONFLUENCE_TOKEN
  spaces: [DOCS, RUNBOOKS]
  cql_filter: 'label = "public-docs"'     # optional
embedding:
  model_name: sentence-transformers/all-mpnet-base-v2   # required, HF-id resolved
output:
  dir: /data/vector_db
  index: byok-confluence
  image: null                             # optional OCI tar path
```

### Error handling

- Auth failure (401/403): exit non-zero with a message naming the auth
  mode and the likely cause (expired Cloud token ≤ 1 yr, revoked PAT).
- Rate limiting (429): honor `Retry-After`, bounded retries, then fail
  loudly.
- Per-page conversion failure: log and continue (page skipped, listed in
  the run summary); abort only if a configurable failure ratio is
  exceeded — a partial crawl must never silently ship a truncated store
  (R8).
- Preflight: verify the embedding model directory is complete
  (`model.safetensors` present) *before* crawling (PoC finding).

### Security considerations

- Read-only Confluence access is sufficient and is the required posture;
  docs recommend a registered service/bot account (instance policies —
  including Red Hat's own — commonly mandate it).
- Secrets only via env/Secret; never logged, never in CLI args (R2).
- **Permission flattening**: imported content is served to every LCS user
  regardless of per-page Confluence restrictions. The admin guide carries
  a prominent warning to import only spaces whose audience matches the
  assistant's audience.
- Crawled corporate content lands in artifacts (store, optionally image):
  treat them with the same confidentiality as the source space.

## Acceptance test surface

| Req | Observable behavior | Verified by |
|-----|---------------------|-------------|
| R1  | One command against a (mock) Confluence yields a queryable store containing all space pages | e2e (mock Confluence), integration |
| R2  | Cloud-token and DC-PAT auth shapes both work; secrets absent from logs/argv | unit (fixtures), e2e |
| R3  | Space/CQL/label selection imports exactly the matching pages | unit, e2e |
| R4  | Query responses cite page title + canonical URL | e2e through lightspeed-stack |
| R5  | Fetch→build→artifact in one invocation; optional image tar loadable | integration |
| R6  | Re-run, no changes: 0 body fetches, 0 re-embeds. Edit: page re-imported. Delete: gone after rebuild | e2e (mock) |
| R7  | Missing/incomplete model fails preflight; artifact loads from a different absolute path | integration |
| R8  | 401/403/429 produce distinct, actionable, non-zero outcomes | unit (fixtures) |
| R9  | Reference CronJob applies cleanly; scheduled run refreshes the artifact; Quadlet timer does the same on a podman-only host | e2e (kind/CRC) or documented manual verification |
| R10 | lightspeed-stack serves the artifact with existing `byok_rag` config | e2e |

## Aspect-specific concerns

### Latency and Cost

No serving-path impact (offline importer). Importer cost per run ≈
1 listing call per ~100 pages + 1 body call per changed page + embedding
of changed pages only (R6). Full first crawl of a large space is
API-bound; Cloud rate limits make very large spaces a multi-minute, not
multi-hour, operation at default limits.

### Failure modes

- Confluence v1 API deprecation on Cloud would break `export_view`
  fetching (spike Decision T2 risk) — isolated inside the fetch stage.
- Macro-heavy pages (Jira tables, drawio) degrade to whatever
  `export_view` renders; content inside unrendered macros is lost
  silently — documented limitation.
- Embedding-model drift between importer and service returns silently
  irrelevant results (R7 warning; not detectable at runtime today).
- CronJob rebuilds while the service reads the mounted file: the reference
  manifest writes to a versioned path and switches atomically
  (symlink/rename), never in-place.

### Rollout / deployment plan

Admin-driven: deploy the scheduler (k8s CronJob, or Quadlet systemd timer
on podman-only hosts) → first full crawl → point `byok_rag` at the
artifact → restart. Refresh = scheduled rebuild + restart trigger
(documented `kubectl rollout restart`, `systemctl restart`, or
operator-specific equivalent). Rollback = repoint to the previous
versioned artifact and restart.

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/lightspeed_rag_content/confluence/__init__.py` (rag-content, new) | Package docstring |
| `src/lightspeed_rag_content/confluence/fetcher.py` (new) | Crawl/CQL/state logic on `atlassian-python-api`; writes pages + manifest + state |
| `src/lightspeed_rag_content/confluence/metadata.py` (new) | `ConfluenceMetadataProcessor(MetadataProcessor)`: `url_function`/`get_file_title` from manifest; `hermetic_build=True` |
| `src/lightspeed_rag_content/confluence/__main__.py` (new) | CLI (`fetch`, `import` subcommands), mirroring `html/__main__.py` |
| `scripts/import_confluence.py` (new) | One-shot orchestration: fetch → `DocumentProcessor` → optional `--output-image` |
| `Containerfile` (modify) | Include the importer entrypoint in the tool image |
| `examples/confluence-cronjob.yaml` (new) | Reference CronJob manifest |
| `examples/confluence-import.container` + `.timer` (new) | Quadlet reference for podman-only hosts |
| `docs/` (rag-content, new page) | Admin automation guide |
| `docs/byok_guide.md` (lightspeed-stack, modify) | Confluence walkthrough, model-match + restart + permission warnings |
| `tests/confluence/` (rag-content, new) | Unit tests on recorded Cloud/DC fixtures; integration test fixture-HTML → artifact |

### Insertion point detail

The pipeline is consumed as-is:
`DocumentProcessor.process(folder, metadata=ConfluenceMetadataProcessor(...),
required_exts=[".html"], file_extractor={".html": HTMLReader()})` then
`save(index, output)`. Two PoC-verified gotchas: `doc_type="html"` sets
only the node parser — the caller must wire `HTMLReader` via
`file_extractor`; and `required_exts` must exclude `manifest.json` /
`state.json` from the corpus.

### Config pattern

Importer flags extend `utils.get_common_arg_parser()` (rag-content
convention) rather than introducing a config file; secrets exclusively via
env vars. No lightspeed-stack Pydantic changes (R10).

### Test patterns

- Unit: recorded REST fixtures for Cloud and DC shapes (pagination,
  CQL windows, 429 with `Retry-After`, 401/403).
- Integration: fixture HTML dir → artifact; assert chunk metadata
  (title/URL), version-skip behavior, deletion diff.
- e2e (lightspeed-stack): mock Confluence REST fixture (v1 listing,
  `export_view`, CQL) driving import → serve → cite; edit and delete
  scenarios per R6. Live Confluence is explicitly not required by CI.

## Open Questions for Future Work

- Hot-reload of a refreshed store without restart — deferred from spike
  Decision S2; candidate epic under LCORE-256.
- Attachments (PDF/Office via byok-pdf pipeline) — deferred from spike
  Decision T5.
- Non-Confluence sources (SharePoint/Git/web) reusing the fetch-stage
  seam — out of scope per LCORE-788 PM scope reduction (2026-06-15).
- OLS/Shipwright adoption of the importer container — pending External
  input (spike doc); affects image-path priority.
- Confluence v1 API longevity on Cloud (export_view/CQL) — monitor;
  isolated in `fetcher.py` (spike Decision T2).

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-07-09 | Initial version | LCORE-2664 spike |
| 2026-07-21 | R9 + rollout + key files: added podman/Quadlet reference alongside the k8s CronJob | PM review on spike PR (spike Decision S4 amended A→D) |

## Appendix A: PoC evidence summary

Validated on Confluence Cloud (redhat.atlassian.net, 20-page space,
read-only token): full crawl → unmodified pipeline → 3.8 MB
`llamastack-faiss` store; correct top-3 retrieval with page-URL citations;
incremental re-run touched 2 API endpoints and re-embedded nothing.
Details and findings: [spike doc, PoC results](byok-confluence-import-spike.md#poc-results).
