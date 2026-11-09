# Fullsend Jira integration

[Fullsend]((https://fullsend.sh/docs)) is an agentic assistant onboarded to this repository. This document
describes how its Jira integration works, what does and does not trigger an agent, 
and how to interact with it safely.

## Overview

With this integration, Fullsend can pick up work straight from the **LCORE**
Jira board and act on it in this repository, with a human in control of every
handoff. Nothing happens automatically from ordinary Jira activity: an agent
runs only when someone performs one of the explicit opt-in actions listed
below.

## How a ticket opts in

A Jira ticket is only visible to Fullsend when it carries the routing label:

```
repo:lightspeed-core/lightspeed-stack
```

Use exactly one `repo:` label on a ticket. Tickets without this label are
invisible to Fullsend, and a ticket carrying more than one `repo:` label is
skipped.

## The poller

A scheduled GitHub Actions workflow (`.github/workflows/fullsend-poll-jira.yml`)
polls the LCORE board every five minutes for non-done issues that carry the
routing label. The poller only observes; it never decides to dispatch on its own
— the per-agent trigger conditions do.

Scheduled polling is **off by default**. It runs on a schedule only when the
GitHub Actions repository variable `FULLSEND_JIRA_POLL_ENABLED` is set to
`true` (repo Settings → Secrets and variables → Actions → Variables). Until
then, the schedule is a no-op.

## What triggers an agent

| Agent  | Dispatches when…                                                                 | Result |
| ------ | -------------------------------------------------------------------------------- | ------ |
| triage | the `ready-to-triage` label is added, **or** a comment's first line is `/fs-triage` | reads the issue and posts an assessment back to Jira |
| code   | the `ready-to-code` label is added, **or** a comment's first line is `/fs-code`     | implements the change and opens a GitHub pull request |

Both require the ticket to carry the `repo:lightspeed-core/lightspeed-stack`
label, and that must be its only label that starts with `repo:` . A ticket with no such label — or with more than one label that starts with `repo:` is skipped.

Triage does **not** automatically hand off to code: automatic triage→code
handoff is disabled by the `TRIAGE_AUTO_CODE: "off"` override in the `env:`
block of [`.fullsend/harness/triage.yaml`](../../.fullsend/harness/triage.yaml)
(set for both `runner` and `sandbox`, since both read it). The upstream default
is `"on"` for bug/documentation/performance issues, so this override is what
keeps a human in the loop: a human always decides whether work proceeds from
triage to implementation. Use `ready-to-code` as the normal, reviewable handoff.

## What does NOT trigger an agent

- **Ordinary Jira edits** — changing fields, status, description, assignee, or
  adding comments that are not a slash command — do nothing.
- **Adding unrelated labels** does nothing. Only `ready-to-triage` and
  `ready-to-code` are dispatch labels. Adding, for example, a priority or
  component label will not start an agent.
- **An already-present label does not re-fire.** Re-triggering requires removing
  and re-adding the label.
- **Actions by bots/automation do not dispatch.** A `/fs-triage` or `/fs-code`
  slash command only dispatches when posted by a human actor, and the Jira
  adapter filters recognized bot events (for example a label added by Fullsend's
  own Jira account) before the trigger is evaluated.

In short: a code change (and the pull request it opens) can only originate from
someone explicitly adding `ready-to-code` to — or commenting `/fs-code` on — a
Jira ticket that already carries this repository's `repo:` label. There is no
path by which an arbitrary label or edit causes refactoring.
