Create a feature spec doc with requirements, architecture, and implementation guide

You are creating a feature spec doc for the Lightspeed Core project.

Follow the guidance in `docs/contributing/howto-write-a-spec-doc.md`.  Use
`docs/contributing/templates/spec-doc-template.md` as the starting point.

If the user provides a JIRA ticket number, look for an existing spike doc:
1. Search filenames in `docs/design/*/` for the JIRA number (bare and with
   LCORE- prefix) and for words likely related to the feature.
2. If not found by filename, grep inside files in `docs/design/*/` for the
   JIRA number.
3. If a spike doc is found, use it as the primary source for the spec doc.
4. If no spike doc exists, let the user know and ask them to provide the path
   if one exists elsewhere.  Otherwise, fetch the JIRA content with
   `sh dev-tools/fetch-jira.sh <number>` and work from that.

The user may also provide a spike doc path or feature description directly.

Place the spec doc at `docs/design/<feature>/<feature>.md`.  Confirm the
feature name and path with the user.
