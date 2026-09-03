# E2E Test Configuration Files

This directory contains configuration files used for end-to-end testing of Lightspeed Core.

## Directory Structure

- `server-mode/` - Configurations for testing when LCore connects to a separate Llama Stack service
- `library-mode/` - Configurations for testing when LCore embeds Llama Stack as a library

## Library mode uses unified configs (LCORE-2342)

The library-mode configurations use the unified single-file format: instead of
the legacy `llama_stack.library_client_config_path`, they carry

```yaml
llama_stack:
  use_as_library_client: true
  config:
    profile: run.yaml
```

The harness/CI copies the provider-specific run config
(`tests/e2e/configs/run-<environment>.yaml`) to `./run.yaml` in the repo root,
and the active `lightspeed-stack.yaml` is also copied to the repo root — so the
relative `profile:` path resolves to that materialized file, which the unified
synthesizer consumes as its baseline. LS behavior is identical to the legacy
two-file path (requirement R7 in the config-merge design doc); the wiring that
selects a provider config stays unchanged. The synthesizer also ensures the
MCP `tool_runtime` provider (`model-context-protocol`) is present on the
profile baseline when missing; many `run-*.yaml` fixtures already include it,
so the ensure is typically a no-op.

The `tests/e2e/configs/run-*.yaml` files therefore serve a dual role: in
server mode they are the run configuration of the standalone Llama Stack
service, and in library mode they are consumed as the unified-mode synthesis
profile. No in-repo test config references them via the legacy mechanism
anymore.

## Common Configuration Features

### Default Configurations (`lightspeed-stack.yaml`)

Both server-mode and library-mode default configurations include:

1. **MCP Servers** - Used for testing MCP-related endpoints:
   - `github-api` - Uses client-provided auth (Authorization header)
   - `gitlab-api` - Uses client-provided auth (X-API-Token header)
   - `k8s-service` - Uses kubernetes auth (not client-provided)
   - `public-api` - No authentication (not client-provided)

   These servers test the `/v1/mcp-auth/client-options` endpoint, which should return only servers accepting client-provided authentication (`github-api` and `gitlab-api`).

2. **Authentication** - Set to `noop` for most tests

3. **User Data Collection** - Enabled for feedback and transcripts testing

### Special-Purpose Configurations

- `lightspeed-stack-auth-noop-token.yaml` - For authorization testing
- `lightspeed-stack-invalid-feedback-storage.yaml` - For negative feedback testing
- `lightspeed-stack-no-cache.yaml` - For cache-disabled scenarios
