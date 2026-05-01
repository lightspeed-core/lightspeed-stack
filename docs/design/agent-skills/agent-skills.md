# Feature design for Agent Skills Support

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-04-09                                |
| **Component**      | Core / Configuration / Utils              |
| **Authors**        | @jboos                                    |
| **Feature**        | [LCORE-1339](https://redhat.atlassian.net/browse/LCORE-1339) |
| **Spike**          | [LCORE-1594](https://redhat.atlassian.net/browse/LCORE-1594) |
| **Links**          | [agentskills.io](https://agentskills.io)  |

## What

Agent Skills support allows LS app teams (e.g., RHEL Lightspeed, Ansible Lightspeed) to extend Lightspeed Core with specialized instructions and domain knowledge packaged as portable skill directories. Skills follow the [Agent Skills open standard](https://agentskills.io). Product teams ship skills alongside the lightspeed-stack container by mounting skill directories via ConfigMaps or container volumes, then specifying the paths in `lightspeed-stack.yaml`. Skill metadata (name, description) is read from `SKILL.md` frontmatter at startup.

**Note**: End users of LS app products do NOT have the ability to add skills, similar to how they cannot add MCP servers. Skill configuration is controlled by product teams at deployment time.

The LLM discovers available skills via a `list_skills` tool, loads full instructions on demand via an `activate_skill` tool, and retrieves reference files via a `load_skill_resource` tool. The system prompt contains behavioral instructions for how to use these tools, not the skill catalog itself.

## Why

Today, Lightspeed Core has limited customization options:
- System prompt can be overridden globally or per-request
- MCP tools provide external capabilities

However, there's no mechanism for:
- Packaging reusable workflows or troubleshooting guides
- Providing domain-specific expertise the LLM can use on demand
- Sharing knowledge across deployments in a portable format

Skills solve this by giving the LLM access to procedural knowledge and domain-specific context it can load when relevant to the current task.

## Requirements

- **R1:** Skill paths are specified in `lightspeed-stack.yaml`; name and description are read from `SKILL.md` frontmatter
- **R2:** Each skill path must point to a directory containing a valid `SKILL.md` file
- **R3:** The system prompt contains behavioral instructions for skill discovery and activation
- **R4:** The LLM can discover skills via `list_skills` tool, load full instructions via `activate_skill` tool, and load reference files via `load_skill_resource` tool
- **R5:** Skill content is returned with structured wrapping (`<skill_content>` and `<skill_resource>` tags) per agentskills.io spec
- **R6:** The LLM can load files from a skill's `references/` subdirectory via `load_skill_resource` tool (path-restricted)
- **R7:** Script execution (`scripts/` subdirectory) is not supported
- **R8:** Skill configuration is validated at startup with clear error messages
- **R9:** Activated skills are tracked per conversation to prevent duplicate injection
- **R10:** Skill content is protected from context compaction

## Use Cases

- **U1:** As an LS app team administrator, I want to configure troubleshooting skills so that the LLM can help users diagnose common issues
- **U2:** As a skill author, I want to create a SKILL.md file with instructions so that I can package domain expertise portably
- **U3:** As a user, I want the LLM to automatically use relevant skills so that I get better answers without manually specifying which skill to use
- **U4:** As an LS app team, I want to deploy domain-specific skills so that the LLM understands product-specific processes and terminology

## Architecture

### Overview

```text
Startup:
  lightspeed-stack.yaml
         │
         ▼
  ┌─────────────────┐
  │ Parse skills    │──► Validate paths, read SKILL.md frontmatter
  │ configuration   │
  └─────────────────┘
         │
         ▼
  ┌─────────────────┐
  │ Build skill     │──► name + description for each skill
  │ catalog         │
  └─────────────────┘

Request flow:
  ┌─────────────────┐
  │ Query request   │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ Build system    │──► Append behavioral instructions (how to use skill tools)
  │ prompt          │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ Register tools  │──► Add list_skills + activate_skill + load_skill_resource tools
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ LLM processes   │──► May call list_skills to discover available skills
  │ request         │
  └────────┬────────┘
           │
           ▼ (if skill relevant)
  ┌─────────────────┐
  │ activate_skill  │──► Returns <skill_content> with body + resource list
  │ tool invocation │
  └────────┬────────┘
           │
           ▼ (if resource needed)
  ┌──────────────────────┐
  │ load_skill_resource  │──► Returns <skill_resource> with file content
  │ tool invocation      │
  └──────────┬───────────┘
             │
             ▼
  ┌─────────────────┐
  │ LLM uses skill  │──► Follows instructions with loaded resources
  │ instructions    │
  └─────────────────┘
```

### Configuration

Skills are configured by specifying paths in `lightspeed-stack.yaml`. Two forms are supported:

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
    - "/var/skills/openshift-troubleshooting/"
    - "/var/skills/code-review/"
```

Each path points to either:
- A directory containing a `SKILL.md` file (single skill)
- A directory containing subdirectories, each with a `SKILL.md` file (multiple skills)

Skill metadata (`name`, `description`) is read from the `SKILL.md` frontmatter at startup.

Each skill directory must contain a `SKILL.md` file:

```
/var/skills/openshift-troubleshooting/
├── SKILL.md              # Required
└── references/           # Optional
    ├── common-errors.md
    └── networking-guide.md
```

Configuration class:

```python
class SkillsConfiguration(ConfigurationBase):
    """Agent skills configuration.

    Specifies paths to skill directories. Skill metadata (name, description)
    is read from SKILL.md frontmatter at startup.
    """

    paths: list[str] = Field(
        default_factory=list,
        title="Skill paths",
        description="Paths to skill directories or directories containing skill subdirectories.",
    )
```

Add to `Configuration` class:

```python
skills: Optional[SkillsConfiguration] = Field(
    default=None,
    title="Agent skills",
    description="Agent skills configuration. Specifies paths to skill directories.",
)
```

Runtime skill data (populated at startup after scanning paths):

```python
@dataclass
class LoadedSkill:
    """Skill loaded from filesystem at startup."""

    name: str
    description: str
    path: Path
    content: str  # SKILL.md body after frontmatter
    references: list[str]  # Files in references/ subdirectory
```

Startup scanning logic:

```python
def load_skills(config: SkillsConfiguration) -> list[LoadedSkill]:
    """Scan configured paths and load all valid skills.

    Each path can be:
    - A directory containing SKILL.md (single skill)
    - A directory containing subdirectories with SKILL.md (multiple skills)
    """
    skills = []
    seen_names: set[str] = set()

    for path_str in config.paths:
        path = Path(path_str)
        if not path.is_dir():
            raise ValueError(f"Skill path does not exist: {path}")

        skill_md = path / "SKILL.md"
        if skill_md.is_file():
            # Single skill directory
            skill = _load_skill_from_dir(path)
            if skill.name in seen_names:
                raise ValueError(f"Duplicate skill name: {skill.name}")
            seen_names.add(skill.name)
            skills.append(skill)
        else:
            # Directory of skill subdirectories
            for subdir in path.iterdir():
                if subdir.is_dir() and (subdir / "SKILL.md").is_file():
                    skill = _load_skill_from_dir(subdir)
                    if skill.name in seen_names:
                        raise ValueError(f"Duplicate skill name: {skill.name}")
                    seen_names.add(skill.name)
                    skills.append(skill)

    return skills
```

### System prompt injection

Behavioral instructions are appended to the system prompt following the [agentskills.io implementation guide](https://agentskills.io/client-implementation/adding-skills-support). The system prompt contains instructions for how to use the skill tools, not the skill catalog itself.

#### Behavioral instructions

The system prompt includes instructions telling the model how to discover and use skills:

```
# Agent Skills

You have access to specialized skills that provide domain-specific instructions.

To discover available skills, call the list_skills tool. This returns the skill
catalog with name and description for each skill.

When a task matches a skill's description, call the activate_skill tool with
the skill's name to load its full instructions. You MUST load and follow the
skill instructions before proceeding with the task.

If the skill instructions reference files in the skill's references/ directory,
use the load_skill_resource tool to load them. Pass the skill name and the
relative path (e.g., "references/guide.md") to retrieve the file content.
```

#### Implementation

```python
SKILL_BEHAVIORAL_INSTRUCTIONS = """
# Agent Skills

You have access to specialized skills that provide domain-specific instructions.

To discover available skills, call the list_skills tool. This returns the skill
catalog with name and description for each skill.

When a task matches a skill's description, call the activate_skill tool with
the skill's name to load its full instructions. You MUST load and follow the
skill instructions before proceeding with the task.

If the skill instructions reference files in the skill's references/ directory,
use the load_skill_resource tool to load them. Pass the skill name and the
relative path (e.g., "references/guide.md") to retrieve the file content.
"""

def get_skill_instructions(skills: list[LoadedSkill]) -> str:
    """Get behavioral instructions for skill tools.

    Returns empty string if no skills are configured.
    """
    if not skills:
        return ""
    return SKILL_BEHAVIORAL_INSTRUCTIONS
```

Modify `get_system_prompt()` in `src/utils/prompts.py`:

```python
def get_system_prompt(system_prompt: Optional[str], loaded_skills: list[LoadedSkill], ...) -> str:
    # ... existing logic to resolve base system prompt ...

    # Append skill behavioral instructions if skills are loaded
    skill_instructions = get_skill_instructions(loaded_skills)
    if skill_instructions:
        resolved_prompt = resolved_prompt + "\n" + skill_instructions

    return resolved_prompt
```

**Note**: If no skills are configured, omit the instructions entirely. The `list_skills` and `activate_skill` tools are also not registered when no skills are configured.

### Skill tools

Three tools are registered for skill discovery, activation, and resource loading. This follows the [tool-based activation pattern](https://agentskills.io/client-implementation/adding-skills-support#dedicated-tool-activation) from agentskills.io and aligns with Google ADK's approach.

#### list_skills tool

The `list_skills` tool returns the skill catalog (name + description for each skill):

```python
def get_list_skills_tool(skills: list[LoadedSkill]) -> Optional[InputTool]:
    """Create the list_skills tool if skills are configured.

    Returns the skill catalog so the LLM can discover available skills.
    """
    if not skills:
        return None

    return InputTool(
        type="function",
        function={
            "name": "list_skills",
            "description": "List available skills with their names and descriptions. Call this to discover what skills are available.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    )


def handle_list_skills(skills: list[LoadedSkill]) -> str:
    """Handle list_skills tool invocation.

    Returns skill catalog in XML format.
    """
    if not skills:
        return "<available_skills/>"

    lines = ["<available_skills>"]
    for skill in skills:
        lines.extend([
            "  <skill>",
            f"    <name>{skill.name}</name>",
            f"    <description>{skill.description}</description>",
            "  </skill>",
        ])
    lines.append("</available_skills>")
    return "\n".join(lines)
```

**Phase 2 evolution**: In a future phase, `list_skills` can accept an optional `query` parameter for keyword/semantic search when the skill catalog grows large (100+ skills).

#### activate_skill tool

The `activate_skill` tool loads full instructions for a specific skill:

```python
def get_activate_skill_tool(skills: list[LoadedSkill]) -> Optional[InputTool]:
    """Create the activate_skill tool if skills are configured.

    The name parameter is constrained to valid skill names (as an enum)
    to prevent the model from hallucinating nonexistent skill names.
    """
    if not skills:
        return None

    skill_names = [skill.name for skill in skills]

    return InputTool(
        type="function",
        function={
            "name": "activate_skill",
            "description": "Load full instructions for a skill. Call this when a task matches a skill's description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": skill_names,
                        "description": "The name of the skill to load",
                    }
                },
                "required": ["name"],
            },
        },
    )
```

#### Structured wrapping

The tool response wraps skill content in identifying tags following the [agentskills.io structured wrapping pattern](https://agentskills.io/client-implementation/adding-skills-support#structured-wrapping). This enables:
- The model to clearly distinguish skill instructions from other conversation content
- The harness to identify skill content during context compaction
- Bundled resources to be surfaced without being eagerly loaded

```python
def handle_activate_skill(name: str, skills: list[LoadedSkill]) -> str:
    """Handle activate_skill tool invocation.

    Returns skill content wrapped in structured tags.
    """
    skill = next((s for s in skills if s.name == name), None)
    if not skill:
        return f"<error>Unknown skill: {name}</error>"

    lines = [
        f'<skill_content name="{skill.name}">',
        skill.content,
        "",
        f"Skill directory: {skill.path}",
        "Relative paths in this skill are relative to the skill directory.",
    ]

    # List bundled resources without eagerly loading them
    if skill.references:
        lines.append("")
        lines.append("<skill_resources>")
        for ref in skill.references:
            lines.append(f"  <file>{ref}</file>")
        lines.append("</skill_resources>")

    lines.append("</skill_content>")
    return "\n".join(lines)
```

#### load_skill_resource tool

The `load_skill_resource` tool loads files from a skill's `references/` subdirectory:

```python
def get_load_skill_resource_tool(skills: list[LoadedSkill]) -> Optional[InputTool]:
    """Create the load_skill_resource tool if skills are configured.

    Loads files from a skill's references/ directory.
    """
    if not skills:
        return None

    skill_names = [skill.name for skill in skills]

    return InputTool(
        type="function",
        function={
            "name": "load_skill_resource",
            "description": "Load a file from a skill's references/ directory. Use this when skill instructions reference additional documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "enum": skill_names,
                        "description": "The name of the skill containing the resource",
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative path to the resource file (e.g., 'references/guide.md')",
                    },
                },
                "required": ["skill_name", "path"],
            },
        },
    )


