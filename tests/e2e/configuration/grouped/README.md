# Grouped E2E configs — wired to features

Features/scenarios use `lightspeed-stack-g-*.yaml` and `@cfg_*` tags.
Legacy YAML filenames remain on disk but are no longer referenced from
active feature Backgrounds (except `@cfg_unified @skip` / legacy unified tests).

## Counts

| Mode | Grouped configs |
|------|-----------------|
| Library | **11** |
| Server | **12** |

## Tags → config

| Tag | Config file |
|-----|-------------|
| `@cfg_default` | `g-default` |
| `@cfg_authorized` | `g-authorized` |
| `@cfg_byok_pdf` | `g-byok-pdf` (library) |
| `@cfg_mcp` | `g-mcp` |
| `@cfg_mcp_invalid` | `g-mcp-invalid` |
| `@cfg_mcp_api_auth` | `g-mcp-api-auth` |
| `@cfg_rbac` | `g-rbac` |
| `@cfg_rh_identity` | `g-rh-identity` |
| `@cfg_negative` | `g-negative` |
| `@cfg_skills` | `g-skills` |
| `@cfg_skills_directory` | `g-skills-directory` |
| `@cfg_tls` | `g-tls` (server) |
| `@cfg_degraded` | `g-degraded` (server) |
| `@cfg_unified` | unified-mode fixtures (`@skip`) |

Multi-config feature files (`mcp`, `skills`, `feedback`, `conversation_cache_v2`,
`http_401_unauthorized`, `llama_stack_disrupted`) use **scenario-level** `@cfg_*`
only so Behave tag filters do not pull the wrong scenarios via feature inheritance.

## CI shards (`.github/workflows/e2e_tests.yaml`)

| Shard | Tag expression |
|-------|----------------|
| default | `@cfg_default` |
| authorized | `@cfg_authorized` |
| mcp | `@cfg_mcp or @cfg_mcp_invalid or @cfg_mcp_api_auth` |
| rbac | `@cfg_rbac` |
| skills | `@cfg_skills or @cfg_skills_directory` |
| other | `@cfg_rh_identity or @cfg_negative or @cfg_byok_pdf or @cfg_tls or @cfg_degraded or @cfg_unified` |

Feature file order is in `tests/e2e/test_list.txt` (same-config blocks contiguous).

Local: `E2E_BEHAVE_TAG_EXPR='not @skip and @cfg_authorized' make test-e2e-tagged-local`

## Restart skipping

Across scenarios **and** consecutive feature files, the same `g-*` basename skips
`The service is restarted`. After each feature, the suite keeps the applied config
(no bootstrap restore) so the next file in the same shard does not pay another
restart. Legacy restore+restart: `E2E_RESTORE_CONFIG_AFTER_FEATURE=1`.

## Safe merges (unchanged rationale)

- **default + inline-rag**: same `e2e-test-docs` id
- **authorized + shields**: no MCP (avoids `check_mcp_auth` on every query)
- **all valid MCP → g-mcp**: same as former `mcp.yaml`
- **no-cache + invalid-feedback → g-negative**: compatible negative paths

## Rejected merges

MCP into authorized; BYOK PDF into default; skills↔directory; MCP invalid into g-mcp.
