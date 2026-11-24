# Conversation Cache Benchmarks

This directory contains benchmark outputs for the conversation cache
implementations.

Each operation has a text summary and an SVG chart:

- `connect`
- `get` for DB with 10, 100, and 1000 records
- `insert_or_append`
- `insert_or_append_existing_key`
- `insert_or_append_skip_user_id_check`
- `delete` for DB with 10, 100, and 1000 records

The corresponding benchmark code lives under `tests/benchmarks/`. Regenerate
these files after benchmark code or cache behavior changes so the published
charts stay in sync with the implementation.
