# Feature design: Llama Stack config merge (unified `lightspeed-stack.yaml`)

|                    |                                                                                  |
|--------------------|----------------------------------------------------------------------------------|
| **Date**           | 2026-04-23                                                                       |
| **Component**      | Lightspeed Core Stack (src/models/config.py, src/lightspeed_stack/llama_stack_configuration.py, src/client.py, src/lightspeed_stack.py, scripts/llama-stack-entrypoint.sh) |
| **Authors**        | Maxim Svistunov                                                                   |
| **Feature**        | [LCORE-836](https://redhat.atlassian.net/browse/LCORE-836)                       |
| **Spike**          | [llama-stack-config-merge-spike.md](llama-stack-config-merge-spike.md)           |
| **Links**          | LCORE-509 (Epic), LCORE-777 (Epic), LCORE-518 (prior spike, Closed), LCORE-779 (auto-regen, Closed) |

## What

This feature collapses the two Lightspeed Core configuration files —
`lightspeed-stack.yaml` (LCORE settings) and `run.yaml` (Llama Stack
operational config) — into a single `lightspeed-stack.yaml`. At runtime,
LCORE synthesizes a full Llama Stack `run.yaml` from high-level
operator-facing inputs (a top-level `inference.providers` list, plus a
`llama_stack.config` sub-section) and hands it to Llama Stack (library
client or subprocess, mode-dependent).

Key shape:

- **Top-level high-level sections** for the common path. v1 ships
  `inference.providers` — added to the *existing* top-level `inference:`
  section (alongside its `default_model` / `default_provider`). These
  sit at the root of `lightspeed-stack.yaml`, not under `llama_stack`,
  so they survive a future backend change (Decision S5 in the spike).
  Future high-level sections (`rag`, `safety`, …) stay under
  `llama_stack.config` until proven backend-agnostic.
- `llama_stack.config.native_override` escape hatch — raw Llama Stack
  schema, deep-merged with list replacement. Covers anything the
  high-level sections don't express.
- `llama_stack.config.profile` — path to a user-authored YAML that serves
  as the synthesis baseline.
- `llama_stack.config.baseline: default | empty` — pick between LCORE's
  built-in baseline and an empty dict (used by the migration tool for
  exact round-trip).
- Legacy two-file mode (`llama_stack.library_client_config_path` +
  external `run.yaml`) is preserved during a deprecation window;
  mutually exclusive with the unified *synthesis inputs* (a non-empty
  `inference.providers` or a `llama_stack.config` block).

## Why

Two-file configuration multiplies the surface area for misconfiguration
and forces every downstream Lightspeed team (RHOAI, Konflux pipelines,
any product integrating LCORE) to understand Llama Stack's full internal
schema. A single source of truth:

- Reduces the number of artifacts deployment tooling must manage
  (Helm values, ConfigMaps, Kustomize overlays).
- Lets downstream teams express their intent at a high level (e.g. "use
  OpenAI with these allowed models") rather than authoring raw LS
  provider entries.
- Preserves an escape hatch so edge cases don't block adoption.

LCORE-518 (closed) proved a generation PoC in principle; LCORE-779
(closed) made configuration regeneration automatic at startup. This
feature completes the picture by making `run.yaml` an implementation
detail that LCORE owns, not an operator-facing artifact.

## Requirements

- **R1:** `lightspeed-stack.yaml` using the unified schema (a non-empty
  top-level `inference.providers`, and/or a `llama_stack.config`
  sub-section) and no external `run.yaml` boots LCORE in both library and
  server modes and serves `/v1/query` successfully.
- **R2:** Legacy mode (`llama_stack.library_client_config_path` +
  external `run.yaml`) works unchanged through the deprecation window:
  fully functional with a startup deprecation WARN in 0.6, removed in
  0.7 (Decision S2, confirmed 2026-05-20).
- **R3:** Setting both `llama_stack.config` and
  `llama_stack.library_client_config_path` in the same file fails at
  configuration load time with a clear error message pointing to the
  migration tool.
- **R4:** `lightspeed-stack --migrate-config --run-yaml X -c Y
  --migrate-output Z` produces a unified configuration from the legacy
  two-file pair. Running the migrated file drives Llama Stack to
  byte-identical behavior as the original pair (dumb-mode lossless
  round-trip).
- **R5:** When `llama_stack.config.native_override` overlaps a key set
  by the high-level section or by the baseline, deep-merge semantics
  apply with list replacement (maps merge recursively; lists are
  replaced wholesale; scalars are replaced).
- **R6:** Secrets that LCORE itself emits are never resolved on disk:
  `apply_high_level_inference` writes `${env.<VAR>}` references
  verbatim, and LCORE does not eagerly resolve env refs in the
  baseline or in `native_override` before writing. (Operators may
  still hand-write literal secrets into `native_override` or into a
  legacy `run.yaml` that is migrated through dumb mode — see the
  Security considerations section for the on-disk implications.)
- **R7:** Existing enrichment behavior (Azure Entra ID, BYOK RAG,
  Solr/OKP) produces the same result in unified mode as in legacy mode
  for equivalent inputs.
- **R8:** A profile referenced by a relative `profile:` path resolves
  against the directory of the loaded `lightspeed-stack.yaml`.
- **R9:** The unified schema (a) extends the existing top-level
  `InferenceConfiguration` with a `providers:
  list[UnifiedInferenceProvider]` field and (b) adds a
  `config: Optional[UnifiedLlamaStackConfig]` field to
  `LlamaStackConfiguration` (holding `baseline` / `profile` /
  `native_override`). Cross-field validation on the **root**
  `Configuration` model enforces mutual exclusion between the unified
  synthesis inputs and legacy mode, and all unified-mode models reject
  unknown fields (`extra="forbid"`).
- **R10:** The synthesized `run.yaml` is written to a persistent known
  path (overwritten each boot) with file mode `0600` (owner read/write
  only — the file may contain literal secrets when `native_override` or
  the dumb migration tool's output carries them; restrictive perms must
  be set on create, not left to umask). Path is logged at startup, and
  a CLI flag `--synthesized-config-output` lets operators override the
  location for debugging.
- **R11:** Shape detection determines mode. Unified mode is signalled by
  the presence of any *synthesis input* — a non-empty top-level
  `inference.providers` or a `llama_stack.config` block; legacy mode by
  `library_client_config_path`. An optional `config_format_version` field
  is accepted but must agree with the detected shape when present. See the
  "Mode detection" table under Architecture for the full matrix.

## Use Cases

- **U1:** As an operator setting up LCORE for the first time, I want to
  write one config file with high-level provider choices (OpenAI, Azure,
  …) so that I don't have to learn Llama Stack's internal schema.
- **U2:** As a downstream team maintainer with an existing heavily
  customized `run.yaml`, I want a mechanical one-shot migration so that
  I can move to the unified format without re-expressing my edge cases.
- **U3:** As an operator whose deployment sits behind a vLLM serving
  stack not covered by the high-level schema, I want to drop my custom
  configuration into `native_override` and still benefit from the rest
  of the unified schema.
- **U4:** As a Lightspeed Core maintainer, I want a single authoritative
  place for docs, examples, and test configs so that downstream teams
  find the same patterns everywhere.
- **U5:** As a Red Hat release manager, I want legacy configs to keep
  working throughout a deprecation window so that downstream products
  can migrate on their own cadence.

## Acceptance test surface

Maps each requirement to one or more observable behaviors. This section
is the source-of-truth that drives the e2e-kickoff JIRA's `.feature`
files — authors read it to write Gherkin scenarios.

| Req | Observable behavior | Verified by |
|---|---|---|
| R1 | Unified config (top-level `inference.providers` and/or `llama_stack.config`, no external `run.yaml`) boots LCORE in library and server mode; `/liveness`, `/readiness`, `/v1/query` succeed | e2e |
| R2 | Legacy two-file config still boots and serves; one startup deprecation WARN in 0.6; no WARN in unified mode | e2e |
| R3 | A config with a synthesis input *and* `library_client_config_path` fails at load with an error naming `--migrate-config` (cover both the `inference.providers` and the `config` case) | e2e + unit |
| R4 | `--migrate-config` on a legacy pair yields a unified file driving byte-identical LS behavior; migrate→synthesize round-trips to the original `run.yaml` | e2e + unit (round-trip) |
| R5 | `native_override` overlapping a baseline/high-level key deep-merges: maps merge, lists replace wholesale, scalars replace | unit (parametric) + e2e (one scalar + one list key) |
| R6 | Synthesized `run.yaml` on disk carries `${env.FOO}` refs for LCORE-emitted secrets, never resolved values | e2e (inspect file) + unit |
| R7 | Enrichment (Azure Entra ID, BYOK RAG, Solr/OKP) yields the same synthesized result in unified mode as legacy for equivalent inputs | unit + integration |
| R8 | A relative `profile:` path resolves against the loaded `lightspeed-stack.yaml` directory; absolute paths always resolve | e2e + unit |
| R9 | Unknown fields rejected (`extra="forbid"`); root validator enforces synthesis-input ⊕ legacy mutual exclusion | unit |
| R10 | Synthesized file written to the persistent known path with mode `0600`, path logged at startup; `--synthesized-config-output` overrides the location | e2e (perms + path) + unit |
| R11 | Shape detection resolves unified vs legacy per the Mode-detection table; `config_format_version`, when set, must agree or load fails | unit + e2e |

## Architecture

### Overview

```text
lightspeed-stack.yaml (unified mode)
       │
       ▼
 ┌────────────────────────────┐
 │ Configuration load         │    Pydantic validation; mutual-exclusion
 │  src/configuration.py      │    check between the synthesis inputs
 │  src/models/config.py      │    (`inference.providers`, `config`)
 └────────────┬───────────────┘    and `library_client_config_path`.
              │ Configuration (typed)
              ▼
 ┌────────────────────────────┐   Baseline selection (profile /
 │ Synthesizer                │   default / empty) + enrichment
 │  synthesize_configuration  │   (BYOK RAG, Solr/OKP) + high-level
 │  (llama_stack_config…)     │   sections + native_override deep-merge.
 └────────────┬───────────────┘
              │ synthesized run.yaml (dict)
              ▼
  Library mode                       Server mode
  ────────────                       ───────────
  Write to deterministic path.       Written by LS container's entrypoint
  AsyncLlamaStackAsLibraryClient     script (same synthesizer, same CLI,
  reads the path and initializes.    auto-detects unified via Python).
                                     `llama stack run <path>` starts LS.
                                     LCORE connects by URL.
```

### Trigger mechanism

At LCORE startup (library mode): if any synthesis input is present (a
non-empty top-level `inference.providers`, or a `llama_stack.config`
block), the synthesizer produces a `run.yaml` dict, writes it to disk,
and passes the path to the library client.

At Llama Stack container startup (server mode): the container's
entrypoint script invokes
`python3 /opt/app-root/llama_stack_configuration.py -c <lightspeed-stack.yaml>
-o /opt/app-root/run.yaml`. The Python CLI auto-detects unified vs legacy
by the same synthesis-input check; in unified mode it synthesizes and
writes the output; in legacy mode it performs in-place enrichment as
before.

### Mode detection

*Synthesis inputs* are the top-level high-level sections (v1: a non-empty
`inference.providers`; future `rag`, …) and the `llama_stack.config`
block. The loaded `lightspeed-stack.yaml` maps to a mode as follows:

| Shape | Mode |
|---|---|
| Any synthesis input, no `library_client_config_path` | **Unified** — LCORE synthesizes `run.yaml` |
| `library_client_config_path`, no synthesis input | **Legacy** — external `run.yaml` used as-is |
| A synthesis input **and** `library_client_config_path` | **Error** at load — points to `--migrate-config` |
| Neither, remote `url` only | **Remote** — externally-managed LS, no synthesis (existing behavior) |
| Neither, library-client mode, no `url` | **Error** — nothing to run |

`url` is orthogonal to the synthesis/legacy split: it composes with
unified mode (server mode — the LS container synthesizes from the same
`lightspeed-stack.yaml`) and with the remote row above. The `inference:`
section always exists (it carries `default_model` / `default_provider`
defaults), so the unified signal is `inference.providers` being
**non-empty**, not the section merely being present. An optional
`config_format_version`, when set, must agree with the detected shape
(the lever for a future hard schema bump).

### Storage / data model changes

No persistent storage is added. The synthesized `run.yaml` is written
once per boot to a deterministic path; not a database. `src/data/
default_run.yaml` is a new package-shipped file, the built-in baseline
Llama Stack configuration.

### Configuration

Top-level high-level sections plus a sub-section under the existing
`llama_stack` block:

```yaml
# Top-level inference config — the existing `inference:` section, extended
# with a `providers:` list (Decision S5). Backend-agnostic: it stays at the
# root, not under `llama_stack`, so it survives a future backend change.
inference:
  default_model: gpt-4o-mini       # existing — query-time default routing
  default_provider: openai         # existing — query-time default routing
  providers:                       # NEW — high-level provider setup (synthesis input)
    - type: openai                 # mapped to remote::openai
      api_key_env: OPENAI_API_KEY
      allowed_models: [gpt-4o-mini]
    - type: sentence_transformers

llama_stack:
  use_as_library_client: true
  # NOTE: library_client_config_path intentionally OMITTED in unified mode.
  # Setting a synthesis input (`inference.providers` or `config`) together
  # with `library_client_config_path` is a validation error.
  config:
    # Baseline selection (backend-specific knobs stay here)
    baseline: default              # default | empty; ignored if `profile` is set
    profile: ./my-profile.yaml     # optional; resolves relative to lightspeed-stack.yaml

    # Escape hatch — raw Llama Stack schema, deep-merged with list replacement
    native_override:
      safety:
        excluded_categories: [spam]
```

Pydantic classes (see `src/models/config.py`):

```python
class UnifiedInferenceProvider(ConfigurationBase):
    type: Literal[
        "openai", "sentence_transformers", "azure", "vertexai",
        "watsonx", "vllm_rhaiis", "vllm_rhel_ai",
    ]
    api_key_env: Optional[str] = None
    allowed_models: Optional[list[str]] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class InferenceConfiguration(ConfigurationBase):
    # Existing top-level section (query-time routing) — UNCHANGED fields:
    default_model: Optional[str] = None
    default_provider: Optional[str] = None
    # NEW (Decision S5): high-level provider setup, the synthesis input.
    # Empty list = not a synthesis input (legacy/remote still possible).
    providers: list[UnifiedInferenceProvider] = Field(default_factory=list)


class UnifiedLlamaStackConfig(ConfigurationBase):
    # Backend-specific knobs only. Per Decision S5, the backend-agnostic
    # high-level sections (inference, ...) live at the root, NOT here.
    baseline: Literal["default", "empty"] = "default"
    profile: Optional[str] = None
    native_override: dict[str, Any] = Field(default_factory=dict)


class LlamaStackConfiguration(ConfigurationBase):
    # existing fields unchanged (url, api_key, use_as_library_client,
    # library_client_config_path, timeout)
    config: Optional[UnifiedLlamaStackConfig] = None


class Configuration(ConfigurationBase):
    # The root lightspeed-stack.yaml model (existing). Relevant fields:
    inference: InferenceConfiguration = Field(default_factory=InferenceConfiguration)
    llama_stack: LlamaStackConfiguration
    # ... other existing fields (name, service, ...) ...

    @model_validator(mode="after")
    def check_unified_vs_legacy(self) -> Self:
        # Synthesis inputs span the root (inference.providers) and the
        # nested llama_stack.config, so the check lives here, not on
        # LlamaStackConfiguration.
        synthesis_input = (
            bool(self.inference.providers)
            or self.llama_stack.config is not None
        )
        legacy_input = self.llama_stack.library_client_config_path is not None
        if synthesis_input and legacy_input:
            raise ValueError("... mutually exclusive ... use --migrate-config")
        # ...legacy / remote checks preserved...
        return self
```

### API changes

None at the REST API surface. Internal API additions in
`src/lightspeed_stack/llama_stack_configuration.py`:

- `synthesize_configuration(lcs_config, config_file_dir, default_baseline)
  -> dict` — the synthesis pipeline.
- `synthesize_to_file(lcs_config, output_file, config_file_dir) -> None` —
  synthesis + write.
- `migrate_config_dumb(run_yaml_path, lightspeed_yaml_path, output_path)
  -> None` — dumb-mode migration (lossless round-trip).
- `deep_merge_list_replace(base, overlay) -> dict` — merge helper.
- `apply_high_level_inference(ls_config, inference)` — high-level expansion.
- `load_default_baseline() -> dict` — loads `src/data/default_run.yaml`.

CLI additions in `src/lightspeed_stack.py`:

- `--migrate-config` — invoke the migration tool.
- `--run-yaml <path>` — input for `--migrate-config`.
- `--migrate-output <path>` — output for `--migrate-config`.
- (recommended for R10) `--synthesized-config-output <path>` — override
  the default deterministic synthesis location.

The legacy CLI docstring in `create_argument_parser()` referencing the
removed `-g/-i/-o` flags is cleaned up as part of the docs JIRA.

### Error handling

- **Synthesis input + legacy set simultaneously**: raised during the
  root `Configuration.check_unified_vs_legacy` validator. Error message
  directs to `--migrate-config`.
- **Library mode with no synthesis input and no
  `library_client_config_path`**: raised during the same root validator.
  Error identifies the valid paths (populate `inference.providers` or a
  `llama_stack.config` block, or set `library_client_config_path`).
- **`profile:` path does not exist**: surfaced as `FileNotFoundError`
  from `open(profile_path)` during synthesis. The implementation JIRA
  should wrap this with context about where the path was resolved.
- **Unknown provider `type` in high-level inference**: rejected by the
  Pydantic `Literal` — operator sees a validation error naming the
  allowed types. Escape: use `native_override`.
- **Unknown fields in any unified-mode section**: rejected by
  `extra="forbid"` on `ConfigurationBase`.
- **Llama Stack rejects the synthesized `run.yaml`**: surfaces as
  whatever LS itself raises (ValidationError from LS's own config
  parsing). The implementation JIRA should log the synthesized file path
  before handing to LS so operators can inspect what failed.

### Security considerations

- **High-level inference emits env refs, not literal secrets**:
  `apply_high_level_inference` writes `${env.<VAR>}` strings, never
  the resolved value. An operator authoring `lightspeed-stack.yaml`
  from scratch with only high-level keys produces synthesized output
  with no literal secrets on disk. LS itself resolves env refs to
  values in-memory at startup via `replace_env_vars()` in
  `llama_stack.core.library_client`.
- **`native_override` (and dumb-mode migration output) MAY carry
  literal secrets**: `native_override` is whatever raw YAML the
  operator drops in, and `migrate_config_dumb()` lifts an existing
  `run.yaml` verbatim — which may already contain `api_key: sk-...`
  if a downstream team baked the secret into their legacy file. The
  synthesized file therefore CANNOT be assumed secret-free.
- **Mandate `0600` on the synthesized file**: `synthesize_to_file()`
  must create the file with mode `0600` (owner read/write only) using
  an explicit create flag — not relying on umask. This bounds the
  blast radius when `native_override` or a migrated `run.yaml` does
  contain a literal secret. (See R10.)
- **Document env-refs as the recommended pattern**: the migration
  tool's `--help` and the migration doc should advise operators to
  replace literal secrets in their legacy `run.yaml` with
  `${env.<VAR>}` references either before migrating, or after
  migration inside the resulting `native_override` block.
- **`native_override` injection surface**: content is
  operator-controlled, so no new surface — same trust model as the
  existing `run.yaml`. LCORE does no template expansion other than
  LS's own `replace_env_vars()` step at load time.

### Migration / backwards compatibility

Coexistence mechanism: shape detection (see R11). Legacy configs with
`llama_stack.library_client_config_path` continue through the
configured deprecation window.

Three operator-facing migration paths (choose per deployment):

| Path | Effort | Result |
|---|---|---|
| Do nothing | 0 | Legacy keeps working until deprecation closes |
| Lift-and-shift | seconds — `lightspeed-stack --migrate-config ...` | Single-file, byte-equivalent LS behavior |
| Re-express | hours+ | Single-file; high-level sections replace `native_override` |

Deprecation schedule (Decision S2, confirmed by @sbunciak 2026-05-20):
unified mode ships in 0.6 with legacy mode fully functional plus a
startup deprecation WARN (no breaking change); the legacy two-file path
is removed in 0.7. Tentative releases: 0.6 end of June 2026, 0.7 end of
September 2026.

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|---|---|
| `src/models/config.py` | Add `UnifiedInferenceProvider`. Extend the existing `InferenceConfiguration` with `providers: list[UnifiedInferenceProvider]`. Add `UnifiedLlamaStackConfig` (`baseline`/`profile`/`native_override`) and a `config` field on `LlamaStackConfiguration`. Put the unified-vs-legacy `model_validator` on the **root** `Configuration` model (spans `inference.providers` + `llama_stack.*`). |
| `src/lightspeed_stack/llama_stack_configuration.py` | Add `synthesize_configuration`, `deep_merge_list_replace`, `apply_high_level_inference`, `load_default_baseline`, `synthesize_to_file`, `migrate_config_dumb`, `PROVIDER_TYPE_MAP`, `DEFAULT_BASELINE_RESOURCE`. Update `main()` to auto-detect unified vs legacy. |
| `src/data/default_run.yaml` | New file — a thinner baseline than today's repo-root `run.yaml`. Notably do **not** reference `${env.EXTERNAL_PROVIDERS_DIR}` without a default (see "Findings discovered during PoC" in the spike doc). |
| `src/client.py` | In `_load_library_client`: branch on `config.config` presence. Add `_synthesize_library_config()` that calls the synthesizer and writes to the deterministic path (R10). Keep `_enrich_library_config` for legacy. |
| `src/lightspeed_stack.py` | Add `--migrate-config`, `--run-yaml`, `--migrate-output`, `--synthesized-config-output` flags. Add an early-exit branch in `main()` that dispatches to `migrate_config_dumb` when `--migrate-config` is set. Clean up stale docstring. |
| `scripts/llama-stack-entrypoint.sh` | No functional change — the Python CLI already auto-detects. Update the comment to document both modes. |
| `test.containerfile` | Copy `src/data/` into `/opt/app-root/data/` so `load_default_baseline()` resolves inside the LS container. |
| `docker-compose.yaml` | Provide a unified-mode variant (either a new compose file or env-var-switched mount list). Legacy compose continues to work. |

### Insertion point detail

**`synthesize_configuration` pipeline** (the core new function):

1. Resolve the backend-specific block `unified =
   lcs_config["llama_stack"].get("config")` — may be `None` when the
   operator set only top-level `inference.providers` (then baseline
   defaults to `default`, no profile, no `native_override`).
2. Baseline: if `unified` and `unified.profile` set → load that file.
   Else if `unified` and `unified.baseline == "empty"` → `{}`. Else →
   `default_baseline` arg or `load_default_baseline()`.
3. Run `dedupe_providers_vector_io` on the baseline.
4. Apply existing enrichment: `enrich_byok_rag`, `enrich_solr` (Azure
   Entra ID intentionally stays separate because it's a `.env`
   side-effect, not an `ls_config` mutation).
5. If top-level `inference.providers` is non-empty →
   `apply_high_level_inference(ls_config, lcs_config["inference"])`.
6. If `unified` and `unified.native_override` non-empty →
   `deep_merge_list_replace(ls_config, native_override)`.
7. `dedupe_providers_vector_io` again for good measure.
8. Return the final dict.

**`_load_library_client` fork point** (in `src/client.py`). The check is
"is there a synthesis input?", which spans the root `inference.providers`
and `llama_stack.config`, so the client needs the root config (or a
precomputed flag) rather than only the `llama_stack` block:

```python
# app_config is the root Configuration; ls = app_config.llama_stack
synthesis_input = bool(app_config.inference.providers) or ls.config is not None
if synthesis_input:
    self._config_path = self._synthesize_library_config()
elif ls.library_client_config_path is not None:
    self._config_path = self._enrich_library_config(ls.library_client_config_path)
else:
    raise ValueError(...)  # caught by the root validator at load time; belt-and-suspenders here
```

### Config pattern

All new config classes extend `ConfigurationBase` (`extra="forbid"`).
Use `Field()` with defaults, title, and description for every attribute.
The unified-vs-legacy mutual-exclusion check is cross-field and spans the
root model's top-level `inference.providers` and the nested
`llama_stack.config` / `library_client_config_path`, so it lives as a
`@model_validator` on the **root** `Configuration` model (not on
`UnifiedLlamaStackConfig` or `LlamaStackConfiguration`). Within
`UnifiedLlamaStackConfig` no cross-field validation is needed —
synthesis precedence is ordered and handled by the synthesizer.

Example config files live in `examples/profiles/` (two reference
profiles — one remote-provider, one inline-provider) and in
`examples/lightspeed-stack-unified.yaml` as the canonical "unified mode"
reference.

### Test patterns

- Framework: pytest + pytest-mock. Unit tests live in
  `tests/unit/test_llama_stack_synthesize.py` (synthesizer + migration)
  and `tests/unit/models/config/test_llama_stack_configuration.py`
  (schema validation).
- Merge semantics: parametric tests over scalar / map / list /
  type-mismatch / precedence cases.
- Round-trip test: migrate → synthesize → assert dict equality with the
  original `run.yaml`. Pattern already live in
  `test_migrate_then_synthesize_reproduces_run_yaml`.
- Schema validation tests: mutual exclusion, remote URL + config,
  library mode + config without legacy path.
- Feature-specific: provider_type map completeness test asserts every
  `Literal` value on `UnifiedInferenceProvider.type` has a
  `PROVIDER_TYPE_MAP` entry.
- e2e behave tests: migrate `tests/e2e/configuration/**` configs to
  unified form as part of LCORE-2342 (Migrate in-repo e2e / integration
  test configurations).

## Open Questions for Future Work

- **Smart migration mode** (`--migrate-config --smart`): factoring an
  existing `run.yaml` into high-level sections rather than dumping to
  `native_override`. Valuable ergonomic win; deferred because the
  factoring rules require careful design per provider type.
- **Additional high-level sections** beyond `inference` — `rag`,
  `safety`, `storage`, `tools`, `vector_stores`, etc. Add as real demand
  appears, not speculatively. Per Decision S5 and the Pydantic AI
  research, these stay under `llama_stack.config` (not lifted to the top
  level like `inference`) until proven backend-agnostic.
- **User-supplied profile directory**: `profile_dir: /etc/lcore/profiles/`
  with name-based lookup. Deferred to v2.
- **LS process supervision** (restart on crash, signal propagation,
  merged logs) — covered by LCORE-777 / LCORE-778, not this feature.
- **Dynamic reconfig / hot-reload** (live `POST /v1/rag` that adds a BYOK
  RAG without restart) — covered by LCORE-781, not this feature. Llama
  Stack's lack of native hot-reload means any implementation requires
  supervised restart, which is out of scope here.
- **`config_format_version`** as an explicit schema version, accepted
  but not required. Will become load-bearing the first time the unified
  schema undergoes a real breaking change.
- **Validation pre-flight against the Llama Stack schema**: today LCORE
  only validates its own schema; LS validates its own at startup.
  Introducing a pre-flight validator would catch bad synthesis earlier
  but creates a heavy dependency on LS internals.

## Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-04-23 | Initial version | Spike completion |

## Appendix A — Worked example: legacy → unified migration

Given legacy:

```yaml
# run.yaml
version: 2
apis: [agents, inference, vector_io, ...]
providers:
  inference:
    - provider_id: openai
      provider_type: remote::openai
      config:
        api_key: ${env.OPENAI_API_KEY}
        allowed_models: ["${env.E2E_OPENAI_MODEL:=gpt-4o-mini}"]
# ... more ...
```

```yaml
# lightspeed-stack.yaml
name: LCS
llama_stack:
  use_as_library_client: true
  library_client_config_path: ./run.yaml
# ... rest ...
```

Run:

```bash
lightspeed-stack --migrate-config \
  --run-yaml run.yaml \
  -c lightspeed-stack.yaml \
  --migrate-output lightspeed-stack-unified.yaml
```

Produces:

```yaml
# lightspeed-stack-unified.yaml
name: LCS
llama_stack:
  use_as_library_client: true
  # library_client_config_path is REMOVED
  config:
    baseline: empty
    native_override:
      version: 2
      apis: [agents, inference, vector_io, ...]
      providers:
        inference:
          - provider_id: openai
            provider_type: remote::openai
            config:
              api_key: ${env.OPENAI_API_KEY}
              allowed_models: ["${env.E2E_OPENAI_MODEL:=gpt-4o-mini}"]
      # ... rest of run.yaml content under native_override ...
# ... rest of lightspeed-stack.yaml content ...
```

Operator uses the unified file directly and can delete the original
`run.yaml`. Subsequent re-expression (moving from `native_override` into
high-level sections) is optional and per-deployment.

## Appendix B — Reference profile example

```yaml
# examples/profiles/openai-remote.yaml
# A minimal profile for an OpenAI-backed remote Llama Stack.
# Referenced via `llama_stack.config.profile: examples/profiles/openai-remote.yaml`.
version: 2
apis: [agents, inference, safety, tool_runtime, vector_io]
providers:
  inference:
    - provider_id: openai
      provider_type: remote::openai
      config:
        api_key: ${env.OPENAI_API_KEY}
        allowed_models: ["${env.OPENAI_MODEL:=gpt-4o-mini}"]
    - provider_id: sentence-transformers
      provider_type: inline::sentence-transformers
# ... the rest is the same shape as a working run.yaml ...
```
