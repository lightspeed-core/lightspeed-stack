# Unified-mode e2e configuration fixtures

Fixtures for the `unified-mode-*.feature` files (LCORE-2341/LCORE-2343).
Same layout as the parent directory: `library-mode/` and `server-mode/`
variants differing only in the `llama_stack` block; the harness resolves
`<dir>/<mode>/<file>` via the standard `configure_service` logic.

All profile-based fixtures reference `run.yaml` — the repo-root copy the CI
harness materializes from `tests/e2e/configs/run-<env>.yaml` — so they stay
provider-agnostic across the providers matrix.

Only bootable fixtures live here. The validation-only and synthesis-only
inputs (invalid configs, `native_override` shapes) belong to the integration
layer — `tests/configuration/unified-mode/` and
`tests/integration/test_unified_synthesis.py` — because e2e steps never run
`src/` CLIs (see `docs/testing/e2e_testing.md`, "Choosing the Test Layer").

| Fixture | Purpose |
|---|---|
| `lightspeed-stack-unified-providers.yaml` | Minimal unified config driven only by top-level `inference.providers` (default baseline, R1/S5). openai-specific — used by `@openai-only` scenarios. |
| `lightspeed-stack-unified-config-only.yaml` | Unified config driven only by `llama_stack.config` (`profile: run.yaml`, R1). |
| `lightspeed-stack-unified-relative-profile.yaml` | Same shape as config-only; exists to pin R8 (relative `profile:` resolves against the config file's directory) as a distinct intent. |
| `lightspeed-stack-unified-absolute-profile.yaml` | `profile:` as a container-absolute path (differs per mode subdir). |
| `lightspeed-stack-legacy-for-migration.yaml` | Legacy half of the migration fixture pair; paired with `tests/e2e/configs/run-ci.yaml`. Deliberately free of enrichment sections so migrate→synthesize round-trips losslessly (see LCORE-3370). Input to the drift guard below; never booted. |
| `lightspeed-stack-unified-migrated.yaml` | **Committed** output of `--migrate-config` for the pair above. Booted by `unified-mode-migration.feature` (`@openai-only`: it inlines the openai run-ci.yaml). `tests/integration/test_unified_mode_cli.py::test_committed_migrated_fixture_matches_cli_output` fails when the CLI output drifts; its docstring has the regeneration command. |
