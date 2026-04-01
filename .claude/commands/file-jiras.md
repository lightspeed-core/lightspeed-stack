Parse proposed JIRAs from a spike doc and file them via the Jira API

You are filing JIRA sub-tickets for a Lightspeed Core feature.

The user will provide either a spike doc path or tell you which feature's
JIRAs to file.  They will also provide the feature ticket number.

Run `sh dev-tools/file-jiras.sh --help` to see the full usage.

## Credentials

Jira credentials are managed by `dev-tools/jira-common.sh`.  If
`~/.config/jira/credentials.json` doesn't exist, the script creates it
with FIXMEs and exits — the user must fill in their credentials before
re-running.  API tokens can be created at
https://id.atlassian.com/manage-profile/security/api-tokens

## Process

1. Run `dev-tools/file-jiras.sh --spike-doc <path> --feature-ticket <key>`
   with `echo "quit"` piped in, so it parses and exits without filing.

2. Read every file in the output directory (default: `docs/design/<feature>/jiras/`).
   For each, verify:
   - Content matches the corresponding section in the spike doc (no truncation,
     no extra content swallowed from subsequent sections).
   - File size is reasonable (a single JIRA should be under ~3KB; if any file
     is much larger, the parser likely grabbed too much).
   - The `<!-- type: ... -->` metadata is correct (Epic/Story/Task).

3. Report any issues to the user.  If all files look correct, tell the user
   to run the script interactively — provide the full command including `cd`
   to the repository root:
   `cd <repo-path> && sh dev-tools/file-jiras.sh --spike-doc <path> --feature-ticket <key>`
