# Spike for Agent Skills Support

## Overview

**The problem**: Lightspeed Core has no mechanism for extending agent capabilities with specialized instructions or domain knowledge. Users cannot package reusable workflows, troubleshooting guides, or domain expertise into portable, discoverable units that the LLM can use on demand.

**The recommendation**: Implement the [Agent Skills open standard](https://agentskills.io) with a config-based discovery model. Skills are defined in `lightspeed-stack.yaml` pointing to directories containing `SKILL.md` files. The LLM sees a skill catalog (name + description) in the system prompt and can request full instructions on demand via a dedicated tool.

**PoC validation**: Not applicable for this spike. The feature is well-defined by the agentskills.io specification and has been implemented by 30+ agent products including Claude Code, GitHub Copilot, Cursor, and OpenAI Codex.

## Decisions for @sbunciak and @ptisnovs

These are the high-level decisions that determine scope, approach, and cost. Each has a recommendation confirmed during spike research.

### Decision 1: Which skill types to support?

| Option | Description |
|--------|-------------|
| A | Built-in skills only (Lightspeed developers ship pre-defined skills) |
| B | Customer-defined only (end users import their own skill definitions) |
| C | Both built-in and customer-defined |

**Recommendation**: **B** (Customer-defined only). This allows end users to extend Lightspeed with their own domain expertise without requiring changes to the core product. Built-in skills can be added later if needed.

### Decision 2: Discovery mechanism?

| Option | Description |
|--------|-------------|
| A | Filesystem-based (scan configured directories for `SKILL.md` files) |
| B | Config-based (define skills in `lightspeed-stack.yaml`) |
| C | API-based (skills registered/managed via REST API) |
| D | Hybrid (built-in via config, customer-defined via filesystem or API) |

**Recommendation**: **B** (Config-based). Skills are defined in `lightspeed-stack.yaml` similar to `mcp_servers`. This provides explicit control over which skills are available, integrates with existing configuration patterns, and avoids filesystem scanning complexity.

### Decision 3: Script execution support?

| Option | Description |
|--------|-------------|
| A | No scripts (only `SKILL.md` instructions) |
| B | Scripts allowed (full spec compliance) |
| C | Deferred (start with no scripts, add later) |

**Recommendation**: **A** (No scripts). As noted in LCORE-1339, there are security concerns with executing arbitrary scripts. The core value of skills is in the instructions — scripts can be added in a future phase after security review if needed.

## Technical decisions for @ptisnovs

Architecture-level and implementation-level decisions.

### Decision 4: Skill content source

| Option | Description |
|--------|-------------|
| A | Path-based (config points to directory containing `SKILL.md`) |
| B | Inline (instructions embedded directly in YAML) |
| C | Both (support either path or inline content) |

**Recommendation**: **A** (Path-based). This follows the agentskills.io spec directory structure, keeps the YAML config clean, and allows skills to include `references/` subdirectories for additional documentation that can be loaded on demand.

### Decision 5: Activation mechanism

| Option | Description |
|--------|-------------|
| A | System prompt injection (skill catalog in system prompt, LLM decides) |
| B | Dedicated tool (register `activate_skill` tool, LLM calls to load) |
| C | Per-request parameter (client specifies which skills to activate) |

**Recommendation**: **A** (System prompt injection) for the catalog, combined with **B** (dedicated tool) for loading full instructions. The system prompt contains the skill catalog (name + description, ~50-100 tokens per skill). When the LLM decides a skill is relevant, it calls the `activate_skill` tool to load the full instructions.

### Decision 6: Skill context management

| Option | Description |
|--------|-------------|
| A | Always loaded (all skills' full instructions in every request) |
| B | Catalog + on-demand (only name/description upfront, full content loaded when LLM requests) |

**Recommendation**: **B** (Catalog + on-demand). This follows the agentskills.io progressive disclosure pattern:
1. **Catalog** (~50-100 tokens/skill) - name + description always in system prompt
2. **Instructions** (<5000 tokens) - full `SKILL.md` body loaded via tool when needed
3. **Resources** (on-demand) - `references/` files loaded via file-read tool when referenced

This keeps the base context small while giving the LLM access to specialized knowledge on demand.

### Decision 7: Configuration structure

Skills are configured as a list in `lightspeed-stack.yaml`, following the `mcp_servers` pattern:

```yaml
skills:
  - name: "code-review"
    description: "Review code for best practices and security issues."
    path: "/var/skills/code-review"
  - name: "troubleshooting"
    description: "Diagnose and fix OpenShift deployment issues."
    path: "/var/skills/troubleshooting"
```

Each skill entry specifies:
- `name`: Unique identifier (validated against `SKILL.md` frontmatter)
- `description`: What the skill does and when to use it
- `path`: Absolute path to directory containing `SKILL.md`

**Recommendation**: Approved. This structure is consistent with existing config patterns and provides explicit control.

## Proposed JIRAs

Each JIRA includes an agentic tool instruction pointing to the spec doc.

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add skill configuration model

**Description**: Add the `SkillConfiguration` Pydantic model and `skills` list to the main configuration. This enables defining skills in `lightspeed-stack.yaml`.

**Scope**:

- Create `SkillConfiguration` class in `src/models/config.py`
- Add `skills: list[SkillConfiguration]` field to `Configuration` class
- Add validation: path exists, contains `SKILL.md`, name matches frontmatter
- Parse `SKILL.md` frontmatter on startup (extract name, description)

**Acceptance criteria**:

- Skills can be defined in `lightspeed-stack.yaml` using the documented format
- Startup fails with clear error if skill path doesn't exist or lacks `SKILL.md`
- Startup fails if configured `name` doesn't match `SKILL.md` frontmatter `name`
- Unit tests cover validation scenarios

**Agentic tool instruction**:

```text
Read the "Configuration" section in docs/design/agent-skills/agent-skills.md.
Key files: src/models/config.py (around line 1817, Configuration class).
Follow the MCP server config pattern (ModelContextProtocolServer class, line 468).
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement skill catalog injection

**Description**: Inject the skill catalog (name + description for each skill) into the system prompt so the LLM knows what skills are available.

**Scope**:

- Create `src/utils/skills.py` module
- Implement `build_skill_catalog()` function that formats skills as XML/structured text
- Modify `get_system_prompt()` in `src/utils/prompts.py` to append skill catalog
- Add behavioral instructions telling the LLM how to use skills

**Acceptance criteria**:

- System prompt includes skill catalog when skills are configured
- Catalog format includes name, description, and path for each skill
- Catalog is omitted when no skills are configured
- Unit tests verify catalog formatting and system prompt injection

**Agentic tool instruction**:

```text
Read the "System prompt injection" section in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/prompts.py (get_system_prompt function),
src/utils/skills.py (new module).
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement activate_skill tool

**Description**: Register a `activate_skill` tool that the LLM can call to load full skill instructions when it decides a skill is relevant.

**Scope**:

- Add `activate_skill` tool registration in `prepare_tools()` in `src/utils/responses.py`
- Implement tool handler that reads `SKILL.md` body content
- Return structured response with skill content and base directory path
- Optionally list `references/` files if present

**Acceptance criteria**:

- LLM can call `activate_skill(name="skill-name")` to load skill instructions
- Tool returns full `SKILL.md` body content (after frontmatter)
- Tool returns skill directory path so LLM can resolve relative references
- Tool returns error if skill name is invalid
- Unit tests cover tool registration and invocation

**Agentic tool instruction**:

```text
Read the "Skill activation tool" section in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/responses.py (prepare_tools function, line 204),
src/utils/skills.py.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add skill reference file access

**Description**: Enable the LLM to read files from the skill's `references/` subdirectory when skill instructions reference them.

**Scope**:

- Ensure existing file-read tool can access skill reference directories
- Add path validation to restrict access to configured skill directories only
- Document the pattern for skill authors to reference files

**Acceptance criteria**:

- LLM can read files from `<skill-path>/references/` using existing file-read capability
- Access is restricted to configured skill directories (no arbitrary filesystem access)
- Skill instructions can use relative paths like `references/troubleshooting-guide.md`
- Integration test verifies reference file access works end-to-end

**Agentic tool instruction**:

```text
Read the "Reference file access" section in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/responses.py, existing file-read tool implementation.
```

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Document Agent Skills feature

**Description**: Create user-facing documentation for the Agent Skills feature including configuration guide, skill authoring guide, and examples.

**Scope**:

- Add configuration documentation to existing config docs
- Create skill authoring guide (SKILL.md format, directory structure)
- Add example skills to `examples/skills/`
- Update README with feature overview

**Acceptance criteria**:

- Users can configure skills by following the documentation
- Skill authors can create compliant skills using the authoring guide
- Example skills demonstrate common use cases (troubleshooting, code review, etc.)

**Agentic tool instruction**:

```text
Read the full spec doc at docs/design/agent-skills/agent-skills.md.
Reference the agentskills.io specification for SKILL.md format details.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add integration and E2E tests for skills

**Description**: Add integration tests and E2E tests to verify the skills feature works correctly end-to-end.

**Scope**:

- Integration tests: skill loading, catalog injection, tool invocation with mocked LLM
- E2E tests: full flow with real LLM, verify skill activation and usage

**Acceptance criteria**:

- Integration tests cover skill configuration, catalog generation, and tool handling
- E2E tests verify a configured skill can be discovered and used by the LLM
- Tests use example skills from `examples/skills/`

**Agentic tool instruction**:

```text
Read the "Testing" section in docs/design/agent-skills/agent-skills.md.
Key test files: tests/integration/endpoints/, tests/e2e/features/.
Follow existing test patterns in the codebase.
```

## Background sections

### Agent Skills specification

The [Agent Skills open standard](https://agentskills.io) defines a portable format for giving AI agents specialized capabilities. Key elements:

**Directory structure**:
```
skill-name/
├── SKILL.md          # Required: metadata + instructions
├── references/       # Optional: additional documentation
└── assets/           # Optional: templates, resources
```

**SKILL.md format**:
```markdown
---
name: skill-name
description: What this skill does and when to use it.
---

# Instructions

Step-by-step instructions for the agent...
```

**Frontmatter fields**:
| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | 1-64 chars, lowercase, hyphens only |
| `description` | Yes | Max 1024 chars, describes what and when |
| `license` | No | License name or file reference |
| `compatibility` | No | Environment requirements |
| `metadata` | No | Arbitrary key-value pairs |

### Progressive disclosure

The agentskills.io spec recommends a three-tier loading strategy:

| Tier | What's loaded | When | Token cost |
|------|---------------|------|------------|
| 1. Catalog | Name + description | Session start | ~50-100 tokens/skill |
| 2. Instructions | Full SKILL.md body | When skill is activated | <5000 tokens (recommended) |
| 3. Resources | References, assets | When instructions reference them | Varies |

This keeps base context small while giving the LLM access to specialized knowledge on demand.

### Adoption

Agent Skills are supported by 30+ agent products including:
- Claude Code, Claude.ai
- GitHub Copilot, VS Code
- Cursor, OpenAI Codex
- Gemini CLI, JetBrains Junie
- Goose, Letta, Spring AI

OpenAI's SDK already includes `LocalSkill` and `Skill` types in its responses module.

### Security considerations

**Scripts excluded**: The `scripts/` subdirectory is not supported in this implementation. As noted in LCORE-1339, executing arbitrary scripts poses security risks. Skills provide value through instructions; script support can be evaluated in a future phase.

**Path restrictions**: The `activate_skill` tool and reference file access are restricted to configured skill directories. The LLM cannot access arbitrary filesystem paths through skills.

**Trust model**: Since skills are configured by administrators in `lightspeed-stack.yaml`, there's an implicit trust that configured skill paths contain appropriate content.

## Appendix A: Existing approaches research

### How other tools handle skills

| Tool | Discovery | Activation | Script support |
|------|-----------|------------|----------------|
| Claude Code | Filesystem scan | File-read or /command | Yes |
| GitHub Copilot | Filesystem scan | System prompt + tool | Yes |
| Cursor | Filesystem scan | System prompt + tool | Yes |
| OpenAI Codex | API-based | API-based | Yes |

### Alternative designs considered

**Filesystem scanning**: Rejected in favor of config-based discovery. Filesystem scanning adds complexity, requires directory configuration anyway, and could inadvertently load untrusted skills from cloned repositories.

**Inline content**: Rejected in favor of path-based. Inline content would clutter the YAML config for multi-skill deployments and doesn't support reference files.

**Always-loaded instructions**: Rejected in favor of catalog + on-demand. Loading all skill instructions upfront wastes context tokens and doesn't scale to many skills.

## Appendix B: Reference sources

- Agent Skills Specification: https://agentskills.io/specification
- Agent Skills Implementation Guide: https://agentskills.io/client-implementation/adding-skills-support
- Agent Skills GitHub: https://github.com/agentskills/agentskills
- Example Skills: https://github.com/anthropics/skills
