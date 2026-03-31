#!/usr/bin/env bash
# File JIRA sub-tickets from a spike doc.
#
# Usage:
#   file-jiras.sh <spike-doc.md> <parent-ticket>
#
# Example:
#   file-jiras.sh docs/design/conversation-compaction/conversation-compaction-spike.md LCORE-1311
#
# Prerequisites:
#   ~/.config/jira/credentials.json with email, token, instance.
#
# The script:
#   1. Parses JIRA sections from the spike doc (### LCORE-???? headings)
#   2. Writes each to /tmp/jiras/NN-short-name.md
#   3. Opens an interactive menu: view, edit, drop, file
#   4. Files selected tickets via Jira REST API

set -euo pipefail

# shellcheck source=jira-common.sh
. "$(dirname "$0")/jira-common.sh"

JIRA_DIR="/tmp/jiras"

# --- Argument parsing ---

if [ $# -lt 2 ]; then
    echo "Usage: file-jiras.sh <spike-doc.md> <parent-ticket>"
    echo "Example: file-jiras.sh docs/design/.../spike.md LCORE-1311"
    exit 1
fi

SPIKE_DOC="$1"
PARENT_TICKET="$2"

if [ ! -f "$SPIKE_DOC" ]; then
    echo "Error: spike doc not found: $SPIKE_DOC"
    exit 1
fi

ensure_jira_credentials

# --- Parse spike doc ---

rm -rf "$JIRA_DIR"
mkdir -p "$JIRA_DIR"

python3 - "$SPIKE_DOC" "$JIRA_DIR" << 'PYEOF'
import re
import sys
from pathlib import Path

spike_doc = Path(sys.argv[1]).read_text()
out_dir = Path(sys.argv[2])

# Split on ### LCORE-???? headings
pattern = r'^### (LCORE-\?{4}.*?)$'
sections = re.split(pattern, spike_doc, flags=re.MULTILINE)

# sections[0] is everything before the first JIRA heading
# Then alternating: heading, body, heading, body, ...
count = 0
for i in range(1, len(sections), 2):
    heading = sections[i].strip()
    body = sections[i + 1].strip() if i + 1 < len(sections) else ""

    # Stop if we hit a non-JIRA heading (e.g., "# PoC results")
    if not heading.startswith("LCORE-"):
        break

    count += 1

    # Truncate body at the first # or ## heading (end of JIRAs section)
    end_match = re.search(r'^#{1,2}\s', body, flags=re.MULTILINE)
    if end_match:
        body = body[:end_match.start()].strip()

    # Strip "LCORE-????: " prefix to get clean title
    clean_title = re.sub(r'^LCORE-\?+:?\s*', '', heading).strip()

    # Extract short name for filename
    short_name = re.sub(r'[^a-z0-9]+', '-', clean_title.lower()).strip('-')
    if not short_name:
        short_name = f"ticket-{count}"

    filename = f"{count:02d}-{short_name}.md"
    content = f"### {clean_title}\n\n{body}\n"
    (out_dir / filename).write_text(content)

print(f"Parsed {count} JIRAs from {sys.argv[1]}")
PYEOF

# --- Count tickets ---

TICKET_COUNT=$(find "$JIRA_DIR" -maxdepth 1 -name '*.md' | wc -l)
if [ "$TICKET_COUNT" -eq 0 ]; then
    echo "No JIRA sections found in $SPIKE_DOC"
    echo "Expected headings like: ### LCORE-???? Title"
    exit 1
fi

# --- Helper functions ---

show_summary() {
    echo ""
    echo "  #  File                                         Title"
    echo "  -- -------------------------------------------- ----------------------------------------"
    i=1
    for f in "$JIRA_DIR"/*.md; do
        title=$(head -1 "$f" | sed 's/^### //')
        fname=$(basename "$f")
        printf "  %-2d %-44s %s\n" "$i" "$fname" "$title"
        i=$((i + 1))
    done
    echo ""
    echo "Parent: $PARENT_TICKET"
    echo "Total: $TICKET_COUNT tickets"
    echo ""
}

get_file_by_number() {
    find "$JIRA_DIR" -maxdepth 1 -name '*.md' | sort | sed -n "${1}p"
}

file_ticket() {
    local ticket_file="$1"
    local title
    title=$(head -1 "$ticket_file" | sed 's/^### //')

    # Check for duplicates
    local project_key="${PARENT_TICKET%%-*}"
    local url_title
    url_title=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$title")
    local dup_check
    dup_check=$(curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        "$JIRA_INSTANCE/rest/api/3/search/jql?jql=project%3D${project_key}%20AND%20summary~%22${url_title}%22&fields=key,summary&maxResults=5" 2>/dev/null || echo "{}")

    local dup_count_file
    dup_count_file=$(mktemp)
    python3 -c "
import json, sys
title = sys.argv[1]
instance = sys.argv[2]
count_file = sys.argv[4]
try:
    data = json.loads(sys.argv[3])
    issues = data.get('issues', [])
    exact = [i for i in issues if i['fields']['summary'].strip().lower() == title.strip().lower()]
    for i in exact:
        print(f'  Existing JIRA with same summary: {i[\"key\"]} — {i[\"fields\"][\"summary\"]}')
        print(f'  {instance}/browse/{i[\"key\"]}')
    with open(count_file, 'w') as f:
        f.write(str(len(exact)))
except Exception as e:
    print(f'  Duplicate check failed: {e}')
    with open(count_file, 'w') as f:
        f.write('-1')
" "$title" "$JIRA_INSTANCE" "$dup_check" "$dup_count_file" >&2
    local dup_count
    dup_count=$(cat "$dup_count_file")
    rm -f "$dup_count_file"

    if [ "$dup_count" -lt 0 ] 2>/dev/null; then
        echo "  Duplicate check failed; skipping ticket for safety." >&2
        return 1
    fi
    if [ "$dup_count" -gt 0 ] 2>/dev/null; then
        printf "  File anyway? (y/n): " >&2
        read -r confirm < /dev/tty
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "  Skipped: $title" >&2
            return 1
        fi
    fi

    # Extract description body (everything after the heading)
    local body
    body=$(tail -n +3 "$ticket_file")

    # Build ADF description from the body text
    local adf_desc
    adf_desc=$(python3 - "$body" << 'ADFEOF'
import json
import re
import sys


def parse_inline(text):
    """Convert markdown inline formatting to ADF text nodes with marks."""
    nodes = []
    # Match: **bold**, *italic*, `code`, [text](url), plain text
    pattern = r'(\*\*.*?\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))'
    parts = re.split(pattern, text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            nodes.append({
                "type": "text",
                "text": part[2:-2],
                "marks": [{"type": "strong"}]
            })
        elif part.startswith("*") and part.endswith("*") and not part.startswith("**"):
            nodes.append({
                "type": "text",
                "text": part[1:-1],
                "marks": [{"type": "em"}]
            })
        elif part.startswith("`") and part.endswith("`"):
            nodes.append({
                "type": "text",
                "text": part[1:-1],
                "marks": [{"type": "code"}]
            })
        elif part.startswith("["):
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', part)
            if m:
                nodes.append({
                    "type": "text",
                    "text": m.group(1),
                    "marks": [{"type": "link", "attrs": {"href": m.group(2)}}]
                })
            else:
                nodes.append({"type": "text", "text": part})
        else:
            nodes.append({"type": "text", "text": part})
    return nodes


def make_paragraph(text):
    return {"type": "paragraph", "content": parse_inline(text)}


def parse_block(para):
    """Convert a markdown block (paragraph, list, heading, code) to ADF node(s)."""
    # Heading
    m = re.match(r'^(#{1,6})\s+(.*)', para)
    if m:
        level = len(m.group(1))
        return {"type": "heading", "attrs": {"level": level}, "content": parse_inline(m.group(2))}

    # Bullet list
    if para.startswith("- "):
        items = [line.lstrip("- ").strip() for line in para.split("\n") if line.strip().startswith("- ")]
        list_items = [{"type": "listItem", "content": [make_paragraph(item)]} for item in items]
        if list_items:
            return {"type": "bulletList", "content": list_items}

    # Numbered list
    if re.match(r'^\d+[\.\)]\s', para):
        items = [re.sub(r'^\d+[\.\)]\s*', '', line).strip() for line in para.split("\n") if re.match(r'^\s*\d+[\.\)]\s', line)]
        list_items = [{"type": "listItem", "content": [make_paragraph(item)]} for item in items]
        if list_items:
            return {"type": "orderedList", "content": list_items}

    # Code block
    if para.startswith("```"):
        code = para.strip("`").strip()
        return {"type": "codeBlock", "content": [{"type": "text", "text": code}]}

    # Plain paragraph
    return make_paragraph(para)


text = sys.argv[1]

# Strip the redundant "**Description**:" line — Jira already has a Description field
text = re.sub(r'^\*\*Description\*\*:\s*', '', text).strip()

paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

content = []
for para in paragraphs:
    node = parse_block(para)
    if node:
        content.append(node)

doc = {"version": 1, "type": "doc", "content": content}
print(json.dumps(doc))
ADFEOF
    )

    # Create the issue
    local payload
    payload=$(python3 - "${PARENT_TICKET%%-*}" "$title" "$adf_desc" "$PARENT_TICKET" << 'PAYEOF'
import json
import sys

project_key, summary, adf_desc_json, parent_ticket = sys.argv[1:5]
print(json.dumps({
    "fields": {
        "project": {"key": project_key},
        "issuetype": {"name": "Task"},
        "summary": summary,
        "description": json.loads(adf_desc_json),
    },
    "update": {
        "issuelinks": [{
            "add": {
                "type": {"name": "Blocks"},
                "outwardIssue": {"key": parent_ticket},
            }
        }]
    }
}))
PAYEOF
)

    local response
    response=$(curl -sS --connect-timeout 10 --max-time 30 -w "\n%{http_code}" \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST "$JIRA_INSTANCE/rest/api/3/issue" \
        -d "$payload")

    local http_code
    http_code=$(echo "$response" | tail -1)
    local body_resp
    body_resp=$(echo "$response" | sed '$d')

    if [ "$http_code" = "201" ]; then
        local key
        key=$(echo "$body_resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
        echo "  Created: $key — $title" >&2
        echo "  $JIRA_INSTANCE/browse/$key" >&2
        echo "$key"
        return 0
    else
        echo "  FAILED ($http_code): $title" >&2
        echo "  $body_resp" >&2
        return 1
    fi
}

# --- Interactive loop ---

show_summary

while true; do
    printf "Command (view|v, edit|e, drop|d, file|f, quit|q): "
    read -r cmd args || exit 0
    args="${args:-}"

    case "$cmd" in
        view|v)
            if [ "$args" = "all" ]; then
                for f in "$JIRA_DIR"/*.md; do
                    echo ""
                    echo "════════════════════════════════════════════════════════════"
                    echo "  $(basename "$f")"
                    echo "════════════════════════════════════════════════════════════"
                    echo ""
                    cat "$f"
                    echo ""
                done
            elif [ -n "$args" ]; then
                for n in $(echo "$args" | tr ',' ' '); do
                    f=$(get_file_by_number "$n")
                    if [ -n "$f" ]; then
                        echo ""
                        echo "════════════════════════════════════════════════════════════"
                        echo "  $(basename "$f")"
                        echo "════════════════════════════════════════════════════════════"
                        echo ""
                        cat "$f"
                        echo ""
                    else
                        echo "  No ticket #$n"
                    fi
                done
            else
                echo "  Usage: view N or view N,M or view all"
            fi
            show_summary
            ;;
        edit|e)
            editor="${EDITOR:-vi}"
            if [ "$args" = "all" ]; then
                $editor "$JIRA_DIR"/*.md
            elif [ -n "$args" ]; then
                files=""
                for n in $(echo "$args" | tr ',' ' '); do
                    f=$(get_file_by_number "$n")
                    if [ -n "$f" ]; then
                        files="$files $f"
                    else
                        echo "  No ticket #$n"
                    fi
                done
                if [ -n "$files" ]; then
                    # shellcheck disable=SC2086
                    $editor $files
                fi
            else
                echo "  Usage: edit N or edit N,M or edit all"
            fi
            show_summary
            ;;
        drop|d)
            if [ -n "$args" ]; then
                for n in $(echo "$args" | tr ',' ' '); do
                    f=$(get_file_by_number "$n")
                    if [ -n "$f" ]; then
                        echo "  Dropped: $(basename "$f")"
                        rm "$f"
                        TICKET_COUNT=$((TICKET_COUNT - 1))
                    else
                        echo "  No ticket #$n"
                    fi
                done
                show_summary
            else
                echo "  Usage: drop N or drop N,M"
            fi
            ;;
        file|f)
            created_keys=""
            if [ "$args" = "all" ]; then
                for f in "$JIRA_DIR"/*.md; do
                    key=$(file_ticket "$f") && created_keys="$created_keys $key"
                done
            elif [ -n "$args" ]; then
                for n in $(echo "$args" | tr ',' ' '); do
                    f=$(get_file_by_number "$n")
                    if [ -n "$f" ]; then
                        key=$(file_ticket "$f") && created_keys="$created_keys $key"
                    else
                        echo "  No ticket #$n"
                    fi
                done
            else
                echo "  Usage: file N or file N,M or file all"
            fi
            if [ -n "$created_keys" ]; then
                echo ""
                echo "Created:$created_keys"
            fi
            show_summary
            ;;
        quit|q)
            echo "Exiting. Ticket files remain in $JIRA_DIR/"
            exit 0
            ;;
        "")
            ;;
        *)
            echo "  Commands: view(v), edit(e), drop(d), file(f), quit(q)"
            ;;
    esac
done
