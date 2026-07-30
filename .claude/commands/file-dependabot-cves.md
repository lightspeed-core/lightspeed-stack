---
name: file-dependabot-cves
description: Fetch Dependabot alerts, cross-reference against LCORE Jira tickets, and file tickets for gaps
---

Audit Dependabot vulnerabilities for `$repo` (default: `lightspeed-core/lightspeed-stack`) and cross-reference them against existing LCORE Jira tickets.

## Step 1: Fetch Dependabot alerts

Fetch open Dependabot alerts using:

```
gh api "repos/$repo/dependabot/alerts" --paginate --jq '.[] | select(.state == "open") | {number, state, severity: .security_vulnerability.severity, package: .security_vulnerability.package.name, ecosystem: .security_vulnerability.package.ecosystem, summary: .security_advisory.summary, cve: (.security_advisory.cve_id // "N/A"), ghsa: .security_advisory.ghsa_id, created: .created_at, fixed_version: (.security_vulnerability.first_patched_version.identifier // "N/A")}'
```

If `$repo` is not provided, default to `lightspeed-core/lightspeed-stack`. Deduplicate results by (CVE + package name) when a CVE is present, or (GHSA ID + package name) when CVE is null/N/A. This prevents collapsing distinct GHSA-only advisories for the same package into a single entry.

## Step 2: Present severity summary

Present a summary table with counts by severity (Critical, High, Medium, Low), then a breakdown table grouped by package: Package | Severity | CVE | Summary | Fix Version.

## Step 3: Search LCORE Jira for existing coverage

!Requires JIRA Atlassian MCP

Search LCORE Jira for existing tickets per affected package. Batch package names into OR clauses to minimize API calls:

- By summary: `project = LCORE AND (summary ~ "pkg1" OR summary ~ "pkg2" ...)`
- By CVE label: `project = LCORE AND labels in ("CVE-XXXX-XXXXX", ...)`

Fields: `summary,status,assignee,priority,labels`. Limit: 50. Paginate if needed.

## Step 4: Cross-reference and classify

Group all Dependabot alerts by **package name**. For each package, cross-reference against LCORE tickets and classify the package as:
- **Covered**: open/in-progress ticket exists that addresses upgrading this package, and the ticket's remediation version covers all current CVEs
- **Stale**: open/in-progress ticket exists, but Dependabot now reports additional CVEs or a higher fix version not reflected in the ticket (e.g., ticket says "upgrade to >= 1.2" but Dependabot now requires >= 1.5)
- **Closed**: ticket done
- **Missing**: no ticket covers this package

Present:
1. A coverage table: Package | Highest Sev. | CVE(s) | Dependabot #(s) | LCORE Ticket(s) | Status | Assignee
2. A **stale table** listing packages with existing tickets that need updating: Package | LCORE Ticket | Current Fix Version in Ticket | Required Fix Version | New CVE(s) to Add
3. A **gaps table** listing only the missing **packages** (not individual CVEs) with their highest severity, all associated CVEs, and the fix version needed to resolve all of them
4. Key findings: coverage ratio, unassigned high/critical items, stale tickets needing updates, duplicate tickets that could be consolidated

## Step 5: Verify gaps

For each gap, cross-reference in JIRA (full-text search by CVE ID) and GitHub (confirm alert is still open) to verify it is a real missing issue. Drop false positives (e.g., already-closed tickets, stale alerts).

## Step 5b: Update stale tickets

For each **stale** package (existing ticket that doesn't cover all current CVEs), propose an update:
- Add any missing CVE IDs to the ticket's labels
- Update the description to include the new CVE(s) — append new CVE sections and update the remediation line to the highest fix version
- Update the ticket summary to reflect the new CVE count (e.g., "Upgrade <package> to address <N> CVE(s)")

Present the proposed updates in a table: LCORE Ticket | Package | Changes (new labels, updated description, updated summary). Ask the user to confirm before applying updates via `jira_update_issue`.

## Step 6: Ask user which gaps to file

Ask the user:
- Whether they want to create LCORE tickets for the missing vulnerabilities
- Which severity levels to include (e.g. "only medium and above", "all", or specific ones)
- The target fix version (look up available versions from `jira_get_project_versions` for LCORE)
- The component to assign (look up available components from `jira_get_project_components` for LCORE)

## Step 7: Fetch full advisory details and draft tickets (one per package)

For each **package** the user wants to file, fetch the full Dependabot advisory details for every alert on that package:

```
gh api "repos/$repo/dependabot/alerts/$alert_number" --jq '{summary: .security_advisory.summary, description: .security_advisory.description, cve: (.security_advisory.cve_id // "N/A"), remediation: (.security_vulnerability.first_patched_version.identifier // "No fix available"), vulnerable_range: .security_vulnerability.vulnerable_version_range}'
```

Create **one ticket per package**, consolidating all its CVEs. Structure each ticket as:

| Field | Value |
|-------|-------|
| **Project** | LCORE |
| **Type** | Vulnerability |
| **Title** | `Upgrade <package> to address <N> CVE(s)` (e.g. "Upgrade cryptography to address 3 CVE(s)") |
| **Component** | As chosen by user |
| **Fix Version** | As chosen by user |
| **Labels** | All CVE IDs for this package (if available), Security |
| **Description** | For each CVE in the package, include: a heading with the CVE ID and advisory summary, the full `security_advisory.description`, and the vulnerable version range. End the description with `**Remediation:** Upgrade <package> to >= <highest_fix_version>` (use the highest fix version across all CVEs for the package, or "No upstream fix available yet" if none exists). |

Present all drafted tickets in a table to the user for review before creating them.

## Step 8: Find the parent CVE epic

Search for the parent epic: `project = LCORE AND issuetype = Epic AND summary ~ "CVE" AND summary ~ "lightspeed-stack" ORDER BY created DESC`. Pick the one whose fix version matches the user's chosen fix version. If ambiguous or none found, ask the user.

## Step 9: Create tickets after user confirmation

Only after the user explicitly confirms the drafts, create one ticket per package using `jira_create_issue` with:
- `project_key`: LCORE
- `issue_type`: Vulnerability
- `summary`: `Upgrade <package> to address <N> CVE(s)`
- `description`: as structured above
- `components`: user's chosen component
- `additional_fields`: `{"fixVersions": [{"id": "<version_id>"}], "labels": ["<CVE-ID-1>", "<CVE-ID-2>", ..., "Security"], "parent": "<EPIC_KEY>"}`

Omit `parent` only if the user chose to skip it.

Report back the created ticket keys and links.
