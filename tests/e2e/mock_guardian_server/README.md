# Mock Granite Guardian server

Stdlib-only OpenAI-compatible stand-in for the granite_guardian e2e shield.

It serves `/v1/chat/completions` with the logprobs shape required by
`pydantic_ai_lightspeed.capabilities.granite_guardian`. Jailbreak-style user
prompts are scored risky; everything else is scored safe.

**CI uses this mock.** To run the same scenarios against the real Granite
Guardian model locally, see
[Granite Guardian: mock (CI) vs real model (local)](../../../docs/testing/e2e_testing.md#granite-guardian-mock-ci-vs-real-model-local).

## Running

```bash
python server.py [port]   # default port 8001
```

In E2E it runs as the `mock-guardian` Docker Compose service on
`lightspeednet`. `lightspeed-stack` waits for it to become healthy, and
shield YAML uses `http://${env.E2E_GUARDIAN_HOSTNAME:=mock-guardian}:8001/v1`.
