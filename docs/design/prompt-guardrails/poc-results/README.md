# Prompt Guardrails PoC — results (LCORE-2657)

This directory validates the **LCS-native guardrails layer** (spike
Decision S1) against a real Granite Guardian model. Read the files in
order; each stands alone.

| File | What it shows |
|------|---------------|
| `01-guardian-probe-results.md` | Real Guardian gives correct verdicts for OOTB and custom (BYOC) risks — the core model-behavior question (6/6). |
| `02-layer-run.json` | Raw output of the actual `src/guardrails/` runner against real Guardian, all three points. |
| `03-layer-findings.md` | Two design findings from the layer run (custom risks must be safety-shaped; output-relevance needs context pairing) + latency. |
| `04-full-stack-e2e.md` | End-to-end through the real FastAPI stack: the input hook fires, a block returns the refusal, metric increments, layers coexist. |
| `05-e2e-log-evidence.md` | Raw lightspeed-stack log lines behind `04`. |
| `06-threshold-scores.md` | **Read this one.** Confidence scores via logprobs (validates per-rule thresholds) *and* the domain false-positive problem that thresholds cannot solve. |

## What the PoC proves

1. Risk selection via the guardian chat template (system slot), including
   custom bring-your-own-criteria definitions, produces correct verdicts
   from a real Granite Guardian (`01`).
2. The `src/guardrails/` layer runs multiple rules per point in parallel
   and aggregates verdicts correctly across input / output / tool_content
   (`02`).
3. The layer integrates into `query.py` at the existing moderation seam:
   a block flows through the real HTTP stack as a refusal with the
   validation-error metric, coexisting additively with the pre-existing
   llama-stack shields (`04`).
4. Per-rule confidence thresholds are implementable via `logprobs` on the
   Guardian call (`06`).

## What the PoC disproved

The assumption that out-of-the-box guardian risks are a safe default.
`jailbreak` flags legitimate OpenShift questions at ~0.98 — as high as
real jailbreaks — so custom domain-tuned definitions are required to
ship, and thresholds are not the remedy (`06`). Measured on the 2B model;
**re-run on the production 8B model before treating as final.**

## How the PoC diverges from the production design

- Activated by the `LCS_GUARDRAILS_POC_CONFIG` env var, not the
  `guardrails:` config section (keeps the throwaway out of `Configuration`
  / OpenAPI).
- One detector backend (`granite_guardian`); no `openai_moderations` /
  `llama_stack_shields` backends.
- Output check is non-streaming only; no streaming checkpoints
  (Decision T4).
- tool_content is a post-hoc check on collected tool results, not the
  agent-loop gating capability (Decision T5 option B, not A).
- 2B guardian on CPU for feasibility; production is 3.3-8B/4.1-8B on GPU.

## Reproduce

```sh
# 1. Guardian model (Ollama >= 0.4 required; 0.3.x cannot load it)
ollama pull granite3-guardian:2b
ollama serve &

# 2. Layer-level run (no full stack needed)
LCS_GUARDRAILS_POC_CONFIG=docs/design/prompt-guardrails/poc-results/guardrails-poc.yaml \
  PYTHONPATH=src uv run python docs/design/prompt-guardrails/poc-results/drive_layer.py

# 3. Full stack (see meta/docs/local-stack-testing.md for service startup)
#    Start Llama Stack (run-ci.yaml) then:
LCS_GUARDRAILS_POC_CONFIG=docs/design/prompt-guardrails/poc-results/guardrails-poc.yaml \
  uv run src/lightspeed_stack.py -c docs/design/prompt-guardrails/poc-results/lcs-poc-config.yaml
#    Then POST /v1/query with {"query":"...","shield_ids":[]} to isolate the
#    guardrails layer from the run-ci.yaml llama-guard shield.
```

## Unit tests

`tests/unit/guardrails/` (17 tests): verdict parsing, risk/definition
selection, point filtering, parallel execution, blocking vs advisory,
config loading. `uv run pytest tests/unit/guardrails/ -q`.
