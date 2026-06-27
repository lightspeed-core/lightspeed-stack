# Summarize Formatting Guide

## Output format

When summarizing text for the user, follow these rules:

- Return exactly one sentence
- Do not add quotation marks around the summary
- Do not add any prefix like "Summary:" or "TL;DR:"
- Keep the summary under 30 words
- Use simple, clear language
- Preserve the original meaning without adding interpretation

## Examples

**Input**: `The quick brown fox jumped over the lazy dog while the cat watched from the windowsill and the bird flew overhead.`
**Output**: `A fox jumped over a dog while a cat and bird observed nearby.`

**Input**: `We need to upgrade our database server because the current one is running out of disk space and memory, which causes frequent timeouts during peak hours.`
**Output**: `The database server needs upgrading due to insufficient disk space and memory causing peak-hour timeouts.`