def handle_load_skill_resource(
    skill_name: str, path: str, skills: list[LoadedSkill]
) -> str:
    """Handle load_skill_resource tool invocation.

    Returns file content wrapped in structured tags.
    """
    skill = next((s for s in skills if s.name == skill_name), None)
    if not skill:
        return f"<error>Unknown skill: {skill_name}</error>"

    # Resolve the path relative to skill directory
    resource_path = (skill.path / path).resolve()
    skill_dir = skill.path.resolve()

    # Security check: ensure path is within skill directory
    try:
        resource_path.relative_to(skill_dir)
    except ValueError:
        return f"<error>Path '{path}' is outside skill directory</error>"

    if not resource_path.is_file():
        return f"<error>Resource not found: {path}</error>"

    try:
        content = resource_path.read_text()
    except Exception as e:
        return f"<error>Failed to read resource: {e}</error>"

    return f'<skill_resource skill="{skill_name}" path="{path}">\n{content}\n</skill_resource>'
```

#### Example load_skill_resource response

```xml
<skill_resource skill="openshift-troubleshooting" path="references/common-errors.md">
# Common OpenShift Errors

## ImagePullBackOff
...
</skill_resource>
```

#### Example tool response

```xml
<skill_content name="openshift-troubleshooting">
# OpenShift Troubleshooting

