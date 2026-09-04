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

# shellcheck disable=SC1091
. "$(dirname "$0")/jira-common.sh"

show_help() {
    echo "Usage: fetch-jira.sh [--comments] [--linked-depth N] <ticket> [additional-tickets...]"
    echo ""
    echo "Fetches JIRA ticket content including description, status, and child issues."
    echo "Bare numbers default to LCORE- prefix."
    echo ""
    echo "Options:"
    echo "  --comments         Also fetch and print the ticket's comment thread."
    echo "                     Comments often contain critical decisions ('we decided"
    echo "                     in standup to defer X') that the description doesn't"
    echo "                     capture. Off by default."
    echo "  --linked-depth N   Recurse N levels deep into subtasks, linked issues,"
    echo "                     and parent-relation children. Default 0 (no recursion;"
    echo "                     just lists related-ticket keys/summaries). N=1 fetches"
    echo "                     the full content of immediate relations; N=2 fetches"
    echo "                     their relations too. Capped at 3 to avoid runaway"
    echo "                     fetches. Already-seen keys are skipped (cycle-safe)."
    echo "  --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  fetch-jira.sh 1234                   Fetch LCORE-1234"
    echo "  fetch-jira.sh LCORE-1234             Same"
    echo "  fetch-jira.sh 836 509 777            Fetch multiple tickets"
    echo "  fetch-jira.sh --comments 1234        Fetch LCORE-1234 with comments"
    echo "  fetch-jira.sh --linked-depth 1 1311  Fetch LCORE-1311 + immediate relations"
}

if [ $# -lt 1 ]; then
    show_help; exit 1
fi

# Parse flags (must come before any positional ticket arg)
FETCH_COMMENTS=0
LINKED_DEPTH=0
while [ $# -gt 0 ]; do
    case "$1" in
        --comments) FETCH_COMMENTS=1; shift ;;
        --linked-depth)
            [ $# -ge 2 ] || { echo "Error: --linked-depth requires a value"; exit 1; }
            LINKED_DEPTH="$2"
            if ! echo "$LINKED_DEPTH" | grep -qE '^[0-9]+$'; then
                echo "Error: --linked-depth must be a non-negative integer"; exit 1
            fi
            if [ "$LINKED_DEPTH" -gt 3 ]; then
                echo "Error: --linked-depth capped at 3 to avoid runaway fetches"; exit 1
            fi
            shift 2 ;;
        --help|-h) show_help; exit 0 ;;
        --*) echo "Unknown flag: $1"; show_help; exit 1 ;;
        *) break ;;  # first positional → ticket key
    esac
done

