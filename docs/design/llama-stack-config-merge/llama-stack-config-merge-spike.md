# Spike: Llama Stack config merge (unified `lightspeed-stack.yaml`)

## Overview

**The problem**: Operators today must maintain two configuration files —
`lightspeed-stack.yaml` (LCORE settings) and `run.yaml` (Llama Stack
operational config: providers, storage, APIs, safety, registered resources).
This split increases the chance of misconfiguration, makes downstream
deployment templates larger, and forces every Lightspeed team to understand
Llama Stack's internal schema. LCORE-836 asks for a single source of truth.

**The recommendation**: A layered approach — "Option C + Option E layer":

- **High-level keys** in `lightspeed-stack.yaml` under a new `llama_stack.config`
  section (inference, later storage/safety/...). Most downstream teams write
  only these.
- **`native_override`** escape hatch under the same section — raw Llama Stack
  schema, deep-merged last. Covers anything the high-level schema doesn't
  express.
- **`profile`** field that points to a YAML file used as the baseline — the
  "profiles" feature is mechanism-only; LCORE ships no profiles of its own
  beyond one or two reference examples under `examples/profiles/`.
- **`baseline: default | empty`** selects whether the synthesis starts from
  LCORE's built-in baseline or a blank slate.
- **Legacy mode preserved**: existing `llama_stack.library_client_config_path`
  works unchanged through a deprecation window. Mutual exclusion with the new
  `llama_stack.config` block is enforced at load time.
- **Migration tool**: `lightspeed-stack --migrate-config` produces a unified
  single-file config from an existing (`run.yaml` + `lightspeed-stack.yaml`)
  pair, lossless round-trip.

**PoC validation**: A Level 3' PoC (per the spike howto) proves the mechanism
end-to-end in library mode. A unified `lightspeed-stack.yaml` containing only
`llama_stack.config` (no external `run.yaml`) successfully drives LCORE:
liveness/readiness green, `/v1/query` returns a real model response,
`native_override` demonstrably takes effect. Full unit-test suite passes
(2098 tests), including a lossless migrate-then-synthesize round-trip.
Server-mode end-to-end was not re-run through docker-compose — the container
rebuild time was impractical and unrelated to PoC quality (the container image
is ~2 GB of LS dependencies); the same synthesis code path is exercised by the
library-mode PoC and unit tests.

---

## Strategic decisions — for @sbunciak (PM) and @tisnik

These set scope, approach, and rollout shape. Each has a recommendation —
please confirm or override.

### Decision S1: Overall shape (Option C + optional Option E)

