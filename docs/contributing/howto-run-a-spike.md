# How to run a spike

A spike is a time-boxed research task that produces a design recommendation and
proposed JIRAs.  This document describes how to run one in the Lightspeed Core
project.

**Claude Code shortcut**: `/spike` runs this process interactively. You can
also use `/spike LCORE-1234` or `/spike 1234` (default project is LCORE, so
the `LCORE-` prefix gets prepended automatically) to have Claude Code fetch
the respective JIRA ticket using `dev-tools/fetch-jira.sh`.

## Outputs

A spike produces:

1. **Spike doc** — decisions with recommendations, design alternatives with
   pros/cons, proposed JIRAs.  Use
   [spike-template.md](templates/spike-template.md).
2. **Spec doc** — permanent in-repo feature spec (requirements, use cases,
   architecture, implementation suggestions).  Use
   [spec-doc-template.md](templates/spec-doc-template.md).  See
   [howto-write-a-spec-doc.md](howto-write-a-spec-doc.md) for details.
3. **PoC** (optional but recommended) — working prototype that validates the
   core mechanism.  Not production code.
4. **PoC validation results** (if PoC was done) — structured evidence.  See
   [howto-organize-poc-output.md](howto-organize-poc-output.md).

## Process

### 1. Set up

- Create a feature branch: `lcore-XXXX-spike-short-description` off
  `upstream/main`.

### 2. Research

- **Current state**: Document how the relevant part of the system works today.
  Include code references (file:line).
- **Existing approaches**: How do other APIs, tools, or frameworks solve the
  same problem?  Focus on the most relevant ones, not an exhaustive survey.
- **Gaps**: What capabilities are missing in the codebase for this feature
  (e.g., no token estimation, no schema for summaries)?

> **Example (LCORE-1311 conversation compaction spike):** Researched OpenAI,
> Anthropic, and Bedrock APIs for compaction approaches.  Identified that
> lightspeed-stack has no token estimation capability.

### 3. Design alternatives

Identify the viable design alternatives.  For each, document:

- What it does
- Implementation sketch
- Pros/cons table
- Verdict (recommended / possible for later / too complex)

Don't include alternatives that are obviously bad.  Only include alternatives
that are genuinely worth considering.

### 4. Build a PoC (recommended)

A PoC validates that the core mechanism works.  It is explicitly not production
code — cut corners on error handling, config, scope, and edge cases.

What to include:
- The minimum code to prove the mechanism works.
- Unit tests for the core logic.
- Pass `uv run make format && uv run make verify`.

What to skip:
- Production config integration.
- Error handling beyond the happy path.

After building, run the PoC against a real stack to verify it works end-to-end.
Document the results in a structured evidence directory (see
[howto-organize-poc-output.md](howto-organize-poc-output.md)).

> **Example (LCORE-1311 conversation compaction spike):** Built a recursive
> summarization PoC, ran a 50-query experiment with probe questions at
> intervals to test context fidelity.

### 5. Write the spike doc

Use [spike-template.md](templates/spike-template.md).

Key principles:
- **Decisions up front, background below.**  The first sections should be the
  decisions that need confirmation.  Background (current architecture, API
  research, etc.) goes in later sections and is linked from the decisions.
- **Split decisions by audience.**  Strategic decisions (approach, model,
  threshold strategy) go in a section for the decision-makers and relevant
  stakeholders.  Technical decisions (storage schema, field naming, buffer
  calculation) go in a section for the tech lead and relevant team members.
- **Proposed JIRAs** follow the decisions.  Each JIRA should have: Description,
  Scope, Acceptance Criteria, and an Agentic tool instruction pointing to the
  spec doc.  Use [jira-ticket-template.md](templates/jira-ticket-template.md).

### 6. Write the spec doc

Use [spec-doc-template.md](templates/spec-doc-template.md) and see
[howto-write-a-spec-doc.md](howto-write-a-spec-doc.md).

