Run a design spike: research, PoC, decisions, and proposed JIRAs

You are starting a spike for a feature in the Lightspeed Core project.

Follow the process in `docs/contributing/howto-run-a-spike.md`.  Use the
templates it references.

If the user provides a JIRA ticket number (e.g., "1234" or "LCORE-1234"),
fetch the ticket content by running `sh dev-tools/fetch-jira.sh <number>`.
The output includes child issues — decide which linked tickets to fetch
for additional context.

Otherwise, the user will provide context about the feature directly.

When proposing JIRAs in the spike doc, specify the type for each ticket
using `<!-- type: Task -->` or `<!-- type: Story -->` (see the JIRA ticket
template).  Use `dev-tools/file-jiras.sh --help` for filing details.

At decision points, present what you've found and ask the user before proceeding.
The user makes the decisions — you assist with the research and documenting.
