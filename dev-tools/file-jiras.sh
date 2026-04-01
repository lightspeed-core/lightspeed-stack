#!/usr/bin/env bash
# File JIRA sub-tickets from a spike doc.
#
# Usage:
#   file-jiras.sh --spike-doc <path> --feature-ticket <key>
#   file-jiras.sh --spike-doc spike.md --feature-ticket LCORE-1311
#   file-jiras.sh --spike-doc spike.md --feature-ticket 1311
#
# Bare numbers default to LCORE- prefix.
#
# The script:
#   1. Parses JIRA sections from the spike doc (### LCORE-???? headings)
#   2. Auto-generates an Epic stub (ticket #0)
#   3. Reads <!-- type: Task/Story/Epic --> metadata from each ticket
#   4. Opens an interactive menu: view, edit, drop, file
#   5. Files Epic first, then children under it
#   6. Links spike ticket to Epic with "Informs" relationship

set -euo pipefail

# shellcheck source=jira-common.sh
. "$(dirname "$0")/jira-common.sh"

EPIC_KEY=""
SPIKE_TICKET_KEY=""

# --- Argument parsing ---

show_help() {
    echo "Usage: file-jiras.sh --spike-doc <path> --feature-ticket <key> [--output-dir <path>]"
    echo ""
    echo "Options:"
    echo "  --spike-doc        Path to the spike doc containing proposed JIRAs"
    echo "  --feature-ticket   Parent feature ticket (e.g., LCORE-1311 or 1311)"
    echo "  --output-dir       Directory for parsed ticket files (default: <spike-doc-dir>/jiras/)"
    echo "  --help             Show this help"
    echo ""
    echo "Example:"
    echo "  file-jiras.sh --spike-doc docs/design/.../spike.md --feature-ticket 1311"
}

SPIKE_DOC=""
FEATURE_TICKET=""
JIRA_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --spike-doc) SPIKE_DOC="$2"; shift 2 ;;
        --feature-ticket) FEATURE_TICKET="$2"; shift 2 ;;
        --output-dir) JIRA_DIR="$2"; shift 2 ;;
        --help|-h) show_help; exit 0 ;;
        *) echo "Unknown argument: $1"; show_help; exit 1 ;;
    esac
done

if [ -z "$SPIKE_DOC" ] || [ -z "$FEATURE_TICKET" ]; then
    show_help
    exit 1
fi

# Bare number → LCORE- prefix
if echo "$FEATURE_TICKET" | grep -qE '^[0-9]+$'; then
    FEATURE_TICKET="LCORE-$FEATURE_TICKET"
fi

if [ ! -f "$SPIKE_DOC" ]; then
    echo "Error: spike doc not found: $SPIKE_DOC"
    exit 1
fi

# Default output dir: docs/design/<feature>/jiras/ (next to the spike doc)
if [ -z "$JIRA_DIR" ]; then
    SPIKE_DIR=$(dirname "$SPIKE_DOC")
    JIRA_DIR="$SPIKE_DIR/jiras"
fi

ensure_jira_credentials

PROJECT_KEY="${FEATURE_TICKET%%-*}"

# --- Helper functions (needed before parse for key detection) ---

get_type() {
    local f="$1"
    grep -o '<!-- type: [A-Za-z]* -->' "$f" 2>/dev/null | head -1 | sed 's/<!-- type: //;s/ -->//' || echo "Task"
}

get_key() {
    local f="$1"
    grep -o '<!-- key: [A-Z]*-[0-9]* -->' "$f" 2>/dev/null | head -1 | sed 's/<!-- key: //;s/ -->//' || true
}

set_key() {
    local f="$1"
    local key="$2"
    if grep -q '<!-- key:' "$f" 2>/dev/null; then
        sed -i "s/<!-- key: [A-Z]*-[0-9]* -->/<!-- key: $key -->/" "$f"
    else
        sed -i "1a\\<!-- key: $key -->" "$f"
    fi
}

# --- Parse spike doc ---

