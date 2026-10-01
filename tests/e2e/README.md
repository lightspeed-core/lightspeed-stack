# E2E Tests

End-to-end tests for the Lightspeed Core Stack REST API (Behave, Gherkin).

**Full guide:** [docs/testing/e2e_testing.md](../../docs/testing/e2e_testing.md) — how to run, environment variables, deployment modes, tags and hooks, Gherkin keywords, configuration, and troubleshooting.

**Granite Guardian locally:** CI uses `mock-guardian`. To point
`shields_granite_guardian.feature` at the real model, see
[Granite Guardian: mock (CI) vs real model (local)](../../docs/testing/e2e_testing.md#granite-guardian-mock-ci-vs-real-model-local).

* Tests: `tests/e2e/features/*.feature`
* Step definitions: `tests/e2e/features/steps/`
* Feature list (run order): `test_list.txt`

**Not sure a scenario is e2e?** Steps must never touch `src/`; validation, migration and synthesis live in `tests/integration/`. See [Choosing the Test Layer](../../docs/testing/e2e_testing.md#choosing-the-test-layer-e2e-or-integration).