## When to use this skill
Use this skill when:
- A user reports pods not starting or crashing
- Deployments are stuck in pending state
...

Skill directory: /var/skills/openshift-troubleshooting
Relative paths in this skill are relative to the skill directory.

<skill_resources>
  <file>references/common-errors.md</file>
  <file>references/networking-guide.md</file>
</skill_resources>
</skill_content>
```

### Reference file access

Skills can include a `references/` subdirectory with additional documentation. The LLM loads these files using the `load_skill_resource` tool when skill instructions reference them.

**Path restriction**: The `load_skill_resource` tool validates that requested paths are within the skill directory. Attempts to traverse outside the skill directory (e.g., using `../`) are rejected with an error.

**Security**: The path validation in `handle_load_skill_resource` prevents directory traversal attacks by resolving the full path and checking it remains within the skill directory:

```python
# Security check: ensure path is within skill directory
resource_path = (skill.path / path).resolve()
skill_dir = skill.path.resolve()
try:
    resource_path.relative_to(skill_dir)
except ValueError:
    return f"<error>Path '{path}' is outside skill directory</error>"
```

### Context management

Once skill instructions are in the conversation context, they must remain effective for the session duration.

#### Protect skill content from compaction

If lightspeed-stack implements context compaction (conversation history summarization), skill content must be exempted from pruning. Skill instructions are durable behavioral guidance — losing them mid-conversation silently degrades performance.

The `<skill_content>` and `<skill_resource>` tags from structured wrapping enable identification during compaction:

```python
def is_skill_content(message: str) -> bool:
    """Check if a message contains skill content that should be protected."""
    return (
        ("<skill_content" in message and "</skill_content>" in message) or
        ("<skill_resource" in message and "</skill_resource>" in message)
    )
