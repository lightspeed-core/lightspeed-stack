# Library-mode PoC evidence

Command:
```bash
export OPENAI_API_KEY=<redacted>
export E2E_OPENAI_MODEL=gpt-4o-mini
uv run lightspeed-stack -c docs/design/llama-stack-config-merge/poc-evidence/lightspeed-stack-unified-library.yaml
```

## What the unified config does

- `llama_stack.config.profile: /abs/path/to/tests/e2e/configs/run-ci.yaml` — baseline loaded from the CI profile
- `llama_stack.config.native_override.safety.default_shield_id: llama-guard` — override proves merge works

## Evidence

- `synthesized-run.yaml` — the full run.yaml LCORE produced from the unified config
- `query-response.json` — a successful `/v1/query` round-trip

## Proves

- `llama_stack.library_client_config_path` was NOT used (no external run.yaml needed)
- `llama_stack.config.profile` was used as the synthesis baseline (path resolution works with absolute paths)
- `llama_stack.config.native_override` was merged onto the baseline
- `AsyncLlamaStackAsLibraryClient` accepts the synthesized file path (answered item #24: file-only, not dict)
- `/v1/query` succeeded end-to-end through the synthesized stack
