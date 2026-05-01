# Spike for Agent Skills Support

## Overview

**The problem**: Lightspeed Core has no mechanism for extending agent capabilities with specialized instructions or domain knowledge. Users cannot package reusable workflows, troubleshooting guides, or domain expertise into portable, discoverable units that the LLM can use on demand.

**The recommendation**: Implement the [Agent Skills open standard](https://agentskills.io) with filesystem-based discovery. Config specifies paths to skill directories; skill metadata (name, description) is read from `SKILL.md` frontmatter at startup. The LLM discovers available skills via a `list_skills` tool, loads full instructions on demand via an `activate_skill` tool, and retrieves reference files via a `load_skill_resource` tool. The system prompt contains behavioral instructions for how to use these tools, not the skill catalog itself.

**PoC validation**: Not applicable for this spike. The feature is well-defined by the agentskills.io specification and has been implemented by 30+ agent products including Claude Code, GitHub Copilot, Cursor, and OpenAI Codex.

## Decisions for @sbunciak and @ptisnovs

These are the high-level decisions that determine scope, approach, and cost. Each has a recommendation confirmed during spike research.

### Decision 1: Which skill types to support?

| Option | Description |
|--------|-------------|
| A | Built-in skills only (Lightspeed Core developers ship pre-defined skills) |
| B | Product team-defined only (LS app teams like RHEL Lightspeed define their own skills) |
| C | Both built-in and product team-defined |

**Recommendation**: **B** (Product team-defined only). This allows LS app teams (e.g., RHEL Lightspeed, Ansible Lightspeed) to extend Lightspeed with domain-specific skills without requiring changes to Lightspeed Core. Product teams ship skills alongside the lightspeed-stack container by mounting skill directories via ConfigMaps or container volumes, then specifying the paths in `lightspeed-stack.yaml`. Skill content is read from `SKILL.md` files at startup. Built-in skills can be added to Lightspeed Core later if common patterns emerge.

**Note**: End users of LS app products do NOT have the ability to add skills, similar to how they cannot add MCP servers. Skill configuration is controlled by product teams at deployment time.

### Decision 2: Discovery mechanism?

| Option | Description |
|--------|-------------|
| A | Filesystem-based (config specifies paths, skill metadata read from `SKILL.md` files) |
| B | Config-based (full skill definitions inlined in `lightspeed-stack.yaml`) |
| C | API-based (skills registered/managed via REST API) |
| D | Hybrid (built-in via config, product team-defined via filesystem or API) |

**Recommendation**: **A** (Filesystem-based). Config specifies paths to skill directories (or a single directory containing multiple skills). Skill metadata (name, description) is read from `SKILL.md` frontmatter at startup. This keeps config lightweight, avoids bloating the config CR in k8s deployments, and allows skill content to be updated independently of config changes. Skills can be mounted via ConfigMaps, volumes, or any standard filesystem mechanism.

### Decision 3: Script execution support?

| Option | Description |
|--------|-------------|
| A | No scripts (only `SKILL.md` instructions) |
| B | Scripts allowed (full spec compliance) |
| C | Deferred (start with no scripts, add later) |

**Recommendation**: **C** (Deferred). As noted in LCORE-1339, there are security concerns with executing arbitrary scripts. Script support will not be implemented until sandbox support (running scripts in an isolated environment) is added. The core value of skills is in the instructions — scripts can be added in a future phase once sandboxing is available.

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
| A | System prompt catalog (skill catalog embedded in system prompt, LLM decides) |
| B | Tool-based discovery (`list_skills` tool returns catalog, `activate_skill` loads instructions, `load_skill_resource` loads reference files) |
| C | Per-request parameter (client specifies which skills to activate) |
| D | Hybrid (catalog in system prompt if < N skills, tool-based discovery otherwise) |

**Recommendation**: **B** (Tool-based discovery). This approach separates behavioral instructions from skill inventory:

1. **System prompt** contains behavioral instructions only:
   - How to discover skills (`list_skills`)
   - How to activate skills (`activate_skill`)
   - How to load reference files (`load_skill_resource`)
   - Requirement to load full instructions before proceeding

2. **`list_skills` tool** returns the skill catalog (name + description for each skill)

3. **`activate_skill` tool** loads full `SKILL.md` instructions when the LLM decides a skill is relevant

4. **`load_skill_resource` tool** loads files from the skill's `references/` subdirectory when needed

**Rationale**: This pattern follows Google ADK's proven approach and provides a clean evolution path:

| Phase | `list_skills` behavior | Scales to |
|-------|------------------------|-----------|
| Phase 1 (initial) | Returns full catalog | ~20 skills |
| Phase 2 (future) | Accepts optional `query` param for keyword/semantic search | 100+ skills |

The phase 2 extension requires only a tool implementation change, not an architectural change. The system prompt instructions and `activate_skill` tool remain unchanged.

**Alternative considered**: Option A (system prompt catalog) was considered but rejected because:
- Token cost grows linearly with skill count (~50-100 tokens/skill)
- Risk of overwhelming the model context with large skill catalogs
- No clean evolution path to search-based discovery

Option D (hybrid) remains viable for deployments with predictable skill counts, but adds complexity. Teams can revisit if phase 2 search proves unreliable for small catalogs.

### Decision 6: Skill context management

| Option | Description |
|--------|-------------|
| A | Always loaded (all skills' full instructions in every request) |
| B | Progressive disclosure (catalog via tool, full content loaded when LLM requests) |

**Recommendation**: **B** (Progressive disclosure). This follows the agentskills.io pattern:
1. **Catalog** (~50-100 tokens/skill) - name + description returned by `list_skills` tool
2. **Instructions** (<5000 tokens) - full `SKILL.md` body loaded via `activate_skill` tool when needed
3. **Resources** (on-demand) - `references/` files loaded via `load_skill_resource` tool when referenced

This keeps the base context small while giving the LLM access to specialized knowledge on demand.

### Decision 7: Configuration structure

Skills are configured by specifying paths to skill directories in `lightspeed-stack.yaml`. Two forms are supported:

**Option A: Directory of skills** (recommended for most deployments)
```yaml
skills:
  paths:
    - "/var/skills/"  # Directory containing skill subdirectories
```

**Option B: Individual skill paths** (for fine-grained control)
```yaml
skills:
  paths:
    - "/var/skills/code-review/"
    - "/var/skills/troubleshooting/"
```

Each path points to either:
- A directory containing a `SKILL.md` file (single skill)
- A directory containing subdirectories, each with a `SKILL.md` file (multiple skills)

Skill metadata (`name`, `description`) is read from the `SKILL.md` frontmatter at startup. This keeps config minimal and allows skill content to be managed independently.

**Recommendation**: Approved. This structure keeps the config CR lightweight and decouples skill content from configuration.

## Proposed JIRAs

Each JIRA includes an agentic tool instruction pointing to the spec doc.

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add skill configuration model

**Description**: Add the `SkillsConfiguration` Pydantic model to the main configuration. This enables specifying skill directory paths in `lightspeed-stack.yaml`.

**Scope**:

- Create `SkillsConfiguration` class in `src/models/config.py` with `paths: list[str]` field
- Add `skills: Optional[SkillsConfiguration]` field to `Configuration` class
- Implement startup scanning: resolve paths, find `SKILL.md` files, parse frontmatter
- Add validation: paths exist, contain valid `SKILL.md` files with required frontmatter
- Store parsed skill metadata (name, description, path) for runtime use

**Acceptance criteria**:

- Skill paths can be configured in `lightspeed-stack.yaml` using the documented format
- Startup scans configured paths and discovers all valid skills
- Startup fails with clear error if path doesn't exist or lacks valid `SKILL.md`
- Duplicate skill names across paths are detected and rejected
- Unit tests cover path scanning and validation scenarios

**Agentic tool instruction**:

```text
Read the "Configuration" section in docs/design/agent-skills/agent-skills.md.
Key files: src/models/config.py (around line 1817, Configuration class).
Follow the MCP server config pattern (ModelContextProtocolServer class, line 468).
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement list_skills tool

**Description**: Register a `list_skills` tool that the LLM can call to discover available skills. Returns the skill catalog (name + description for each configured skill).

**Scope**:

- Create `src/utils/skills.py` module with skill catalog management
- Add `list_skills` tool registration in `prepare_tools()` in `src/utils/responses.py`
- Implement tool handler that returns formatted skill catalog (name + description)
- Modify `get_system_prompt()` in `src/utils/prompts.py` to add behavioral instructions for skill discovery, activation, and resource loading

**Acceptance criteria**:

- LLM can call `list_skills()` to get the catalog of available skills
- Tool returns name and description for each configured skill
- Tool returns empty list when no skills are configured
- System prompt includes behavioral instructions (how to use `list_skills`, `activate_skill`, and `load_skill_resource`)
- Unit tests verify tool registration, catalog formatting, and system prompt instructions

**Agentic tool instruction**:

```text
Read the "Tool-based discovery" section in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/responses.py (prepare_tools function, line 204),
src/utils/prompts.py (get_system_prompt function),
src/utils/skills.py (new module).
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement activate_skill tool

**Description**: Register an `activate_skill` tool that the LLM can call to load full skill instructions when it decides a skill is relevant. This complements `list_skills` by providing the detailed instructions for a specific skill.

**Scope**:

- Add `activate_skill` tool registration in `prepare_tools()` in `src/utils/responses.py`
- Implement tool handler that reads `SKILL.md` body content
- Return structured response with skill content and base directory path
- Optionally list `references/` files if present

**Acceptance criteria**:

- LLM can call `activate_skill(name="skill-name")` to load skill instructions
- Tool returns full `SKILL.md` body content (after frontmatter)
- Tool returns skill directory path so LLM can resolve relative references
- Tool returns list of available reference files if `references/` directory exists
- Tool returns error if skill name is invalid or not found in catalog
- Unit tests cover tool registration and invocation

**Agentic tool instruction**:

```text
Read the "Skill activation tool" section in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/responses.py (prepare_tools function, line 204),
src/utils/skills.py.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement load_skill_resource tool

**Description**: Register a `load_skill_resource` tool that the LLM can call to load files from a skill's `references/` subdirectory. This is the third skill tool, complementing `list_skills` and `activate_skill`.

**Scope**:

- Add `load_skill_resource` tool registration in `prepare_tools()` in `src/utils/responses.py`
- Implement tool handler that reads files from skill `references/` directories
- Add path validation to restrict access to configured skill directories only
- Return file content wrapped in structured tags

**Acceptance criteria**:

- LLM can call `load_skill_resource(skill_name="skill-name", path="references/guide.md")` to load a reference file
- Tool returns file content for valid paths within the skill's directory
- Tool returns error if skill name is invalid or path is outside skill directory
- Access is restricted to configured skill directories (no arbitrary filesystem access)
- Integration test verifies reference file access works end-to-end

**Agentic tool instruction**:

```text
Read the "load_skill_resource tool" section in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/responses.py (prepare_tools function, line 204),
src/utils/skills.py.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Wire skill tools into request flow

**Description**: Integrate the three skill tools (`list_skills`, `activate_skill`, `load_skill_resource`) into the request processing flow. This includes tool registration, invocation handling, and context management.

**Scope**:

- Register all three skill tools when skills are configured
- Add tool invocation routing in the response handler to dispatch skill tool calls
- Integrate skill behavioral instructions into `get_system_prompt()`
- Implement `SkillTracker` for per-conversation activation deduplication
- Ensure skill content (`<skill_content>`, `<skill_resource>` tags) is protected from context compaction

**Acceptance criteria**:

- All three skill tools are registered when skills are configured in `lightspeed-stack.yaml`
- Tool invocations are correctly routed to their handlers in `src/utils/skills.py`
- System prompt includes behavioral instructions when skills are configured
- Duplicate skill activations within a conversation return a note instead of re-injecting content
- Skill content in conversation context is preserved during compaction
- Integration test verifies end-to-end flow: list → activate → load_resource

**Agentic tool instruction**:

```text
Read the "Skill tools" and "Context management" sections in docs/design/agent-skills/agent-skills.md.
Key files: src/utils/responses.py (prepare_tools, response handling),
src/utils/prompts.py (get_system_prompt),
src/utils/skills.py (tool handlers, SkillTracker).
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
### LCORE-???? Add integration tests for skills

**Description**: Add integration tests to verify skill loading, catalog injection, and tool invocation with mocked LLM responses.

**Scope**:

- Test skill configuration loading and validation
- Test catalog generation with skills injected
- Test tool invocation handling with mocked LLM

**Acceptance criteria**:

- Integration tests cover skill configuration, catalog generation, and tool handling
- Tests use example skills from `examples/skills/`
- Tests mock LLM responses to verify tool invocation flow

**Agentic tool instruction**:

```text
Read the "Testing" section in docs/design/agent-skills/agent-skills.md.
Key test files: tests/integration/endpoints/.
Follow existing integration test patterns in the codebase.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add E2E feature file for skills

**Description**: Write Gherkin feature file(s) defining E2E test scenarios for the skills feature.

**Scope**:

- Define feature file with scenarios for skill discovery and usage
- Cover skill activation via conversation
- Include scenarios for skill tool invocation

**Acceptance criteria**:

- Feature file(s) created in `tests/e2e/features/`
- Scenarios cover skill discovery, activation, and usage
- Scenarios use example skills from `examples/skills/`
- Feature file follows existing Gherkin patterns in the codebase

**Agentic tool instruction**:

```text
Read the "Testing" section in docs/design/agent-skills/agent-skills.md.
Key test files: tests/e2e/features/*.feature.
Follow existing feature file patterns in the codebase.
```

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement E2E step definitions for skills

**Description**: Implement the step definitions to support the skills E2E feature file scenarios.

**Scope**:

- Implement step definitions for skill-related Gherkin steps
- Handle skill configuration setup in test environment
- Verify skill tool invocation and responses

**Acceptance criteria**:

- Step definitions implemented in `tests/e2e/features/steps/`
- All scenarios in the skills feature file pass
- Steps follow existing step definition patterns in the codebase

**Agentic tool instruction**:

```text
Read the "Testing" section in docs/design/agent-skills/agent-skills.md.
Key test files: tests/e2e/features/steps/.
Follow existing step definition patterns using behave framework.
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
| 1. Catalog | Name + description | LLM calls `list_skills` | ~50-100 tokens/skill |
| 2. Instructions | Full SKILL.md body | LLM calls `activate_skill` | <5000 tokens (recommended) |
| 3. Resources | References, assets | LLM calls `load_skill_resource` | Varies |

This keeps base context small while giving the LLM access to specialized knowledge on demand. The system prompt contains only behavioral instructions (~200 tokens) regardless of skill count.

### Adoption

Agent Skills are supported by 30+ agent products including:
- Claude Code, Claude.ai
- GitHub Copilot, VS Code
- Cursor, OpenAI Codex
- Gemini CLI, JetBrains Junie
- Goose, Letta, Spring AI

OpenAI's SDK already includes `LocalSkill` and `Skill` types in its responses module.

### Security considerations

**Scripts deferred**: The `scripts/` subdirectory is not supported in this implementation. As noted in LCORE-1339, executing arbitrary scripts poses security risks. Script support will be added in a future phase once sandbox support (running scripts in an isolated environment) is available.

**Path restrictions**: The `activate_skill` tool and reference file access are restricted to configured skill directories. The LLM cannot access arbitrary filesystem paths through skills.

**Trust model**: Skills are configured by LS app teams (e.g., RHEL Lightspeed) at deployment time, not by end users. Product teams mount skill directories into the container via ConfigMaps or volumes and specify the paths in `lightspeed-stack.yaml`. This mirrors the MCP server trust model — end users cannot add arbitrary skills, only use the skills their product team has deployed.

## Appendix A: Existing approaches research

### How other tools handle skills

| Tool | Discovery | Activation | Script support |
|------|-----------|------------|----------------|
| Claude Code | Filesystem scan | File-read or /command | Yes |
| GitHub Copilot | Filesystem scan | System prompt + tool | Yes |
| Cursor | Filesystem scan | System prompt + tool | Yes |
| OpenAI Codex | API-based | API-based | Yes |
| Google ADK | `list_skills` tool | `load_skill` + `load_skill_resource` tools | Yes (`run_skill_script`) |

**Note**: Google ADK's approach aligns with our recommendation. They use three tools: `list_skills` returns the catalog, `load_skill` loads instructions, and `load_skill_resource` loads reference files. Their system prompt contains behavioral instructions (how to use the tools), not the skill catalog itself.

### Alternative designs considered

**Full config-based definitions**: Rejected in favor of filesystem-based with config paths. Inlining full skill definitions (name, description, instructions) in `lightspeed-stack.yaml` would bloat the config CR in k8s deployments and couple skill content updates to config changes. Instead, config specifies paths and skill metadata is read from `SKILL.md` files.

**Inline content**: Rejected in favor of path-based. Inline content would clutter the YAML config for multi-skill deployments and doesn't support reference files.

**Always-loaded instructions**: Rejected in favor of progressive disclosure. Loading all skill instructions upfront wastes context tokens and doesn't scale to many skills.

**System prompt catalog injection**: Rejected in favor of tool-based discovery (`list_skills`). Embedding the skill catalog directly in the system prompt:
- Increases token cost linearly with skill count (~50-100 tokens/skill)
- Risks overwhelming the model context with large skill catalogs
- Provides no clean evolution path to search-based discovery
The tool-based approach keeps the system prompt constant (behavioral instructions only) and allows phase 2 extension to semantic search without architectural changes.

## Appendix B: Reference sources

- Agent Skills Specification: https://agentskills.io/specification
- Agent Skills Implementation Guide: https://agentskills.io/client-implementation/adding-skills-support
- Agent Skills GitHub: https://github.com/agentskills/agentskills
- Example Skills: https://github.com/anthropics/skills
