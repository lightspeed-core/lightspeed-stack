# Feature design: Llama Stack config merge (unified `lightspeed-stack.yaml`)

|                    |                                                                                  |
|--------------------|----------------------------------------------------------------------------------|
| **Date**           | 2026-04-23                                                                       |
| **Component**      | Lightspeed Core Stack (src/models/config.py, src/llama_stack_configuration.py, src/client.py, src/lightspeed_stack.py, scripts/llama-stack-entrypoint.sh) |
| **Authors**        | Maxim Svistunov                                                                   |
| **Feature**        | [LCORE-836](https://redhat.atlassian.net/browse/LCORE-836)                       |
| **Spike**          | [llama-stack-config-merge-spike.md](llama-stack-config-merge-spike.md)           |
| **Links**          | LCORE-509 (Epic), LCORE-777 (Epic), LCORE-518 (prior spike, Closed), LCORE-779 (auto-regen, Closed) |

## What

This feature collapses the two Lightspeed Core configuration files —
`lightspeed-stack.yaml` (LCORE settings) and `run.yaml` (Llama Stack
operational config) — into a single `lightspeed-stack.yaml`. At runtime,
LCORE synthesizes a full Llama Stack `run.yaml` from a new
`llama_stack.config` sub-section and hands it to Llama Stack (library
client or subprocess, mode-dependent).

Key shape:

- High-level keys under `llama_stack.config` for the common path
  (v1: `inference`; future: `storage`, `safety`, `tools`).
- `llama_stack.config.native_override` escape hatch — raw Llama Stack
  schema, deep-merged with list replacement. Covers anything the
  high-level schema doesn't express.
- `llama_stack.config.profile` — path to a user-authored YAML that serves
  as the synthesis baseline.
- `llama_stack.config.baseline: default | empty` — pick between LCORE's
  built-in baseline and an empty dict (used by the migration tool for
  exact round-trip).
- Legacy two-file mode (`llama_stack.library_client_config_path` +
  external `run.yaml`) is preserved during a deprecation window;
  mutually exclusive with `llama_stack.config`.

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

- **R1:** `lightspeed-stack.yaml` with a `llama_stack.config` sub-section
  and no external `run.yaml` boots LCORE in both library and server modes
  and serves `/v1/query` successfully.
- **R2:** Legacy mode (`llama_stack.library_client_config_path` +
  external `run.yaml`) works unchanged until the deprecation window
  closes. A startup WARN is emitted one release after unified mode lands.
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
- **R6:** Secrets are never resolved into the synthesized file on disk.
  `${env.FOO}` references appear verbatim in the synthesized `run.yaml`.
- **R7:** Existing enrichment behavior (Azure Entra ID, BYOK RAG,
  Solr/OKP) produces the same result in unified mode as in legacy mode
  for equivalent inputs.
- **R8:** A profile referenced by a relative `profile:` path resolves
  against the directory of the loaded `lightspeed-stack.yaml`.
- **R9:** The unified schema extends current `LlamaStackConfiguration`
  pydantic model with a new `config: Optional[UnifiedLlamaStackConfig]`
  field; validation enforces mutual exclusion with legacy mode and
  rejects unknown fields (`extra="forbid"`).
- **R10:** The synthesized `run.yaml` is written to a persistent known
  path (overwritten each boot), logged, and a CLI flag
  `--synthesized-config-output` lets operators override the location for
  debugging.
- **R11:** Shape detection determines mode (unified vs legacy); an
  optional `config_format_version` field is accepted but must agree with
  the shape when present.

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

## Architecture

### Overview

```text
lightspeed-stack.yaml (unified mode)
       │
       ▼
 ┌────────────────────────────┐
 │ Configuration load         │    Pydantic validation, mutual-exclusion
 │  src/configuration.py      │    check between `config` and
 │  src/models/config.py      │    `library_client_config_path`.
 └────────────┬───────────────┘
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

At LCORE startup (library mode): if `llama_stack.config` is set in the
loaded `lightspeed-stack.yaml`, the synthesizer produces a `run.yaml`
dict, writes it to disk, and passes the path to the library client.

At Llama Stack container startup (server mode): the container's
entrypoint script invokes
`python3 /opt/app-root/llama_stack_configuration.py -c <lightspeed-stack.yaml>
-o /opt/app-root/run.yaml`. The Python CLI auto-detects unified vs legacy
by `llama_stack.config` presence; in unified mode it synthesizes and
writes the output; in legacy mode it performs in-place enrichment as
before.

### Storage / data model changes

No persistent storage is added. The synthesized `run.yaml` is written
once per boot to a deterministic path; not a database. `src/data/
default_run.yaml` is a new package-shipped file, the built-in baseline
Llama Stack configuration.

### Configuration

New sub-section under the existing `llama_stack` block:

```yaml
llama_stack:
  use_as_library_client: true
  # NOTE: library_client_config_path intentionally OMITTED in unified mode.
  # Setting both `config` and `library_client_config_path` is a validation error.
  config:
    # Baseline selection
    baseline: default              # default | empty; ignored if `profile` is set
    profile: ./my-profile.yaml     # optional; resolves relative to lightspeed-stack.yaml

    # High-level sections (v1: inference; future: storage, safety, tools, ...)
    inference:
      providers:
        - type: openai             # mapped to remote::openai
          api_key_env: OPENAI_API_KEY
          allowed_models: [gpt-4o-mini]
        - type: sentence_transformers

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


class UnifiedInferenceSection(ConfigurationBase):
    providers: list[UnifiedInferenceProvider] = Field(default_factory=list)


class UnifiedLlamaStackConfig(ConfigurationBase):
    baseline: Literal["default", "empty"] = "default"
    profile: Optional[str] = None
    inference: Optional[UnifiedInferenceSection] = None
    native_override: dict[str, Any] = Field(default_factory=dict)


class LlamaStackConfiguration(ConfigurationBase):
    # existing fields unchanged (url, api_key, use_as_library_client,
    # library_client_config_path, timeout)
    config: Optional[UnifiedLlamaStackConfig] = None

    @model_validator(mode="after")
    def check_llama_stack_model(self) -> Self:
        if self.config is not None and self.library_client_config_path is not None:
            raise ValueError("... mutually exclusive ... use --migrate-config")
        # ...legacy checks preserved...
        return self
```

### API changes

None at the REST API surface. Internal API additions in
`src/llama_stack_configuration.py`:

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

- **Unified + legacy set simultaneously**: raised during
  `LlamaStackConfiguration.check_llama_stack_model`. Error message
  directs to `--migrate-config`.
- **Library mode with neither `config` nor `library_client_config_path`**:
  raised during the same validator. Error identifies the two valid paths.
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

- **No secrets written to disk**: `apply_high_level_inference` emits
  `${env.<VAR>}` references, never the resolved secret. The synthesized
  `run.yaml` is safe to log path-wise; its contents only contain env
  references for secrets.
- **`native_override` is raw YAML**: content is operator-controlled, so
  no new injection surface — same trust model as the existing
  `run.yaml`. LCORE does no template expansion other than the existing
  `replace_env_vars()` step in the load pipeline.
- **Synthesized file location**: persistent known path, world-readable
  by default in a container. This is acceptable because the file
  contains only env-var references for secrets; operators who want
  stricter filesystem permissions should tighten the mount.

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

Deprecation schedule: calendar-based (per Decision S2 in the spike);
concrete numbers set by @sbunciak at release time. Default recommended
shape: unified mode ships as opt-in at release N; legacy-mode WARN
begins one release later; legacy-mode removal no sooner than 6 months
after WARN begins.

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|---|---|
| `src/models/config.py` | Add `UnifiedInferenceProvider`, `UnifiedInferenceSection`, `UnifiedLlamaStackConfig`. Modify `LlamaStackConfiguration` — add `config` field, extend the `model_validator` for mutual-exclusion check. |
| `src/llama_stack_configuration.py` | Add `synthesize_configuration`, `deep_merge_list_replace`, `apply_high_level_inference`, `load_default_baseline`, `synthesize_to_file`, `migrate_config_dumb`, `PROVIDER_TYPE_MAP`, `DEFAULT_BASELINE_RESOURCE`. Update `main()` to auto-detect unified vs legacy. |
| `src/data/default_run.yaml` | New file — a thinner baseline than today's repo-root `run.yaml`. Notably do **not** reference `${env.EXTERNAL_PROVIDERS_DIR}` without a default (see PoC surprise in the spike doc). |
| `src/client.py` | In `_load_library_client`: branch on `config.config` presence. Add `_synthesize_library_config()` that calls the synthesizer and writes to the deterministic path (R10). Keep `_enrich_library_config` for legacy. |
| `src/lightspeed_stack.py` | Add `--migrate-config`, `--run-yaml`, `--migrate-output`, `--synthesized-config-output` flags. Add an early-exit branch in `main()` that dispatches to `migrate_config_dumb` when `--migrate-config` is set. Clean up stale docstring. |
| `scripts/llama-stack-entrypoint.sh` | No functional change — the Python CLI already auto-detects. Update the comment to document both modes. |
| `test.containerfile` | Copy `src/data/` into `/opt/app-root/data/` so `load_default_baseline()` resolves inside the LS container. |
| `docker-compose.yaml` | Provide a unified-mode variant (either a new compose file or env-var-switched mount list). Legacy compose continues to work. |

### Insertion point detail

**`synthesize_configuration` pipeline** (the core new function):

1. Retrieve `unified = lcs_config["llama_stack"]["config"]` — raise if absent.
2. Baseline: if `unified.profile` set → load that file. Else if
   `unified.baseline == "empty"` → `{}`. Else → `default_baseline` arg or
   `load_default_baseline()`.
3. Run `dedupe_providers_vector_io` on the baseline.
4. Apply existing enrichment: `enrich_byok_rag`, `enrich_solr` (Azure
   Entra ID intentionally stays separate because it's a `.env`
   side-effect, not an `ls_config` mutation).
5. If `unified.inference` present → `apply_high_level_inference`.
6. If `unified.native_override` non-empty →
   `deep_merge_list_replace(ls_config, native_override)`.
7. `dedupe_providers_vector_io` again for good measure.
8. Return the final dict.

**`_load_library_client` fork point** (in `src/client.py`):

```python
if config.config is not None:
    self._config_path = self._synthesize_library_config()
elif config.library_client_config_path is not None:
    self._config_path = self._enrich_library_config(config.library_client_config_path)
else:
    raise ValueError(...)  # caught by the validator at load time; belt-and-suspenders here
```

### Config pattern

All new config classes extend `ConfigurationBase` (`extra="forbid"`).
Use `Field()` with defaults, title, and description for every attribute.
Cross-field validation in `UnifiedLlamaStackConfig` is not currently
needed — the precedence is strictly ordered and handled by the
synthesizer, not by the model.

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
  unified form as part of LCORE-???? (test migration JIRA).

## Open Questions for Future Work

- **Smart migration mode** (`--migrate-config --smart`): factoring an
  existing `run.yaml` into high-level sections rather than dumping to
  `native_override`. Valuable ergonomic win; deferred because the
  factoring rules require careful design per provider type.
- **Additional high-level sections** beyond `inference` — `storage`,
  `safety`, `tools`, `vector_stores`, etc. Add as real demand appears,
  not speculatively.
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