```

#### Deduplicate activations

Track which skills have been activated in the current conversation. If the model attempts to load a skill already in context, return a note instead of re-injecting:

```python
class SkillTracker:
    """Track activated skills per conversation."""

    def __init__(self):
        self._activated: dict[str, set[str]] = {}  # conversation_id -> skill names

    def is_activated(self, conversation_id: str, skill_name: str) -> bool:
        return skill_name in self._activated.get(conversation_id, set())

    def mark_activated(self, conversation_id: str, skill_name: str) -> None:
        if conversation_id not in self._activated:
            self._activated[conversation_id] = set()
        self._activated[conversation_id].add(skill_name)

    def clear(self, conversation_id: str) -> None:
        self._activated.pop(conversation_id, None)
```

When a skill is already activated:

```python
if skill_tracker.is_activated(conversation_id, name):
    return f"<note>Skill '{name}' is already loaded in this conversation.</note>"
```

### Error handling

| Scenario | Error |
|----------|-------|
| Skill path doesn't exist | Startup fails: "Skill path does not exist: {path}" |
| SKILL.md not found | Startup fails: "SKILL.md not found at {path}/SKILL.md" |
| Name mismatch | Startup fails: "Skill name mismatch: config has '{x}' but SKILL.md has '{y}'" |
| Invalid YAML frontmatter | Startup fails: "Invalid SKILL.md frontmatter: {error}" |
| Unknown skill in activate_skill | Tool returns: `<error>Unknown skill: {name}</error>` |
| Unknown skill in load_skill_resource | Tool returns: `<error>Unknown skill: {skill_name}</error>` |
| Path outside skill directory | Tool returns: `<error>Path '{path}' is outside skill directory</error>` |
| Resource file not found | Tool returns: `<error>Resource not found: {path}</error>` |

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/models/config.py` | Add `SkillsConfiguration` class and `skills` field to `Configuration` |
| `src/utils/skills.py` | New module: `LoadedSkill`, `load_skills()`, `parse_skill_md()`, `get_skill_instructions()`, `handle_list_skills()`, `handle_activate_skill()`, `handle_load_skill_resource()` |
| `src/utils/prompts.py` | Modify `get_system_prompt()` to append behavioral instructions |
| `src/utils/responses.py` | Modify `prepare_tools()` to include `list_skills`, `activate_skill`, and `load_skill_resource` tools |
| `src/constants.py` | Add skill-related constants |

