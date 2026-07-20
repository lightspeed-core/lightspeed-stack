# Spike for Prompt Guardrails (LCORE-230)

Spike ticket: [LCORE-2657](https://redhat.atlassian.net/browse/LCORE-2657)
Feature ticket: [LCORE-230](https://redhat.atlassian.net/browse/LCORE-230)
Spec doc: [prompt-guardrails.md](prompt-guardrails.md)

## Overview

**The problem**: LCORE-230 asks for optional prompt guardrails — safety-tuned
LLM checks on prompts and answers (prompt injection is OWASP LLM risk #1) —
configurable via the lightspeed-stack config file. Input-side moderation
already exists (Llama Stack shields via the Moderations API), but there is no
output-side moderation, no lightspeed-stack-side configuration surface, no
support for Granite Guardian or custom risk definitions, and the current
mechanism is bound to a Llama Stack API surface that upstream has already
deleted (OGX 1.x removed the entire Safety API). Ask Red Hat's migration to
Lightspeed Core is blocked on parity with their existing Granite
Guardian-based guardrails ([LCORE-2253](https://redhat.atlassian.net/browse/LCORE-2253)).

**The recommendation**: build an **LCS-native guardrails layer** — a
lightspeed-stack-owned module that invokes guardian models through any
OpenAI-compatible endpoint, with pluggable detector backends (Granite
Guardian chat-template adapter, generic OpenAI-moderations endpoint, and a
transitional bridge to today's Llama Stack shields). Guardrail *points*
(`input` / `output` / `tool_content`) are first-class in the config schema.
Recommended guardian model: **IBM Granite Guardian** (Apache 2.0). See
[Decision S1](#decision-s1-where-the-guardrails-engine-lives),
[S2](#decision-s2-guardrail-points-in-scope),
[S3](#decision-s3-recommended-guardian-model).

**PoC validation**: Validated the LCS-native layer against real IBM
Granite Guardian (`granite3-guardian:2b`, Ollama, CPU) — end-to-end
through the full local stack. Custom bring-your-own-criteria risks work;
the input hook blocks through real HTTP with the validation-error metric;
the new layer coexists additively with the existing llama-stack shields.
Two design-shaping findings (custom risks must be safety-shaped;
output-relevance needs context pairing). See [PoC results](#poc-results)
and `poc-results/` (removed before merge).

## Strategic decisions — reviewer: @sbunciak

High-level decisions that determine scope, approach, and cost. Each has a
recommendation — please confirm or override.

### Decision S1: Where the guardrails engine lives

Today's input moderation calls Llama Stack's Moderations API per registered
shield ([background](#current-state-in-lightspeed-stack)). Upstream Llama
Stack (now OGX) deleted that entire API surface in 1.x
([background](#upstream-trajectory-llama-stack--ogx-1x)), and the team plans
to reduce Llama Stack to an inference provider
([LCORE-1099](https://redhat.atlassian.net/browse/LCORE-1099)). Ask Red Hat's
production guardrails bypass Llama Stack safety entirely — they call Granite
Guardian on vLLM through a plain OpenAI client
([background](#ask-red-hat-baseline)).

| Option | Description |
|--------|-------------|
| A — Extend the Llama Stack shields path | Add output-side `moderations.create` calls next to the existing input call. Smallest delta; dies with OGX 1.x; cannot express Guardian custom risks. |
| B — Responses API `guardrails=` parameter | Delegate enforcement to llama-stack (0.6.0 runs input+output checks internally). Least code; deepest coupling; loses LCS pre-flight control (RAG skip, blocked-turn persistence); no custom risks; parameter shape changes again in OGX 1.x. |
| C — LCS-native guardrails layer | lightspeed-stack owns detection: pluggable detector backends called via OpenAI-compatible endpoints; guardrail points and risk definitions configured in the LCS config file. Survives OGX 1.x and the Llama Stack phase-out; reproduces the Ask RH pattern. |
| D — TrustyAI FMS Guardrails Orchestrator | Delegate detection to the RHOAI guardrails stack. Productized, but a heavy infrastructure dependency for an optional LCS feature; its llama-stack provider requires the 0.x Safety API. |

**Recommendation**: **C** — LCS-native layer with pluggable detector
backends. Ship three backends: `granite_guardian` (chat-template invocation,
custom risks), `openai_moderations` (any OpenAI-compatible `/v1/moderations`
endpoint — this also covers OGX 1.x's `moderation_endpoint` services and
TrustyAI gateways, making D a *deployment choice*, not an architecture), and
`llama_stack_shields` (transitional bridge wrapping today's behavior).
The existing input-moderation path keeps working unchanged during the
transition (see [S5](#decision-s5-fate-of-the-existing-shields-moderation-path)).

**Confidence**: 80%

### Decision S2: Guardrail points in scope

The feature must define *where* checks run. Ask RH needs input screening and
output relevance checks. OWASP LLM01 additionally prescribes screening
third-party content entering the context (RAG chunks, MCP tool outputs) —
the *indirect* prompt-injection vector — which upstream OGX explicitly
declined to cover (a differentiation opportunity, and LCS's MCP surface is
growing: [LCORE-231](https://redhat.atlassian.net/browse/LCORE-231)).

| Option | Description |
|--------|-------------|
| A — Input + output only | Ask RH parity; leanest epic; indirect injection unaddressed. |
| B — Input + output, tool-content as follow-up | Same epic scope as A, but the config schema treats the point as first-class and a named follow-up JIRA covers tool content. |
| C — Input + output + tool-content, all in epic | Complete OWASP posture in one epic; commits to per-tool-call moderation latency being manageable. |

**Recommendation**: **C** — all three points in the epic (spike-author
decision). Mitigations for the latency commitment: rules bind to points
explicitly (a rule only runs where configured), tool-content rules default
to none, and the PoC measures per-check latency to inform defaults. If
reviewers find the tool-content latency budget unacceptable, the fallback
is option B: the tool-content ticket moves out of the epic unchanged — the
architecture is identical in both options.

**Confidence**: 70%

### Decision S3: Recommended guardian model

LCORE-230 explicitly asks to "recommend the best suited open source guardian
model". Landscape details in
[background](#guardian-model-landscape).

| Option | Description |
|--------|-------------|
| A — IBM Granite Guardian (3.3-8B / 4.1-8B) | Apache 2.0. Jailbreak + harm categories + RAG relevance triad + custom criteria (BYOC) in one model. GuardBench leader. In production for Ask RH today. |
| B — Meta Llama Guard 4 | Strong MLCommons-taxonomy content safety; no custom risks, no RAG checks; gated Llama community license. |
| C — Meta Prompt Guard 2 (22M/86M) | Excellent cheap injection/jailbreak classifier; not a content-safety model; gated Llama license. |

**Recommendation**: **A** — Granite Guardian: 4.1-8B as the forward
recommendation, 3.3-8B as the production-validated reference (Ask RH).
Document Prompt Guard 2 as an *optional* low-latency pre-filter for
deployments whose license posture allows it; do not make it the default.

**Confidence**: 90%

### Decision S4: Fate of LCORE-2710 ("AskRedHat Custom Guardrails" Epic)

[LCORE-2710](https://redhat.atlassian.net/browse/LCORE-2710) is an empty
Epic under LCORE-230. Stefan's comment on it steers exactly where this spike
landed: guardrails should be generally applicable; product-specific risk
configuration belongs to product teams. The custom-risk mechanism in the
proposed design (per-rule `definition`, the Guardian BYOC pattern) *is* the
generic answer to "custom guardrails".

| Option | Description |
|--------|-------------|
| A — Close LCORE-2710 as superseded | The Epic(s) proposed by this spike cover the need; Ask RH's specific risk definitions become *their* config, not our code. |
| B — Repurpose LCORE-2710 | Rename/respecify it as the implementation Epic for this feature. |

**Recommendation**: **A** — close as superseded by the Epic proposed here,
with a comment pointing at the spec doc's custom-risk configuration section.
Needs @sbunciak's call (his Epic).

**Confidence**: 75%

### Decision S5: Fate of the existing shields moderation path

Input moderation via Llama Stack shields is live on four endpoints today,
with `shield_ids` request-override semantics documented in `docs/responses.md`.

| Option | Description |
|--------|-------------|
| A — Keep unchanged during transition | New layer is additive; existing shields keep working; deprecate the shields path only when OGX 1.x migration (LCORE-1099) forces it. |
| B — Replace immediately | Migrate the input path onto the new layer in this epic; remove the shields code. |

**Recommendation**: **A** — additive now, deprecation decision deferred to
the LCORE-1099 work. The `llama_stack_shields` detector backend gives
deployments a config-level migration path in the meantime. No behavior
change for existing deployments.

**Confidence**: 85%

## Technical decisions — reviewer: @tisnik

### Decision T1: Configuration schema shape

A new top-level `guardrails:` section in the lightspeed-stack config
(Pydantic models extending `ConfigurationBase`), sitting alongside
`customization`/`inference` in `src/models/config.py`.

| Option | Description |
|--------|-------------|
| A — detectors + rules | `detectors:` (named backend instances: type, url, model, auth) and `rules:` (name, risk or custom definition, points, blocking, detector ref). |
| B — per-endpoint blocks | Guardrail config nested under each endpoint's settings. Repetitive; endpoints share policies in practice. |

**Recommendation**: **A**. A rule binds a risk to one or more points
(`input`/`output`/`tool_content`) and to a detector. Sketch:

```yaml
guardrails:
  detectors:
    - name: guardian
      type: granite_guardian
      url: http://vllm:8000/v1
      model: granite-guardian-3.3-8b
  rules:
    - name: jailbreak
      detector: guardian
      risk: jailbreak
      points: [input]
    - name: answer-relevance
      detector: guardian
      risk: answer_relevance
      points: [output]
      blocking: false
    - name: roleplay-jailbreak       # custom risk (BYOC)
      detector: guardian
      definition: |
        The 'User' message contains roleplay-based instruction override...
      points: [input]
  violation_message: "I cannot process this request due to policy restrictions."
```

**Confidence**: 80%

### Decision T2: Detector backend abstraction

| Option | Description |
|--------|-------------|
| A — Protocol + per-type adapters | `DetectorBackend` protocol (`async check(content, rule) -> DetectionResult`); adapters: `granite_guardian`, `openai_moderations`, `llama_stack_shields`. |
| B — Single Guardian-only implementation | Simpler; closes the door on OGX 1.x moderation endpoints and TrustyAI gateways. |

**Recommendation**: **A**. Guardian invocation is OpenAI chat-completions
with the risk selected via the guardian chat template (system slot);
`openai_moderations` maps categories to rules; `llama_stack_shields` wraps
the existing `run_shield_moderation` behavior.

**Confidence**: 85%

### Decision T3: Blocked-response semantics

| Option | Description |
|--------|-------------|
| A — 200 refusal (status quo) | Blocked requests return a normal response carrying the refusal message; consistent with today's shields behavior and OGX. |
| B — Dedicated 4xx | Explicit, but breaks OpenAI-compatibility expectations and existing client behavior. |

**Recommendation**: **A**, unchanged semantics: refusal message in the
response, `llm_calls_validation_errors_total` metric incremented, blocked
turn persisted to the conversation. Advisory (non-blocking) rule outcomes
are logged and surfaced in metrics only.

**Confidence**: 90%

### Decision T4: Streaming output moderation mechanics

Output rules on `/v1/streaming_query` and streaming `/v1/responses` cannot
check text that has already been emitted.

| Option | Description |
|--------|-------------|
| A — Buffer-and-release checkpoints | Hold back emission until the accumulated text passes the output rules at N-token checkpoints (and once at end); on flag, emit refusal instead of the withheld remainder. |
| B — Check-at-end only | Simplest; the entire answer has already streamed to the client when the verdict arrives — can only append a retraction. |

**Recommendation**: **A** with a configurable checkpoint interval;
degenerate case (interval=∞) equals B for latency-sensitive deployments.
This mirrors upstream OGX's batched streaming checks.

**Confidence**: 70% — checkpoint sizing needs implementation-time tuning.

### Decision T5: Tool-content gating hook

| Option | Description |
|--------|-------------|
| A — pydantic-ai capability hook | Run tool-content rules on each tool result before it re-enters the agent loop (the existing capability mechanism: `wrap_run`-style interception). True gating. |
| B — Post-hoc check on collected tool_results | Runs once after the turn; detects but cannot prevent the model having already consumed the content. |

**Recommendation**: **A** for the production design (B is what the PoC
demonstrates). The capability mechanism is already how the inert
question-validity/redaction features hook the agent loop — same seam,
llama-stack-independent.

**Confidence**: 75%

### Decision T6: Failure posture when the detector is unreachable

| Option | Description |
|--------|-------------|
| A — Fail-closed default, configurable | Detector error ⇒ request blocked (as OGX chose), with `on_detector_error: block|allow` per deployment. |
| B — Fail-open | Availability over safety; silently drops protection exactly when under load. |

**Recommendation**: **A**. A guardrailed deployment that silently loses its
guardrails is worse than a refused request; deployments that disagree flip
the config.

**Confidence**: 85%

### Decision T7: Relationship to the inert pydantic-ai safety capabilities

`QuestionValidity` and `PiiRedactionCapability` exist, unwired.

| Option | Description |
|--------|-------------|
| A — Same hook mechanism, separate features | Guardrails use the capability seam; wiring question-validity/redaction into `Configuration` stays out of scope. |
| B — Unify into one safety framework now | One "policy" config covering guardrails + validity + redaction; larger blast radius, blocks on unrelated decisions. |

**Recommendation**: **A**, with the config schema leaving room (top-level
`guardrails:` doesn't preclude sibling sections later).

**Confidence**: 80%

## Out of scope

- **OGX 1.x migration mechanics** — how lightspeed-stack consumes OGX 1.x
  is [LCORE-1099](https://redhat.atlassian.net/browse/LCORE-1099)'s scope;
  this design only ensures guardrails don't depend on APIs deleted there.
- **Wiring the question-validity and PII-redaction capabilities** — same
  hook mechanism, separate feature (Decision T7); needs its own
  prioritization.
- **Non-text modalities** (image safety) — no current LCS use case.
- **Per-user / per-conversation guardrail policies** — config is
  deployment-level; RBAC-scoped policies would need a design of their own.
- **Guardian model fine-tuning / threshold calibration guidance** — Ask RH
  tunes thresholds for their product; we document the mechanism, not the
  values.
- **Moderation of stored conversation history on retrieval** — only new
  turns are guarded.

## Proposed JIRAs

### Epic: Prompt guardrails for Lightspeed Core

LCS-native prompt guardrails: a lightspeed-stack-owned guardrails layer
invoking guardian models via OpenAI-compatible endpoints, configured in the
lightspeed-stack config file, covering input, output, and tool-content
guardrail points (LCORE-230).

**Goals**:
- Deployers can enable input/output/tool-content guardrails purely via the
  LCS config file, with out-of-the-box and custom (BYOC) risk definitions.
- Granite Guardian is supported and documented as the recommended model;
  any OpenAI-compatible moderations endpoint works as an alternative
  detector.
- Guardrails survive the Llama Stack → OGX 1.x transition unchanged.
- Ask Red Hat's guardrails usage (parallel multi-risk input screening,
  output relevance checks, custom risks) is reproducible on Lightspeed
  Core.

**Scope**:
- In: detector framework + Granite Guardian and OpenAI-moderations
  backends, `guardrails:` config section, all three guardrail points,
  streaming semantics, docs + configuration example, integration/e2e tests.
- Out: see the spike doc's Out-of-scope section.

**Success criteria**:
- A documented config example yields: injection prompt blocked at input,
  unsafe answer blocked at output, poisoned tool result blocked before the
  model consumes it — each observable via API behavior and metrics.

<!-- type: Story -->
<!-- key: LCORE-???? -->
#### LCORE-???? E2E feature files for prompt guardrails (no step implementation)

**User story**: As a Lightspeed Core e2e engineer, I want the behave
feature files for prompt-guardrails scenarios written before the feature
implementation lands, so that the test shape reflects the feature's
intended behavior rather than the chosen implementation, and any
architectural gaps surface early.

**Description**: Author behave `.feature` files under `tests/e2e/features/`
describing guardrails behaviors: input block (OOTB risk), input block
(custom risk definition), output advisory rule (non-blocking), output
blocking rule, tool-content block, guardrails disabled (no interference),
detector unreachable (fail-closed), streaming refusal semantics. Step
definitions are explicitly **not** part of this ticket — they are covered
by a later sibling ticket (LCORE-????).

**Scope**:
- `.feature` files covering R1..Rn from the spec doc
- Additions to `tests/e2e/test_list.txt`
- Author from spec doc requirements only; do not read implementation code

**Acceptance criteria**:
- behave parses every new `.feature` file without syntax errors
- behave marks all new scenario steps as `undefined`
- `uv run make test-e2e` remains green (new scenarios skipped/undefined, not failing)

**Blocks**: LCORE-???? (step-definitions counterpart)

**Agentic tool instruction**:

```text
Read "Requirements" and "Acceptance test surface" in
docs/design/prompt-guardrails/prompt-guardrails.md.
Do NOT read other JIRAs' scope sections or the implementation code while
authoring; the point of this ticket is feature files uncontaminated by
implementation detail.
Key files to create: tests/e2e/features/prompt-guardrails-*.feature plus
additions to tests/e2e/test_list.txt. Do NOT create step definitions.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Implement behave step definitions for prompt-guardrails feature files

**Description**: Implement Python step definitions under
`tests/e2e/features/steps/` for the `.feature` files authored in
LCORE-???? (kickoff). Take the Gherkin as-is; if a scenario cannot be
implemented faithfully, raise it against the spec doc rather than quietly
weakening the test. Requires a guardian-model stand-in the CI environment
can run (mock detector endpoint or a small real model — decide against the
spec doc's test-pattern section).

**Blocked by**:
- LCORE-???? (E2E feature files kickoff)
- LCORE-???? (guardrails config + detector framework)
- LCORE-???? (input point), LCORE-???? (output point), LCORE-???? (tool content)

**Agentic tool instruction**:

```text
Read "Architecture" and "Requirements" in
docs/design/prompt-guardrails/prompt-guardrails.md.
Take feature files from tests/e2e/features/prompt-guardrails-*.feature
as-is; do not modify Gherkin to accommodate implementation constraints.
To verify: `uv run make test-e2e` runs every new scenario green.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Guardrails configuration schema and detector framework

**Description**: Add the top-level `guardrails:` config section (Pydantic
models per Decision T1) and the `DetectorBackend` protocol with the
`granite_guardian` and `openai_moderations` backends (Decision T2),
including parallel rule execution, timeouts, and the fail-closed error
posture (Decision T6). No endpoint wiring yet.

**Scope**:
- `src/models/config.py` (`guardrails:` section) + config docs regeneration
- New `src/guardrails/` package: models, protocol, backends, runner
- Unit tests for schema validation, rule/point selection, parallel
  execution, verdict aggregation, error posture

**Acceptance criteria**:
- Config examples validate; unknown fields rejected (`extra="forbid"`)
- Unit tests cover both backends against mocked endpoints
- `uv run make verify` green; `docs/openapi.json` regenerated

**Agentic tool instruction**:

```text
Read "Architecture > Configuration" and "Architecture > Detector backends"
in docs/design/prompt-guardrails/prompt-guardrails.md.
Key files: src/models/config.py, src/guardrails/, tests/unit/guardrails/.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Input guardrail point on all query endpoints

**Description**: Run configured `input` rules on the moderation input in
`/v1/query`, `/v1/streaming_query`, `/v1/responses`, and `/rlsapi`,
feeding the existing moderation-result seam (blocked ⇒ refusal response,
RAG skip, blocked-turn persistence, validation-error metric), additive to
the existing Llama Stack shields path (Decision S5).

**Blocked by**: LCORE-???? (config + detector framework)

**Acceptance criteria**:
- Input rules run in parallel with per-rule latency logged/metered
- Blocked behavior byte-compatible with today's shields refusals
- Unit + integration tests for pass/block/advisory outcomes

**Agentic tool instruction**:

```text
Read "Architecture > Request lifecycle integration" in
docs/design/prompt-guardrails/prompt-guardrails.md.
Key files: src/app/endpoints/query.py, streaming_query.py, responses.py,
rlsapi_v1.py, src/utils/shields.py, src/guardrails/.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Output guardrail point with streaming checkpoint semantics

**Description**: Run configured `output` rules on generated answers before
they reach the client: non-streaming (single check) and streaming
(buffer-and-release checkpoints per Decision T4). Advisory rules record
metrics without blocking (relevance checks per the Ask RH pattern).

**Blocked by**: LCORE-???? (config + detector framework)

**Acceptance criteria**:
- Non-streaming: flagged blocking rule replaces the answer with the refusal
- Streaming: flagged checkpoint suppresses withheld text and emits refusal
- Advisory rules never alter the response; outcomes visible in metrics

**Agentic tool instruction**:

```text
Read "Architecture > Request lifecycle integration" and "Architecture >
Streaming semantics" in docs/design/prompt-guardrails/prompt-guardrails.md.
Key files: src/utils/agents/query.py, src/utils/agents/streaming.py,
src/utils/streaming_sse.py, src/guardrails/.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Tool-content guardrail point via agent-loop hook

**Description**: Run configured `tool_content` rules on each tool/MCP
result before it re-enters the agent context (pydantic-ai capability hook
per Decision T5), blocking poisoned third-party content (indirect prompt
injection, OWASP LLM01).

**Blocked by**: LCORE-???? (config + detector framework)

**Acceptance criteria**:
- Flagged tool result never reaches the model; turn continues or refuses
  per rule's blocking flag
- Latency: per-tool-call overhead measured and documented
- Integration test with a mock MCP server returning injected content

**Agentic tool instruction**:

```text
Read "Architecture > Tool-content gating" in
docs/design/prompt-guardrails/prompt-guardrails.md.
Key files: src/pydantic_ai_lightspeed/capabilities/, src/utils/pydantic_ai_helpers.py,
src/guardrails/, dev-tools/mcp-mock-server/.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
#### LCORE-???? Integration tests for the guardrails layer

**Description**: pytest integration tests exercising the guardrails layer
against a scripted OpenAI-compatible mock detector: multi-rule parallel
runs, custom-risk definitions, advisory vs blocking, detector-down
fail-closed, per-point selection.

**Blocked by**: LCORE-???? (config + detector framework)

**Acceptance criteria**:
- Integration suite runs without any real guardian model
- Covers every Decision T1–T6 behavior observable at the layer boundary

**Agentic tool instruction**:

```text
Read "Testing" in docs/design/prompt-guardrails/prompt-guardrails.md.
Key files: tests/integration/, src/guardrails/.
```

<!-- type: Story -->
<!-- key: LCORE-???? -->
#### LCORE-???? Documentation, configuration example, and model recommendation

**Description**: Deployer-facing documentation: enabling guardrails, the
`guardrails:` config reference, a complete worked example (Granite
Guardian on vLLM/RHAIIS; Ollama for development), custom risk definitions
(BYOC), the recommended-model statement (Decision S3) with licensing
notes, and guidance on advisory vs blocking rules and failure posture.

**Blocked by**: LCORE-???? (config + detector framework), input/output/tool
point tickets

**Acceptance criteria**:
- `docs/user_doc/` guide + config example validated against a running stack
- LCORE-230's "recommend the best suited open source guardian model"
  acceptance item is satisfied by the docs

**Agentic tool instruction**:

```text
Read the whole spec doc docs/design/prompt-guardrails/prompt-guardrails.md.
Key files: docs/user_doc/, examples/ (config example).
```

## PoC results

Full evidence in `poc-results/` (`README.md` first). PoC code lives in
`src/guardrails/` with unit tests in `tests/unit/guardrails/`; both are
removed before merge.

### What the PoC does

A minimal LCS-native guardrails layer (`src/guardrails/`): a
`GraniteGuardian` detector invoking the model via an OpenAI-compatible
chat-completions endpoint (risk selected in the system slot), a rule/point
runner executing a point's rules in parallel, and a hook in
`src/app/endpoints/query.py` feeding the existing
`ShieldModerationResult` seam.

**Important**: The PoC diverges from the production design in these ways:
- Activation via `LCS_GUARDRAILS_POC_CONFIG` env var, not the `guardrails:`
  config section (avoids touching `Configuration`/OpenAPI in a throwaway).
- Single detector (Granite Guardian via OpenAI-compatible endpoint); no
  `openai_moderations` / `llama_stack_shields` backends.
- Tool-content check is post-hoc on collected tool results (Decision T5
  option B), not the gating capability hook (option A).
- Output check is non-streaming `/v1/query` only; no streaming checkpoints.
- 2B guardian on CPU for feasibility; production uses 3.3-8B/4.1-8B on GPU.

### Results

- **Real Guardian verdicts, 6/6 correct** across OOTB (`jailbreak`,
  `harm`) and a custom BYOC (`leet-speak`) risk, benign and malicious each
  (`poc-results/01-guardian-probe-results.md`).
- **Layer run, all three points** against real Guardian: input block
  (jailbreak, leet-speak), tool_content block (poisoned MCP note,
  `blocked=True`), advisory output rule recorded without blocking
  (`poc-results/02-layer-run.json`).
- **Full-stack e2e**: benign query answered normally; a jailbreak and a
  *benign-but-leet-obfuscated* query blocked through real HTTP with the
  `[guardrails-poc]` refusal, `ls_llm_validation_errors_total` incremented
  to 2.0; the new layer and the run-ci llama-guard shield coexist
  additively (`shield_ids: []` selects between them)
  (`poc-results/04-full-stack-e2e.md`, `05-e2e-log-evidence.md`).

### Findings discovered during the PoC

- **Finding A — custom risks must be safety-shaped.** A custom definition
  that is not a safety concept ("contains the word 'pineapple'") is not
  reliably evaluated — Guardian is a safety classifier, not a keyword
  matcher. *Implication*: the docs ticket (LCORE-????) and the spec doc's
  custom-risk guidance must state that BYOC definitions express
  safety-adjacent concepts (obfuscation, roleplay jailbreak, policy
  violation) — arbitrary predicates belong to the regex-redaction
  mechanism. `poc-results/03-layer-findings.md`.
- **Finding B — output relevance risks require context pairing.** OOTB
  relevance risks (`answer_relevance`, `context_relevance`, `groundedness`)
  need the (retrieved-context, answer) pair; an answer-only check is
  noise. *Implication*: the output guardrail-point ticket (LCORE-????)
  must thread the turn's retrieved context into relevance-rule detector
  calls — reflected in the spec doc's Detector-backends note.
  `poc-results/03-layer-findings.md`.
- **Finding C — additive coexistence confirmed.** The existing llama-guard
  shield runs before the new layer and can pre-empt it; requests select
  between layers via `shield_ids`. This validates Decision S5 (additive
  now, deprecate at LCORE-1099) empirically.

## Proposed incidental JIRAs

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Fix lint-openapi Makefile target after openapi.json move

**Description**: `make lint-openapi` (part of `make verify`) fails on a
clean checkout of `main` with "No files found to lint": commit `d731ce76`
(LCORE-2933) moved `docs/openapi.json` to `docs/devel_doc/openapi.json`
but `Makefile:282` still lints the old path. Update the target (and any
other stale references) to the new location.

**Acceptance criteria**:
- `uv run make verify` passes on a clean checkout of `main`.

## Incidental findings

- `make verify` is broken on current `main`: the `lint-openapi` target
  points at `docs/openapi.json`, which LCORE-2933 (`d731ce76`) moved to
  `docs/devel_doc/openapi.json`. See the proposed incidental JIRA above.

## External input needed

- **@sbunciak**: Decision S4 (close vs repurpose LCORE-2710 — his Epic).
- **Ask Red Hat team** (via @sbunciak): review that the custom-risk config
  sketch (Decision T1) can express their four production risks; the Jira
  record ([RHAIRFE-98](https://redhat.atlassian.net/browse/RHAIRFE-98)
  comments) is our only requirements source — their gap-analysis document
  (linked from [LCORE-2316](https://redhat.atlassian.net/browse/LCORE-2316))
  should be checked for additional guardrails asks.

## Background sections

### Current state in lightspeed-stack

Input moderation is live on all four query endpoints via Llama Stack's
OpenAI-compatible Moderations API, driven by shields registered in the
llama-stack run config:

- `src/utils/shields.py:122` — `run_shield_moderation()` iterates shields,
  calls `client.moderations.create(input=..., model=shield.provider_resource_id)`,
  returns `ShieldModerationBlocked` (refusal message, metric increment) on
  the first flagged result.
- Call sites: `src/app/endpoints/query.py` (pre-RAG, raw user input only),
  `streaming_query.py`, `responses.py`, `rlsapi_v1.py`. Blocked requests
  skip RAG, return a 200 refusal, and persist the blocked turn.
- Request override: `QueryRequest.shield_ids` with the
  `disable_shield_ids_override` lockdown (`src/models/config.py:1663`).
- Output-side: `detect_shield_violations()` (`src/utils/shields.py:58`) is
  dead code; **no output moderation exists**.
- A second, llama-stack-independent track exists but is inert:
  `src/pydantic_ai_lightspeed/capabilities/question_validity/` (LLM-judge
  topic gate) and `.../redaction/` (regex PII redaction, input+output
  hooks), with config models (`QuestionValidityConfig`, `RedactionConfig`
  at `src/models/config.py:2479,2528`) never attached to `Configuration`.
- e2e configs all register one `inline::llama-guard` shield
  (`tests/e2e/configs/run-ci.yaml:38-42,134-137`).

Gaps: no output moderation, no LCS-side guardrails config, no Granite
Guardian / custom-risk support, no dedicated design doc, no e2e coverage of
blocking behavior.

### Llama Stack 0.6.0 safety surface (pinned version)

- Safety API: `client.safety.run_shield(messages, shield_id)` →
  `RunShieldResponse.violation` (`info|warn|error`); OpenAI-compatible
  `client.moderations.create(input, model)`; `client.shields.list()`
  (register/delete are deprecated).
- Providers: inline `llama-guard`, `prompt-guard` (injection/jailbreak
  classifier, filesystem-loaded weights), `code-scanner`; remote `bedrock`,
  `nvidia` (NeMo Guardrails), `passthrough`, `sambanova`. **No Granite
  Guardian provider; no TrustyAI provider in-tree** (TrustyAI's is
  out-of-tree and needs this classic Safety API).
- The classic Agents shields machinery (`input_shields`/`output_shields`,
  `ShieldCallStep`) is removed/dead in 0.6.0.
- The Responses API accepts `guardrails=[<shield_id>...]`: input checked
  before inference, accumulated output checked during streaming, violations
  yield refusal responses (not errors), enforcement via `run_moderation`.
  lightspeed-stack does not use this parameter today.

### Upstream trajectory: Llama Stack → OGX 1.x

Upstream renamed to OGX (`ogx-ai/ogx`). **OGX 1.0.0 (2026-05-12) deleted
the entire Safety API** — `/v1/moderations`, `/v1/shields`,
`/v1/safety/run-shield`, and all safety providers — replacing it with a
server-side `moderation_endpoint` (any OpenAI-compatible moderations
service) plus a per-request `guardrails: true` boolean. Fail-closed.
Upstream declined: separate input-vs-output config, and moderation of
server-side tool outputs (indirect injection) — both closed NOT_PLANNED.
The 0.5.x/0.6.x maintenance line keeps the classic Safety API. Combined
with the plan to reduce Llama Stack to an inference provider
(LCORE-1099), any guardrails design bound to shields/Moderations dies at
that migration; an LCS-native layer does not.

### Ask Red Hat baseline

From RHAIRFE-98 (Jira comments, 2025-08-13) and the public Ask Red Hat
technology attributions: Granite Guardian (3.2-5B then, 3.3-8B now) served
on vLLM (Red Hat AI Inference Server), invoked via a plain OpenAI client —
not via llama-stack safety. Input: multiple risks checked in parallel
(Guardian has no batch API): modified Harm (CVE questions permitted), and
custom risks Roleplay Jailbreak, Leet Speak, Amnesia. Output: retrieved
context and generated answer checked against Context Relevance and Answer
Relevance (OOTB risks) — output guardrails need access to retrieved
context, not just the answer. RHAIRFE-98 was closed by pointing at RHOAI
3.0's Guardrails Orchestrator (Granite Guardian as a HuggingFace detector),
not by an upstream llama-stack provider.

### Guardian model landscape

- **IBM Granite Guardian** (Apache 2.0): 3.x (2B/5B/8B, 3.3 adds thinking
  mode) and 4.1-8B (April 2026, improved bring-your-own-criteria). Detects
  harm umbrella (bias, profanity, violence, sexual content, unethical
  behavior), jailbreak, RAG hallucination triad (context relevance,
  groundedness, answer relevance), function-call hallucination; custom
  criteria via BYOC. Generative classifier: risk selected via chat
  template, constrained yes/no verdict. GuardBench leader (six of top-10
  slots). No dedicated indirect-injection criterion.
- **Meta Llama Guard 4** (12B, Llama community license): MLCommons S1–S14
  content-safety taxonomy, prompts and responses; no custom risks, no RAG
  checks.
- **Meta Prompt Guard 2** (22M/86M classifiers, Llama license): dedicated
  jailbreak/injection detector for prompts and third-party content; 86M:
  97.5% recall @ 1% FPR, ~92 ms on GPU; 22M CPU-friendly (~19 ms). The
  natural cheap tier for tool-content screening where licensing allows.
- **NeMo Guardrails / ShieldGemma / LlamaFirewall**: framework or
  lower-relevance alternatives; TrustyAI FMS orchestrator productizes
  detectors (incl. Granite Guardian) in RHOAI 2.19+/3.0.
- Caveat: detection is risk reduction, not a security boundary — published
  bypasses exist for classifier-based defenses; OWASP prescribes layered
  controls (which the three-point design provides).

### Design alternatives considered and rejected

- **Responses `guardrails=` delegation** (S1-B): verdict — rejected;
  couples enforcement to an API shape that changed in 0.6.0 and changes
  again in 1.x, and cannot express parallel custom-risk checks.
- **TrustyAI FMS as the required engine** (S1-D): verdict — rejected as a
  requirement, supported as a deployment choice through the
  `openai_moderations`-style backend against gateway endpoints.
- **Upstreaming a Granite Guardian llama-stack provider** (the original
  RHAIRFE-98 ask): verdict — moot; upstream deleted the provider surface.

## Glossary

- **Guardrail point**: lifecycle position where rules run — `input`
  (user prompt), `output` (generated answer), `tool_content` (tool/RAG
  content entering the context).
- **Rule**: binding of a risk (OOTB id or custom definition) to points,
  a detector, and a blocking/advisory flag.
- **Detector backend**: adapter that turns a rule check into a concrete
  model invocation (Guardian chat template, OpenAI moderations, legacy
  shields).
- **BYOC**: bring-your-own-criteria — Guardian's custom risk-definition
  mechanism.
- **Advisory rule**: flagged results are recorded (logs/metrics) without
  blocking the response.
