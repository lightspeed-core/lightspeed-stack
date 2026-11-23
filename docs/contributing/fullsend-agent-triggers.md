# Fullsend agent triggers

Quick reference for how to invoke each Fullsend agent in
`lightspeed-core/lightspeed-stack`. Agents are triggered by **comments** or
**labels** — on a GitHub pull request or on a Jira ticket, depending on the
agent.

For the Jira pipeline's safety model, routing label, and poller details, see
[fullsend-jira-integration.md](fullsend-jira-integration.md).

Two rules apply to every slash command below:

- The command must be the **first line** of the comment.
- It is only honored from a **human** actor — comments/labels from bots or
  automation are ignored.

## Summary

| Agent | Where | How to trigger | What it does |
| ---------- | ----------- | ---------------------------------------------------- | ------------------------------------------------ |
| triage | Jira ticket | `ready-to-triage` label, or `/fs-triage` comment | Posts a triage assessment back to the ticket |
| code | Jira ticket | `ready-to-code` label, or `/fs-code` comment | Implements the change and opens a GitHub PR |
| review | GitHub PR | `/fs-review` comment | Posts a code review on the PR |
| fix | GitHub PR | `/fs-fix` comment (plus an automatic path — see below) | Pushes fixes to the PR branch |
| retro | — | **Disabled** (`enabled: false`) | — |
| prioritize | — | **Disabled** (`enabled: false`) | — |

## Jira agents: triage and code

Both only act on a Jira ticket that carries the routing label
`repo:lightspeed-core/lightspeed-stack` **as its only `repo:` label**, and are
dispatched by the scheduled poller (not instantly — see the Jira integration
doc).

Typical ticket flow:

1. Add the `repo:lightspeed-core/lightspeed-stack` label to the ticket.
2. Comment **`/fs-triage`** (or add the `ready-to-triage` label). Triage reads
   the ticket and posts an assessment comment. It does **not** automatically
   start the code agent — a human decides whether to proceed.
3. After reviewing the triage summary, comment **`/fs-code`** (or add the
   `ready-to-code` label). The code agent implements the change and opens a
   GitHub pull request.

`ready-to-code` is the normal, reviewable handoff from triage; the `/fs-code`
comment is the explicit manual route. You can add extra guidance in the
triggering comment or in the ticket itself — the agent reads the ticket (title,
description, comments) as its brief.

## GitHub PR agents: review and fix

### review

Comment **`/fs-review`** on a pull request to get a code review. Review runs
**only** on that explicit command — it does not run automatically when a PR is
opened, pushed to, or marked ready.

### fix

Comment **`/fs-fix`** on a pull request to have the agent push fixes to the PR
branch. Comment **`/fs-fix-stop`** to stop an in-progress fix run.

Unlike the other agents, `fix` is on the upstream default harness and is **not
restricted to a command**, so it also has an **automatic** path: when a Fullsend
review bot requests changes on a PR, `fix` may run automatically if either the PR
author is a bot or the PR carries the `fullsend-fix` label — and never if the PR
carries the `fullsend-no-fix` label. It is currently the only agent with any
automatic trigger in this rollout.

## Disabled agents

`retro` and `prioritize` are disabled (`enabled: false`) for the initial rollout
and do not run from any label or command. (On Fullsend v0.51.0+ the `roles` list
does not gate execution, so these are disabled explicitly; see the Jira
integration doc.)