if [ $# -lt 1 ]; then
    echo "Error: no ticket specified"; show_help; exit 1
fi

ensure_jira_credentials

TICKET="$1"
# If bare number, prepend LCORE-
if echo "$TICKET" | grep -qE '^[0-9]+$'; then
    TICKET="LCORE-$TICKET"
fi

# Tracks already-fetched keys across recursion (space-delimited, with
# leading and trailing spaces so substring matching works cleanly).
FETCHED_KEYS=" "

fetch_ticket() {
    local key="$1"
    local indent="${2:-}"
    local depth="${3:-0}"

    # Cycle / dup protection
    case "$FETCHED_KEYS" in
        *" $key "*) return 0 ;;
    esac
    FETCHED_KEYS="$FETCHED_KEYS$key "

    local data
    data=$(curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        "$JIRA_INSTANCE/rest/api/3/issue/$key?fields=summary,status,issuetype,description,issuelinks,subtasks,parent" 2>/dev/null)

    # Optional: fetch comments (only if --comments was passed). Empty
    # JSON object signals "no comments fetched" to the Python printer.
    local comments_data='{}'
    if [ "$FETCH_COMMENTS" -eq 1 ]; then
        comments_data=$(curl -sS --connect-timeout 10 --max-time 30 \
            -u "$JIRA_EMAIL:$JIRA_TOKEN" \
            "$JIRA_INSTANCE/rest/api/3/issue/$key/comment" 2>/dev/null) || comments_data='{}'
    fi

    if echo "$data" | python3 -c "import sys,json; json.load(sys.stdin)['key']" >/dev/null 2>&1; then
        python3 -c "
import json, sys, textwrap

data = json.loads(sys.argv[1])
indent = sys.argv[2]
comments_data = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
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


# ADF (Atlassian Document Format) → markdown-ish text extractor.
# Hoisted to top-level so both description and comments can use it.
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
                elif m.get('type') == 'link':
                    # Keep the target: a link whose text differs from its
                    # href (ticket keys, "here", PR titles) is otherwise lost.
                    href = m.get('attrs', {}).get('href', '')
                    if href and href != text:
                        text = text + ' <' + href + '>'
            return [text]
        if ntype == 'inlineCard':
            # Smart links (pasted Jira/GitHub URLs) carry the URL only here.
            return ['<' + node.get('attrs', {}).get('url', '') + '>']
        if ntype == 'mention':
            return [node.get('attrs', {}).get('text', '@?')]
        if ntype == 'hardBreak':
            return ['\n']
        if ntype == 'rule':
            return ['---']
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
        if ntype == 'blockquote':
            child_text = []
            for c in node.get('content', []):
                child_text.extend(extract_text(c, depth))
            return ['> ' + l for l in ''.join(child_text).strip().split('\n')]
        if ntype == 'table':
            rows = []
            for row in node.get('content', []):
                cells = []
                for cell in row.get('content', []):
                    cell_text = []
                    for c in cell.get('content', []):
                        cell_text.extend(extract_text(c, depth))
                    cells.append(''.join(cell_text).strip())
                rows.append(' | '.join(cells))
            return rows
        for c in node.get('content', []):
            lines.extend(extract_text(c, depth))
        if ntype == 'paragraph' and lines:
            lines.append('')
    return lines


# Description
desc = fields.get('description')
if desc and isinstance(desc, dict):
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

# Comments (only when --comments was requested upstream; otherwise
# comments_data is the empty {} sentinel.)
comments = comments_data.get('comments', []) if isinstance(comments_data, dict) else []
if comments:
    print(f'{indent}Comments ({len(comments)}):')
    for c in comments:
        author = c.get('author', {}).get('displayName') or c.get('author', {}).get('emailAddress') or 'unknown'
        created = c.get('created', '')[:10]  # YYYY-MM-DD
        body = c.get('body')
        print(f'{indent}  --- {author} ({created}) ---')
        if isinstance(body, dict):
            # Reuse the same ADF extractor used for descriptions.
            text_lines = extract_text(body)
            text = '\n'.join(text_lines).strip()
            if not text:
                text = '(comment body in ADF format; no text extracted)'
        elif isinstance(body, str):
            text = body
        else:
            text = '(comment has no body)'
        for line in text.split('\n'):
            print(f'{indent}    {line}')
        print()
" "$data" "$indent" "$comments_data"
    else
        echo "${indent}Error fetching $key"
        echo "$data" | head -3
        return 1
    fi

    # Recurse into related tickets if depth > 0
    if [ "$depth" -gt 0 ]; then
        # Extract subtask + linked-issue keys from already-fetched data
        local related_keys
        related_keys=$(echo "$data" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    fields = d.get('fields', {})
    out = []
    for st in fields.get('subtasks', []):
        out.append(st['key'])
    for link in fields.get('issuelinks', []):
        if 'outwardIssue' in link:
            out.append(link['outwardIssue']['key'])
        elif 'inwardIssue' in link:
            out.append(link['inwardIssue']['key'])
    print(' '.join(out))
except Exception:
    pass
" 2>/dev/null)

        # Also fetch JQL parent= children
        local jql_kids
        jql_kids=$(curl -sS --connect-timeout 10 --max-time 30 \
            -u "$JIRA_EMAIL:$JIRA_TOKEN" \
            "$JIRA_INSTANCE/rest/api/3/search/jql?jql=parent%3D${key}&fields=key&maxResults=20" 2>/dev/null | \
            python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    for issue in d.get('issues', []):
        print(issue['key'])
except Exception:
    pass
" 2>/dev/null | tr '\n' ' ')

        local rk
        for rk in $related_keys $jql_kids; do
            [ -z "$rk" ] && continue
            echo
            fetch_ticket "$rk" "${indent}  " $((depth - 1))
        done
    fi
}

# Fetch main ticket (with depth recursion if requested)
fetch_ticket "$TICKET" "" "$LINKED_DEPTH"

# At depth 0, also list JQL parent= children as a flat summary (legacy
# behavior — useful as a quick "what's underneath" overview without
# fetching each one). At depth > 0, the recursive fetch_ticket already
# pulled them in, so skip this listing to avoid duplication.
if [ "$LINKED_DEPTH" -eq 0 ]; then
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
fi

# If additional ticket keys are passed as arguments, fetch those too
shift
for extra in "$@"; do
    if echo "$extra" | grep -qE '^[0-9]+$'; then
        extra="LCORE-$extra"
    fi
    echo "────────────────────────────────────────────────────────"
    echo ""
    fetch_ticket "$extra" "" "$LINKED_DEPTH"
done
