# Agent Skills Guide

> [!NOTE]
> Agent Skills is a feature introduced in Lightspeed Core Stack version 0.6.0.

This guide covers how to configure Agent Skills in Lightspeed Core Stack and how to author your own skills.

---

- [Introduction](#introduction)
- [Configuration](#configuration)
  - [Option A: Directory of Skills](#option-a-directory-of-skills)
  - [Option B: Individual Skill Paths](#option-b-individual-skill-paths)
- [Skill Directory Structure](#skill-directory-structure)
- [SKILL.md Format](#skillmd-format)
  - [Frontmatter Fields](#frontmatter-fields)
  - [Body Content](#body-content)
- [Creating a Skill](#creating-a-skill)
- [How Skills Work at Runtime](#how-skills-work-at-runtime)
- [Limitations](#limitations)
- [References](#references)

---

# Introduction

Agent Skills allow product teams (e.g., RHEL Lightspeed, Ansible Lightspeed) to extend Lightspeed Core with specialized instructions and domain knowledge. Skills are packaged as portable directories following the [Agent Skills open standard](https://agentskills.io).

A skill is a `SKILL.md` file containing metadata and instructions that the LLM can load on demand. For example, a troubleshooting skill might contain step-by-step diagnostic procedures for a specific product, while a code review skill might contain a checklist and best practices.

> [!IMPORTANT]
> Skills are configured by **product teams at deployment time**. End users of LS app products do not have the ability to add skills, similar to how they cannot add MCP servers.

# Configuration

Skills are configured in `lightspeed-stack.yaml` by specifying paths to skill directories. Two forms are supported.

## Option A: Directory of Skills

Point to a parent directory containing skill subdirectories. Each subdirectory with a `SKILL.md` file is loaded as a skill.

```yaml
skills:
  paths:
    - "/var/skills/"
```

This loads all skills found under `/var/skills/`:

```
/var/skills/
├── openshift-troubleshooting/
│   ├── SKILL.md
│   └── references/
│       └── common-errors.md
├── code-review/
│   └── SKILL.md
└── ansible-playbooks/
    ├── SKILL.md
    └── references/
        └── module-reference.md
```

## Option B: Individual Skill Paths

Point directly to specific skill directories for fine-grained control over which skills are loaded.

```yaml
skills:
  paths:
    - "/var/skills/openshift-troubleshooting/"
    - "/var/skills/code-review/"
```

> [!TIP]
> Option A is recommended for most deployments. Use Option B when you need to selectively include specific skills from a larger collection.

See [examples/lightspeed-stack-skills.yaml](../examples/lightspeed-stack-skills.yaml) for a complete configuration example.

# Skill Directory Structure

Each skill is a directory containing, at minimum, a `SKILL.md` file:

```
skill-name/
├── SKILL.md              # Required: metadata + instructions
└── references/           # Optional: additional documentation
    ├── guide.md
    └── troubleshooting.md
```

- **`SKILL.md`** (required): Contains YAML frontmatter with metadata and Markdown body with instructions.
- **`references/`** (optional): Contains additional documentation files that the LLM can load on demand when the skill instructions reference them.

> [!NOTE]
> Script execution (`scripts/` subdirectory) is not supported. Only `SKILL.md` and `references/` files are used at runtime.

# SKILL.md Format

The `SKILL.md` file must contain YAML frontmatter (between `---` delimiters) followed by Markdown content.

## Frontmatter Fields

| Field           | Required | Description |
|-----------------|----------|-------------|
| `name`          | Yes      | Skill identifier. Max 64 characters. Lowercase letters, numbers, and hyphens only. Must match the parent directory name. |
| `description`   | Yes      | What the skill does and when to use it. Max 1024 characters. |

### `name` rules

- 1-64 characters
- Lowercase letters (`a-z`), numbers (`0-9`), and hyphens (`-`) only
- Must not start or end with a hyphen
- Must not contain consecutive hyphens (`--`)
- Must match the parent directory name

**Valid names**: `openshift-troubleshooting`, `code-review`, `data-analysis`

**Invalid names**: `OpenShift-Troubleshooting` (uppercase), `-code-review` (starts with hyphen), `code--review` (consecutive hyphens)

### `description` guidance

The description should include both **what** the skill does and **when** to use it. Include specific keywords that help the LLM identify relevant tasks.

```yaml
# Good: specific about what and when
description: Diagnose and fix common OpenShift deployment issues including pod failures, networking problems, and resource constraints. Use when users report deployment failures or application issues on OpenShift.

# Poor: too vague
description: Helps with OpenShift.
```

## Body Content

The Markdown body after the frontmatter contains the skill instructions. There are no format restrictions. Write whatever helps the LLM perform the task effectively.

Recommended sections:
- Step-by-step instructions
- Examples of inputs and outputs
- Common edge cases and how to handle them

> [!TIP]
> Keep `SKILL.md` under 500 lines. Move detailed reference material to files in the `references/` subdirectory and reference them from the main instructions.

# Creating a Skill

Follow these steps to create a new skill:

**1. Create the skill directory**

The directory name must match the `name` field in `SKILL.md`.

```bash
mkdir -p /var/skills/my-skill
```

**2. Create the `SKILL.md` file**

```markdown
---
name: my-skill
description: A brief description of what this skill does and when to use it.
---

# My Skill

## When to use this skill

Use this skill when:
- Condition A applies
- The user asks about topic B

## Instructions

1. First, do X
2. Then check Y
3. If Z occurs, see [the reference guide](references/guide.md)
```

**3. (Optional) Add reference files**

```bash
mkdir -p /var/skills/my-skill/references
```

Add documentation files that the skill instructions reference:

```markdown
# references/guide.md

Detailed reference content goes here...
```

**4. Add the skill path to configuration**

Add the path to your `lightspeed-stack.yaml`:

```yaml
skills:
  paths:
    - "/var/skills/"  # If using a directory of skills
```

**5. Restart the service**

Skills are loaded at startup. Restart Lightspeed Core Stack to pick up new or modified skills.

See [examples/skills/](../examples/skills/) for complete working examples.

# How Skills Work at Runtime

Skills use a progressive disclosure pattern with three LLM tools:

1. **`list_skills`** — The LLM calls this to discover available skills. Returns the name and description of each skill.
2. **`activate_skill`** — When a task matches a skill's description, the LLM calls this to load the full instructions from `SKILL.md`.
3. **`load_skill_resource`** — If the skill instructions reference files in `references/`, the LLM calls this to load them on demand.

```
User question
     │
     ▼
LLM calls list_skills → sees skill catalog (name + description)
     │
     ▼ (if task matches a skill)
LLM calls activate_skill → loads full SKILL.md instructions
     │
     ▼ (if instructions reference a file)
LLM calls load_skill_resource → loads file from references/
     │
     ▼
LLM follows skill instructions to answer
```

The system prompt contains behavioral instructions telling the LLM how to use these tools. When no skills are configured, the tools and instructions are omitted entirely.

> [!NOTE]
> Skills are tracked per conversation. If a skill is already loaded in a conversation, re-activating it returns a note instead of re-injecting the content.

# Limitations

- **No script execution**: The `scripts/` subdirectory from the agentskills.io spec is not supported. Skills provide instructions only; they do not execute code.
- **Read-only**: Skills are loaded from the filesystem at startup and are read-only at runtime.
- **No remote loading**: Skills must be present on the local filesystem. Loading from URLs or registries is not supported.
- **Duplicate names**: Skill names must be unique across all configured paths. Duplicate names cause a startup error.

# References

- [Agent Skills Specification](https://agentskills.io/specification) — the open standard for skill format
- [Agent Skills Implementation Guide](https://agentskills.io/client-implementation/adding-skills-support) — client implementation guidance
- [Feature Design Document](design/agent-skills/agent-skills.md) — internal design spec for the Lightspeed Core implementation
- [Example Skills](../examples/skills/) — working example skills
- [Example Configuration](../examples/lightspeed-stack-skills.yaml) — example `lightspeed-stack.yaml` with skills configured
