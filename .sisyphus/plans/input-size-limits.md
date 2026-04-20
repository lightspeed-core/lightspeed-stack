# Enforce Input Size Limits on /v1/infer and /responses

## TL;DR

> **Quick Summary**: Raise `/v1/infer` question limit from 10KB to 32KB to match CLA client, and add a 64KB JSON-size DoS guard to `/responses` which currently has no limit at all.
> 
> **Deliverables**:
> - `/v1/infer` question field max_length raised to 32,000
> - `/responses` input field validated via `len(json.dumps())` against 65,536 limit
> - Unit tests for both changes
> - PR against lightspeed-core/lightspeed-stack
>
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — sequential (2 small changes + tests + PR)
> **Critical Path**: Task 1 → Task 2 → Task 3
> **JIRA**: RSPEED-2875

---

## Context

### Original Request
Align input size limits between the CLA client (32KB) and lightspeed-stack backends. The CLA client truncates at 32,000 chars before sending. The `/v1/infer` endpoint rejects at 10,240 chars (Pydantic `max_length`), causing raw 422 JSON errors for inputs between 10KB-32KB (RSPEED-2855). The `/responses` endpoint has no limit at all.

### Key Decisions (from interview)
- Brian Smith: keep CLA client at 32,000 — make server compatible
- `/v1/infer`: raise `max_length` from 10,240 to 32,000
- `/responses`: use `len(json.dumps(value))` as the guard — covers all 8 `ResponseItem` subtypes without recursion
- `/responses` limit set to 65,536 (64KB) not 32,000 — because JSON encoding adds structural overhead (field names, braces, quotes) beyond the actual text content. A 32KB text payload serialized as a list of message items will be well under 64KB, but could exceed 32KB due to JSON structure.
- goose-proxy always sends the list form, using 3 item types: `message`, `function_call`, `function_call_output`

---

## Work Objectives

### Core Objective
Prevent oversized inputs from producing raw Pydantic errors on `/v1/infer` and add a missing DoS guard to `/responses`.

### Concrete Deliverables
- Modified `src/models/rlsapi/requests.py` — one-line change
- Modified `src/models/requests.py` — new `@field_validator` on `ResponsesRequest`
- Updated/new unit tests

### Must Have
- `/v1/infer` `question` field accepts up to 32,000 characters
- `/responses` `input` field rejects payloads whose JSON serialization exceeds 65,536 bytes
- The 422 error message is clear (not a raw Pydantic dump)
- All existing tests still pass
- New tests cover the limit boundaries

### Must NOT Have (Guardrails)
- Do NOT change the CLA client's 32,000 limit
- Do NOT add limits to other `/v1/infer` context fields (stdin, attachments, terminal — these are already at 65,536 and are fine)
- Do NOT change the ResponseInput type alias — add validation, don't restructure
- Do NOT break the OpenAI Responses API spec compliance
- Do NOT add per-field validation on list items — use the json.dumps approach

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (tests-after — update existing, add new)
- **Framework**: pytest
- **Commands**: `uv run make test-unit`, `uv run make verify`

---

## Execution Strategy

### Sequential (3 tasks)

```
Task 1: Raise /v1/infer question limit [quick]
Task 2: Add /responses input size validator [quick]  
Task 3: Run tests and create PR [quick]

Critical Path: Task 1 → Task 2 → Task 3
```

---

## TODOs

- [ ] 1. Raise /v1/infer question field max_length to 32,000

  **What to do**:
  - In `src/models/rlsapi/requests.py`, line 180: change `max_length=10_240` to `max_length=32_000`
  - Update the existing unit test in `tests/unit/models/rlsapi/` that tests the max_length boundary — search for `10240` or `10_240` in test files and update to `32_000`
  - Check for any integration tests referencing the old limit

  **Must NOT do**:
  - Do not change any other field limits in this file (stdin, attachments, terminal are fine at 65,536)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 2, Task 3
  - **Blocked By**: None

  **References**:
  - `src/models/rlsapi/requests.py:177-183` — the `question` Field definition with current `max_length=10_240`
  - `tests/unit/models/rlsapi/` — existing tests for request validation
  - Commit `5a99ee77` by Sam Doran — "Add max lengths for rlsapi fields" — added the original limits

  **Acceptance Criteria**:
  - [ ] `max_length=32_000` in `src/models/rlsapi/requests.py`
  - [ ] Existing tests updated to reflect new limit
  - [ ] `uv run make test-unit` passes

  **QA Scenarios**:
  ```
  Scenario: Question at 32,000 chars accepted
    Tool: Bash (pytest)
    Steps:
      1. Run unit test that creates RlsapiV1InferRequest with question="x" * 32_000
      2. Assert no ValidationError raised
    Expected Result: Request object created successfully

  Scenario: Question at 32,001 chars rejected
    Tool: Bash (pytest)
    Steps:
      1. Run unit test that creates RlsapiV1InferRequest with question="x" * 32_001
      2. Assert ValidationError raised with message containing "32000" or "32_000"
    Expected Result: ValidationError raised
  ```

  **Commit**: YES
  - Message: `fix(rlsapi): raise question max_length from 10240 to 32000 (RSPEED-2875)`
  - Files: `src/models/rlsapi/requests.py`, test files
  - Pre-commit: `uv run make test-unit`

---