See [Design alternatives considered](#design-alternatives-considered) for the
full option set and scoring.

| Option | Summary |
|---|---|
| A (Embedded native only) | `lightspeed-stack.yaml.llama_stack.config` is raw Llama Stack schema |
| **B + C (High-level + native override)** | High-level keys cover the common path, `native_override` as escape hatch |
| E (Profiles) | Named or path-based pre-built config bundles, layered on top of A/B/C |
| G (Kustomize-style patches) | Ship a default baseline, operator writes JSON-Patch-like overlays |

**Recommendation**: **C** (high-level + native_override) with **E** (profile
feature, no shipped profiles) as an optional layer. Best balance of UX,
escape-hatch power, validation rigor, and dynamic-reconfig fit for the
broader feature roadmap (LCORE-777/781).

### Decision S2: Deprecation timeline for the legacy path

Legacy mode (`llama_stack.library_client_config_path` + external `run.yaml`)
must coexist with unified mode through a deprecation window to avoid breaking
downstream teams. Three candidate cadences:

| Cadence | Timing |
|---|---|
| N+2 releases | Opt-in → warning → removed over two releases after landing |
| N+3 releases | Opt-in → warning (N+1) → removed at N+3 |
| **Calendar-based** | e.g., "removed no sooner than 6 months after warning starts" |

**Recommendation**: **calendar-based**, because the right number depends on
LCORE's release cadence and downstream consumers' update latency — both of
which the spike author does not own. @sbunciak to set the actual numbers.

### Decision S3: Downstream implications we may not have seen

The spike author has direct evidence of Konflux/Tekton usage (`.tekton/` dir)
and RHOAI testing (`tests/e2e-prow/rhoai/`). Other downstream consumers —
RHOAI operator CRs, Helm charts, Kustomize overlays, any other products —
are not visible from this repo alone.

**Ask**: Reviewers from downstream teams to confirm whether their deployment
setup treats `run.yaml` as a separate artifact (ConfigMap, templated file,
build-time asset) that this design would need to accommodate.

### Decision S4: Scope of this spike — what is deliberately left out

The following related work streams are **not** included in this spike and
should be tracked as separate future JIRAs:

- **Llama Stack process supervision** from LCORE (restart-on-crash, signal
  propagation, merged logs). Orthogonal to config merging; covered by
  LCORE-777 / LCORE-778.
- **Hot-reload / dynamic reconfig** (e.g., live `POST /v1/rag` that adds a
  BYOK RAG without restart). Llama Stack does not natively support
  hot-reload; achieving it would require supervision + restart flows.
  Covered by LCORE-781.

**Recommendation**: confirm this scope split. If reviewers want any of the
above pulled in, this spike's JIRAs grow accordingly.

---

## Technical decisions — for @tisnik and team leads

Architecture-level and implementation-level. Each has a recommendation
grounded in the PoC.

### Decision T1: Format detection (shape vs version field vs both)

How does LCORE tell unified-mode configs from legacy-mode configs?

| Option | Works by |
|---|---|
| Shape only | Presence of `llama_stack.config` → unified; else legacy |
| Version field only | Explicit `config_format_version: 2` required |
| **Both (soft-coupled)** | Shape decides; version field optional but must agree when present |

**Recommendation**: **both, soft-coupled**. Gives a cheap upgrade path for
future real schema bumps without forcing every existing user to add a
version field today. Confidence: 75%.

### Decision T2: Override precedence (inside Option C)

When `llama_stack.config.native_override` overlaps with a high-level key,
what semantics?

| Strategy | Example: `safety: {excluded_categories: [a, b]}` vs override `{excluded_categories: [c]}` |
|---|---|
| Deep-merge, append lists | result: `[a, b, c]` |
| **Deep-merge, replace lists** | result: `[c]`; other keys in `safety` preserved |
| Whole-key override | result: whole `safety` replaced; lose `default_shield_id` unless restated |
| JSON Patch (ops) | explicit — `{op: replace, path: /safety/excluded_categories, value: [c]}` |

**Recommendation**: **deep-merge with list replacement**. Simple mental model,
no list-merge tarpit, keeps scalar + map overrides minimal. Implemented in
`deep_merge_list_replace()`. Confidence: 70%.

See [Merge semantics worked examples](#merge-semantics-worked-examples).

### Decision T3: Secrets in synthesized files

The synthesized run.yaml lives on disk (library mode: `$TMPDIR`; server mode:
inside the LS container). Option space:

| Option | On-disk content |
|---|---|
| **Keep env-var refs verbatim** | `api_key: ${env.OPENAI_API_KEY}` (resolved by LS at start) |
| Resolve before writing | `api_key: sk-...` |

**Recommendation**: **keep env-var refs verbatim**. Security-leaning default;
resolved secrets never touch the disk. Implemented in
`apply_high_level_inference` (emits `${env.<NAME>}` strings). Confidence: 95%.

### Decision T4: Synthesized file location

Where the synthesized `run.yaml` goes at runtime:

| Option | Path |
|---|---|
| Temp file | `$TMPDIR/llama_stack_synthesized_config.yaml` |
| **Persistent known path** | Local: `./.generated/run.yaml` or `~/.local/state/lightspeed-stack/run.yaml`; Container: `/app-root/.generated/run.yaml`. Overwrite on each boot. |

**Recommendation**: **persistent known path, overwrite on boot**. Debuggable,
no stale-file risk (always overwritten before LS starts). The PoC used
`$TMPDIR` for expediency; production should use the persistent path. CLI flag
`--synthesized-config-output <path>` for debugging. Confidence: 85%.

### Decision T5: Migration tool invocation

How operators invoke the migration tool:

| Option | Example |
|---|---|
| Separate script under `scripts/` | `uv run python scripts/migrate-config.py ...` |
| **Flag on main entry point** | `lightspeed-stack --migrate-config --run-yaml X -c Y --migrate-output Z` |
| Subcommand refactor | `lightspeed-stack migrate-config ...` (BREAKS existing invocations) |

**Recommendation**: **flag on main entry point**. Parallels the existing
`--dump-configuration` / `--dump-schema` flags; zero breaking change to
existing invocations. Implemented in `src/lightspeed_stack.py` + a
companion `migrate_config_dumb()` function. Confidence: 90%.

### Decision T6: Profile distribution

How profiles (Option E layer) reach downstream teams:

| Option | Details |
|---|---|
| Ship named profiles in `src/profiles/` | LCORE ships a pre-curated set; `profile: openai-remote` resolves |
| **Feature only, no shipped profiles** | `profile: <path-to-file>` is the only invocation; teams author their own; LCORE ships 1–2 reference examples under `examples/profiles/` |

**Recommendation**: **feature only, no shipped profiles**. Avoids
profile-sprawl and the burden of keeping "blessed" profiles in sync with
downstream products. 1–2 reference examples in `examples/profiles/` are
documentation, not shipped runtime assets. Confidence: 85%.

### Decision T7: The `baseline` field (added during PoC)

During the PoC, strict lossless round-trip for the migration tool surfaced
a need: when `native_override` contains an entire run.yaml body, the default
baseline's keys still leak into the result via deep-merge. Fix: a
`baseline: "default" | "empty"` field.

- `baseline: default` (default value) — start from LCORE's built-in baseline
- `baseline: empty` — start from `{}`. Used by the dumb migration tool so
  round-trip is exact.

**Recommendation**: **accept this field**. Alternatives (`inherit_defaults:
bool`, `starting_point: ...`) are cosmetic. Confidence: 80%. Reviewers: any
preference on naming before this ships?

### Decision T8: Konflux / Tekton pipelines

The `.tekton/` directory exists in this repo. If any Konflux/Tekton pipeline
templates or mounts `run.yaml` separately, unified mode needs that pipeline
to either (a) keep using legacy mode during the deprecation window, or
(b) mount the unified `lightspeed-stack.yaml` and drop the `run.yaml` mount.

**Ask**: owner of `.tekton/` to confirm current pipeline shape and plan
migration.

### Decision T9: Library client API (resolved by PoC)

**Finding from PoC**: `AsyncLlamaStackAsLibraryClient` in `llama-stack` only
accepts a file-path string. It does not accept a dict. This means library
mode must write the synthesized config to disk — no dict-only shortcut
available. Not a decision; a fact to note in the spec doc.

---

## Proposed JIRAs

Each JIRA's agentic-tool instruction points to the spec doc
(`llama-stack-config-merge.md`), the permanent reference. The first JIRA
(authoring e2e feature files) is the intentional kickoff — it happens
before feature implementation so the test shape is not influenced by
implementation choices.

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? E2E feature files for unified mode (no step implementation)

**User story**: As a Lightspeed Core e2e engineer, I want the behave
feature files for unified-mode scenarios written before the feature
implementation lands, so that the test shape reflects the feature's
intended behavior rather than the chosen implementation, and any
architectural gaps surface early.

**Description**: Author behave `.feature` files under `tests/e2e/features/`
that describe the behaviors required of unified mode. Step definitions
(Python glue) are explicitly **not** part of this ticket — they are
covered by a later sibling ticket (LCORE-???? — Implement step
definitions). The feature files can be submitted for review and land
before implementation of the feature itself begins.

**Scope**:
- `.feature` files covering, at minimum, these R1–R11 surfaces from the
  spec doc:
  - Boot LCORE with unified `lightspeed-stack.yaml` (no external
    `run.yaml`); `/liveness`, `/readiness`, and `/v1/query` succeed.
  - Boot LCORE with legacy config
    (`library_client_config_path` + external `run.yaml`); same result.
  - Setting both `llama_stack.config` and
    `llama_stack.library_client_config_path` fails at config-load time
    with a clear error that mentions `--migrate-config`.
  - Migration tool: `lightspeed-stack --migrate-config ...` produces a
    unified file that drives equivalent Llama Stack behavior.
  - `native_override` deep-merges onto the baseline with list
    replacement (tested on a scalar key and a list key).
  - `profile:` path (absolute and relative-to-config-dir) loads the
    referenced baseline.
  - Secrets appear as `${env.FOO}` references in the synthesized
    `run.yaml` on disk; never resolved to raw values.
  - Legacy mode emits a one-line deprecation WARN at startup; unified
    mode does not.
- Additions to `tests/e2e/test_list.txt` so behave discovers the new
  files.
- Gherkin scenarios authored from the spec doc (`R1..R11`) only; author
  must avoid reading the implementation JIRAs' scope sections while
  drafting scenarios.

**Acceptance criteria**:
- behave parses every new `.feature` file without syntax errors.
- behave marks all new scenario steps as `undefined` (step definitions
  land in LCORE-????).
- `uv run make test-e2e` remains green (new scenarios are skipped or
  reported undefined, not failing).
- Any ambiguity or architectural tension uncovered while authoring is
  captured either as a comment in the spec doc or as a new sub-JIRA.

**Blocks**: LCORE-???? (Implement behave step definitions for unified
mode).

**Agentic tool instruction**:
```text
Read "Requirements" (R1..R11) and "Use Cases" in
docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Do NOT read the other JIRAs' scope sections or the synthesizer/schema
implementation code while authoring; the point of this ticket is to
produce feature files uncontaminated by implementation detail.
Key files to create: tests/e2e/features/unified-mode-*.feature plus
additions to tests/e2e/test_list.txt. Do NOT create step definitions in
tests/e2e/features/steps/.
To verify: `uv run behave --dry-run tests/e2e/features/unified-mode-*.feature`
parses successfully; `uv run make test-e2e` still green with the new
scenarios reported as undefined.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Unified `llama_stack.config` schema + synthesizer

**Description**: Implement the unified-mode config schema
(`UnifiedLlamaStackConfig`, `UnifiedInferenceSection`,
`UnifiedInferenceProvider`) and the synthesizer that produces a full Llama
Stack `run.yaml` from it. Wire library mode to the synthesizer. Preserve
legacy mode through mutual-exclusion validation.

**Scope**:
- New Pydantic classes in `src/models/config.py`.
- New functions in `src/llama_stack_configuration.py`:
  `synthesize_configuration`, `deep_merge_list_replace`,
  `apply_high_level_inference`, `load_default_baseline`, `synthesize_to_file`.
- A shipped default baseline at `src/data/default_run.yaml`.
- Library-mode wiring in `src/client.py`: detect unified vs legacy, write
  synthesized file, pass path to library client.
- Cross-field validation: reject both `config` and
  `library_client_config_path` set simultaneously.
- Legacy behavior (`llama_stack.library_client_config_path` path) unchanged.

**Acceptance criteria**:
- Unified `lightspeed-stack.yaml` (no external `run.yaml`) boots LCORE in
  library mode and serves `/v1/query`.
- Legacy configs continue to work with no change.
- Mutual-exclusion error message fires cleanly when both forms are set.
- Unit tests for synthesizer, merge semantics, schema validation.

**Agentic tool instruction**:
```text
Read the "Architecture" and "Implementation Suggestions" sections of
docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files to create or modify:
  src/models/config.py  (new classes; modify LlamaStackConfiguration)
  src/llama_stack_configuration.py  (synthesize_configuration + helpers)
  src/data/default_run.yaml  (new)
  src/client.py  (library-mode wiring)
To verify: run a unified-mode config end-to-end via `uv run lightspeed-stack -c <config>` and confirm /v1/query succeeds.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Migration tool — dumb-mode lift-and-shift

**Description**: Implement `--migrate-config` on the `lightspeed-stack` CLI
that produces a unified single-file config from an existing
(`run.yaml` + `lightspeed-stack.yaml`) pair. Dumb mode places the entire
`run.yaml` body under `llama_stack.config.native_override` with
`baseline: empty`, removes `library_client_config_path`.

**Scope**:
- `migrate_config_dumb()` function in `src/llama_stack_configuration.py`.
- `--migrate-config`, `--run-yaml`, `--migrate-output` flags in
  `src/lightspeed_stack.py`.
- Round-trip test: migrate → synthesize → byte-identical to original
  `run.yaml`.

**Acceptance criteria**:
- `lightspeed-stack --migrate-config --run-yaml X -c Y --migrate-output Z`
  produces a unified config that boots LCORE in library mode to the same
  Llama Stack behavior as the original pair.
- Round-trip unit test passes.
- `--help` describes the flag clearly.

**Agentic tool instruction**:
```text
Read "Migration tool" in docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files: src/lightspeed_stack.py, src/llama_stack_configuration.py,
tests/unit/test_llama_stack_synthesize.py.
To verify: migrate the repo's root run.yaml + lightspeed-stack.yaml, then
start LCORE with the output; confirm /v1/query works.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? LS container entrypoint + deployment artifacts for unified mode

**Description**: Update the Llama Stack container entrypoint and deployment
manifests so server mode works end-to-end from a unified
`lightspeed-stack.yaml`. Rebuild guidance for container images that bundle
the synthesizer script and default baseline.

**Scope**:
- Update `scripts/llama-stack-entrypoint.sh` — the existing script already
  defers to the Python CLI for auto-detection; document that behavior.
- Update `test.containerfile` to copy `src/data/` into the LS container so
  `load_default_baseline()` resolves.
- Provide a unified-mode `docker-compose.yaml` (or update the existing one)
  that mounts only `lightspeed-stack.yaml` into the LS container.
- Update `.tekton/` pipelines as needed (coordinate with pipeline owner,
  see Decision T8).

**Acceptance criteria**:
- `docker compose up` with a unified `lightspeed-stack.yaml` starts both
  containers healthy; `/v1/query` works through LCORE → LS.
- Legacy docker-compose layout (with external `run.yaml` mount) still works.

**Agentic tool instruction**:
```text
Read "Architecture → Server mode" in docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files: scripts/llama-stack-entrypoint.sh, test.containerfile,
docker-compose.yaml, .tekton/*.yaml.
To verify: docker compose up with the unified config; curl LCORE /v1/query.
```

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Migrate in-repo e2e / integration test configurations

**User story**: As a Lightspeed Core maintainer, I want the in-repo e2e and
integration tests to use the unified-mode config format, so that the
reference configuration shapes downstream teams see are the new ones.

**Description**: Convert `tests/e2e/configs/run-*.yaml` and
`tests/e2e/configuration/**/lightspeed-stack*.yaml` into unified form
(or delete the `run-*.yaml` side and fold the content into the
corresponding `lightspeed-stack*.yaml`). Migrate `tests/e2e-prow/rhoai/`
configs similarly.

**Scope**:
- Identify every test config that references `run.yaml`.
- Mechanically migrate using the migration tool (dumb mode).
- Re-run the full e2e suite and resolve any differences.

**Acceptance criteria**:
- No in-repo test config references an external `run.yaml`.
- `uv run make test-e2e` passes.
- Existing test coverage is preserved (no tests deleted solely to make the
  migration pass).

**Agentic tool instruction**:
```text
Read "Migration paths" in docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files: tests/e2e/configs/, tests/e2e/configuration/, tests/e2e-prow/rhoai/.
To verify: `uv run make test-e2e` green.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement behave step definitions for unified-mode feature files

**Description**: Implement the Python step definitions
(`@given`/`@when`/`@then` functions) under `tests/e2e/features/steps/`
for the `.feature` files authored in LCORE-???? (E2E feature files
kickoff). After this ticket lands, the scenarios transition from
`undefined` to fully executing.

The feature files are taken as-is — do not modify the Gherkin to make
implementation easier. If a scenario cannot be implemented faithfully,
raise it against the spec doc (and possibly back to LCORE-???? kickoff)
rather than quietly weakening the test.

**Scope**:
- Step definitions for every step pattern in the new `.feature` files.
- Fixtures or helpers under `tests/e2e/features/steps/` as needed
  (e.g., temp-dir config authoring, subprocess start/stop for LCORE,
  HTTP client helpers reusing existing `tests/e2e/` patterns).
- CI wiring so the new scenarios run as part of `uv run make test-e2e`.

**Acceptance criteria**:
- behave reports zero `undefined` steps across the new `.feature`
  files.
- `uv run make test-e2e` runs the new scenarios and they pass.
- No Gherkin edit was made to accommodate implementation constraints
  (or if any edit was made, it is documented in a PR comment with
  explicit rationale).

**Blocked by**:
- LCORE-???? (E2E feature files for unified mode — the `.feature`
  files being implemented against).
- LCORE-???? (Unified schema + synthesizer), LCORE-????
  (Migration tool), LCORE-???? (LS container entrypoint + deployment)
  — the feature under test must exist.

**Agentic tool instruction**:
```text
Read "Architecture" and "Requirements" in
docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files to create: tests/e2e/features/steps/unified-mode*.py (or
extend existing step-definition modules if patterns reuse cleanly).
Do not modify tests/e2e/features/unified-mode-*.feature — take the
Gherkin as-is. If a scenario genuinely cannot be implemented faithfully,
file a sub-ticket rather than changing the Gherkin quietly.
To verify: `uv run make test-e2e` runs every new scenario green and
behave reports zero undefined steps.
```

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Docs migration to unified mode as primary

**User story**: As an operator reading Lightspeed Core docs, I want the
single-file unified configuration to be the primary way documented, with
legacy mode clearly marked as a deprecation path.

**Description**: Update
`docs/deployment_guide.md`, `docs/byok_guide.md`, `docs/okp_guide.md`,
`docs/rag_guide.md`, `docs/providers.md`, `docs/config.md`, `README.md`,
`docs/local-stack-testing.md` to document unified mode as primary. Add a
migration section with the migration tool command. Clean up the stale
`create_argument_parser` docstring in `src/lightspeed_stack.py` that still
mentions the removed `-g/-i/-o` flags.

**Scope**:
- Each doc file touched.
- A new migration section (step-by-step).
- Update the `create_argument_parser` docstring in
  `src/lightspeed_stack.py`.

**Acceptance criteria**:
- Every doc page that showed a two-file setup also shows the unified-mode
  equivalent.
- Migration tool invocation documented with a worked example.
- `docs/openapi.md` / `docs/config.html` regenerated.

**Agentic tool instruction**:
```text
Read "Deprecation timeline" and "Migration paths" in docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files: docs/*.md, docs/*.html, docs/*.json, README.md, src/lightspeed_stack.py docstring.
To verify: rendered docs present the unified mode first; legacy mode is visibly deprecated.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Reference profile examples and profile-path doc

**Description**: Add `examples/profiles/` with two reference profile YAML
files — one remote-provider (OpenAI) and one inline-provider (sentence-
transformers + FAISS) — purely as reference material. Document how operators
write and reference their own profiles via
`llama_stack.config.profile: <path>`.

**Scope**:
- `examples/profiles/openai-remote.yaml`
- `examples/profiles/inline-faiss.yaml`
- Docs section: how to author a profile, where to place it, how to
  reference it from `lightspeed-stack.yaml`.

**Acceptance criteria**:
- Both examples load cleanly via the synthesizer (sanity test).
- A docs section titled "Profiles" exists and has a worked example.

**Agentic tool instruction**:
```text
Read "Profiles" in docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files to create: examples/profiles/*.yaml, a "Profiles" section in docs/config.md or docs/deployment_guide.md.
To verify: load the example via `uv run lightspeed-stack -c <wrapper.yaml>` referencing the profile; confirm LS boots.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Deprecation warning for legacy mode

**Description**: After the unified-mode feature lands (one release later),
emit a one-line startup WARN when `library_client_config_path` is set. Link
to the migration doc. Legacy mode continues to fully function.

**Scope**:
- Warning emission point: on load in `LlamaStackConfiguration`
  `check_llama_stack_model` validator, or at LCORE startup.
- Log line format includes a stable URL fragment to the migration doc.

**Acceptance criteria**:
- Legacy configs still load and run.
- A single WARN line appears at startup when legacy fields are used.
- The warning is not emitted in unified mode.

**Agentic tool instruction**:
```text
Read "Deprecation timeline" in docs/design/llama-stack-config-merge/llama-stack-config-merge.md.
Key files: src/models/config.py (or src/lightspeed_stack.py startup).
To verify: run LCORE with a legacy config; confirm WARN line; run with unified config; confirm no WARN.
```

---

## PoC results

### What the PoC does

The PoC is at Level 3' (per the spike howto): unified config works
end-to-end in library mode, with overrides and a profile. Server-mode
end-to-end validation was skipped — same synthesis code path, container
rebuild time was impractical.

**Important**: The PoC diverges from the production design in these ways:

- Uses `$TMPDIR` for the synthesized `run.yaml` instead of the persistent
  known path recommended in Decision T4.
- No `--synthesized-config-output` CLI flag yet.
- Migration tool has only the "dumb" mode; "smart" factoring into
  high-level keys is out of scope.
- No deprecation warning yet (that's its own JIRA).
- High-level inference's emitted `provider_id` uses the Literal value
  directly (`sentence_transformers` with underscore), which differs from
  the baseline's `sentence-transformers` (hyphen). Acceptable in the PoC
  because the validation used `baseline: default` + a `native_override`
  path, not high-level inference, to avoid this naming collision. Resolution
  before production: align the emitted `provider_id` with the Literal
  values that already exist in common baselines (hyphenated form).

### Results

See [poc-evidence/library-mode/](poc-evidence/library-mode/) for the full
evidence bundle:

- `lightspeed-stack-unified-library.yaml` — the unified-mode config used
- `synthesized-run.yaml` — what LCORE produced (3.7 KB)
- `query-response.json` — a real `/v1/query` round-trip

Summary of validation:

| Check | Evidence |
|---|---|
| Liveness 200 | `curl /liveness` → `{"alive":true}` |
| Readiness 200 | `curl /readiness` → `{"ready":true,"reason":"All providers are healthy","providers":[]}` |
| `/v1/query` works | `{"response":"The three primary colors are red, blue, and yellow.",...}` |
| Profile loaded | `profile: /.../tests/e2e/configs/run-ci.yaml` resolved |
| `native_override` took effect | `safety.default_shield_id: llama-guard` in synthesized output |
| No external `run.yaml` needed | No `library_client_config_path` in config |
| Secrets preserved as env refs | `api_key: ${env.OPENAI_API_KEY}` in synthesized file |
| Full unit suite | 2098 passed, 1 skipped, 0 failed |
| Round-trip lossless | `test_migrate_then_synthesize_reproduces_run_yaml` green |

### Surprise discovered during PoC

- **`AsyncLlamaStackAsLibraryClient` takes a file path, not a dict** (Decision
  T9). The library client reads the file itself. Consequence: library mode
  must write a synthesized file to disk. No dict-only shortcut.
- **`profile:` path resolution** uses the directory of the
  `lightspeed-stack.yaml`. Relative paths work only when the profile is
  co-located with the LCORE config. Absolute paths always work. Spec doc
  recommends documenting this clearly.
- **Default baseline requires `EXTERNAL_PROVIDERS_DIR`**. `src/data/default_run.yaml`
  (copied from the repo's `run.yaml`) references `${env.EXTERNAL_PROVIDERS_DIR}`
  without a default. Either ship a thinner default baseline, or change the
  reference to `${env.EXTERNAL_PROVIDERS_DIR:=~/.llama/providers.d}`. Flagging
  for the implementation JIRA.
- **High-level inference naming collision** (described above in "divergence
  from production design").

---

## Background sections

### Current architecture (before LCORE-836)

Two files:

- **`lightspeed-stack.yaml`** — LCORE settings: service host/port, auth,
  conversation cache, user data collection, MCP servers, authentication,
  authorization, quota, etc. Also contains `llama_stack:` with
  connection-to-LS settings (URL/api_key or library-client mode with a path
  to an external `run.yaml`).
- **`run.yaml`** — Llama Stack operational config: `apis`, `providers`
  (inference, safety, tool_runtime, vector_io, agents, ...), `storage`,
  `registered_resources`, `vector_stores`, `safety`.

**Existing enrichment** (`src/llama_stack_configuration.py`):

- LCORE already enriches an input `run.yaml` with dynamic values from
  `lightspeed-stack.yaml`: Azure Entra ID tokens (side-effect to `.env`),
  BYOK RAG entries, Solr/OKP provider/store/model registration. Output is
  an enriched `run.yaml`.
- Called in two places: `scripts/llama-stack-entrypoint.sh` at LS container
  boot (server mode) and `src/client.py:_enrich_library_config()` (library
  mode).
- LCORE-779 made this automatic; LCORE-518 (closed spike) proved (re)generation
  feasibility. Both are the groundwork the current spike builds on.

The new synthesizer *subsumes* the enrichment: it builds the full run.yaml
(baseline + enrichment + high-level + native_override) rather than
incrementally enriching an existing one.

### Design alternatives considered

Attributes (★ = high-weight for LCORE-836):

| Attribute | A | B+C | C+E | E | G |
|---|---|---|---|---|---|
| ★ Operator UX | 2 | 4–5 | **4** | 5 | 3 |
| Abstraction cleanliness | 1 | 4 | 3 | 4 | 2 |
| LS schema resilience | 1 | 4 | 3 | 3 | 2 |
| ★ Escape-hatch power | 5 | 3 | 5 | 5 | 5 |
| Implementation cost | 4 | 2 | 2 | 3 | 3 |
| Maintenance load | 2 | 3 | 3 | 2 | 3 |
| ★ Backward compatibility | 3 | 3 | 3 | 3 | 4 |
| Validation rigor | 2 | 5 | 4 | 3 | 2 |
| ★ Dynamic-reconfig fit | 2 | 5 | 4 | 4 | 2 |
| ★ Library+server parity | 5 | 4 | 4 | 5 | 5 |
| Provider plurality | 5 | 4 | 5 | 4 | 5 |
| Testability | 3 | 4 | 3 | 5 | 3 |

- **A (Embedded native)** — no abstraction win; same LS schema exposure as today.
- **B (High-level only)** — best UX when everything maps, painful at the edges.
- **C (B + `native_override`)** — recommended; combines B's UX with A's escape hatch.
- **E (Profiles, feature-only)** — optional layer on top of C.
- **G (Kustomize-style patches)** — strong for backward compat, weak on
  validation and dynamic reconfig.

### Merge semantics — worked examples

Given the baseline:
```yaml
safety:
  default_shield_id: llama-guard
  excluded_categories: [violence, sexual_content]
providers:
  inference:
    - provider_id: openai
      provider_type: remote::openai
      config:
        api_key: ${env.OPENAI_API_KEY}
```

And `native_override`:
```yaml
safety:
  excluded_categories: [spam]
```

**Deep-merge-with-list-replacement (chosen)** produces:
```yaml
safety:
  default_shield_id: llama-guard          # preserved (not in override)
  excluded_categories: [spam]             # list replaced
providers:                                # not in override — preserved
  inference:
    - provider_id: openai
      ...
```

The recommendation's appeal: to keep `default_shield_id`, the user doesn't
have to restate it. To replace `excluded_categories`, the user provides the
new list — they don't need to know a patch syntax.

### Process-model recap (no LCORE supervision of LS)

**Library mode**: LCORE process embeds the Llama Stack library client. LCORE
synthesizes `run.yaml` to a file, calls `AsyncLlamaStackAsLibraryClient(path)`,
initializes, serves. One process.

**Server mode**: Llama Stack runs as a separate process (container). LCORE
connects to it over HTTP. Under unified mode, the LS container's entrypoint
reads the mounted `lightspeed-stack.yaml`, the Python CLI auto-detects
unified mode, synthesizes `run.yaml`, then `exec llama stack run` with it.
LCORE container reads the same `lightspeed-stack.yaml`, ignores the
`config` sub-block (server mode — only connection fields matter), connects.
Two processes. LCORE does **not** start, monitor, or supervise the LS
process — the orchestrator (docker-compose, systemd, k8s) does. Supervision
is out of scope for this spike (see Decision S4).

### What must not break during rollout

See [Backward compatibility scope](#backward-compatibility-scope). The four
must-not-break surfaces:

1. Existing `lightspeed-stack.yaml` with `library_client_config_path`.
2. Existing `run.yaml` content, including fields LCORE doesn't model.
3. Existing CI/CD templating that treats `run.yaml` as a separate artifact.
4. Existing enrichment behavior (Azure Entra ID, BYOK RAG, Solr/OKP).

### Backward compatibility scope

Detection rule at load time:

| `lightspeed-stack.yaml` shape | Interpretation |
|---|---|
| `llama_stack.library_client_config_path` set, no `llama_stack.config` | **Legacy** — today's behavior |
| `llama_stack.config.*` present | **Unified** — new path |
| Both present | Error at load time — clear message |
| Neither (remote URL only, no config) | Existing remote mode — unchanged |

Three migration paths operators can choose:

| Path | Effort | Result |
|---|---|---|
| Do nothing | 0 | Legacy keeps working until deprecation window closes |
| Lift-and-shift (via migration tool) | seconds | Unified single file, zero semantic change |
| Re-express | hours+ | Unified single file, fully adopts the high-level schema |

---

## Appendix A — Files changed in the PoC

Relative to `upstream/main`:

| File | Purpose |
|---|---|
| `src/models/config.py` | New classes: `UnifiedInferenceProvider`, `UnifiedInferenceSection`, `UnifiedLlamaStackConfig`; modified `LlamaStackConfiguration` (adds `config` field + mutual-exclusion validator) |
| `src/llama_stack_configuration.py` | New: `synthesize_configuration`, `deep_merge_list_replace`, `apply_high_level_inference`, `load_default_baseline`, `synthesize_to_file`, `migrate_config_dumb`. CLI `main()` auto-detects unified vs legacy. |
| `src/data/default_run.yaml` | Built-in default baseline (copied from repo root `run.yaml` for the PoC — implementation JIRA should slim it down; see PoC surprise about `EXTERNAL_PROVIDERS_DIR`) |
| `src/client.py` | Library-mode path picks synthesis for unified configs, enrichment for legacy |
| `src/lightspeed_stack.py` | `--migrate-config`, `--run-yaml`, `--migrate-output` flags |
| `scripts/llama-stack-entrypoint.sh` | Comment updated — script itself needs no change (Python CLI auto-detects) |
| `test.containerfile` | Copies `src/data/` into the LS container |
| `tests/unit/test_llama_stack_synthesize.py` | 22 new tests: merge semantics, high-level inference, synthesize pipeline, migration round-trip |
| `tests/unit/models/config/test_llama_stack_configuration.py` | 3 new tests: unified/legacy mutual exclusion |
| `tests/unit/models/config/test_dump_configuration.py` | 5 expected-dict updates (new `config: None` field appears in dumps) |
| `tests/unit/test_client.py` | Error-message regex updated |
| `docs/design/llama-stack-config-merge/` | Spike doc, spec doc, PoC evidence, proposed JIRAs |

## Appendix B — Commands to reproduce the library-mode PoC

```bash
# 1. Start LCORE in library mode with a unified config
export OPENAI_API_KEY=<your-key>
export E2E_OPENAI_MODEL=gpt-4o-mini
mkdir -p /tmp/lcore-836-poc
uv run lightspeed-stack \
  -c docs/design/llama-stack-config-merge/poc-evidence/lightspeed-stack-unified-library.yaml

# 2. In another shell — query
curl -s http://localhost:8080/liveness
curl -s http://localhost:8080/readiness
curl -s -X POST http://localhost:8080/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Name three primary colors. One sentence."}'

# 3. Inspect what was synthesized
cat /tmp/llama_stack_synthesized_config.yaml
```
