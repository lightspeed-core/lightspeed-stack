# Conversion quality evidence (sanitized)

Largest crawled page ("Atlassian Cloud FAQ", export_view HTML → docling →
Markdown, 0.14 s). Body text redacted (internal); structure shown verbatim:

```
# Atlassian Cloud FAQ

## Review the answers to common questions you may have about our Cloud environment.

##### **What is Atlassian Cloud?**

[paragraph — clean prose, no markup artifacts]

##### **What is the timeline and when is the migration?**

**[bold lead sentence]**

- [nested list, 2 levels, rendered correctly]
    - [timezone conversion sub-items]
```

Observations:

- Headings, bold, links, and 2-level nested lists all convert cleanly.
- Confluence expand-macros arrive already expanded in `export_view`
  (their content is present as regular headings/paragraphs).
- No letter-spaced-font artifacts (the known docling weakness with
  Confluence "Export to PDF" does not apply to the HTML path).
- Minor: one stray list item rendered as an empty `-` bullet
  (trailing empty list node in the source HTML) — harmless for chunking.
