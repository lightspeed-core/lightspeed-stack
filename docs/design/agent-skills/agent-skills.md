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

Agent Skills support allows customers to extend Lightspeed Core with specialized instructions and domain knowledge packaged as portable skill directories. Skills follow the [Agent Skills open standard](https://agentskills.io) and are configured in `lightspeed-stack.yaml`.

The LLM sees a skill catalog (name + description) in the system prompt and can load full instructions on demand using the `activate_skill` tool.

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

- **R1:** Skills are defined in `lightspeed-stack.yaml` as a list of entries with name, description, and path
- **R2:** Each skill path must point to a directory containing a valid `SKILL.md` file
- **R3:** The skill catalog (name + description) is injected into the system prompt with behavioral instructions
- **R4:** The LLM can load full skill instructions via the `activate_skill` tool
- **R5:** Skill content is returned with structured wrapping (`<skill_content>` tags) per agentskills.io spec
- **R6:** The LLM can read files from a skill's `references/` subdirectory (allowlisted paths)
- **R7:** Script execution (`scripts/` subdirectory) is not supported
- **R8:** Skill configuration is validated at startup with clear error messages
- **R9:** Activated skills are tracked per conversation to prevent duplicate injection
- **R10:** Skill content is protected from context compaction

## Use Cases

- **U1:** As a platform administrator, I want to configure troubleshooting skills so that the LLM can help users diagnose common issues
- **U2:** As a skill author, I want to create a SKILL.md file with instructions so that I can package domain expertise portably
- **U3:** As a user, I want the LLM to automatically use relevant skills so that I get better answers without manually specifying which skill to use
- **U4:** As an enterprise customer, I want to deploy custom skills so that the LLM understands our internal processes and terminology

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
  │ Build system    │──► Append skill catalog + behavioral instructions
  │ prompt          │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ Register tools  │──► Add activate_skill tool alongside MCP/RAG tools
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ LLM processes   │──► Sees catalog, decides if skill is relevant
  │ request         │
  └────────┬────────┘
           │
           ▼ (if skill needed)
  ┌─────────────────┐
  │ activate_skill  │──► Returns <skill_content> with body + resources
  │ tool invocation │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ LLM uses skill  │──► May read reference files if needed
  │ instructions    │
  └─────────────────┘
```

### Configuration

Skills are configured in `lightspeed-stack.yaml`:

```yaml
skills:
  - name: "openshift-troubleshooting"
    description: "Diagnose and fix common OpenShift deployment issues including pod failures, networking problems, and resource constraints."
    path: "/var/skills/openshift-troubleshooting"
  - name: "code-review"
    description: "Review code for best practices, security vulnerabilities, and performance issues."
    path: "/var/skills/code-review"
```

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
class SkillConfiguration(ConfigurationBase):
    """Agent skill configuration.

    Skills provide specialized instructions that the LLM can load on demand.
    Each skill is a directory containing a SKILL.md file with frontmatter
    metadata and markdown instructions.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        title="Skill name",
        description="Unique skill identifier. Must match the 'name' field in SKILL.md frontmatter.",
    )

    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        title="Skill description",
        description="What the skill does and when to use it. Shown to the LLM in the skill catalog.",
    )

    path: str = Field(
        ...,
        title="Skill path",
        description="Absolute path to the skill directory containing SKILL.md.",
    )

    # Populated at startup after parsing SKILL.md
    _content: str = PrivateAttr(default="")
    _references: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def validate_skill_path(self) -> Self:
        """Validate skill path and parse SKILL.md."""
        skill_md_path = Path(self.path) / "SKILL.md"
        if not skill_md_path.is_file():
            raise ValueError(f"SKILL.md not found at {skill_md_path}")

        # Parse and validate SKILL.md
        content = skill_md_path.read_text(encoding="utf-8")
        frontmatter, body = parse_skill_md(content)

        if frontmatter.get("name") != self.name:
            raise ValueError(
                f"Skill name mismatch: config has '{self.name}' but "
                f"SKILL.md has '{frontmatter.get('name')}'"
            )

        self._content = body
        self._references = list_references(Path(self.path))
        return self
```

Add to `Configuration` class:

```python
skills: list[SkillConfiguration] = Field(
    default_factory=list,
    title="Agent skills",
    description="Agent skills provide specialized instructions the LLM can load on demand.",
)
```

### System prompt injection

The skill catalog is appended to the system prompt following the [agentskills.io implementation guide](https://agentskills.io/client-implementation/adding-skills-support).

#### Catalog format

The catalog uses XML format with `<available_skills>` containing `<skill>` elements:

```xml
<available_skills>
  <skill>
    <name>openshift-troubleshooting</name>
    <description>Diagnose and fix common OpenShift deployment issues including pod failures, networking problems, and resource constraints.</description>
  </skill>
  <skill>
    <name>code-review</name>
    <description>Review code for best practices, security vulnerabilities, and performance issues.</description>
  </skill>
</available_skills>
```

#### Behavioral instructions

The catalog is preceded by behavioral instructions telling the model how to use skills:

```
The following skills provide specialized instructions for specific tasks.
When a task matches a skill's description, call the activate_skill tool
with the skill's name to load its full instructions.
```

#### Implementation

```python
def build_skill_catalog(skills: list[SkillConfiguration]) -> str:
    """Build skill catalog XML for system prompt injection.

    Follows the agentskills.io implementation guide format.
    """
    if not skills:
        return ""

    lines = [
        "",
        "# Available Skills",
        "",
        "The following skills provide specialized instructions for specific tasks.",
        "When a task matches a skill's description, call the activate_skill tool",
        "with the skill's name to load its full instructions.",
        "",
        "<available_skills>",
    ]

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

Modify `get_system_prompt()` in `src/utils/prompts.py`:

```python
def get_system_prompt(system_prompt: Optional[str], ...) -> str:
    # ... existing logic to resolve base system prompt ...

    # Append skill catalog if skills are configured
    skill_catalog = build_skill_catalog(configuration.skills)
    if skill_catalog:
        resolved_prompt = resolved_prompt + "\n" + skill_catalog

    return resolved_prompt
```

**Note**: If no skills are configured, omit the catalog entirely. Don't show an empty `<available_skills/>` block.

### Skill activation tool

Register an `activate_skill` tool that the LLM can call to load full instructions. This follows the [dedicated tool activation pattern](https://agentskills.io/client-implementation/adding-skills-support#dedicated-tool-activation) from agentskills.io.

#### Tool registration

```python
def get_skill_tool(skills: list[SkillConfiguration]) -> Optional[InputTool]:
    """Create the activate_skill tool if skills are configured.

    The name parameter is constrained to valid skill names (as an enum)
    to prevent the model from hallucinating nonexistent skill names.
    If no skills are available, don't register the tool at all.
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
def handle_activate_skill(name: str, skills: list[SkillConfiguration]) -> str:
    """Handle activate_skill tool invocation.

    Returns skill content wrapped in structured tags.
    """
    skill = next((s for s in skills if s.name == name), None)
    if not skill:
        return f"<error>Unknown skill: {name}</error>"

    lines = [
        f'<skill_content name="{skill.name}">',
        skill._content,
        "",
        f"Skill directory: {skill.path}",
        "Relative paths in this skill are relative to the skill directory.",
    ]

    # List bundled resources without eagerly loading them
    if skill._references:
        lines.append("")
        lines.append("<skill_resources>")
        for ref in skill._references:
            lines.append(f"  <file>{ref}</file>")
        lines.append("</skill_resources>")

    lines.append("</skill_content>")
    return "\n".join(lines)
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

Skills can include a `references/` subdirectory with additional documentation. The LLM can read these files using existing file-read capabilities when skill instructions reference them.

**Path restriction**: File reads are restricted to configured skill directories. The skill tool returns the `base_path` so the LLM can construct valid paths like `{base_path}/references/guide.md`.

#### Permission allowlisting

Following the [agentskills.io guidance](https://agentskills.io/client-implementation/adding-skills-support#permission-allowlisting), skill directories should be allowlisted for file access so the model can read bundled resources without triggering permission prompts. Without this, every reference to a bundled file results in a permission dialog, breaking the flow.

```python
def is_path_in_skill_directory(path: str, skills: list[SkillConfiguration]) -> bool:
    """Check if a path is within a configured skill directory."""
    resolved_path = Path(path).resolve()
    for skill in skills:
        skill_dir = Path(skill.path).resolve()
        try:
            resolved_path.relative_to(skill_dir)
            return True
        except ValueError:
            continue
    return False
```

### Context management

Once skill instructions are in the conversation context, they must remain effective for the session duration.

#### Protect skill content from compaction

If lightspeed-stack implements context compaction (conversation history summarization), skill content must be exempted from pruning. Skill instructions are durable behavioral guidance — losing them mid-conversation silently degrades performance.

The `<skill_content>` tags from structured wrapping enable identification during compaction:

```python
def is_skill_content(message: str) -> bool:
    """Check if a message contains skill content that should be protected."""
    return "<skill_content" in message and "</skill_content>" in message
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
| Unknown skill in read_skill | Tool returns: {"error": "Unknown skill: {name}"} |

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/models/config.py` | Add `SkillConfiguration` class and `skills` field to `Configuration` |
| `src/utils/skills.py` | New module: `parse_skill_md()`, `build_skill_catalog()`, `handle_read_skill()` |
| `src/utils/prompts.py` | Modify `get_system_prompt()` to append skill catalog |
| `src/utils/responses.py` | Modify `prepare_tools()` to include skill tool |
| `src/constants.py` | Add skill-related constants |

### Insertion point detail

**Configuration loading** (`src/models/config.py`):
- Add `SkillConfiguration` class following the `ModelContextProtocolServer` pattern (line 468)
- Add `skills: list[SkillConfiguration]` to `Configuration` class (around line 1852)
- Validation happens in `@model_validator` during config parsing

**System prompt injection** (`src/utils/prompts.py`):
- `get_system_prompt()` currently returns the resolved prompt at line 80
- Insert skill catalog append before the return statement
- Import `build_skill_catalog` from new `utils/skills.py` module

**Tool registration** (`src/utils/responses.py`):
- `prepare_tools()` at line 204 builds the tool list
- Add skill tool after MCP tools (around line 260)
- Tool handler needs to be registered for the `read_skill` function type

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
- Config validation tests: `tests/unit/models/config/test_skill_configuration.py`
- Skill parsing tests: `tests/unit/utils/test_skills.py`
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