#!/usr/bin/env python3

"""Simple CLI to hit the local LLM /v1/query endpoint."""

import argparse
import os
import sys
from time import perf_counter

import requests

DEFAULT_URL = os.getenv("LLM_URL", "http://localhost:8080/v1/query/")


def main() -> int:
    """
    CLI entry point that sends a query to a local LLM endpoint and prints the model response.

    Parses command-line arguments (--query, --system-prompt, --url, --timeout),
    POSTs a JSON payload with the query and system prompt to the configured
    endpoint, and prints the returned "response" value followed by the request
    elapsed time. Error diagnostics are printed to stderr.

    Returns:
        int: Exit code where
            `0` indicates success,
            `1` indicates an HTTP/request failure,
            `2` indicates the server response was not valid JSON,
            `3` indicates the JSON response did not contain a `"response"` field.

    """
    parser = argparse.ArgumentParser(
        description="Send a query to a local LLM endpoint."
    )
    parser.add_argument(
        "--query",
        default="Say Hello",
        help="User query text. Defaults to 'Say Hello'.",
    )
    parser.add_argument(
        "--system-prompt",
        default="You are a helpful assistant",
        help="System prompt sent along with the query.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Endpoint URL. Defaults to env LLM_URL or {DEFAULT_URL!r}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="Request timeout in seconds (default: 30).",
    )
    args = parser.parse_args()

    payload = {"query": args.query, "system_prompt": args.system_prompt}

    t0 = perf_counter()
    try:
        resp = requests.post(url=args.url, json=payload, timeout=args.timeout)
        elapsed = perf_counter() - t0
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        elapsed = perf_counter() - t0
        print(f"Request failed after {elapsed:.2f}s: {e}", file=sys.stderr)
        return 1

    try:
        obj = resp.json()
    except ValueError:
        print("Server response is not valid JSON.", file=sys.stderr)
        print(resp.text[:1000], file=sys.stderr)
        return 2

    if "response" not in obj:
        print("JSON is missing 'response' field:", file=sys.stderr)
        print(obj, file=sys.stderr)
        return 3

    print(obj["response"])
    print(f"Response time {elapsed:.2f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
