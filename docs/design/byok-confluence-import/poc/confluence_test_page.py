#!/usr/bin/env python3
"""PoC helper: manage the editable test page for the incremental-sync demo.

Subcommands:
  create  - ensure the private PoC space exists and create the test page
            containing a distinctive retrieval probe ("codeword").
  edit    - update the test page in place, changing the codeword, so the
            next incremental crawl sees exactly one modified page.
  delete-page / delete-space - cleanup after the PoC.

The space is created via `POST /wiki/rest/api/space/_private`, which is
visible only to the creating user.
"""

import argparse
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.request

CRED_FILE = pathlib.Path.home() / ".config/jira/credentials.json"
BASE = "https://redhat.atlassian.net"
SPACE_KEY = "LCORE2664POC"
SPACE_NAME = "LCORE-2664 Confluence import PoC (temporary)"
PAGE_TITLE = "LCORE-2664 incremental sync test page"

CODEWORD_V1 = "AMBER-FALCON"
CODEWORD_V2 = "COBALT-HERON"


def _auth_header() -> str:
    creds = json.loads(CRED_FILE.read_text())
    token = base64.b64encode(f"{creds['email']}:{creds['token']}".encode()).decode()
    return f"Basic {token}"


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        headers={
            "Authorization": _auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def page_body(codeword: str, note: str) -> str:
    return (
        f"<p>This page exists solely for the LCORE-2664 spike PoC "
        f"(BYOK auto-import from Confluence). {note}</p>"
        f"<p>The current secret codeword for retrieval testing is "
        f"<strong>{codeword}</strong>. Remember the codeword {codeword}.</p>"
        f"<h2>Purpose</h2><p>Validates that an incremental crawl picks up "
        f"page edits via CQL lastmodified and page version numbers.</p>"
    )


def ensure_space() -> None:
    try:
        api("GET", f"/wiki/rest/api/space/{SPACE_KEY}")
        print(f"space {SPACE_KEY} already exists")
    except urllib.error.HTTPError as err:
        if err.code != 404:
            raise
        api("POST", "/wiki/rest/api/space/_private",
            {"key": SPACE_KEY, "name": SPACE_NAME})
        print(f"created private space {SPACE_KEY}")


def find_page() -> dict | None:
    res = api("GET", f"/wiki/rest/api/content?spaceKey={SPACE_KEY}"
                     f"&type=page&expand=version&limit=25")
    for page in res.get("results", []):
        if page["title"] == PAGE_TITLE:
            return page
    return None


def cmd_create() -> None:
    ensure_space()
    if find_page():
        print("test page already exists")
        return
    page = api("POST", "/wiki/rest/api/content", {
        "type": "page",
        "title": PAGE_TITLE,
        "space": {"key": SPACE_KEY},
        "body": {"storage": {
            "value": page_body(CODEWORD_V1, "Initial revision."),
            "representation": "storage",
        }},
    })
    print(f"created page id={page['id']} codeword={CODEWORD_V1}")


def cmd_edit() -> None:
    page = find_page()
    if not page:
        sys.exit("test page not found; run create first")
    new_version = page["version"]["number"] + 1
    api("PUT", f"/wiki/rest/api/content/{page['id']}", {
        "type": "page",
        "title": PAGE_TITLE,
        "version": {"number": new_version},
        "body": {"storage": {
            "value": page_body(CODEWORD_V2, "EDITED revision for the delta demo."),
            "representation": "storage",
        }},
    })
    print(f"edited page id={page['id']} -> v{new_version} codeword={CODEWORD_V2}")


def cmd_delete_page() -> None:
    page = find_page()
    if not page:
        print("test page already gone")
        return
    api("DELETE", f"/wiki/rest/api/content/{page['id']}")
    print(f"deleted page id={page['id']}")


def cmd_delete_space() -> None:
    api("DELETE", f"/wiki/rest/api/space/{SPACE_KEY}")
    print(f"deletion of space {SPACE_KEY} requested (async long task)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=["create", "edit", "delete-page", "delete-space"])
    args = parser.parse_args()
    {"create": cmd_create, "edit": cmd_edit,
     "delete-page": cmd_delete_page, "delete-space": cmd_delete_space}[args.command]()


if __name__ == "__main__":
    main()