if [ -d "$JIRA_DIR" ] && ls "$JIRA_DIR"/*.md >/dev/null 2>&1; then
    printf "Existing ticket files found in $JIRA_DIR/. Re-parse (existing ticket files will be overwritten)? (y/n): " >&2
    read -r reparse
    if [ "$reparse" != "y" ] && [ "$reparse" != "Y" ]; then
        echo "Using existing files."
        # Skip to interactive loop
        SKIP_PARSE=1
    fi
fi

if [ "${SKIP_PARSE:-}" != "1" ]; then
rm -rf "$JIRA_DIR"
mkdir -p "$JIRA_DIR"

python3 - "$SPIKE_DOC" "$JIRA_DIR" "$FEATURE_TICKET" << 'PYEOF'
import re
import sys
from pathlib import Path

spike_doc = Path(sys.argv[1]).read_text()
out_dir = Path(sys.argv[2])
feature_ticket = sys.argv[3]

# --- Extract spike ticket key from metadata table or first paragraph ---
spike_key_match = re.search(r'\*\*Spike\*\*.*?(LCORE-\d+)', spike_doc)
if not spike_key_match:
    # Try "deliverable for LCORE-XXXX" pattern
    spike_key_match = re.search(r'deliverable for (LCORE-\d+)', spike_doc)
if not spike_key_match:
    # Try first LCORE- reference in the first 500 chars
    spike_key_match = re.search(r'(LCORE-\d+)', spike_doc[:500])
spike_key = spike_key_match.group(1) if spike_key_match else ""

# --- Extract one-line problem statement for Epic description ---
problem_match = re.search(r'\*\*The problem\*\*:\s*(.+?)(?:\n\n|\n\*\*)', spike_doc, re.DOTALL)
problem_line = problem_match.group(1).strip().split('\n')[0] if problem_match else ""

# --- Generate Epic stub ---
# Derive Epic title from the spike doc's parent directory name
spike_path = Path(sys.argv[1])
feature_dir = spike_path.parent.name
if feature_dir and feature_dir not in ('design', 'docs', '.'):
    epic_title = f"Implement {feature_dir.replace('-', ' ')}"
else:
    epic_title = "TODO: Epic title"

epic_content = f"<!-- type: Epic -->\n### {epic_title}\n"

(out_dir / "00-epic.md").write_text(epic_content)

# --- Parse JIRA sections ---
pattern = r'^### (LCORE-\?{4}.*?)$'
sections = re.split(pattern, spike_doc, flags=re.MULTILINE)

count = 0
for i in range(1, len(sections), 2):
    heading = sections[i].strip()
    body = sections[i + 1].strip() if i + 1 < len(sections) else ""

    if not heading.startswith("LCORE-"):
        break

    count += 1

    # Truncate body at the first # or ## heading (end of JIRAs section)
    end_match = re.search(r'^#{1,2}\s', body, flags=re.MULTILINE)
    if end_match:
        body = body[:end_match.start()].strip()

    # Strip "LCORE-????: " prefix to get clean title
    clean_title = re.sub(r'^LCORE-\?+:?\s*', '', heading).strip()

    # Extract type: look in the preceding section's last line (the comment
    # sits on the line before the ### heading), then fall back to body.
    ticket_type = "Task"
    if i > 0:
        preceding = sections[i - 1] if i - 1 >= 0 else ""
        for line in preceding.strip().split('\n')[-3:]:
            m = re.search(r'<!--\s*type:\s*(\w+)\s*-->', line)
            if m:
                ticket_type = m.group(1)
                break

    # Strip any <!-- type: ... --> that leaked into body from the next ticket
    body = re.sub(r'\n<!--\s*type:\s*\w+\s*-->\s*$', '', body).strip()

    # Extract short name for filename
    short_name = re.sub(r'[^a-z0-9]+', '-', clean_title.lower()).strip('-')
    if not short_name:
        short_name = f"ticket-{count}"

    filename = f"{count:02d}-{short_name}.md"

    # Write with type metadata at top
    content = f"<!-- type: {ticket_type} -->\n### {clean_title}\n\n{body}\n"

    (out_dir / filename).write_text(content)

# Write metadata file for the script to read
meta = {"spike_ticket": spike_key, "count": count}
import json
(out_dir / ".meta.json").write_text(json.dumps(meta))

print(f"Parsed {count} JIRAs + 1 Epic from {sys.argv[1]}")
if spike_key:
    print(f"Spike ticket: {spike_key}")
PYEOF

fi  # end SKIP_PARSE

# --- Read metadata ---
if [ -f "$JIRA_DIR/.meta.json" ]; then
    SPIKE_TICKET_KEY=$(python3 -c "import json; print(json.load(open('$JIRA_DIR/.meta.json')).get('spike_ticket', ''))")
fi

# Check if Epic already has a key from a previous session
EPIC_FILE=$(find "$JIRA_DIR" -maxdepth 1 -name '00-epic.md' 2>/dev/null | head -1)
if [ -n "$EPIC_FILE" ]; then
    EPIC_KEY=$(get_key "$EPIC_FILE")
fi

# --- Helper functions ---

show_summary() {
    echo ""
    printf "  %-3s %-7s %-13s %-35s %s\n" "#" "Type" "Status" "Title" "Parent"
    printf "  %-3s %-7s %-13s %-35s %s\n" "---" "-------" "-------------" "-----------------------------------" "--------------------"
    local i=0
    for f in "$JIRA_DIR"/*.md; do
        local title
        title=$(grep '^### ' "$f" | head -1 | sed 's/^### //')
        local ttype
        ttype=$(get_type "$f")
        local existing_key
        existing_key=$(get_key "$f")
        local status parent
        if [ -n "$existing_key" ]; then
            status="filed:$existing_key"
        else
            status="new"
        fi
        if [ "$ttype" = "Epic" ]; then
            parent="$FEATURE_TICKET"
        elif [ -n "$EPIC_KEY" ] && [ "$EPIC_KEY" != "__NONE__" ]; then
            parent="$EPIC_KEY"
        else
            parent="Epic #0"
        fi
        printf "  %-3d %-7s %-13s %-35s %s\n" "$i" "$ttype" "$status" "$title" "$parent"
        i=$((i + 1))
    done
    echo ""
    if [ -n "$SPIKE_TICKET_KEY" ]; then
        echo "  Spike ticket $SPIKE_TICKET_KEY will be linked to Epic with \"Informs\""
    fi
    echo ""
}

get_file_by_number() {
    find "$JIRA_DIR" -maxdepth 1 -name '*.md' | sort | sed -n "$((${1} + 1))p"
}

ensure_epic_key() {
    # If we already have an Epic key, nothing to do
    if [ -n "$EPIC_KEY" ]; then
        return 0
    fi

    echo ""
    echo "  No Epic filed yet. Children need an Epic parent."
    echo "    1. File Epic #0 first, then continue"
    echo "    2. Enter an existing Epic key (e.g., LCORE-1600)"
    echo "    3. File without Epic (Blocks link to $FEATURE_TICKET instead)"
    printf "  Choice (1/2/3): "
    read -r choice < /dev/tty

    case "$choice" in
        1)
            local epic_file
            epic_file=$(find "$JIRA_DIR" -maxdepth 1 -name '*.md' | sort | head -1)
            local epic_type
            epic_type=$(get_type "$epic_file")
            if [ "$epic_type" != "Epic" ]; then
                echo "  Error: first ticket is not an Epic. Edit it or re-order files." >&2
                return 1
            fi
            EPIC_KEY=$(file_single_ticket "$epic_file" "Epic" "$FEATURE_TICKET")
            if [ -z "$EPIC_KEY" ]; then
                echo "  Epic filing failed." >&2
                return 1
            fi
            # Link spike ticket to Epic
            if [ -n "$SPIKE_TICKET_KEY" ]; then
                link_spike_to_epic
            fi
            ;;
        2)
            printf "  Epic key: "
            read -r EPIC_KEY < /dev/tty
            ;;
        3)
            EPIC_KEY="__NONE__"
            ;;
        *)
            echo "  Invalid choice."
            return 1
            ;;
    esac
}

link_spike_to_epic() {
    if [ -z "$SPIKE_TICKET_KEY" ] || [ -z "$EPIC_KEY" ] || [ "$EPIC_KEY" = "__NONE__" ]; then
        return
    fi
    local link_payload
    link_payload=$(python3 -c "
import json
print(json.dumps({
    'type': {'name': 'Informs'},
    'inwardIssue': {'key': '$SPIKE_TICKET_KEY'},
    'outwardIssue': {'key': '$EPIC_KEY'}
}))
")
    curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST "$JIRA_INSTANCE/rest/api/3/issueLink" \
        -d "$link_payload" >/dev/null 2>&1 && \
        echo "  Linked: $SPIKE_TICKET_KEY informs $EPIC_KEY" >&2 || \
        echo "  Warning: failed to link $SPIKE_TICKET_KEY to $EPIC_KEY" >&2
}

file_single_ticket() {
    local ticket_file="$1"
    local issue_type="$2"
    local parent_key="$3"

    local title
    title=$(grep '^### ' "$ticket_file" | head -1 | sed 's/^### //')

    # Check if this ticket already has a key (update instead of create)
    local existing_key
    existing_key=$(get_key "$ticket_file")

    # Skip duplicate check for updates — we already know the ticket
    if [ -z "$existing_key" ]; then
    # Check for duplicates
    local url_title
    url_title=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$title")
    local dup_check
    dup_check=$(curl -sS --connect-timeout 10 --max-time 30 \
        -u "$JIRA_EMAIL:$JIRA_TOKEN" \
        "$JIRA_INSTANCE/rest/api/3/search/jql?jql=project%3D${PROJECT_KEY}%20AND%20summary~%22${url_title}%22&fields=key,summary&maxResults=5" 2>/dev/null || echo "{}")

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
    fi  # end skip duplicate check for updates

    # Extract description body (everything after the heading, skip metadata comments)
    local body
    body=$(grep -v '^<!-- \(type\|key\):' "$ticket_file" | tail -n +2)

    # Build ADF description
    local adf_desc
    adf_desc=$(python3 - "$body" << 'ADFEOF'
import json
import re
import sys


def parse_inline(text):
    nodes = []
    pattern = r'(\*\*.*?\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))'
    parts = re.split(pattern, text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            nodes.append({"type": "text", "text": part[2:-2], "marks": [{"type": "strong"}]})
        elif part.startswith("*") and part.endswith("*") and not part.startswith("**"):
            nodes.append({"type": "text", "text": part[1:-1], "marks": [{"type": "em"}]})
        elif part.startswith("`") and part.endswith("`"):
            nodes.append({"type": "text", "text": part[1:-1], "marks": [{"type": "code"}]})
        elif part.startswith("["):
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', part)
            if m:
                nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "link", "attrs": {"href": m.group(2)}}]})
            else:
                nodes.append({"type": "text", "text": part})
        else:
            nodes.append({"type": "text", "text": part})
    return nodes


def make_paragraph(text):
    return {"type": "paragraph", "content": parse_inline(text)}


def parse_block(para):
    m = re.match(r'^(#{1,6})\s+(.*)', para)
    if m:
        level = len(m.group(1))
        return {"type": "heading", "attrs": {"level": level}, "content": parse_inline(m.group(2))}
    if para.startswith("- "):
        items = [line.lstrip("- ").strip() for line in para.split("\n") if line.strip().startswith("- ")]
        list_items = [{"type": "listItem", "content": [make_paragraph(item)]} for item in items]
        if list_items:
            return {"type": "bulletList", "content": list_items}
    if re.match(r'^\d+[\.\)]\s', para):
        items = [re.sub(r'^\d+[\.\)]\s*', '', line).strip() for line in para.split("\n") if re.match(r'^\s*\d+[\.\)]\s', line)]
        list_items = [{"type": "listItem", "content": [make_paragraph(item)]} for item in items]
        if list_items:
            return {"type": "orderedList", "content": list_items}
    if para.startswith("```"):
        code = para.strip("`").strip()
        return {"type": "codeBlock", "content": [{"type": "text", "text": code}]}
    return make_paragraph(para)


text = sys.argv[1]
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

    if [ -n "$existing_key" ]; then
        # UPDATE existing ticket (summary, description, parent)
        local update_payload
        update_payload=$(python3 - "$title" "$adf_desc" "$parent_key" << 'UPDEOF'
import json
import sys

summary, adf_desc_json, parent_key = sys.argv[1:4]
fields = {
    "summary": summary,
    "description": json.loads(adf_desc_json),
}
if parent_key:
    fields["parent"] = {"key": parent_key}
print(json.dumps({"fields": fields}))
UPDEOF
)
        local response
        response=$(curl -sS --connect-timeout 10 --max-time 30 -w "\n%{http_code}" \
            -u "$JIRA_EMAIL:$JIRA_TOKEN" \
            -H "Content-Type: application/json" \
            -X PUT "$JIRA_INSTANCE/rest/api/3/issue/$existing_key" \
            -d "$update_payload")

        local http_code
        http_code=$(echo "$response" | tail -1)

        if [ "$http_code" = "204" ]; then
            echo "  Updated: $existing_key — $title ($issue_type)" >&2
            echo "  $JIRA_INSTANCE/browse/$existing_key" >&2
            echo "$existing_key"
            return 0
        else
            local body_resp
            body_resp=$(echo "$response" | sed '$d')
            echo "  FAILED update ($http_code): $existing_key — $title" >&2
            echo "  $body_resp" >&2
            return 1
        fi
    else
        # CREATE new ticket
        local payload
        payload=$(python3 - "$PROJECT_KEY" "$title" "$adf_desc" "$parent_key" "$issue_type" << 'PAYEOF'
import json
import sys

project_key, summary, adf_desc_json, parent_key, issue_type = sys.argv[1:6]
fields = {
    "project": {"key": project_key},
    "issuetype": {"name": issue_type},
    "summary": summary,
    "description": json.loads(adf_desc_json),
    "parent": {"key": parent_key},
}
print(json.dumps({"fields": fields}))
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
            echo "  Created: $key — $title ($issue_type)" >&2
            echo "  $JIRA_INSTANCE/browse/$key" >&2
            # Write key back into the file
            set_key "$ticket_file" "$key"
            echo "$key"
            return 0
        else
            echo "  FAILED ($http_code): $title" >&2
            echo "  $body_resp" >&2
            return 1
        fi
    fi
}

file_ticket() {
    local ticket_file="$1"
    local ttype
    ttype=$(get_type "$ticket_file")

    if [ "$ttype" = "Epic" ]; then
        # Check if Epic already has a key (pre-existing)
        local epic_existing
        epic_existing=$(get_key "$ticket_file")
        if [ -n "$epic_existing" ]; then
            EPIC_KEY="$epic_existing"
        fi
        EPIC_KEY=$(file_single_ticket "$ticket_file" "Epic" "$FEATURE_TICKET")
        if [ -n "$EPIC_KEY" ] && [ -n "$SPIKE_TICKET_KEY" ]; then
            link_spike_to_epic
        fi
        echo "$EPIC_KEY"
    else
        # Need an Epic key for children — refresh from Epic file if not set
        if [ -z "$EPIC_KEY" ] || [ "$EPIC_KEY" = "__NONE__" ]; then
            local epic_file
            epic_file=$(find "$JIRA_DIR" -maxdepth 1 -name '00-epic.md' 2>/dev/null | head -1)
            if [ -n "$epic_file" ]; then
                local ek
                ek=$(get_key "$epic_file")
                if [ -n "$ek" ]; then
                    EPIC_KEY="$ek"
                fi
            fi
        fi
        if [ -z "$EPIC_KEY" ] || [ "$EPIC_KEY" = "__NONE__" ]; then
            ensure_epic_key || return 1
        fi
        if [ "$EPIC_KEY" = "__NONE__" ]; then
            # Fallback: Blocks link (filed as standalone Task linked to feature)
            file_single_ticket "$ticket_file" "$ttype" "$FEATURE_TICKET"
        else
            file_single_ticket "$ticket_file" "$ttype" "$EPIC_KEY"
        fi
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
                    echo "  $(basename "$f")  [$(get_type "$f")]"
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
                        echo "  $(basename "$f")  [$(get_type "$f")]"
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
                echo "Filed:$created_keys"
            fi
            # Refresh EPIC_KEY from file (subshell can't propagate variable changes)
            local epic_file
            epic_file=$(find "$JIRA_DIR" -maxdepth 1 -name '00-epic.md' 2>/dev/null | head -1)
            if [ -n "$epic_file" ]; then
                local ek
                ek=$(get_key "$epic_file")
                if [ -n "$ek" ]; then
                    EPIC_KEY="$ek"
                fi
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
