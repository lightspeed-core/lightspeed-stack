# End-to-End (E2E) Tests Guide

This guide describes how to run, extend, and understand the Lightspeed Core Stack end-to-end tests. The suite uses **Behave** (BDD) with Gherkin feature files and runs against a live service (Docker Compose or Prow/OpenShift).

---

## Table of Contents

1. [Overview](#overview)
2. [Directory Layout](#directory-layout)
3. [How to Run E2E Tests](#how-to-run-e2e-tests)
4. [Environment Variables](#environment-variables)
5. [Deployment Modes: Server vs Library](#deployment-modes-server-vs-library)
6. [Tags and Hooks](#tags-and-hooks)
7. [Configuration Files](#configuration-files)
8. [Feature Files and Steps](#feature-files-and-steps)
9. [Gherkin Keywords in Feature Files](#gherkin-keywords-in-feature-files)
10. [Writing New Scenarios](#writing-new-scenarios)
11. [Troubleshooting](#troubleshooting)

---

## Overview

- **Framework**: [Behave](https://behave.readthedocs.io/) (Python BDD).
- **Scope**: REST API of the Lightspeed Core Stack (query, streaming_query, models, info, health, feedback, conversations, RBAC, MCP, etc.).
- **Execution**: Tests run in a **separate process** from the app. They send HTTP requests to the service and (in server mode) optionally talk to the Llama Stack service for shield setup.
- **Environments**: Local (Docker Compose) or Prow/OpenShift (containers/pods). Mode is detected via `E2E_DEPLOYMENT_MODE` and `RUNNING_PROW`.

---

## Directory Layout

**E2E tests (Behave, feature files, steps):**

```
tests/e2e/
├── README.md                    # Short pointer to this guide (docs/e2e_testing.md)
├── test_list.txt                # List of feature files (run order)
├── features/
│   ├── environment.py           # Hooks: before_all, before_feature, before_scenario, after_scenario, after_feature
│   ├── *.feature                # Gherkin feature files
│   └── steps/                   # Step definitions
│       ├── common.py            # Service started, default state, host/port from env
│       ├── common_http.py       # HTTP helpers (status, body, headers)
│       ├── auth.py              # Authorization header steps
│       ├── llm_query_response.py # query / streaming_query steps
│       ├── feedback.py          # Feedback API steps
│       ├── conversation.py      # Conversations / cache steps
│       ├── health.py            # Health and llama-stack disruption
│       ├── info.py, models.py   # Info and models endpoints
│       ├── rbac.py              # RBAC steps
│       └── ...
├── configuration/               # Lightspeed-stack configs used by E2E (local Docker)
│   ├── server-mode/             # When Llama stack runs in separate process
│   └── library-mode/            # When Llama Stack is in-process
├── configs/                     # Llama Stack run configs (run-ci.yaml, etc.)
├── utils/
│   ├── utils.py                 # restart_container, switch_config, wait_for_container_health, etc.
│   ├── prow_utils.py            # Prow/OpenShift helpers (restore_llama_stack_pod, etc.)
│   └── llama_stack_shields.py   # Shield unregister/register (server mode, optional)
├── mock_mcp_server/             # Mock MCP server for MCP tests
└── rag/                         # RAG test data (e.g. for FAISS)
```

**Prow/OpenShift E2E (pipelines, manifests, configs used when `RUNNING_PROW` is set):**

```
tests/e2e-prow/
└── rhoai/                       # RHOAI / OpenShift E2E
    ├── run-tests.sh             # Entry to run E2E in Prow
    ├── pipeline.sh              # Main pipeline definition
    ├── pipeline-services.sh     # Services pipeline
    ├── pipeline-vllm.sh         # vLLM pipeline
    ├── pipeline-test-pod.sh     # Test pod pipeline
    ├── configs/                 # Lightspeed-stack configs for Prow (used by environment.py when is_prow)
    │   ├── lightspeed-stack.yaml
    │   ├── lightspeed-stack-auth-noop-token.yaml
    │   ├── lightspeed-stack-rbac.yaml
    │   ├── lightspeed-stack-auth-rh-identity.yaml
    │   ├── lightspeed-stack-no-cache.yaml
    │   ├── lightspeed-stack-invalid-feedback-storage.yaml
    │   └── run.yaml             # Llama Stack run config for Prow
    ├── scripts/
    │   ├── e2e-ops.sh           # E2E ops (e.g. disrupt/restore llama-stack) — called from prow_utils
    │   ├── bootstrap.sh
    │   ├── deploy-vllm.sh
    │   ├── fetch-vllm-image.sh
    │   ├── get-vllm-pod-info.sh
    │   └── gpu-setup.sh
    └── manifests/               # OpenShift/Kubernetes manifests
        ├── lightspeed/          # Lightspeed stack, llama-stack, mock-jwks, mcp-mock-server
        ├── vllm/                # vLLM runtime and inference services (CPU/GPU)
        ├── operators/           # Operator install (operatorgroup, operators, ds-cluster)
        ├── namespaces/          # NFD, nvidia-operator
        └── gpu/                 # NFD and cluster policy for GPU
```

---

## How to Run E2E Tests

### Prerequisites

- **Local**: Docker Compose stack up (e.g. `docker compose up -d`). The app and Llama Stack must be reachable at the host/ports you configure (see [Environment Variables](#environment-variables)).
- **Prow**: Pipeline runs in OpenShift; `RUNNING_PROW` is set and Prow-specific paths/configs are used.

### Commands

From the project root:

```bash
# Run all E2E tests (excluding @skip)
uv run make test-e2e
# or
uv run make test-e2e-local
```

Both targets use:

```text
uv run behave --color --format pretty --tags=-skip -D dump_errors=true @tests/e2e/test_list.txt
```

- **Feature set**: The list of feature files is in `tests/e2e/test_list.txt`. Order matters for execution.
- **Excluding scenarios**: `--tags=-skip` excludes scenarios tagged with `@skip`.

### Running a Subset

```bash
# Single feature file
uv run behave tests/e2e/features/query.feature --tags=-skip

# Scenarios with a given tag (e.g. Authorized)
uv run behave tests/e2e/features/query.feature --tags=Authorized

# Exclude a tag
uv run behave tests/e2e/features/health.feature --tags=-skip-in-library-mode
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_DEPLOYMENT_MODE` | `server` | `server` or `library`. Drives config paths and which scenarios run (e.g. `@skip-in-library-mode`). |
| `E2E_LSC_HOSTNAME` | `localhost` | Host of the Lightspeed Core Stack API. |
| `E2E_LSC_PORT` | `8080` | Port of the Lightspeed Core Stack API. |
| `E2E_LLAMA_HOSTNAME` | `localhost` | Host of the Llama Stack service (server mode). |
| `E2E_LLAMA_PORT` | `8321` | Port of the Llama Stack service. |
| `E2E_LLAMA_STACK_URL` | — | Full base URL for Llama Stack (overrides host/port if set). Used by shield helpers. |
| `E2E_LLAMA_STACK_API_KEY` | `xyzzy` | API key for Llama Stack client (e.g. shield API). |
| `E2E_DEFAULT_MODEL_OVERRIDE` | — | Override default LLM model id (e.g. `gpt-4o-mini`). |
| `E2E_DEFAULT_PROVIDER_OVERRIDE` | — | Override default provider id (e.g. `openai`). |
| `FAISS_VECTOR_STORE_ID` | — | Vector store id for FAISS-related scenarios. |
| `RUNNING_PROW` | — | Set in Prow/OpenShift; enables Prow config paths and pod/container ops. |
| `OPENAI_API_KEY` | — | **Required.** Used by the app and Llama Stack for LLM calls (e.g. OpenAI). The E2E tests and the stack will not run correctly without it. |

For local Docker runs, defaults are usually enough. Override when the stack is on different host/ports or when using library mode. **You must set `OPENAI_API_KEY`** for the tests (and the services) to run.

---

## Deployment Modes: Server vs Library

- **Server mode** (`E2E_DEPLOYMENT_MODE=server`): Lightspeed Core Stack talks to a **separate** Llama Stack service (e.g. `llama-stack` container). Configs under `configuration/server-mode/` are used. Scenarios that need a dedicated Llama Stack container (e.g. "llama-stack unreachable") run; those tagged `@skip-in-library-mode` run as well.
- **Library mode** (`E2E_DEPLOYMENT_MODE=library`): Llama Stack runs **in-process** with the app. Configs under `configuration/library-mode/` are used. Scenarios tagged `@skip-in-library-mode` are skipped (no separate llama-stack to disrupt or query for shields).

Mode is set in `before_all` from `E2E_DEPLOYMENT_MODE` and stored as `context.is_library_mode`.

---

## Tags and Hooks

All tag behaviour is implemented in **`features/environment.py`**: the hooks (`before_all`, `before_feature`, `before_scenario`, `after_scenario`, `after_feature`) read `scenario.effective_tags` or `feature.tags` and run the corresponding setup or teardown. You can add new tags by extending these hooks (and, if the tag switches config, by adding a Lightspeed Stack config and wiring it as in [Writing New Scenarios](#writing-new-scenarios)).

### Scenario Tags

| Tag | Effect |
|-----|--------|
| `@skip` | Scenario is skipped (reason: "Marked with @skip"). Use for broken or WIP scenarios. |
| `@skip-in-library-mode` | Scenario is skipped when `E2E_DEPLOYMENT_MODE=library`. Used for tests that require a separate Llama Stack (e.g. connection disruption). |
| `@local` | Skipped unless running in "local" mode (context flag). |
| `@InvalidFeedbackStorageConfig` | Before scenario: switch to invalid-feedback-storage config and restart container. After: restore feature config and restart. |
| `@NoCacheConfig` | Before scenario: switch to no-cache config and restart. After: restore and restart. |
| `@disable-shields` | (If used) Before scenario: unregister shield (e.g. llama-guard) via Llama Stack API; after: re-register. **Server mode only**; skipped in library mode. |
| `@Authorized` | Feature-level: use auth-noop-token config for the whole feature; restore in after_feature. |
| `@RBAC` | Feature-level: use RBAC config; restore in after_feature. |
| `@RHIdentity` | Feature-level: use RH identity config; restore in after_feature. |
| `@Feedback` | Feature-level: set feedback conversation list; after_feature deletes those conversations. |
| `@MCP` | Feature-level: use MCP config; restore in after_feature. |

### Multiple Tags and Skip Comment

You can put several tags on one scenario. To document why a scenario is skipped, add a Gherkin comment above the tags:

```gherkin
  # Only in server mode; llama-stack is in-process in library mode
  @skip-in-library-mode
  @skip
  Scenario: Check if service report proper readiness when llama stack is not available
```

### Hooks (environment.py)

- **before_all**: Sets `deployment_mode`, `is_library_mode`, detects or overrides `default_model` / `default_provider`, sets `faiss_vector_store_id`.
- **before_feature**: Applies feature-level config and restarts container for `Authorized`, `RBAC`, `RHIdentity`, `Feedback`, `MCP`.
- **before_scenario**: Skips scenarios for `@skip`, `@local`, `@skip-in-library-mode`; applies scenario config for `InvalidFeedbackStorageConfig` / `NoCacheConfig`; for `@disable-shields` (server mode) unregisters the shield.
- **after_scenario**: Restores Llama Stack if it was disrupted; restores config and restarts for scenario config tags; for `@disable-shields` re-registers the shield.
- **after_feature**: Restores config and restarts for `Authorized`, `RBAC`, `RHIdentity`, `MCP`; deletes feedback conversations for `Feedback`.

---

## Configuration Files

- **Lightspeed-stack**: Under `tests/e2e/configuration/server-mode/` and `library-mode/`. Switched via `switch_config()` and copied into the container's config path (or applied via ConfigMap in Prow). Names like `lightspeed-stack.yaml`, `lightspeed-stack-auth-noop-token.yaml`, `lightspeed-stack-rbac.yaml`, etc.
- **Llama Stack**: Under `tests/e2e/configs/` (e.g. `run-ci.yaml`). Used by the Llama Stack container; not switched by Behave step-by-step, but the stack is started with the appropriate run config.

See `tests/e2e/configuration/README.md` for a short description of each config.

---

## Feature Files and Steps

### List of feature files

The feature files below are run in the order given in `tests/e2e/test_list.txt`:

| Feature file | What it tests |
|--------------|----------------|
| `faiss.feature` | FAISS support: vector store registration, RAGs endpoint, file_search tool. |
| `smoketests.feature` | Smoke tests: main endpoint reachability. |
| `authorized_noop.feature` | `/v1/authorized` endpoint with noop auth (no token required). |
| `authorized_noop_token.feature` | `/v1/authorized` endpoint with noop-with-token auth (user_id, token validation). |
| `authorized_rh_identity.feature` | `/v1/authorized` endpoint with RH identity auth (x-rh-identity header, entitlements). |
| `rbac.feature` | Role-Based Access Control: admin/user/viewer/query-only/no-role permissions on query, models, conversations, info. |
| `conversations.feature` | Conversations API: list, get by id, delete; auth and error cases. |
| `conversation_cache_v2.feature` | Conversation Cache V2 API: conversations CRUD, topic summary, cache-off and llama-stack-down behaviour. |
| `feedback.feature` | Feedback endpoint: enable/disable, status, submit feedback (sentiment, conversation id), invalid storage. |
| `health.feature` | Readiness and liveness endpoints; behaviour when llama-stack is unavailable. |
| `info.feature` | Info, OpenAPI, shields, tools, metrics, MCP client auth options endpoints. |
| `query.feature` | Query endpoint: LLM responses, system prompt, auth errors, missing/invalid params, attachments, context length (413), llama-stack down. |
| `streaming_query.feature` | Streaming query endpoint: token stream, system prompt, auth, params, attachments, context length (413 / stream error). |
| `rest_api.feature` | REST API: OpenAPI endpoint. |
| `mcp.feature` | MCP (Model Context Protocol): tools, query, streaming_query with MCP auth (required, token, invalid token). |
| `models.feature` | Models endpoint: list models, filter, empty result; error when llama-stack unreachable. |

If you add a new feature file, add it to **`tests/e2e/test_list.txt`** so it is included when you run the full E2E suite (e.g. `make test-e2e`). The order in that file is the run order.

- **Feature files** (`*.feature`): Gherkin `Feature` / `Scenario` / `Given` / `When` / `Then`. One file per area (query, streaming_query, health, models, info, feedback, conversations, rbac, etc.).
- **Steps**: Implemented in `features/steps/*.py`. Steps receive `context` and use it to store host/port, auth headers, response, and shared data (e.g. `context.response`, `context.default_model`). Placeholders like `{MODEL}` and `{PROVIDER}` in feature tables or docstrings are replaced with `context.default_model` and `context.default_provider` via `replace_placeholders()`.

Key step modules:

- **common.py**: "The service is started locally" (set host/port from env), "The system is in default state".
- **common_http.py**: Status code, body content, headers.
- **auth.py**: Set Authorization header.
- **llm_query_response.py**: Call query/streaming_query, too-long query, parse streamed response, assert fragments and error messages.
- **health.py**: "The llama-stack connection is disrupted" (stop container in server mode; sets `llama_stack_was_running` for restore in after_scenario).

---

## Gherkin Keywords in Feature Files

Feature files use [Gherkin](https://cucumber.io/docs/gherkin/) syntax. Below is what each keyword means and how this project uses it.

### Structure keywords

| Keyword | Meaning | Example |
|--------|---------|--------|
| **Feature** | Title and optional description of a capability. One per `.feature` file. | `Feature: Query endpoint API tests` |
| **Background** | Steps run **before every scenario** in that feature. Use for common setup (e.g. "service started", "API prefix"). | `Background:` then `Given The service is started locally` |
| **Scenario** | One concrete test: a list of steps that set up, act, and assert. | `Scenario: Check if LLM responds properly...` |
| **Scenario Outline** | Template for multiple scenarios; steps can use placeholders that are filled from an **Examples** table. (Used when the same flow is repeated with different data.) | `Scenario Outline:` with `Examples:` table |

### Step keywords (Given / When / Then / And / But)

Each line in a scenario is a **step**. The keyword indicates the step's role; Behave matches the line to a step definition (e.g. `@given("The service is started locally")`).

| Keyword | Meaning | Typical use in this project |
|--------|---------|-----------------------------|
| **Given** | Precondition or initial state. | Service is started, system in default state, auth header set, llama-stack disrupted. |
| **When** | The action under test. | Call an endpoint (query, streaming_query, GET readiness), send a request body. |
| **Then** | Expected outcome (assertion). | Status code is 200, body contains text or matches schema, response has certain fields. |
| **And** | Continuation of the previous keyword. Same role as the last Given/When/Then, but reads more naturally. | "Given X **And** Y" = two preconditions; "Then A **And** B" = two assertions. |
| **But** | Same as And, but used for contrast. | "Then status is 200 **But** body does not contain …" (rare in this suite.) |

**Convention for this suite:** Each scenario should have **exactly one When step** (the single action under test). It can have **one or more Given steps** (optionally followed by And for more preconditions) and **one or more Then steps** (optionally followed by And for more assertions). So: 1–n Given (+ And), one When, 1–n Then (+ And).

**Example:**

```gherkin
Scenario: Check if service report proper readiness state
  Given The system is in default state
   When I access endpoint "readiness" using HTTP GET method
   Then The status code of the response is 200
    And The body of the response is the following
        """
        {"ready": true, "reason": "All providers are healthy", "providers": []}
        """
```

Here, **Given** sets state, **When** performs the HTTP call, **Then** and **And** state the assertions.

### Literals and special syntax

| Syntax | Meaning | Example |
|--------|---------|--------|
| **Doc string** | Multi-line argument to the step (between `"""`). Often JSON request or expected body. | Request body: `"""` … `"""` |
| **Data table** | Table of values (header row, then rows). The step receives it as `context.table`. | `\| Fragments in LLM response \|` then `\| ask \|` |
| **Placeholders** | `{MODEL}` and `{PROVIDER}` in doc strings are replaced with `context.default_model` and `context.default_provider` by the steps. | `"model": "{MODEL}", "provider": "{PROVIDER}"` |
| **Step argument** | Quoted or unquoted text in the step line. Matches capture groups in the step definition. | `I use "query" to ask question` → endpoint `"query"`; `I access endpoint "readiness"` → `"readiness"`. |

### Tags and comments

| Syntax | Meaning | Example |
|--------|---------|--------|
| **@tag** | Tag for filtering or hooks. Above Feature (applies to all scenarios) or above Scenario (that scenario only). | `@Authorized`, `@skip`, `@skip-in-library-mode` |
| **# comment** | Gherkin comment. Ignored by Behave. Use to explain why a scenario is skipped or to document a scenario. | `# Only in server mode` above a scenario |

### Summary

- **Feature** = what is under test (e.g. "Query endpoint API tests").
- **Background** = shared setup for every scenario in the file.
- **Scenario** = one test case.
- **Given** = preconditions; **When** = action; **Then** / **And** = expectations.
- Doc strings (`"""`) = multi-line JSON or text; tables (`|...|`) = structured data for the step.
- Placeholders `{MODEL}` and `{PROVIDER}` are filled from context by the step code.
- Tags (`@...`) drive skipping and hooks; comments (`#`) are for humans.

---

## Writing New Scenarios

1. **Choose or add a feature file** under `tests/e2e/features/` and use existing steps where possible. If you add a new file, **add it to `tests/e2e/test_list.txt`** so the suite runs it. 
2. **Use tags** for mode-dependent or config-dependent behavior (`@skip-in-library-mode`, `@Authorized`, etc.). **Adding a tag that switches configuration** (e.g. a new feature-level or scenario-level config) usually means you must also add or change a **Lightspeed Stack config** file under `configuration/server-mode/` or `library-mode/` and wire the tag in `environment.py` (e.g. in `before_feature` / `after_feature` or `before_scenario` / `after_scenario`) so the config is applied and the container restarted when the tag is active.
3. **Use placeholders** `{MODEL}` and `{PROVIDER}` in request bodies so the same scenario works with different backends.
4. **Add step definitions** in the appropriate `features/steps/*.py` if you need new steps; reuse `context` for host, port, auth, and responses.
5. **Optional**: If the scenario needs a dedicated config, add a new YAML under `configuration/server-mode/` (and optionally `library-mode/`), add an entry to `_CONFIG_PATHS` in `environment.py`, and handle the tag in the before/after hooks so the config is switched and the lightspeed-stack container is restarted.
6. **Run** with `uv run make test-e2e` or a targeted `behave` command; exclude `@skip` with `--tags=-skip` if needed.

---

## Troubleshooting

- **503 or "Unable to connect to Llama Stack"**: In server mode, ensure the Llama Stack container is running and healthy. After a scenario that disrupts Llama Stack, `after_scenario` restores it; if restore fails, check diagnostics (see `_print_llama_stack_diagnostics` in `environment.py` if present) and container logs.
- **"Container state improper" / restart fails**: Usually the llama-stack container is in a bad state. Ensure it is started (or recreated) before restarting lightspeed-stack; see Docker/Podman and compose usage in the project.
- **Readonly database (SQLite) in Llama Stack**: If the RAG KV DB is on a bind-mounted path that becomes read-only (e.g. after restart), move it to a named volume (e.g. via `KV_RAG_PATH` in docker-compose) so writes succeed.
- **ChunkedEncodingError on streaming_query**: The step for streaming_query uses `stream=True` and consumes the stream; if you add new streaming steps, avoid reading the full response with `response.content` and use the same stream-reading pattern so a server close after an error event does not raise.
- **Event loop is closed (httpx/AsyncClient)**: In E2E, any code that creates an `AsyncLlamaStackClient` (e.g. for shields) must close it (e.g. `await client.close()`) in a `finally` block before the event loop is torn down (e.g. before `asyncio.run()` returns).
- **Scenarios skipped**: Check tags (`@skip`, `@skip-in-library-mode`, `@local`) and `E2E_DEPLOYMENT_MODE`; ensure the scenario is not excluded by `--tags=-skip` (or the opposite if you intend to run only skipped scenarios for debugging).

For more on test structure and commands, see the main project guide (`CLAUDE.md`) and `tests/e2e/features/steps/README.md`.
