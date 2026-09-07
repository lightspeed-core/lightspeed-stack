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

# The Python programs below are held in quoted heredocs rather than
# passed inline to 'python3 -c'. An inline program sits inside a
# double-quoted shell word, which makes every quote, dollar sign and
# backtick in it shell syntax first and Python second. That is what broke
# this file with an SC2140 warning, and it stays a hazard for anyone
# editing the extractor. A <<'EOF' heredoc is passed through verbatim, so
# the Python can be written exactly as Python.

PRINT_TICKET_PY=$(cat <<'PYEOF_PRINT_TICKET_PY'
import datetime, json, sys, textwrap

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


# Jira appends its own '#icft=KEY' tracking fragment to internal smart
# links and issue mentions. It is never part of the target and only adds
# noise to the rendered line, so drop it from every URL we print.
def clean_url(url):
    return url.split('#icft=')[0] if '#icft=' in url else url


# ADF (Atlassian Document Format) → markdown-ish text extractor.
# Hoisted to top-level so both description and comments can use it.
def extract_text(node, depth=0):
    lines = []
    if isinstance(node, dict):
        ntype = node.get('type', '')
        if ntype == 'text':
            text = node.get('text', '')
            marks = node.get('marks', [])
            href = ''
            for m in marks:
                if m.get('type') == 'strong':
                    text = f'**{text}**'
                elif m.get('type') == 'code':
                    text = f'`{text}`'
                elif m.get('type') == 'em':
                    text = f'_{text}_'
                elif m.get('type') == 'strike':
                    text = f'~~{text}~~'
                elif m.get('type') == 'link':
                    href = m.get('attrs', {}).get('href', '')
            # Keep the target: a link whose text differs from its href
            # (ticket keys, 'here', PR titles) is otherwise lost. Appended
            # after the other marks so the URL never lands inside a code
            # span or bold run, whatever order the marks arrived in, and
            # compared against the raw text so an autolinked bare URL that
            # also carries a mark is still recognised as its own target.
            href = clean_url(href)
            if href and href != node.get('text', ''):
                text = text + ' <' + href + '>'
            return [text]
        if ntype == 'inlineCard':
            # Smart links (pasted Jira/GitHub URLs) carry the URL only here,
            # either directly or inside the resolved JSON-LD 'data' blob.
            attrs = node.get('attrs', {})
            data = attrs.get('data')
            url = attrs.get('url') or (data.get('url', '') if isinstance(data, dict) else '')
            url = clean_url(url)
            return ['<' + url + '>'] if url else []
        if ntype == 'mention':
            return [node.get('attrs', {}).get('text', '@?')]
        if ntype == 'emoji':
            attrs = node.get('attrs', {})
            return [attrs.get('text') or attrs.get('shortName') or '']
        if ntype == 'status':
            # A status lozenge carries meaning no other node repeats, so a
            # ticket saying a step is DONE reads as empty without this.
            label = node.get('attrs', {}).get('text', '')
            return ['[' + label + ']'] if label else []
        if ntype == 'date':
            timestamp = node.get('attrs', {}).get('timestamp', '')
            if not timestamp:
                return []
            try:
                moment = datetime.datetime.fromtimestamp(
                    int(timestamp) / 1000, datetime.timezone.utc
                )
                return [moment.strftime('%Y-%m-%d')]
            except (ValueError, TypeError, OverflowError, OSError):
                return [str(timestamp)]
        if ntype in ('media', 'mediaInline'):
            # Attachments have no text of their own; name them so a ticket
            # that argues from a screenshot does not read as if it argued
            # from nothing.
            attrs = node.get('attrs', {})
            name = attrs.get('alt') or attrs.get('id') or ''
            return ['[attachment: ' + name + ']'] if name else ['[attachment]']
        if ntype in ('mediaSingle', 'mediaGroup'):
            for c in node.get('content', []):
                lines.extend(extract_text(c, depth))
            return lines
        if ntype == 'hardBreak':
            return ['\n']
        if ntype == 'rule':
            return ['---']
        if ntype == 'paragraph':
            # A paragraph's children are inline runs — text, smart links,
            # mentions. The generic block walk below puts every child on its
            # own line, which chops any sentence containing a link into
            # fragments, so join them into one flowing line instead and let
            # an explicit hardBreak be the only thing that splits it.
            joined = ''.join(
                piece
                for c in node.get('content', [])
                for piece in extract_text(c, depth)
            )
            if not joined.strip():
                return []
            return joined.split('\n') + ['']
        if ntype == 'listItem':
            child_text = []
            for c in node.get('content', []):
                child_text.extend(extract_text(c, depth))
            # Join on a newline before collapsing so an item holding two
            # paragraphs keeps a space between them instead of running the
            # last word of one into the first word of the next. The marker
            # is added by the enclosing list, which is the only place that
            # knows whether the item needs a bullet or a number.
            return [' '.join('\n'.join(child_text).split())]
        if ntype in ('bulletList', 'orderedList'):
            ordered = ntype == 'orderedList'
            first = node.get('attrs', {}).get('order', 1) if ordered else 1
            try:
                first = int(first)
            except (ValueError, TypeError):
                first = 1
            for number, c in enumerate(node.get('content', []), start=first):
                for item in extract_text(c, depth + 1):
                    if not item:
                        continue
                    marker = f'{number}. ' if ordered else '- '
                    lines.append('  ' * (depth + 1) + marker + item)
            return lines
        if ntype == 'taskList':
            for c in node.get('content', []):
                lines.extend(extract_text(c, depth + 1))
            return lines
        if ntype == 'taskItem':
            # Without the box a done item and an open one render identically.
            child_text = []
            for c in node.get('content', []):
                child_text.extend(extract_text(c, depth))
            body = ' '.join('\n'.join(child_text).split())
            state = node.get('attrs', {}).get('state', 'TODO')
            box = '[x]' if state == 'DONE' else '[ ]'
            return ['  ' * depth + '- ' + box + ' ' + body] if body else []
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
            return ['```\n' + ''.join(child_text) + '\n```']
        if ntype == 'panel':
            # Jira panels carry their severity in the attrs, not the text,
            # so an info note and a warning read the same without this.
            panel_type = node.get('attrs', {}).get('panelType', 'info')
            child_text = []
            for c in node.get('content', []):
                child_text.extend(extract_text(c, depth))
            body = '\n'.join(child_text).strip()
            if not body:
                return []
            body_lines = body.split('\n')
            head = '**[' + panel_type.upper() + ']** ' + body_lines[0]
            return [head] + body_lines[1:] + ['']
        if ntype == 'blockquote':
            child_text = []
            for c in node.get('content', []):
                child_text.extend(extract_text(c, depth))
            # Children already come back one line each; joining on '' would
            # run every paragraph of the quote together into a single line.
            quoted = '\n'.join(child_text).strip()
            if not quoted:
                return []
            return ['> ' + ln if ln else '>' for ln in quoted.split('\n')]
        if ntype == 'table':
            rows = []
            for row in node.get('content', []):
                cells = []
                header = False
                for cell in row.get('content', []):
                    if cell.get('type') == 'tableHeader':
                        header = True
                    cell_text = []
                    for c in cell.get('content', []):
                        cell_text.extend(extract_text(c, depth))
                    # Collapse to a single line: a cell holding two
                    # paragraphs would otherwise inject a newline into the
                    # middle of the row and break the whole table. Join on a
                    # newline first so the paragraph boundary survives as the
                    # space that separates them.
                    cells.append(' '.join('\n'.join(cell_text).split()))
                if not cells:
                    continue
                rows.append(' | '.join(cells))
                # Emit the markdown rule under a header row so the result is
                # a real table rather than pipe-separated lines.
                if header and len(rows) == 1:
                    rows.append(' | '.join(['---'] * len(cells)))
            return rows + [''] if rows else []
        for c in node.get('content', []):
            lines.extend(extract_text(c, depth))
    return lines


# Description
desc = fields.get('description')
if desc and isinstance(desc, dict):
    text_lines = extract_text(desc)
    # Strip newlines only: a plain strip() would also eat the indent of the
    # first line, so a description opening with a list lost its leading
    # bullet indent while every later item kept it.
    desc_text = '\n'.join(text_lines).strip('\n')
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
            text = '\n'.join(text_lines).strip('\n')
            if not text:
                text = '(comment body in ADF format; no text extracted)'
        elif isinstance(body, str):
            text = body
        else:
            text = '(comment has no body)'
        for line in text.split('\n'):
            print(f'{indent}    {line}')
        print()
PYEOF_PRINT_TICKET_PY
)

