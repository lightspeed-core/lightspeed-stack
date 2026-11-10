#!/usr/bin/env python3

"""Display all Enterprise Contract failures found in EC job logs.

Usage:
print_ec_failures.py log_file_name.log [--json]
"""

import argparse
import json
import sys
from pathlib import Path

PREFIX = "[report-json]"


def main() -> int:
    """Print component check counts and violation messages from an EC log.

    Read the file named by the first command-line argument, joining the
    stripped text after ``[report-json]`` on lines starting with that prefix
    into a JSON report. Write the parsed report to ``logs.json`` in the current
    directory, overwriting it even when the report has no components key.

    When --json command line flag is given, write the parsed report to
    logs.json using exclusive creation (the file must not already exist). The
    file is only written after successful component extraction.'

    Return 0 after printing the summary, including when violations exist.
    Return 1 for a missing argument, missing or inaccessible input file, absent
    report data, invalid JSON, or a missing components key. Other file I/O
    errors and input text decoding errors propagate, as can errors from
    unexpected report structures.
    """
    json_raw_data = ""

    # check CLI arguments
    if len(sys.argv) < 2:
        print("Usage: print_ec_failures.py log_file_name.log [--json]")
        return 1

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file_name")
    parser.add_argument(
        "--json", action="store_true", help="export to logs.json (must not exist)"
    )
    args = parser.parse_args()
    log_file_name = args.log_file_name

    # read the log file that contains several sections
    # and where each line has some prefix
    try:
        with Path(log_file_name).open("r", encoding="utf-8") as log_file:
            for line in log_file:
                # retrieve just those lines with JSON data
                # and append them
                if line.startswith(PREFIX):
                    stripped = line[len(PREFIX) :].strip()
                    json_raw_data += stripped
    except (FileNotFoundError, PermissionError) as e:
        print("Unable to open input file", e)
        return 1

    if not json_raw_data:
        print("Provided log file does not contain any reports")
        return 1

    json_data = None

    # deserialize JSON
    try:
        json_data = json.loads(json_raw_data)
    except json.JSONDecodeError as e:
        print("Unable to deserialize JSON data:", e)
        return 1

    if not isinstance(json_data, dict) or not isinstance(
        json_data.get("components"), list
    ):
        print("Unable to find components attribute in EC data")
        return 1

    # print summary
    for component in json_data["components"]:
        print(f"Component: {component.get('name', 'unknown component!')}")
        violations = component.get("violations", [])
        warnings = component.get("warnings", [])
        successes = component.get("successes", [])
        total = (
            (num_successes := len(successes))
            + (num_warnings := len(warnings))
            + (num_violations := len(violations))
        )
        print(f"    total checks: {total}")
        print(f"    successes:    {num_successes}")
        print(f"    warnings:     {num_warnings}")
        print(f"    violations:   {num_violations}")
        for i, violation in enumerate(violations):
            print(f"        #{i+1}: {violation.get('msg', 'NO VIOLATION MSG!')}")

    if args.json:
        try:
            # exclusive creation also protects files created after validation.
            with Path("logs.json").open("x", encoding="utf-8") as json_file:
                json.dump(json_data, json_file, indent=4)
        except OSError as e:
            print("Unable to write JSON report:", e, file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
