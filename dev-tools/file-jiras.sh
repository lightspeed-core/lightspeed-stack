#!/usr/bin/env bash
# File JIRA sub-tickets from a spike doc or template with placeholders.
#
# Usage:
#   file-jiras.sh --spike-doc <path> --feature-ticket <key>
#   file-jiras.sh --spike-doc spike.md --feature-ticket LCORE-1311
#   file-jiras.sh --spike-doc spike.md --feature-ticket 1311
#   file-jiras.sh --spike-doc release-jiras.md --feature-ticket LCORE-2000 \
#                 --var X=0 --var Y=7 --var Z=0 --var PRE=rc1
#
# Bare numbers default to LCORE- prefix.
#
# The script:
#   1. Replaces {KEY} placeholders with --var values (if any)
#   2. Parses JIRA sections from the doc (### LCORE-???? headings)
#   3. Auto-generates an Epic stub (ticket #0)
#   4. Reads <!-- type: Task/Story/Epic --> metadata from each ticket
#   5. Opens an interactive menu: view, edit, drop, file
#   6. Files Epic first, then children under it
#   7. Links spike ticket to Epic with "Informs" relationship

set -euo pipefail

# shellcheck disable=SC1091
. "$(dirname "$0")/jira-common.sh"

EPIC_KEY=""
SPIKE_TICKET_KEY=""

# --- Argument parsing ---

show_help() {
    echo "Usage: file-jiras.sh --spike-doc <path> --feature-ticket <key> [--output-dir <path>] [--parse-only]"
    echo "                     [--var KEY=VALUE ...]"
    echo ""
    echo "Options:"
    echo "  --spike-doc        Path to the spike doc containing proposed JIRAs"
    echo "  --feature-ticket   Parent feature ticket (e.g., LCORE-1311 or 1311)"
    echo "  --output-dir       Directory for parsed ticket files (default: <spike-doc-dir>/jiras/)"
    echo "  --var KEY=VALUE    Replace {KEY} placeholders in the doc before parsing."
    echo "                     Repeatable. Useful for template docs like release-jiras.md."
    echo "                     Example: --var X=0 --var Y=7 --var Z=0 --var PRE=rc1"
    echo "  --parse-only       Parse the spike doc into ticket files and exit;"
    echo "                     skip the interactive filing loop and credentials check."
    echo "                     Useful for inspecting parsed output, pre-commit hooks,"
    echo "                     and CI validation."
    echo "  --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  file-jiras.sh --spike-doc docs/design/.../spike.md --feature-ticket 1311"
    echo "  file-jiras.sh --spike-doc dev-tools/release-jiras.md --feature-ticket 2000 \\"
    echo "                --var X=0 --var Y=7 --var Z=0 --var PRE=rc1"
}

SPIKE_DOC=""
FEATURE_TICKET=""
JIRA_DIR=""
PARSE_ONLY=0
PLACEHOLDER_VARS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --spike-doc)
            [ $# -ge 2 ] || { echo "Error: --spike-doc requires a value"; exit 1; }
            SPIKE_DOC="$2"; shift 2 ;;
        --feature-ticket)
            [ $# -ge 2 ] || { echo "Error: --feature-ticket requires a value"; exit 1; }
            FEATURE_TICKET="$2"; shift 2 ;;
        --output-dir)
            [ $# -ge 2 ] || { echo "Error: --output-dir requires a value"; exit 1; }
            JIRA_DIR="$2"; shift 2 ;;
        --var)
            [ $# -ge 2 ] || { echo "Error: --var requires KEY=VALUE"; exit 1; }
            case "$2" in
                *=*) PLACEHOLDER_VARS+=("$2") ;;
                *) echo "Error: --var value must be KEY=VALUE (got '$2')"; exit 1 ;;
            esac
            shift 2 ;;
        --parse-only|--dry-run)
            PARSE_ONLY=1; shift ;;
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

# Credentials are only required for actual filing (POST/PUT to JIRA).
# In --parse-only mode the script writes parsed files locally and exits;
# skip the credential prompt so the parser can run without a configured
# Jira account (useful for CI / pre-commit hooks / agent inspection).
if [ "$PARSE_ONLY" -eq 0 ]; then
    ensure_jira_credentials
