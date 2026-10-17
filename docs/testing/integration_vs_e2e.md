# Integration tests and end-to-end tests

This repository has three test layers. A test belongs in the lowest layer that can still fail when the behavior breaks.

| | Unit | Integration | End to end |
|---|---|---|---|
| Where | `tests/unit/` | `tests/integration/` | `tests/e2e/` |
| How | pytest, one function or class | pytest, several real components in-process | behave, a separate process from the service |
| Real | the code under test | config loading, SQLite, auth, pipelines, repo CLIs | a deployed stack (Docker Compose locally, OpenShift in Prow) |
| Fake | every collaborator | external services only (OGX, LLM providers) | nothing inside the service; the test sees public surfaces |
| May import `src/` | yes | yes | no |
| Run | `make test-unit` (60% coverage) | `make test-integration` (10% coverage) | `make test-e2e` (no coverage gate) |
| Cost | seconds | seconds | minutes, needs containers |

Integration calls Python. It imports a handler or runs `src/lightspeed_stack.py` as a subprocess. The database and YAML config are real. The OGX client is a mock. `TestClient` against the FastAPI app is still integration: same process, no container.

End to end calls the deployed service. A scenario sends HTTP, restarts a container, or reads `docker logs`. Step definitions under `tests/e2e/features/steps/` must not import, call, or shell out to anything under `src/`. If a scenario needs a generated file, commit the file and guard the generator with an integration test.

The check: could this scenario run unchanged against a container image, with no source checkout on the machine? If yes, it is end to end. If it needs `src/lightspeed_stack.py`, `src/ogx_configuration.py`, or any import of the service, it is integration.

| Looks like | It is |
|---|---|
| `TestClient` GET `/openapi.json` inside pytest | integration |
| `subprocess` of `src/lightspeed_stack.py --migrate-config` | integration |
| `requests` against a container the test just started | end to end |
| `docker logs` / `docker restart` | end to end |
| Status code and response schema | either; the subject decides the layer |
| A word the model happened to write | a flaky end-to-end test |

## Good integration tests

These keep several real components and stub only the external service.

| File | What it proves |
|---|---|
| `tests/integration/endpoints/test_responses_integration.py` | `responses_endpoint_handler` plus the real SQLite session. The check that matters is the conversation row (owner, model, provider, turn), not the response object. |
| `tests/integration/test_unified_synthesis.py` | Real YAML through `AppConfig.load_configuration` and `synthesize_to_file`: baseline selection, enrichment, parity with the legacy path. No port, no Docker. |
| `tests/integration/test_unified_mode_cli.py` | `src/lightspeed_stack.py --dump-configuration` and `--migrate-config` as a subprocess: exit code, message, file mode. This is how operators and the container entrypoint invoke the script. |
| `tests/integration/test_otel_trace_propagation.py` | A W3C `traceparent` through `query_endpoint_handler`. Spans from more than one component share a trace id. An in-memory exporter is enough. |

## Good end-to-end tests

These fail only when the running stack is wrong, and they look at surfaces a caller outside the repo can see.

| File | What it proves |
|---|---|
| `tests/e2e/features/health.feature`, `smoketests.feature` | The local service is up. Status, schema, and — for health — an exact JSON body the service produces, not a model. |
| `tests/e2e/features/unified-mode-boot.feature` | A unified-mode YAML, a container restart, then `readiness` and `query` return 200. It does not inspect the synthesized file. |
| `tests/e2e/features/unified-mode-synthesis.feature` | After restart, container logs contain the synthesized path (`docker inspect` / `docker logs` in `tests/e2e/features/steps/unified_mode.py`). Synthesis rules stay in `test_unified_synthesis.py`. |
| `tests/e2e/features/ogx_disrupted.feature`, `degraded_mode_startup.feature` | OGX is actually stopped. HTTP then shows 503, readiness `unhealthy`, or `ls_started_in_degraded_mode`. Mocking `ApiException` in `test_info_integration.py` covers the handler branch; it does not cover restart order. |
| `tests/e2e/features/unified-mode-migration.feature` | The stack boots from the committed `lightspeed-stack-unified-migrated.yaml`. The scenario does not run `--migrate-config`. `test_unified_mode_cli.py` guards that fixture against drift. |

## Poor fits

These tests check something true. They sit in the wrong layer, or they assert something the layer cannot keep stable.

| File | What is wrong |
|---|---|
| `tests/integration/endpoints/test_authorized_endpoint.py` | Loads `test_config`, discards it, calls one handler, compares the result to noop-auth constants. No second component. That is a unit test. |
| `test_health_liveness` in `tests/integration/endpoints/test_health_integration.py` | Same shape: unused config fixture, assertion is `response.alive is True`. Liveness does not consult OGX. The other tests in that file, which map stubbed provider health into the readiness payload, are real integration tests. |
| `tests/integration/test_version.py` | Compares `version.__version__` with `pdm show --version`. No config, database, or handler. The repo runs tests with `uv`, not `pdm`. |
| `tests/integration/container_lifecycle/test_container_lifecycle.py` | Builds an image, polls `http://localhost:8321/v1/health`, and `exec`s into the container. That is a deployed stack, collected by `make test-integration`, and one function does build, start, probe, mounts, and cleanup. The behave suite never runs it. |
| `tests/unit/app/endpoints/test_info.py` and `tests/integration/endpoints/test_info_integration.py` | Both call `info_endpoint_handler` with a mocked OGX version. The integration test earns its place: it reads `name` (`"foo bar baz"`) from `tests/configuration/lightspeed-stack.yaml` and uses the real noop auth fixture. The unit happy path only asserts `response.name is not None`. |
| `@flaky` scenarios in `tests/e2e/features/query.feature` (also `streaming_query.feature`, `mcp.feature`, parts of `responses.feature`) | The reply must contain `"ask"`, `"checkout"`, or `"image"`. The contract is status 200 and token counters. The extra word depends on the model. |

`tests/e2e/features/conversation-compaction.feature` also matches response fragments, and that use holds. The scenario plants names (`north-quarry`, `blue-lagoon`) and later asks for them. The fragment is a value the test wrote. Stable end-to-end assertions are status, schema, `context_status`, metrics, and planted facts.

## Where a new test goes

1. One function's branch: unit test, collaborators mocked.
2. A wrong database row, merged config, span parent, or CLI exit code: integration test. Use `test_config`, `test_db_session`, `mock_ogx_client`, and `mock_conversation_store` from `tests/integration/conftest.py`.
3. A container that does not become ready, a missing log line after restart, or a 503 only when the OGX process is gone: behave scenario. Reuse steps. Do not import `src/`.
4. A scenario that needs a generated file: commit the file, and add an integration test that fails when regeneration would change it.
5. Assert the contract. Tag model-wording checks so the default run does not depend on them.

How to run each layer is in [testing.md](testing.md). Scenario tags, deployment modes, and hooks are in [e2e_testing.md](e2e_testing.md). Integration fixtures are in [tests/integration/README.md](../../tests/integration/README.md).