The spec doc assumes all recommendations are accepted.  It is the permanent
in-repo reference for implementation.  If a decision is overridden during
review, update the spec doc accordingly.

### 7. Open the PR

Use [spike-pr-template.md](templates/spike-pr-template.md).

The PR should contain:
- The spike doc and spec doc (in `docs/design/<feature>/`).
- PoC code and tests (will be removed before merge).
- PoC validation results (will be removed before merge).

In the PR description:
- List the decisions that need confirmation, with links to the specific lines
  in the spike doc.
- Point reviewers to the "Proposed JIRAs" section for JIRA review.
- Note which sections need reviewer input and which are background reference.

**Constructing review links**: Use the full commit hash with `?plain=1` for
line references in markdown files on GitHub.  Format:
```
https://github.com/ORG/REPO/blob/FULL_COMMIT_HASH/path/to/file.md?plain=1#L10-L25
```
Without `?plain=1`, GitHub renders the markdown and line anchors don't work.

> **Example (LCORE-1311 conversation compaction spike):** PR grouped reviewer
> asks into strategic decisions (5 items), technical decisions (4 items), and
> proposed JIRAs — each with links to the specific sections.

### 8. Incorporate reviewer feedback

When reviewers comment or an external review comes in:

1. Update both the spike doc and spec doc to reflect adopted changes.
2. Post a re-review request in the PR tagging the decision-makers.  Group
   by action needed:
   - **New decisions** to confirm (link to each)
   - **Changed decisions** to re-confirm (link to each)
   - **Updated JIRAs** to review (link to each)

> **Example (LCORE-1311 conversation compaction spike):** Reviewer suggested
> marker-based conversation handling instead of bypassing the `conversation`
> parameter.  Adopted the suggestion, updated
> [Decision 6](../design/conversation-compaction/conversation-compaction-spike.md)
> in the spike doc and R10 in the spec doc.

### 9. File JIRAs

Once all decisions are confirmed:

1. Update the parent feature ticket description to point to the spec doc.
2. File sub-JIRAs under the parent ticket using
   [jira-ticket-template.md](templates/jira-ticket-template.md).
   Use `dev-tools/file-jiras.sh --spike-doc <path> --feature-ticket <key>`
   to parse and file them from the spike doc (Claude Code shortcut:
   `/file-jiras`).  The script auto-creates an Epic under the feature
   ticket and files children under it.
3. Ensure all four categories are covered across the filed tickets:
   implementation, integration tests, e2e tests, and documentation.
   Not every category needs its own ticket — combine where it makes sense.
4. Each sub-JIRA's agentic tool instruction should point to the **spec doc**
   (not the spike doc), since the spec doc is the permanent reference.
5. After filing, update the spike doc: replace `LCORE-????` placeholders with
   the actual ticket keys.  The filed ticket files in
   `docs/design/<feature>/jiras/` have `<!-- key: LCORE-XXXX -->` metadata
   that maps each ticket to its filed key.

### 10. Prepare for merge

Before merging:

- **Keep**: spec doc, spike doc.
- **Remove**: PoC code, PoC validation results, test config files, experiment
  scripts.
- File the JIRA tickets under the parent ticket (step 9).
- Communicate the merge plan in the PR (what stays, what goes) and get
  acknowledgement before merging.

The spike doc stays in the repo because it records decision rationale, PoC
evidence, and the design space explored — context that the spec doc doesn't
capture.

## Checklist

```
[ ] Branch created off upstream/main
[ ] Current state documented
[ ] Existing approaches researched
[ ] Design alternatives documented with pros/cons
[ ] PoC built and validated (if applicable)
[ ] Spike doc written (decisions up front, background below)
[ ] Spec doc written (with accepted recommendations)
[ ] PR opened with structured reviewer asks
[ ] Reviewer feedback incorporated
[ ] JIRAs filed under parent ticket
[ ] PoC code and experiment data removed before merge
[ ] Spike doc and spec doc remain in merge
```
