#!/usr/bin/env bash
# Shared Jira API helpers for dev-tools scripts.
# Source this file: . "$(dirname "$0")/jira-common.sh"

JIRA_CREDS="$HOME/.config/jira/credentials.json"

ensure_jira_credentials() {
    if [ ! -f "$JIRA_CREDS" ]; then
        mkdir -p "$(dirname "$JIRA_CREDS")"
        cat > "$JIRA_CREDS" << 'CREDS'
{
  "email": "FIXME: your Red Hat email (e.g., user@redhat.com)",
  "token": "FIXME: create a token at https://id.atlassian.com/manage-profile/security/api-tokens",
  "instance": "https://redhat.atlassian.net"
}
CREDS
        chmod 600 "$JIRA_CREDS"
        echo "Created $JIRA_CREDS with FIXMEs — edit it with your credentials before proceeding."
        exit 1
    fi

    # Check for unfilled FIXMEs
    if grep -q "FIXME" "$JIRA_CREDS"; then
        echo "Error: $JIRA_CREDS still contains FIXME entries. Edit it with your credentials."
        exit 1
    fi

    # Variables below are used by the sourcing scripts (file-jiras.sh, fetch-jira.sh)
    # shellcheck disable=SC2034
    JIRA_EMAIL=$(python3 -c "import json; print(json.load(open('$JIRA_CREDS'))['email'])")
    # shellcheck disable=SC2034
    JIRA_TOKEN=$(python3 -c "import json; print(json.load(open('$JIRA_CREDS'))['token'])")
    # shellcheck disable=SC2034
    JIRA_INSTANCE=$(python3 -c "import json; print(json.load(open('$JIRA_CREDS'))['instance'])")
}