### Insertion point detail

**Configuration loading** (`src/models/config.py`):
- Add `SkillsConfiguration` class with `paths: list[str]` field
- Add `skills: Optional[SkillsConfiguration]` to `Configuration` class (around line 1852)
- Path validation happens at startup in `load_skills()` function

**System prompt injection** (`src/utils/prompts.py`):
- `get_system_prompt()` currently returns the resolved prompt at line 80
- Insert behavioral instructions append before the return statement
- Import `get_skill_instructions` from new `utils/skills.py` module

**Tool registration** (`src/utils/responses.py`):
- `prepare_tools()` at line 204 builds the tool list
- Add `list_skills`, `activate_skill`, and `load_skill_resource` tools after MCP tools (around line 260)
- Tool handlers need to be registered for all three skill tool function types

### SKILL.md parsing

```python
import re
import yaml
from pathlib import Path

def parse_skill_md(content: str) -> tuple[dict, str]:
    """Parse SKILL.md into frontmatter dict and body string."""
    # Match YAML frontmatter between --- delimiters
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must have YAML frontmatter between --- delimiters")

    frontmatter_text, body = match.groups()

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e

    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter must be a YAML mapping")

    if "name" not in frontmatter:
        raise ValueError("SKILL.md frontmatter must include 'name' field")

    if "description" not in frontmatter:
        raise ValueError("SKILL.md frontmatter must include 'description' field")

    return frontmatter, body.strip()


def list_references(skill_path: Path) -> list[str]:
    """List files in the skill's references/ subdirectory."""
    refs_dir = skill_path / "references"
    if not refs_dir.is_dir():
        return []

    return [
        str(f.relative_to(skill_path))
        for f in refs_dir.rglob("*")
        if f.is_file()
    ]
```