- [ ] 2. Add input size validator to /responses endpoint

  **What to do**:
  - In `src/models/requests.py`, add a `@field_validator("input")` to the `ResponsesRequest` class
  - The validator should:
    1. Import `json` at the top of the file
    2. If value is a `str`: check `len(value) > 65_536`
    3. If value is a `list`: serialize with `json.dumps()` using a Pydantic-aware serializer (the list items are Pydantic models, so use `[item.model_dump() for item in value]` before `json.dumps`), then check length
    4. Raise `ValueError` with a clear message like "Input exceeds maximum allowed size of 65536 characters"
  - Add unit tests in `tests/unit/models/` or `tests/unit/app/endpoints/test_responses.py`:
    - String input at exactly 65,536 — accepted
    - String input at 65,537 — rejected
    - List input with total JSON size under 65,536 — accepted
    - List input with total JSON size over 65,536 — rejected

  **Must NOT do**:
  - Do not modify the `ResponseInput` type alias in `src/utils/types.py`
  - Do not add per-field validation on individual list items
  - Do not change any other fields on `ResponsesRequest`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References**:
  - `src/models/requests.py:698` — `input: ResponseInput` field on `ResponsesRequest`
  - `src/utils/types.py:165` — `type ResponseInput = str | list[ResponseItem]` type alias
  - `src/utils/types.py:153-163` — the `ResponseItem` union with all 8 subtypes
  - `tests/unit/app/endpoints/test_responses.py` — existing responses endpoint tests showing test patterns, mock setup, and fixture conventions
  - lightspeed-stack `AGENTS.md` — coding standards require docstrings, type annotations, Google-style docstrings

  **Acceptance Criteria**:
  - [ ] `@field_validator("input")` added to `ResponsesRequest`
  - [ ] String inputs over 65,536 chars raise `ValueError`
  - [ ] List inputs whose JSON serialization exceeds 65,536 bytes raise `ValueError`
  - [ ] Clear error message in the ValueError (not raw Pydantic internals)
  - [ ] Unit tests cover boundary cases for both string and list branches
  - [ ] `uv run make test-unit` passes
  - [ ] `uv run make verify` passes (linting, type checking)

  **QA Scenarios**:
  ```
  Scenario: String input at limit accepted
    Tool: Bash (pytest)
    Steps:
      1. Create ResponsesRequest with input="x" * 65_536
      2. Assert no ValidationError
    Expected Result: Request created successfully

  Scenario: String input over limit rejected
    Tool: Bash (pytest)
    Steps:
      1. Create ResponsesRequest with input="x" * 65_537
      2. Assert ValidationError with message containing "65536"
    Expected Result: ValidationError raised

  Scenario: List input under limit accepted
    Tool: Bash (pytest)
    Steps:
      1. Create list of ResponseMessage items with moderate text
      2. Verify json.dumps(serialized) length < 65_536
      3. Create ResponsesRequest with input=list
      4. Assert no ValidationError
    Expected Result: Request created successfully

  Scenario: List input over limit rejected
    Tool: Bash (pytest)
    Steps:
      1. Create list of ResponseMessage items with large text totaling > 65KB serialized
      2. Create ResponsesRequest with input=list
      3. Assert ValidationError
    Expected Result: ValidationError raised
  ```

  **Commit**: YES
  - Message: `feat(responses): add input size limit of 64KB via JSON serialization guard (RSPEED-2875)`
  - Files: `src/models/requests.py`, test files
  - Pre-commit: `uv run make test-unit`

---

- [ ] 3. Run full verification and create PR

  **What to do**:
  - Run `uv run make verify` (all linters: black, pylint, pyright, ruff, docstyle)
  - Run `uv run make test-unit` (full test suite)
  - Fix any failures
  - Create PR against `lightspeed-core/lightspeed-stack` with:
    - Title: "RSPEED-2875: enforce input size limits on /v1/infer and /responses"
    - Body summarizing both changes, linking RSPEED-2875 and RSPEED-2855
  - Push branch and open PR

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Task 1, Task 2

  **Acceptance Criteria**:
  - [ ] `uv run make verify` passes
  - [ ] `uv run make test-unit` passes
  - [ ] PR opened with clear description
  - [ ] PR URL returned

  **Commit**: NO (already committed in Tasks 1 and 2)

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — Verify both changes landed, limits are correct (32,000 for /v1/infer, 65,536 for /responses), tests pass
- [ ] F2. **Code Quality Review** — `uv run make verify` passes, no `as any`/`@ts-ignore` equivalent, proper docstrings
- [ ] F3. **Scope Fidelity Check** — Only the specified files were changed, no scope creep

---

## Commit Strategy

- Task 1: `fix(rlsapi): raise question max_length from 10240 to 32000 (RSPEED-2875)`
- Task 2: `feat(responses): add input size limit of 64KB via JSON serialization guard (RSPEED-2875)`

---

## Success Criteria

### Verification Commands
```bash
uv run make verify     # Expected: all linters pass
uv run make test-unit  # Expected: all tests pass
```

### Final Checklist
- [ ] `/v1/infer` question field accepts 32,000 chars
- [ ] `/responses` input field rejects payloads > 65,536 bytes (JSON-serialized)
- [ ] Clear error messages on rejection
- [ ] All tests pass
- [ ] PR opened