fi

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

get_parent_epic_file() {
    # Returns the parent_epic_file slug (filename without .md) for a child
    # ticket file, or empty string if not present (legacy / Epic / incidental).
    local f="$1"
    grep -o '<!-- parent_epic_file: [^ ]* -->' "$f" 2>/dev/null | head -1 | sed 's/<!-- parent_epic_file: //;s/ -->//' || true
}

is_incidental() {
    # Returns 0 if this ticket file is marked incidental (no Epic parent;
    # files under FEATURE_TICKET directly).
    local f="$1"
    grep -q '<!-- incidental: true -->' "$f" 2>/dev/null
}

# Portable sed -i (macOS requires '' argument, GNU doesn't)
_sed_i() {
    if sed --version 2>/dev/null | grep -q GNU; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

set_key() {
    local f="$1"
    local key="$2"
    if grep -q '<!-- key:' "$f" 2>/dev/null; then
        _sed_i "s/<!-- key: [A-Za-z]*-[A-Za-z0-9]* -->/<!-- key: $key -->/" "$f"
    else
        _sed_i "1a\\
<!-- key: $key -->" "$f"
    fi
}

# --- Parse spike doc ---

if [ -d "$JIRA_DIR" ] && ls "$JIRA_DIR"/*.md >/dev/null 2>&1; then
    printf "Existing ticket files found in %s/. Re-parse (existing ticket files will be overwritten)? (y/n): " "$JIRA_DIR" >&2
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

python3 - "$SPIKE_DOC" "$JIRA_DIR" "$FEATURE_TICKET" ${PLACEHOLDER_VARS[@]+"${PLACEHOLDER_VARS[@]}"} << 'PYEOF'
import json
import re
import sys
from pathlib import Path

spike_doc = Path(sys.argv[1]).read_text()
out_dir = Path(sys.argv[2])
feature_ticket = sys.argv[3]

# Apply {KEY} placeholder substitutions from --var arguments
for kv in sys.argv[4:]:
    key, value = kv.split('=', 1)
    spike_doc = spike_doc.replace('{' + key + '}', value)

unreplaced = set(re.findall(r'\{([A-Z][A-Z0-9_]*)\}', spike_doc))
if unreplaced:
    print(f"  Warning: unreplaced placeholders: {', '.join(sorted(unreplaced))}", file=sys.stderr)


def strip_multiline_comments(text):
    """Strip HTML comment blocks that span multiple lines.

    Single-line metadata comments like <!-- type: Task --> or
    <!-- key: LCORE-1234 --> are preserved (no newlines inside).
    Multi-line commented-out examples in templates (e.g., the
    `### Epic: Documentation` example block in the spike-template)
    are stripped so the parser doesn't pick them up as real headings.
    """
    def replace(m):
        return '' if '\n' in m.group(0) else m.group(0)
    return re.sub(r'<!--[\s\S]*?-->', replace, text)


def slugify(text, max_words=8):
    """Convert text to lowercase dash-separated slug, truncated to max_words."""
    words = re.findall(r'[a-z0-9]+', text.lower())
    if not words:
        return 'ticket'
    return '-'.join(words[:max_words])


def extract_type(preceding_text):
    """Extract <!-- type: X --> from the last few lines of preceding text."""
    for line in preceding_text.strip().split('\n')[-5:]:
        m = re.search(r'<!--\s*type:\s*(\w+)\s*-->', line)
        if m:
            return m.group(1)
    return "Task"


def strip_leaked_metadata(body):
    """Remove trailing <!-- type/key/parent_epic_file --> that leaks into body
    from the next ticket's heading area."""
    body = re.sub(r'\n<!--\s*type:\s*\w+\s*-->\s*$', '', body)
    body = re.sub(r'\n<!--\s*key:\s*[\w-]+\s*-->\s*$', '', body)
    body = re.sub(r'\n<!--\s*parent_epic_file:[^>]*-->\s*$', '', body)
    return body.strip()


# Pre-process: strip multi-line HTML comments
clean_doc = strip_multiline_comments(spike_doc)

# --- Extract spike ticket key (unchanged behavior) ---
spike_key_match = re.search(r'\*\*Spike\*\*.*?(LCORE-\d+)', clean_doc)
if not spike_key_match:
    spike_key_match = re.search(r'deliverable for (LCORE-\d+)', clean_doc)
if not spike_key_match:
    spike_key_match = re.search(r'(LCORE-\d+)', clean_doc[:500])
spike_key = spike_key_match.group(1) if spike_key_match else ""


# --- Locate Proposed JIRAs section (accepts H1 or H2 — older spikes used H1) ---
proposed_match = re.search(
    r'^#{1,2}\s+Proposed JIRAs\s*$\n(.*?)(?=^#{1,2}\s|\Z)',
    clean_doc,
    re.MULTILINE | re.DOTALL,
)
if not proposed_match:
    print(f"Error: 'Proposed JIRAs' section not found in {sys.argv[1]}", file=sys.stderr)
    sys.exit(1)
proposed_section = proposed_match.group(1)


# --- Locate Proposed incidental JIRAs section (optional, H1 or H2) ---
incidental_match = re.search(
    r'^#{1,2}\s+Proposed incidental JIRAs\s*$\n(.*?)(?=^#{1,2}\s|\Z)',
    clean_doc,
    re.MULTILINE | re.DOTALL,
)
incidental_section = incidental_match.group(1) if incidental_match else ""


def parse_proposed_section(section_text):
    """Parse the Proposed JIRAs section into (epic_blocks, parse_mode).

    epic_blocks is a list of (epic_name, epic_prose, [(child_heading,
    child_body, child_type), ...]).

    parse_mode is 'epic_grouped' (new shape: ### Epic + #### LCORE) or
    'legacy_flat' (old shape: ### LCORE flat) or 'empty'.
    """
    epic_pattern = re.compile(r'^###\s+Epic:\s*(.+?)\s*$', re.MULTILINE)
    epic_matches = list(epic_pattern.finditer(section_text))

    if epic_matches:
        epic_blocks = []
        for i, em in enumerate(epic_matches):
            epic_name = em.group(1).strip()
            start = em.end()
            end = (epic_matches[i + 1].start()
                   if i + 1 < len(epic_matches) else len(section_text))
            epic_text = section_text[start:end]

            # Children at H4 — match both LCORE-???? (placeholder) and
            # LCORE-NNNN (real key, for re-syncing already-filed tickets)
            child_pattern = re.compile(r'^####\s+(LCORE-[\d?]+.*?)$', re.MULTILINE)
            child_matches = list(child_pattern.finditer(epic_text))

            epic_prose = (
                epic_text[:child_matches[0].start()].strip()
                if child_matches else epic_text.strip()
            )

            children = []
            for j, cm in enumerate(child_matches):
                child_heading = cm.group(1).strip()
                cstart = cm.end()
                cend = (child_matches[j + 1].start()
                        if j + 1 < len(child_matches) else len(epic_text))
                child_body = epic_text[cstart:cend].strip()
                preceding = epic_text[:cm.start()]
                ticket_type = extract_type(preceding[-300:])
                child_body = strip_leaked_metadata(child_body)
                children.append((child_heading, child_body, ticket_type))

            epic_blocks.append((epic_name, epic_prose, children))
        return epic_blocks, "epic_grouped", []

    # Backward compat: flat ### LCORE-... children, no Epic boundaries.
    # Match both LCORE-???? (placeholder) and LCORE-NNNN (real key).
    legacy_pattern = re.compile(r'^###\s+(LCORE-[\d?]+.*?)$', re.MULTILINE)
    legacy_matches = list(legacy_pattern.finditer(section_text))
    if not legacy_matches:
        return [], "empty", []

    children = []
    for i, m in enumerate(legacy_matches):
        heading = m.group(1).strip()
        cstart = m.end()
        cend = (legacy_matches[i + 1].start()
                if i + 1 < len(legacy_matches) else len(section_text))
        body = section_text[cstart:cend].strip()
        preceding = section_text[:m.start()]
        ticket_type = extract_type(preceding[-300:])
        body = strip_leaked_metadata(body)
        children.append((heading, body, ticket_type))

    # <!-- no-epic --> directive: skip auto-Epic generation.
    if '<!-- no-epic -->' in spike_doc:
        return [], "no_epic", children

    # Auto-generate Epic name from spike-doc parent dir
    spike_path = Path(sys.argv[1])
    feature_dir = spike_path.parent.name
    if feature_dir and feature_dir not in ('design', 'docs', '.'):
        epic_name = f"Implement {feature_dir.replace('-', ' ')}"
    else:
        epic_name = "TODO: Epic title"

    return [(epic_name, "", children)], "legacy_flat", []


epic_blocks, parse_mode, no_epic_tickets = parse_proposed_section(proposed_section)


# --- Structure linter ---
# Warns about likely-mistakes in the spike doc's Proposed JIRAs shape.
# Errors (which exit non-zero) are reserved for unparseable structure;
# warnings (which print and continue) are for inconsistencies the user
# should know about.

def lint_proposed_section(section_text, epic_blocks, parse_mode):
    """Emit warnings to stderr; return True on success, False on error."""
    issues = []  # list of (severity, message)

    # Mixed shape: both `### Epic:` and `### LCORE-` at H3 level
    epic_count = len(re.findall(r'^###\s+Epic:\s+', section_text, re.MULTILINE))
    h3_lcore_count = len(re.findall(r'^###\s+LCORE-[\d?]+', section_text, re.MULTILINE))
    if epic_count > 0 and h3_lcore_count > 0:
        issues.append((
            "WARNING",
            f"Mixed shape detected: {epic_count} `### Epic:` boundaries plus "
            f"{h3_lcore_count} flat `### LCORE-...` H3 stubs. The flat ones "
            f"will not be parsed under any Epic; demote them to `#### LCORE-...` "
            f"under an `### Epic:` heading or remove the Epic boundaries."
        ))

    # Epic with zero children
    for epic_name, _, children in epic_blocks:
        if not children:
            issues.append((
                "WARNING",
                f"Epic '{epic_name}' has no child JIRAs (no `#### LCORE-...` "
                f"H4 sub-headings under it). Either add children or remove "
                f"the empty Epic block."
            ))

    # Duplicate child titles within or across Epics
    all_titles = []
    for epic_name, _, children in epic_blocks:
        for heading, _, _ in children:
            clean = re.sub(r'^LCORE-[\d?]+\s*:?\s*', '', heading).strip().lower()
            all_titles.append((epic_name, clean))
    seen = {}
    for epic_name, title in all_titles:
        if title in seen:
            issues.append((
                "WARNING",
                f"Duplicate JIRA title '{title}' (in Epic '{seen[title]}' and "
                f"Epic '{epic_name}'). Each child JIRA should have a unique "
                f"title; the parser uses titles for filename generation."
            ))
        else:
            seen[title] = epic_name

    # No JIRAs at all (no_epic mode has its own tickets, so skip this check)
    total_children = sum(len(c) for _, _, c in epic_blocks)
    if total_children == 0 and parse_mode != "no_epic":
        issues.append((
            "ERROR",
            "Proposed JIRAs section parsed zero JIRAs. Expected at least one "
            "`### LCORE-...` (legacy) or `#### LCORE-...` under `### Epic:` (new)."
        ))

    # Print issues
    for severity, msg in issues:
        prefix = "  [LINT-{}]".format(severity)
        # Wrap long messages for readability
        words = msg.split(' ')
        line = prefix
        for w in words:
            if len(line) + 1 + len(w) > 100:
                print(line, file=sys.stderr)
                line = "    " + w
            else:
                line = line + " " + w
        if line.strip():
            print(line, file=sys.stderr)

    return not any(s == "ERROR" for s, _ in issues)


if not lint_proposed_section(proposed_section, epic_blocks, parse_mode):
    sys.exit(1)


def parse_incidental_section(section_text):
    """Parse incidental section (always flat ### LCORE-)."""
    if not section_text:
        return []
    pattern = re.compile(r'^###\s+(LCORE-[\d?]+.*?)$', re.MULTILINE)
    matches = list(pattern.finditer(section_text))
    out = []
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        cstart = m.end()
        cend = (matches[i + 1].start()
                if i + 1 < len(matches) else len(section_text))
        body = section_text[cstart:cend].strip()
        preceding = section_text[:m.start()]
        ticket_type = extract_type(preceding[-300:])
        body = strip_leaked_metadata(body)
        out.append((heading, body, ticket_type))
    return out


incidental_tickets = parse_incidental_section(incidental_section)

# <!-- no-epic --> tickets are treated as incidental (filed under feature-ticket)
incidental_tickets = no_epic_tickets + incidental_tickets


# --- Write parsed files ---
file_count = 0
total_jiras = 0
total_epics = 0

for epic_name, epic_prose, children in epic_blocks:
    epic_slug = slugify(epic_name)
    epic_filename = f"{file_count:02d}-epic-{epic_slug}.md"
    epic_content = (
        f"<!-- type: Epic -->\n"
        f"<!-- key: LCORE-xxxx -->\n"
        f"### {epic_name}\n"
        f"\n"
        f"{epic_prose}\n"
    )
    (out_dir / epic_filename).write_text(epic_content)
    parent_epic_stub = epic_filename.rsplit('.md', 1)[0]
    file_count += 1
    total_epics += 1

    for child_heading, child_body, ticket_type in children:
        # Detect real ticket key in heading (e.g., "LCORE-1569: Add ...")
        # vs placeholder ("LCORE-???? E2E ..."). Real keys are preserved
        # so the script PUT-updates the existing ticket rather than POSTing
        # a duplicate.
        key_match = re.match(r'LCORE-(\d+)\s*:?\s*', child_heading)
        ticket_key = f"LCORE-{key_match.group(1)}" if key_match else "LCORE-xxxx"
        clean_title = re.sub(r'^LCORE-[\d?]+\s*:?\s*', '', child_heading).strip()
        short_name = slugify(clean_title)
        child_filename = f"{file_count:02d}-{short_name}.md"
        child_content = (
            f"<!-- type: {ticket_type} -->\n"
            f"<!-- key: {ticket_key} -->\n"
            f"<!-- parent_epic_file: {parent_epic_stub} -->\n"
            f"### {clean_title}\n"
            f"\n"
            f"{child_body}\n"
        )
        (out_dir / child_filename).write_text(child_content)
        file_count += 1
        total_jiras += 1

# Incidental tickets — file under FEATURE_TICKET directly (no Epic parent)
for heading, body, ticket_type in incidental_tickets:
    key_match = re.match(r'LCORE-(\d+)\s*:?\s*', heading)
    ticket_key = f"LCORE-{key_match.group(1)}" if key_match else "LCORE-xxxx"
    clean_title = re.sub(r'^LCORE-[\d?]+\s*:?\s*', '', heading).strip()
    short_name = slugify(clean_title)
    inc_filename = f"{file_count:02d}-incidental-{short_name}.md"
    inc_content = (
        f"<!-- type: {ticket_type} -->\n"
        f"<!-- key: {ticket_key} -->\n"
        f"<!-- incidental: true -->\n"
        f"### {clean_title}\n"
        f"\n"
        f"{body}\n"
    )
    (out_dir / inc_filename).write_text(inc_content)
    file_count += 1
    total_jiras += 1


# --- Metadata file ---
meta = {
    "spike_ticket": spike_key,
    "epic_count": total_epics,
    "jira_count": total_jiras,
    "incidental_count": len(incidental_tickets),
    "parse_mode": parse_mode,
}
(out_dir / ".meta.json").write_text(json.dumps(meta))

inc_str = f", {len(incidental_tickets)} incidental" if incidental_tickets else ""
print(
    f"Parsed {total_epics} Epic(s) + {total_jiras - len(incidental_tickets)} JIRA(s)"
    f"{inc_str} from {sys.argv[1]} (mode: {parse_mode})"
)
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
        elif is_incidental "$f"; then
            parent="$FEATURE_TICKET (incidental)"
        else
            local parent_epic_file
            parent_epic_file=$(get_parent_epic_file "$f")
            if [ -n "$parent_epic_file" ]; then
                local epic_path="$JIRA_DIR/${parent_epic_file}.md"
                if [ -f "$epic_path" ]; then
                    local pk
                    pk=$(get_key "$epic_path")
                    if [ -n "$pk" ]; then
                        parent="$pk"
                    else
                        parent="(unfiled: $parent_epic_file)"
                    fi
                else
                    parent="(missing: $parent_epic_file)"
                fi
            else
                # Legacy / fallback (no parent_epic_file metadata)
                if [ -n "$EPIC_KEY" ] && [ "$EPIC_KEY" != "__NONE__" ]; then
                    parent="$EPIC_KEY"
                else
                    parent="(no epic)"
                fi
            fi
        fi
        printf "  %-3d %-7s %-13s %-35s %s\n" "$i" "$ttype" "$status" "$title" "$parent"
        i=$((i + 1))
    done
    echo ""
    if [ -n "$SPIKE_TICKET_KEY" ]; then
        echo "  Spike ticket $SPIKE_TICKET_KEY will be linked to first filed Epic with \"Informs\""
    fi
    echo ""
}

get_file_by_number() {
    find "$JIRA_DIR" -maxdepth 1 -name '*.md' | sort | sed -n "$((${1} + 1))p"
}

ensure_epic_key() {
    # If we already have an Epic key in this shell, nothing to do
    if [ -n "$EPIC_KEY" ]; then
        return 0
    fi

    # Try to restore from state file (set in a previous subshell that
    # had `key=$(file_ticket ...)` capture, so its EPIC_KEY didn't
    # propagate back to the parent shell).
    if [ -f "$JIRA_DIR/.epic-key" ]; then
        EPIC_KEY=$(cat "$JIRA_DIR/.epic-key")
        if [ -n "$EPIC_KEY" ]; then
            return 0
        fi
    fi

    # All user-facing prompts go to stderr so they're visible even when
    # this function is called from inside a `$(...)` capture context
    # (which would otherwise swallow stdout into a variable).
    {
        echo ""
        echo "  No Epic filed yet. Children need an Epic parent."
        echo "    1. File Epic #0 first, then continue"
        echo "    2. Enter an existing Epic key (e.g., LCORE-1600)"
        echo "    3. File without Epic (Blocks link to $FEATURE_TICKET instead)"
        printf "  Choice (1/2/3): "
    } >&2
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
            printf "  Epic key: " >&2
            read -r EPIC_KEY < /dev/tty
            ;;
        3)
            EPIC_KEY="__NONE__"
            ;;
        *)
            echo "  Invalid choice." >&2
            return 1
            ;;
    esac

    # Persist for subsequent subshells so the user isn't re-prompted for
    # every ticket in the file loop.
    if [ -n "$EPIC_KEY" ]; then
        echo "$EPIC_KEY" > "$JIRA_DIR/.epic-key"
    fi
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
    body=$(grep -v '^<!-- \(type\|key\|incidental\|parent_epic_file\):' "$ticket_file" | grep -v '^### ' | tail -n +1)

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


def is_table_paragraph(para):
    """Detect a GitHub-flavored markdown table.

    A markdown table is at least 2 contiguous lines:
      Line 1: starts with `|` and has cell content
      Line 2: separator with only `|`, `-`, `:`, and whitespace
              (e.g., `|---|---|` or `|:---|---:|`)
    """
    lines = para.strip().split('\n')
    if len(lines) < 2:
        return False
    if not lines[0].lstrip().startswith('|'):
        return False
    sep = lines[1].strip()
    return bool(re.match(r'^\|[\s\-:|]+\|?\s*$', sep))


def parse_table_row(line, cell_kind):
    """Parse a single `| a | b | c |` line into a tableRow ADF node."""
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    cells_text = s.split('|')
    cells = []
    for ct in cells_text:
        text = ct.strip()
        # ADF cells require at least one block-level node — use an empty
        # paragraph for empty cells.
        if text:
            content = [make_paragraph(text)]
        else:
            content = [{"type": "paragraph", "content": []}]
        cells.append({"type": cell_kind, "attrs": {}, "content": content})
    return {"type": "tableRow", "content": cells}


def parse_table(para):
    """Convert a markdown-table paragraph into an ADF table node."""
    lines = para.strip().split('\n')
    header_line = lines[0]
    # lines[1] is the separator — skipped (no semantic content)
    body_lines = lines[2:] if len(lines) > 2 else []

    rows = [parse_table_row(header_line, cell_kind="tableHeader")]
    for bl in body_lines:
        if bl.strip():
            rows.append(parse_table_row(bl, cell_kind="tableCell"))

    return {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": rows,
    }


def parse_block(para):
    if is_table_paragraph(para):
        return parse_table(para)
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
        # File Epic under FEATURE_TICKET. With multi-Epic support, each Epic
        # is filed independently; we capture the FIRST filed Epic into
        # EPIC_KEY so the spike-to-Epic "Informs" link uses it (per
        # convention: link to the primary/first Epic).
        local filed_key
        filed_key=$(file_single_ticket "$ticket_file" "Epic" "$FEATURE_TICKET")
        if [ -z "$filed_key" ]; then
            return 1
        fi
        if [ -z "$EPIC_KEY" ] || [ "$EPIC_KEY" = "__NONE__" ]; then
            EPIC_KEY="$filed_key"
            # Persist for subsequent subshells (file_ticket runs inside
            # `key=$(...)` capture; assignments don't propagate back).
            echo "$EPIC_KEY" > "$JIRA_DIR/.epic-key"
            if [ -n "$SPIKE_TICKET_KEY" ]; then
                link_spike_to_epic
            fi
        fi
        echo "$filed_key"
        return 0
    fi

    if is_incidental "$ticket_file"; then
        # Incidental tickets file directly under FEATURE_TICKET (no Epic).
        file_single_ticket "$ticket_file" "$ttype" "$FEATURE_TICKET"
        return $?
    fi

    # Regular child: route to its parent_epic_file's filed key.
    local parent_epic_file
    parent_epic_file=$(get_parent_epic_file "$ticket_file")

    local parent
    if [ -n "$parent_epic_file" ]; then
        local epic_path="$JIRA_DIR/${parent_epic_file}.md"
        if [ ! -f "$epic_path" ]; then
            echo "  Error: parent_epic_file '$parent_epic_file' not found at $epic_path" >&2
            return 1
        fi
        parent=$(get_key "$epic_path")
        if [ -z "$parent" ]; then
            echo "  Error: parent epic '$parent_epic_file' has not been filed yet (no key)." >&2
            echo "  File the Epic first, then retry filing this ticket." >&2
            return 1
        fi
    else
        # Legacy fallback: no parent_epic_file metadata. Use single-Epic
        # flow with the global EPIC_KEY (refresh from any epic file in the
        # directory if not yet set).
        if [ -z "$EPIC_KEY" ] || [ "$EPIC_KEY" = "__NONE__" ]; then
            local epic_file
            epic_file=$(find "$JIRA_DIR" -maxdepth 1 \( -name '*-epic-*.md' -o -name '00-epic.md' \) 2>/dev/null | sort | head -1)
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
            parent="$FEATURE_TICKET"
        else
            parent="$EPIC_KEY"
        fi
    fi

    file_single_ticket "$ticket_file" "$ttype" "$parent"
}

# --- Parse-only short-circuit ---
# In --parse-only mode the parsed files are already written by the parse
# step above. Skip the interactive loop and exit cleanly.
if [ "$PARSE_ONLY" -eq 1 ]; then
    echo ""
    echo "Parsed files in $JIRA_DIR/"
    ls -1 "$JIRA_DIR" 2>/dev/null
    echo ""
    echo "(--parse-only: skipping interactive filing loop and exiting.)"
    exit 0
fi

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
                echo "Done:$created_keys"
            fi
            # Refresh EPIC_KEY from the state file. Subshells (`key=$(file_ticket ...)`)
            # cannot propagate variable assignments back to the parent shell, so
            # ensure_epic_key and the Epic-filing path persist EPIC_KEY to
            # $JIRA_DIR/.epic-key. Re-read it here so the parent shell sees the
            # current value for show_summary and subsequent commands.
            if [ -f "$JIRA_DIR/.epic-key" ]; then
                _ek=$(cat "$JIRA_DIR/.epic-key")
                if [ -n "$_ek" ]; then
                    EPIC_KEY="$_ek"
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