### Config pattern

All config classes extend `ConfigurationBase` which sets `extra="forbid"`. Use `Field()` with defaults, title, and description. Add `@model_validator(mode="after")` for path validation.

Example config file: `examples/lightspeed-stack-skills.yaml`

### Test patterns

- Framework: pytest + pytest-asyncio + pytest-mock
- Config validation tests: `tests/unit/models/config/test_skills_configuration.py`
- Skill loading/parsing tests: `tests/unit/utils/test_skills.py`
- Integration tests: `tests/integration/endpoints/test_query_with_skills.py`

**Test fixtures**:
```python
@pytest.fixture
def sample_skill_dir(tmp_path):
    """Create a sample skill directory for testing."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
description: A test skill for unit tests.
---

# Test Skill Instructions

These are test instructions.
""")

    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "guide.md").write_text("# Guide\n\nReference content.")

    return skill_dir
```

## Open Questions for Future Work

- **Script support**: Should `scripts/` subdirectory execution be added in a future phase? Requires security review.
- **Built-in skills**: Should Lightspeed ship pre-defined skills for common use cases?
- **Skill versioning**: Should skills support version metadata for compatibility tracking?
- **Remote skills**: Should skills be loadable from URLs or registries?
- **Skill metrics**: Should skill activation be tracked in Prometheus metrics?

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-04-29 | Add `load_skill_resource` tool as third skill tool | Dedicated tool for loading reference files instead of relying on generic file-read |
| 2026-04-27 | Tool-based discovery: `list_skills` returns catalog, system prompt has behavioral instructions only | Scales better, clean evolution path to search-based discovery |
| 2026-04-27 | Config specifies paths only; name/description read from SKILL.md | Keep config lightweight, avoid bloating CR |
| 2026-04-09 | Initial version | Spike completion |

## Appendix A: Agent Skills Specification

The full specification is at https://agentskills.io/specification.

Key points:
- `SKILL.md` must have YAML frontmatter with `name` (required) and `description` (required)
- `name` must be 1-64 characters, lowercase letters/numbers/hyphens, match parent directory
- `description` should be 1-1024 characters, describe what and when
- Body content after frontmatter contains the instructions (no format restrictions)
- Recommended to keep `SKILL.md` under 500 lines, move detailed reference material to separate files

## Appendix B: Example Skill

```markdown
---
name: openshift-troubleshooting
description: Diagnose and fix common OpenShift deployment issues including pod failures, networking problems, and resource constraints. Use when users report deployment failures or application issues on OpenShift.
---

# OpenShift Troubleshooting

## When to use this skill

Use this skill when:
- A user reports pods not starting or crashing
- Deployments are stuck in pending state
- Services are unreachable
- Resource quota issues are suspected

## Diagnostic steps

### 1. Check pod status

First, identify the problematic pods:

oc get pods -n <namespace> | grep -v Running

For each failing pod, get detailed status:

oc describe pod <pod-name> -n <namespace>

Look for:
- **Pending**: Usually resource constraints or scheduling issues
- **CrashLoopBackOff**: Application crash, check logs
- **ImagePullBackOff**: Image registry access issues

### 2. Check events

oc get events -n <namespace> --sort-by='.lastTimestamp'

### 3. Check logs

oc logs <pod-name> -n <namespace>
oc logs <pod-name> -n <namespace> --previous  # For crashed pods

## Common issues and solutions

See [references/common-errors.md](references/common-errors.md) for detailed solutions.
```markdown