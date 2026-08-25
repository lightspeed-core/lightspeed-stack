# Feature design for Prompt Guardrails

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-07-20                                |
| **Component**      | lightspeed-stack                          |
| **Authors**        | Maxim Svistunov                           |
| **Feature**        | [LCORE-230](https://redhat.atlassian.net/browse/LCORE-230) |
| **Spike**          | [LCORE-2657](https://redhat.atlassian.net/browse/LCORE-2657) |
| **Links**          | [Spike doc](prompt-guardrails-spike.md), [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) |

## What

An optional, config-driven guardrails layer owned by lightspeed-stack,
implemented as new pydantic-ai-lightspeed **shields** — the same
mechanism that already powers the `question_validity` and `redaction`
shields in `shields:`. Deployers declare guardian-backed shields
(detectors reachable through OpenAI-compatible APIs — Granite Guardian on
vLLM/RHAIIS, or any `/v1/moderations` service) as new named entries in the
existing `shields:` configuration list. Each such shield carries a **rule**
(an out-of-the-box risk id or a custom risk definition) bound to one or
more guardrail **points**: `input`, `output`, `tool_content`, with a
blocking or advisory posture. The layer runs the applicable shields in
parallel at each point of the request lifecycle and blocks (or annotates)
requests whose content is flagged.

## Why

Prompt injection is OWASP's #1 LLM risk. lightspeed-stack's pydantic-ai
`shields:` configuration already lets deployers declare named guardrails
(`question_validity`, `redaction`) that run as first-class pydantic-ai
capabilities — but it has no detector-backed screening: no Granite
Guardian support, no generic `/v1/moderations` gateway support, no custom
risk definitions, and no systematic output or tool-content coverage beyond
what `redaction` happens to cover. (A separate, older Llama Stack
moderation path — `client.moderations.create`, invoked from the
now-stubbed `run_shield_moderation` — predates `shields:` entirely and is
being phased out in OGX 1.x; it is out of scope here and this feature adds
no dependency on it.) Ask Red Hat's migration to Lightspeed Core
([LCORE-2253](https://redhat.atlassian.net/browse/LCORE-2253)) is blocked
on exactly the missing detector capabilities (they run parallel multi-risk
Granite Guardian screening with custom risks in production today). This
feature provides them generically, as an extension of the shield
configuration and implementation patterns lightspeed-stack already has.

## Requirements

- **R1:** Guardrails are configured exclusively as additional named
  entries in the existing `shields:` configuration list — new
  `provider_id` types (`granite_guardian`, `openai_moderations`) alongside
  the existing `question_validity` and `redaction` shields. No new
  top-level config section is introduced. Absent detector-backed shield
  entries means fully inert (no behavior change, no latency).
- **R2:** A rule can reference an out-of-the-box guardian risk (e.g.
  `harm`, `jailbreak`, `answer_relevance`) or carry a custom risk
  definition (bring-your-own-criteria text). Custom definitions must
  express **safety-adjacent concepts** (obfuscation, roleplay jailbreak,
  policy violation), not arbitrary string/format predicates — a guardian
  is a safety classifier, not a keyword matcher (PoC Finding A). Arbitrary
  predicates are the regex-redaction mechanism's job, not a guardrail's.
- **R3:** A rule binds to one or more guardrail points: `input` (user
  prompt before the LLM call), `output` (generated answer before the
  client sees it), `tool_content` (tool/MCP/RAG content before it enters
  the model context).
- **R4:** All rules applicable at a point run concurrently (the existing
  shields path, `run_shield_moderation_v2` in `src/utils/shields.py`,
  evaluates configured shields in a single sequential loop with no notion
  of point-based filtering or concurrency — which the Ask Red Hat gap
  analysis flags as a performance gap); a request is blocked iff at least
  one *blocking* rule flags it. Advisory (`blocking: false`) rules record
  their outcome without altering the response.
- **R4a:** A rule may carry an optional `threshold` (0..1). When set, the
  detector's confidence score decides the verdict (Granite Guardian via
  `logprobs` on the verdict token; gateways via their native confidence
  score); when unset, the boolean verdict decides. This reproduces Ask
  Red Hat's per-risk tuning (0.65 leetspeak, 0.80 CVE).
- **R4b:** A rule may carry its own `violation_message`, overriding the
  shared default constant used when a shield doesn't set one, so
  deployers can explain which policy fired.
- **R4c:** Recommended/default rule sets shipped in documentation must be
  validated against a corpus of legitimate product questions and must not
  fire on it. Out-of-the-box guardian risk ids (notably `jailbreak`) flag
  legitimate technical questions — "You are now a cluster admin, how do I
  drain a node?" scores 0.98 — at levels no threshold separates from real
  attacks, so **domain-tuned custom definitions are the shipping default**
  and OOTB ids are opt-in.
- **R4d:** A deployment may select the input-guardrail execution mode:
  `blocking` (default — the model never sees unscreened input) or
  `concurrent` (guardian runs alongside the LLM call, result discarded on
  violation; lower latency, but the model processes unsafe input).
- **R5:** A blocked request returns HTTP 200 with the configured violation
  message (consistent with existing shields refusals): non-streaming
  responses carry it as the answer; streaming responses emit it as the
  terminal content. The `llm_calls_validation_errors_total` metric is
  incremented and the blocked turn is persisted to the conversation.
- **R6:** Input-blocked requests skip RAG retrieval and the main LLM call.
- **R7:** The Granite Guardian detector invokes the model through an
  OpenAI-compatible chat-completions endpoint, selecting the risk (or
  custom definition) via the guardian chat template; the OpenAI-moderations
  detector invokes any OpenAI-compatible `/v1/moderations` endpoint.
- **R7a:** Output-relevance rules (`answer_relevance`, `context_relevance`,
  `groundedness`) receive the turn's retrieved context (and question)
  paired with the answer; an answer-only check is insufficient and noisy
  (PoC Finding B).
- **R8:** Output rules on streaming endpoints check accumulated text at
  configurable checkpoints; content past a failed checkpoint is never
  emitted.
- **R9:** Detector errors (unreachable endpoint, timeout) block the request
  by default (`on_detector_error: block`), overridable to `allow` per
  shield.
- **R10:** Per-rule detection outcomes and latencies are logged and
  exposed as metrics.
- **R11:** The existing `question_validity` and `redaction` shields, and
  the separate legacy Llama Stack moderation path, continue to work
  unchanged when no `granite_guardian`/`openai_moderations` shields are
  configured; the new shield types are purely additive entries in the same
  `shields:` list and may run side by side with existing shields.

## Use Cases

- **U1:** As a Lightspeed product team (e.g. Ask Red Hat), I want to
  declare my guardian model endpoint and my product's risk set (OOTB +
  custom definitions) in the LCS config file, so that my product is
  protected without custom code.
- **U2:** As a deployer, I want prompts that attempt jailbreak/injection
  blocked before they reach the LLM, so that the assistant cannot be
  subverted.
- **U3:** As a deployer, I want generated answers checked (e.g. harm,
  answer relevance) before delivery, so that unsafe or off-context output
  never reaches users.
- **U4:** As a deployer of an MCP-enabled assistant, I want tool and RAG
  content screened before the model consumes it, so that indirect prompt
  injection via third-party content is caught.
- **U5:** As an SRE, I want per-rule outcomes and latencies in metrics, so
  that I can observe block rates and tune thresholds/rules.
- **U6:** As a security engineer, I want the service to fail closed when
  the guardian endpoint is down, so that protection cannot silently lapse.

## Architecture

### Overview

```text
             ┌────────────────────────────── lightspeed-stack ──────────────────────────────┐
             │                                                                              │
 user query ─┼─► input rules ──blocked──► 200 refusal (skip RAG + LLM; persist turn)        │
             │   (parallel)                                                                 │
             │      │ passed                                                                │
             │      ▼                                                                       │
             │   RAG retrieval ─► LLM call (Responses API)                                  │
             │                       │        ▲                                             │
             │                 tool results   │ tool_content rules gate each result         │
             │                       └────────┘ (flagged content never enters context)      │
             │      ▼                                                                       │
             │   output rules ──blocked──► refusal replaces/terminates answer               │
             │   (checkpointed when streaming)                                              │
             │      │ passed                                                                │
             └──────┼───────────────────────────────────────────────────────────────────────┘
                    ▼
                 response
                                     all rule checks ──► shield capability ──► guardian model
                                                       (Guardian chat template  (vLLM / RHAIIS /
                                                        or /v1/moderations)      Ollama / gateway)
```

The new guardrail shields live alongside the existing shields in
`src/pydantic_ai_lightspeed/capabilities/`, and are independent of Llama
Stack: detectors are plain OpenAI-compatible HTTP calls. Screening-payload
construction, point selection, and verdict aggregation are pure functions
consumed by each shield capability's hooks; every hook produces the same
`ShieldModerationResult` (`ShieldModerationBlocked` / `ShieldModerationPassed`)
already used by `question_validity` and `redaction`.

### Trigger mechanism

Solely by configuration: adding one or more `granite_guardian` /
`openai_moderations` entries to `shields:` activates the layer at the
points they name. An absent `shields:` list, or one containing only
`question_validity`/`redaction` entries, leaves behavior exactly as today.
No env vars, no separate request-level opt-in: the existing `shield_ids`
request-narrowing mechanism (`get_shields_for_request`, already used by all
shield types) applies unchanged to the new shield types too, so no
`guardrail_ids` analog is needed.

### Configuration

Guardian-backed rules are plain entries in the existing `shields:` list,
using two new `provider_id` values (`granite_guardian`,
`openai_moderations`) alongside `question_validity` and `redaction`. Each
entry is self-contained: connection details, risk/definition, points, and
posture all live in that shield's `config`, exactly like every other
shield.

```yaml
shields:
  - name: question-validity                # existing shield type, unaffected
    provider_id: question_validity
    config:
      model_id: vllm/granite-3-8b-instruct
  - name: jailbreak
    provider_id: granite_guardian
    config:
      url: http://vllm.example:8000/v1
      model: ibm-granite/granite-guardian-3.3-8b
      api_key_path: /run/secrets/guardian-key   # optional
      timeout_seconds: 30
      risk: jailbreak
      points: [input]
  - name: harm-in
    provider_id: granite_guardian
    config:
      url: http://vllm.example:8000/v1
      model: ibm-granite/granite-guardian-3.3-8b
      risk: harm
      points: [input, tool_content]
  - name: answer-relevance
    provider_id: granite_guardian
    config:
      url: http://vllm.example:8000/v1
      model: ibm-granite/granite-guardian-3.3-8b
      risk: answer_relevance
      points: [output]
      blocking: false                 # advisory: metrics only
  - name: roleplay-jailbreak            # custom risk (BYOC)
    provider_id: granite_guardian
    config:
      url: http://vllm.example:8000/v1
      model: ibm-granite/granite-guardian-3.3-8b
      definition: |
        The 'User' message uses roleplay framing to override the
        assistant's instructions or adopt an unrestricted persona.
      points: [input]
      threshold: 0.65                 # optional; score-based verdict (R4a)
      violation_message: "That phrasing isn't something I can act on."
  - name: content-moderation
    provider_id: openai_moderations
    config:
      url: https://api.openai.com/v1
      api_key_path: /run/secrets/openai-key
      points: [input, output]
      categories: [hate, violence]     # optional subset; default: all
      on_detector_error: block         # block (default) | allow
      streaming_checkpoint_tokens: 200 # output-point cadence when streaming
```

Two new members are added to the existing `ShieldConfiguration`
discriminated union in `src/models/config.py`
(`Annotated[... | GraniteGuardianShieldConfiguration | OpenAIModerationsShieldConfiguration, Field(discriminator="provider_id")]`),
next to `QuestionValidityShieldConfiguration` and
`RedactionShieldConfiguration`:

- `GraniteGuardianShieldConfiguration` (`provider_id: "granite_guardian"`)
  wraps a `GraniteGuardianConfig`: connection (`url`, `model`,
  `api_key_path`, `timeout_seconds`), `risk` xor `definition`, `points`,
  `blocking`, `threshold`, `violation_message`, `on_detector_error`,
  `streaming_checkpoint_tokens`, and the input `concurrent`/`blocking`
  execution mode (R4d).
- `OpenAIModerationsShieldConfiguration` (`provider_id: "openai_moderations"`)
  wraps an `OpenAIModerationsConfig` with the same connection / points /
  blocking / threshold / violation_message / on_detector_error /
  streaming_checkpoint_tokens shape, plus an optional `categories` filter.

No new top-level config section is introduced —
`Configuration.shields: list[ShieldConfiguration]` is the only attachment
point, and the existing `validate_shield_names_unique` model validator
continues to apply across all shield types unchanged. New validators on
the two config models: `risk` xor `definition` present; `points`
non-empty. Where several shields point at the same guardian endpoint, they
simply repeat the connection fields — no separate top-level "detectors"
registry is introduced (see Client lifecycle below for how connections are
still reused at runtime).

### Detector backends

Each detector-backed shield type implements a shared internal
`DetectorBackend` protocol: `async check(item: ScreeningItem, config:
GraniteGuardianConfig | OpenAIModerationsConfig) -> DetectionResult`, used
by the shield capability's hooks (below), never called directly by
endpoints. The unit screened is a **structured payload**, not a bare
string, because relevance rules need more than the answer text:

```python
class ScreeningItem(BaseModel):
    text: str                        # the primary content being screened
    context: Optional[str] = None    # retrieved RAG context (relevance rules)
    question: Optional[str] = None    # the user question (answer-relevance)
```

Simple rules (harm, jailbreak on input) populate only `text`;
output-relevance rules populate `text` (the answer) plus `context` and/or
`question`. Each backend maps this canonical payload to its own wire form
(the Guardian chat template's context/answer framing; the moderations
`input` field). Defining this one interface up front is what lets the
`run`, `before_model_request`/`after_model_request`, and `after_tool_execute`
hooks (below) all call detection the same way (R7a depends on it).
Backends:

- **granite_guardian** — OpenAI chat-completions call; system slot selects
  the risk id or carries the custom definition (guardian chat template);
  verdict parsed from the constrained yes/no answer. Output-relevance risks
  send the `ScreeningItem`'s `context`/`question` alongside `text`, packed
  per the guardian template.
- **openai_moderations** — POST `/v1/moderations`; a rule maps to flagged
  categories (all, or a configured subset). Covers OGX 1.x
  `moderation_endpoint` services, TrustyAI gateways, and OpenAI itself.

There is no Llama Stack shields backend: the separate, older
`client.moderations.create` moderation path predates the `shields:`
configuration entirely, is being phased out in OGX 1.x, and is left
untouched by this feature (see Migration section).

**Client lifecycle**: connections are keyed by `(url, model,
api_key_path)` and cached process-wide (a small module-level registry,
the same pattern `AsyncOgxClientHolder` uses for the main Llama Stack
client), so shield instances that share a guardian endpoint share **one
long-lived HTTP client**, not one per request or per shield. Constructing
an `AsyncOpenAI` (or equivalent) per check creates a fresh connection pool
each time — leaking connections if unclosed, and forfeiting connection
reuse even when closed, which matters because guardrails add a
round-trip to every request. The PoC constructs per call (context-managed
so nothing leaks) and is explicitly not the production pattern.

### Request lifecycle integration

Each detector-backed shield is a pydantic-ai `AbstractSafetyCapability`
subclass (`src/pydantic_ai_lightspeed/capabilities/base.py`), exactly like
`QuestionValidity` and `PiiRedactionCapability`, and is wired into the
agent the same way: `_shield_capability()` in
`src/utils/pydantic_ai_helpers.py` gains match-case arms for
`GraniteGuardianConfig`/`OpenAIModerationsConfig`, so `_agent_capabilities()`
picks them up automatically wherever shields already flow (`build_agent`,
`get_agent_capability_tools`). Point binding maps onto existing pydantic-ai
capability hooks rather than a new dispatch mechanism:

- **Input**: `run_shield_moderation_v2` (`src/utils/shields.py`) already
  loops over `config.shields`, calling each shield's `run()` before RAG
  retrieval and the main LLM call — this is the seam every shield type
  uses today, and the one R5/R6 already depend on (refusal shape, RAG
  skip, turn persistence, metrics). It is extended to: (a) select only the
  detector-backed shields whose `points` include `input` (question_validity
  and redaction remain implicitly input-bound, as today), and (b) run
  those shields' `run()` calls concurrently (`asyncio.gather`) instead of
  the current sequential loop — closing the gap R4 calls out. Each
  detector-backed shield also implements `wrap_run` (the same hook
  `QuestionValidity` uses) so the check also applies to any turn that
  reaches the agent graph directly, for defense in depth.
- **Output**: the shield's `after_model_request` hook — the same hook
  `PiiRedactionCapability` already uses for its own output pass — checks
  the model's response text (plus, for relevance risks, the turn's
  retrieved context/question) before it is added to history; a blocking
  verdict replaces the response with the shield's `violation_message` and
  ends the turn. For streaming, `wrap_run_event_stream` checkpoints
  accumulated text every `streaming_checkpoint_tokens` and stops
  forwarding events once a checkpoint fails, so content past a failed
  checkpoint is never emitted (R8).
- **Tool content**: the shield's `after_tool_execute` hook screens each
  tool result (MCP tool output, RAG chunks returned by the RAG tool)
  before it is appended to conversation history and re-enters the model's
  context; a flagged result is replaced by a policy notice or aborts the
  turn per the shield's `blocking` flag — the same interception pattern as
  `PiiRedactionCapability`'s message-rewriting hooks, applied to tool
  results instead of user/response text.

No new framework-agnostic module or runner-level call site is introduced:
detection logic (payload construction, backend HTTP calls, verdict
parsing) lives as internal helpers next to each capability
(`src/pydantic_ai_lightspeed/capabilities/guardian/core.py`, mirroring
`capabilities/redaction/core.py`), and every entry point into it is one of
the pydantic-ai hooks above.

### API changes

None to request models in the core epic. Response behavior on block is the
established refusal shape. Request-level narrowing is already covered by
the existing `shield_ids` field, since these are ordinary shields; no new
`guardrail_ids` field is needed.

### Error handling

Detector connectivity/timeout errors follow the shield's own
`on_detector_error`: `block` (default) returns the refusal shape with a
distinct log line and metric label; `allow` logs a warning and proceeds.
Config errors (bad risk spec, both/neither of `risk`/`definition` set,
empty `points`) fail startup validation the same way other shield config
errors do today.

### Security considerations

- Guardian endpoints and API keys are deployment secrets — keys are read
  from files (`api_key_path`) per project convention, never inline.
- Detection is risk reduction, not a security boundary: published bypasses
  exist for classifier-based defenses. Layered posture (all three points +
  least-privilege MCP config) is the mitigation; thresholds/risks are
  deployment policy.
- Moderated content is sent to the guardian endpoint: deployers must place
  detectors within the same trust boundary as the serving LLM.

### Migration / backwards compatibility

No `granite_guardian`/`openai_moderations` shield entries ⇒ byte-identical
behavior to today (R11): `shields:` and its existing
`question_validity`/`redaction` handling are untouched, since the new
types are purely additive members of the same `ShieldConfiguration`
discriminated union. The separate, older Llama Stack `client.moderations.create`
moderation path (currently stubbed to always pass in `run_shield_moderation`)
is unrelated to `shields:` and is untouched by this feature; its removal
is tracked separately under LCORE-1099 and is not blocked on this work.

## Acceptance test surface

| Req | Observable behavior | Verified by |
|-----|---------------------|-------------|
| R1  | No `granite_guardian`/`openai_moderations` shields configured ⇒ responses and latency unchanged | e2e |
| R2  | OOTB risk blocks a matching prompt; custom definition blocks its target phrasing | e2e |
| R7a | Relevance rule receives context+answer; answer-only run flagged as misconfiguration in review | integration |
| R3  | A rule with `points: [output]` never fires on input, and vice versa | integration |
| R4  | Two input rules ⇒ both detector calls observed concurrently; advisory rule never alters response | integration |
| R4a | Same content flips verdict across a threshold boundary (e.g. 0.6 vs 0.9); unset threshold falls back to boolean verdict | integration |
| R4b | Rule with its own `violation_message` returns that text, not the global default | e2e |
| R4c | Documented recommended rule set produces zero blocks on the legitimate-question corpus | e2e / tuning fixture |
| R4d | `concurrent` mode returns the same verdict as `blocking` for the same input, with lower wall-clock | integration |
| R5  | Blocked query ⇒ HTTP 200, violation message as answer, metric incremented, turn persisted | e2e |
| R6  | Input-blocked query produces no RAG retrieval and no main-LLM call | integration |
| R7  | Guardian receives risk id / definition in the system slot; moderations backend hits `/v1/moderations` | integration |
| R8  | Streaming: flagged checkpoint ⇒ refusal emitted, withheld text never sent | e2e |
| R9  | Detector down ⇒ refusal (default) / pass-through (`allow`) | e2e |
| R10 | Per-rule outcome + latency present in logs and metrics | integration |
| R11 | Deployment with only `question_validity`/`redaction` shields (or none) behaves exactly as before the feature | e2e |

## Aspect-specific concerns

### Latency and Cost

Each blocking rule adds one guardian inference to the critical path;
parallel execution makes the per-point cost ≈ the slowest single check
(Guardian-8B on GPU: high tens to low hundreds of ms; small CPU models:
lower). Input and output points each add at most one such round;
`tool_content` multiplies by tool-call count — deployers control exposure
via rule→point bindings, and per-rule latency metrics (R10) make the cost
observable. PoC latency measurements: see the spike doc's PoC results.

### Observability

Per-rule structured logs (rule, point, verdict, latency, raw verdict
text at debug); metrics: existing `llm_calls_validation_errors_total` on
block, plus per-rule outcome/latency counters and histograms. Detector
errors get a distinct metric label to drive alerting (fail-closed events
are page-worthy).

### Failure modes

- Guardian endpoint down ⇒ R9 posture (default: block; alert fires).
- Guardian misbehaving (non-yes/no output) ⇒ treated as not-flagged for
  advisory rules and per `on_detector_error` for blocking rules
  (unparseable verdict ≈ detector error).
- Slow detector ⇒ per-shield timeout bounds the stall; timeout ⇒ R9.
- Config drift (shield config carries both/neither `risk` and `definition`,
  or empty `points`) ⇒ startup validation error, same as other shield
  config mistakes today.

### Runbook / oncall implications

New alert: detector-error rate (fail-closed blocks). Recovery: restore the
guardian endpoint or temporarily set `on_detector_error: allow` /remove
rules (explicit, logged policy change). Block-rate dashboards distinguish
policy blocks (working as intended) from error blocks.

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/models/config.py` | Add `GraniteGuardianShieldConfiguration`, `OpenAIModerationsShieldConfiguration` (+ `GraniteGuardianConfig`/`OpenAIModerationsConfig`) to the existing `ShieldConfiguration` discriminated union |
| `src/pydantic_ai_lightspeed/capabilities/guardian/` (new) | `GraniteGuardianCapability`/`OpenAIModerationsCapability` (`AbstractSafetyCapability` subclasses), `DetectorBackend` implementations, `ScreeningItem` payload helpers, HTTP client cache — mirrors `capabilities/redaction/` |
| `src/utils/pydantic_ai_helpers.py` | Extend `_shield_capability()` match-case to build the new capability types |
| `src/utils/shields.py` | Make `run_shield_moderation_v2`'s loop point-aware (only `input`-bound shields) and concurrent (`asyncio.gather`) instead of sequential |
| `src/utils/agents/streaming.py`, `src/utils/streaming_sse.py` | Verify `wrap_run_event_stream` checkpointing surfaces cleanly through the existing SSE generators |
| `src/metrics/` | Per-shield outcome/latency instruments |
| `docs/user_doc/`, `examples/` | Deployer guide + validated config example |

No endpoint changes are needed: `src/app/endpoints/query.py`,
`streaming_query.py`, `responses.py`, and `rlsapi_v1.py` already call
`run_shield_moderation_v2(..., configuration.configuration.shields, ...)`
for every shield type, and already build the agent via `build_agent`/
`_agent_capabilities`, which is how the new shields reach the output and
tool-content hooks too.

### Insertion point detail

The input path needs no new call site: `run_shield_moderation_v2` already
returns `ShieldModerationBlocked` (message, synthetic moderation id) when
a shield's `run()` blocks, and every downstream branch in every endpoint
already handles it — the change is confined to making its shield-selection
and iteration point-aware and concurrent. The output and tool-content
hooks follow the `PiiRedactionCapability`'s message-rewriting pattern
(`src/pydantic_ai_lightspeed/capabilities/redaction/_capability.py`):
`after_model_request` for output text, `after_tool_execute` for tool
results, both replacing content (or raising to abort the turn, for a
`blocking` verdict) instead of the pass-through/redaction rewrite
`PiiRedactionCapability` performs.

### Config pattern

Follow the project's Configuration conventions (see
[CLAUDE.md](../../../CLAUDE.md) — Configuration section); schema and YAML
example above. Regenerate `docs/openapi.json` and config docs after
attaching the section.

### Test patterns

- Unit/integration tests need **no real guardian**: a scripted
  OpenAI-compatible mock (respond yes/no per marker phrases) exercises
  every layer behavior deterministically.
- e2e needs a guardian stand-in the CI environment can run: either the
  mock detector as a service, or a small real model where resources allow
  — decide in the step-definitions ticket against CI constraints.
- Concurrency: assert parallelism (not sequencing) of multi-rule points
  via call-timestamp capture in the mock.

## Open Questions for Future Work

- Streaming checkpoint sizing defaults — spike Decision T4 (70%
  confidence); tune during implementation with real latency data.
- Cheap classifier tier for `tool_content` (Prompt Guard 2-class) and its
  licensing posture — deferred from spike Decisions S2/S3.
- Deprecation timeline for the separate, legacy Llama Stack
  `client.moderations.create` moderation path — unrelated to this feature;
  owned by LCORE-1099.

Resolved by folding guardrails into `shields:` (this revision):
request-level rule narrowing (spike Decision T1) is already covered by the
existing `shield_ids` field, and unifying question-validity/PII-redaction
with detector-based guardrails under one policy/config umbrella (spike
Decision T7) is exactly what the `shields:` extension does.

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-07-20 | Initial version | LCORE-2657 spike |
| 2026-08-03 | Added R4a (per-rule thresholds), R4b (per-rule violation messages), R4d (input execution mode), R7a (output-relevance context pairing); `ScreeningItem` detector payload; client-lifecycle and `src/runners` integration notes | Decisions T8–T10 and PoC finding B |
| 2026-08-03 | Added R4c (recommended rule sets validated against a legitimate-question corpus) | PoC finding D — OOTB `jailbreak` false-positives on legitimate OpenShift questions at ~0.98 |
| 2026-08-03 | PR #2182 review: `DetectorBackend` takes a structured payload; recommended-model rec split (3.3-8B benchmarked, 4.1-8B extrapolated) | @sbunciak / @tisnik review + CodeRabbit |
| 2026-08-24 | Removed the `llama_stack_shields` detector type entirely; folded guardrails into the existing `shields:` configuration (new `granite_guardian`/`openai_moderations` provider_id shield types) instead of a new top-level `guardrails:` section; grounded the implementation in pydantic-ai capability hooks (`run`, `wrap_run`, `before_model_request`/`after_model_request`, `after_tool_execute`, `wrap_run_event_stream`) matching the existing `question_validity`/`redaction` shields, removing the separate framework-agnostic `src/guardrails/` module; resolved the request-level narrowing and shields-unification open questions as a consequence | User feedback |
