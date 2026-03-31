#!/usr/bin/env bash
# Fetch JIRA ticket content and its linked/child tickets.
#
# Usage:
#   fetch-jira.sh <ticket>
#   fetch-jira.sh 1234          (defaults to LCORE-1234)
#   fetch-jira.sh LCORE-1234
#
# Prerequisites:
#   ~/.config/jira/credentials.json with email, token, instance.
#
# Output: ticket summary, description, acceptance criteria, status,
# and linked/child tickets (fetched recursively one level deep).

set -euo pipefail

# shellcheck source=jira-common.sh
. "$(dirname "$0")/jira-common.sh"

if [ $# -lt 1 ]; then
    echo "Usage: fetch-jira.sh <ticket-number-or-key>"
    echo "Example: fetch-jira.sh 1234  or  fetch-jira.sh LCORE-1234"
    exit 1
fi

ensure_jira_credentials

TICKET="$1"
# If bare number, prepend LCORE-
if echo "$TICKET" | grep -qE '^[0-9]+$'; then
    TICKET="LCORE-$TICKET"
fi

fetch_ticket() {
    local key="$1"
    local indent="${2:-}"

    local data
    data=$(curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        "$JIRA_INSTANCE/rest/api/3/issue/$key?fields=summary,status,issuetype,description,issuelinks,subtasks,parent" 2>/dev/null)

    if echo "$data" | python3 -c "import sys,json; json.load(sys.stdin)['key']" >/dev/null 2>&1; then
        python3 -c "
import json, sys, textwrap

data = json.loads(sys.argv[1])
indent = sys.argv[2]
key = data['key']
fields = data['fields']
summary = fields['summary']
status = fields['status']['name']
issue_type = fields['issuetype']['name']
parent = fields.get('parent', {})
parent_key = parent.get('key', '') if parent else ''

print(f'{indent}=== {key}: {summary} ===')
print(f'{indent}Type: {issue_type} | Status: {status}')
if parent_key:
    print(f'{indent}Parent: {parent_key}')
print()

# Description
desc = fields.get('description')
if desc and isinstance(desc, dict):
    # ADF format — extract text
    def extract_text(node, depth=0):
        lines = []
        if isinstance(node, dict):
            ntype = node.get('type', '')
            if ntype == 'text':
                text = node.get('text', '')
                marks = node.get('marks', [])
                for m in marks:
                    if m.get('type') == 'strong':
                        text = f'**{text}**'
                    elif m.get('type') == 'code':
                        text = f'\`{text}\`'
                return [text]
            if ntype == 'hardBreak':
                return ['\n']
            if ntype == 'listItem':
                child_text = []
                for c in node.get('content', []):
                    child_text.extend(extract_text(c, depth))
                return ['  ' * depth + '- ' + ''.join(child_text).strip()]
            if ntype in ('bulletList', 'orderedList'):
                for c in node.get('content', []):
                    lines.extend(extract_text(c, depth + 1))
                return lines
            if ntype == 'heading':
                level = node.get('attrs', {}).get('level', 1)
                child_text = []
                for c in node.get('content', []):
                    child_text.extend(extract_text(c, depth))
                return ['#' * level + ' ' + ''.join(child_text).strip()]
            if ntype == 'codeBlock':
                child_text = []
                for c in node.get('content', []):
                    child_text.extend(extract_text(c, depth))
                return ['\`\`\`\n' + ''.join(child_text) + '\n\`\`\`']
            for c in node.get('content', []):
                lines.extend(extract_text(c, depth))
            if ntype == 'paragraph' and lines:
                lines.append('')
        return lines

    text_lines = extract_text(desc)
    desc_text = '\n'.join(text_lines).strip()
    if desc_text:
        for line in desc_text.split('\n'):
            print(f'{indent}{line}')
        print()

# Links
links = fields.get('issuelinks', [])
if links:
    print(f'{indent}Linked issues:')
    for link in links:
        link_type = link.get('type', {}).get('name', '?')
        if 'outwardIssue' in link:
            linked = link['outwardIssue']
            direction = link.get('type', {}).get('outward', 'relates to')
        elif 'inwardIssue' in link:
            linked = link['inwardIssue']
            direction = link.get('type', {}).get('inward', 'relates to')
        else:
            continue
        lkey = linked['key']
        lsummary = linked['fields']['summary']
        lstatus = linked['fields']['status']['name']
        print(f'{indent}  {direction}: {lkey} — {lsummary} [{lstatus}]')
    print()

# Subtasks
subtasks = fields.get('subtasks', [])
if subtasks:
    print(f'{indent}Child issues:')
    for st in subtasks:
        skey = st['key']
        ssummary = st['fields']['summary']
        sstatus = st['fields']['status']['name']
        print(f'{indent}  {skey} — {ssummary} [{sstatus}]')
    print()
" "$data" "$indent"
    else
        echo "${indent}Error fetching $key"
        echo "$data" | head -3
    fi
}

# Fetch main ticket
fetch_ticket "$TICKET"

# Search for child issues via parent= JQL (Jira Cloud hierarchy)
CHILD_KEYS=$(curl -sS --connect-timeout 10 --max-time 30 \
    -u "$JIRA_EMAIL:$JIRA_TOKEN" \
    "$JIRA_INSTANCE/rest/api/3/search/jql?jql=parent%3D${TICKET}&fields=key,summary,status,issuetype&maxResults=20" 2>/dev/null | \
    python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for issue in data.get('issues', []):
        key = issue['key']
        summary = issue['fields']['summary']
        status = issue['fields']['status']['name']
        itype = issue['fields']['issuetype']['name']
        print(f'{key} ({itype}) [{status}]: {summary}')
except Exception:
    pass
" 2>/dev/null)

if [ -n "$CHILD_KEYS" ]; then
    echo "Child issues:"
    echo "$CHILD_KEYS" | while read -r line; do
        echo "  $line"
    done
    echo ""
fi

# If additional ticket keys are passed as arguments, fetch those too
shift
for extra in "$@"; do
    if echo "$extra" | grep -qE '^[0-9]+$'; then
        extra="LCORE-$extra"
    fi
    echo "────────────────────────────────────────────────────────"
    echo ""
    fetch_ticket "$extra"
done
