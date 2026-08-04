# Unified-mode e2e configuration fixtures

Fixtures for the five `unified-mode-*.feature` files (LCORE-2341/LCORE-2343).
Same layout as the parent directory: `library-mode/` and `server-mode/`
variants differing only in the `llama_stack` block; the harness resolves
`<dir>/<mode>/<file>` via the standard `configure_service` logic.

All profile-based fixtures reference `run.yaml` — the repo-root copy the CI
harness materializes from `tests/e2e/configs/run-<env>.yaml` — so they stay
provider-agnostic across the providers matrix.

| Fixture | Purpose |
|---|---|
| `lightspeed-stack-unified-providers.yaml` | Minimal unified config driven only by top-level `inference.providers` (default baseline, R1/S5). openai-specific — used by `@openai-only` scenarios. |
| `lightspeed-stack-unified-config-only.yaml` | Unified config driven only by `llama_stack.config` (`profile: run.yaml`, R1). |
| `lightspeed-stack-unified-relative-profile.yaml` | Same shape as config-only; exists to pin R8 (relative `profile:` resolves against the config file's directory) as a distinct intent. |
| `lightspeed-stack-unified-absolute-profile.yaml` | `profile:` as a container-absolute path (differs per mode subdir). |
| `lightspeed-stack-unified-native-override-scalar.yaml` | `native_override` replaces an overlapping scalar key (R5). Synthesis-only; never booted. |
| `lightspeed-stack-unified-native-override-list.yaml` | `native_override` replaces an overlapping list wholesale (R5). Synthesis-only; never booted. |
| `lightspeed-stack-invalid-providers-and-legacy.yaml` | INVALID: `inference.providers` + `library_client_config_path` (mutual exclusion, R3). Validation-only. |
| `lightspeed-stack-invalid-config-and-legacy.yaml` | INVALID: `llama_stack.config` + `library_client_config_path` (R3). Validation-only. |
| `lightspeed-stack-invalid-version-legacy-unified-body.yaml` | INVALID: `config_format_version: legacy` on a unified-shaped body (R11, LCORE-2872). Validation-only. |
| `lightspeed-stack-legacy-for-migration.yaml` | Legacy half of "the legacy migration fixture pair"; paired with the repo-root `run.yaml`. Deliberately free of enrichment sections so migrate→synthesize round-trips losslessly (see LCORE-3370). |
| `lightspeed-stack-unified-migrated.yaml` | Generated at test time by the `--migrate-config` step; gitignored and cleaned up after each scenario. |
