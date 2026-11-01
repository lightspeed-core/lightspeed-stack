#!/usr/bin/env python3

"""Filter to fix the generated OpenAPI documentation with configuration schema."""

import fileinput

TABLE_ROW_CONTINUATION_LINE = " |"

lines = list(fileinput.input())

lines_count = len(lines)

in_json = False
in_table = False

for i in range(lines_count):
    current_line = lines[i].rstrip("\r\n")

    if current_line == "Examples":
        continue
    if current_line == "```json":
        in_json = True
        continue
    if current_line == "```" and in_json:
        in_json = False
        continue
    if in_json:
        continue

    # limit check
    if i == lines_count - 1:
        print(current_line)
        break

    # the next line must exists -> read it
    next_line = lines[i + 1].rstrip("\r\n")

    # skip the continuation line as it was used already
    # during previous line processing
    if current_line == TABLE_ROW_CONTINUATION_LINE:
        continue

    # check if table row continuation line is present
    if next_line == TABLE_ROW_CONTINUATION_LINE:
        print(current_line + TABLE_ROW_CONTINUATION_LINE)
    else:
        print(current_line)