RELATED_KEYS_PY=$(cat <<'PYEOF_RELATED_KEYS_PY'
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
PYEOF_RELATED_KEYS_PY
)

JQL_KIDS_PY=$(cat <<'PYEOF_JQL_KIDS_PY'
import json, sys
try:
    d = json.load(sys.stdin)
    for issue in d.get('issues', []):
        print(issue['key'])
except Exception:
    pass
PYEOF_JQL_KIDS_PY
)

CHILD_KEYS_PY=$(cat <<'PYEOF_CHILD_KEYS_PY'
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
PYEOF_CHILD_KEYS_PY
)

fetch_ticket() {
    local key="$1"
    local indent="${2:-}"
    local depth="${3:-0}"

    # Cycle / dup protection
    case "$FETCHED_KEYS" in
        *" $key "*) return 0 ;;
    esac
    FETCHED_KEYS="$FETCHED_KEYS$key "

    # The '|| data=' guard matters: under 'set -e' an unguarded assignment
    # from a failing curl aborts the whole script, so a single unreachable
    # ticket would kill a multi-ticket or recursive run instead of falling
    # through to the 'Error fetching' branch below and carrying on.
    local data
    data=$(curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        "$JIRA_INSTANCE/rest/api/3/issue/$key?fields=summary,status,issuetype,description,issuelinks,subtasks,parent" 2>/dev/null) || data=''

    # Optional: fetch comments (only if --comments was passed). Empty
    # JSON object signals "no comments fetched" to the Python printer.
    local comments_data='{}'
    if [ "$FETCH_COMMENTS" -eq 1 ]; then
        comments_data=$(curl -sS --connect-timeout 10 --max-time 30 \
            -u "$JIRA_EMAIL:$JIRA_TOKEN" \
            "$JIRA_INSTANCE/rest/api/3/issue/$key/comment" 2>/dev/null) || comments_data='{}'
    fi

    if echo "$data" | python3 -c "import sys,json; json.load(sys.stdin)['key']" >/dev/null 2>&1; then
        python3 -c "$PRINT_TICKET_PY" "$data" "$indent" "$comments_data"
    else
        echo "${indent}Error fetching $key"
        echo "$data" | head -3
        return 1
    fi

    # Recurse into related tickets if depth > 0
    if [ "$depth" -gt 0 ]; then
        # Extract subtask + linked-issue keys from already-fetched data
        local related_keys
        related_keys=$(echo "$data" | python3 -c "$RELATED_KEYS_PY" 2>/dev/null)

        # Also fetch JQL parent= children
        local jql_kids
        jql_kids=$(curl -sS --connect-timeout 10 --max-time 30 \
            -u "$JIRA_EMAIL:$JIRA_TOKEN" \
            "$JIRA_INSTANCE/rest/api/3/search/jql?jql=parent%3D${key}&fields=key&maxResults=20" 2>/dev/null | \
            python3 -c "$JQL_KIDS_PY" 2>/dev/null | tr '\n' ' ') || jql_kids=''

        local rk
        for rk in $related_keys $jql_kids; do
            [ -z "$rk" ] && continue
            echo
            # A relation we cannot fetch is reported by fetch_ticket and
            # then tolerated: it must not abandon the rest of the recursion.
            fetch_ticket "$rk" "${indent}  " $((depth - 1)) || true
        done
    fi
}

# Every requested ticket is attempted even when an earlier one fails, so
# one unreachable key does not hide the rest of the output; the script
# still exits non-zero if any of them failed.
EXIT_STATUS=0

# Fetch main ticket (with depth recursion if requested)
fetch_ticket "$TICKET" "" "$LINKED_DEPTH" || EXIT_STATUS=1

# At depth 0, also list JQL parent= children as a flat summary (legacy
# behavior — useful as a quick "what's underneath" overview without
# fetching each one). At depth > 0, the recursive fetch_ticket already
# pulled them in, so skip this listing to avoid duplication.
if [ "$LINKED_DEPTH" -eq 0 ]; then
    CHILD_KEYS=$(curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        "$JIRA_INSTANCE/rest/api/3/search/jql?jql=parent%3D${TICKET}&fields=key,summary,status,issuetype&maxResults=20" 2>/dev/null | \
        python3 -c "$CHILD_KEYS_PY" 2>/dev/null) || CHILD_KEYS=''

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
    fetch_ticket "$extra" "" "$LINKED_DEPTH" || EXIT_STATUS=1
done

exit "$EXIT_STATUS"
