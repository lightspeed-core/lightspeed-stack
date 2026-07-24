#!/usr/bin/env python3
"""PoC: fetch Confluence pages as rendered HTML for the BYOK RAG pipeline.

Fetches all pages from the given Confluence spaces via the v1 REST API
(`body.export_view` = rendered HTML), writes one HTML file per page plus a
`manifest.json` (page id -> title/url/version) consumed by the metadata
processor, and a `state.json` sync watermark.

Modes:
  - Full crawl (default, or no state file): enumerate every page in each space.
  - Incremental (`--incremental`, requires state file): CQL `lastmodified >=`
    watermark to find changed pages, full ID enumeration to detect deletions.

PoC shortcuts (not production shape): credentials read from the Jira CLI
credentials file; no retry/backoff beyond honoring nothing; no attachments.
"""

import argparse
import base64
import datetime
import json
import pathlib
import sys
import urllib.parse
import urllib.request

CRED_FILE = pathlib.Path.home() / ".config/jira/credentials.json"
BASE = "https://redhat.atlassian.net"
EXPAND = "body.export_view,version,space"
# Overlap buffer so CQL minute granularity / timezone skew can't miss edits;
# version comparison deduplicates re-fetches.
WATERMARK_OVERLAP_MIN = 10


def _auth_header() -> str:
    creds = json.loads(CRED_FILE.read_text())
    token = base64.b64encode(f"{creds['email']}:{creds['token']}".encode()).decode()
    return f"Basic {token}"


def api_get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": _auth_header(), "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def list_space_page_ids(space: str) -> dict[str, int]:
    """Enumerate all page ids (id -> version) in a space, no bodies."""
    ids: dict[str, int] = {}
    start = 0
    while True:
        res = api_get(
            "/wiki/rest/api/content",
            {"spaceKey": space, "type": "page", "limit": 100, "start": start,
             "expand": "version"},
        )
        for page in res.get("results", []):
            ids[page["id"]] = page["version"]["number"]
        if len(res.get("results", [])) < 100:
            return ids
        start += 100


def fetch_page(page_id: str) -> dict:
    return api_get(f"/wiki/rest/api/content/{page_id}", {"expand": EXPAND})


def changed_page_ids(spaces: list[str], since_utc: datetime.datetime) -> set[str]:
    """CQL delta: page ids modified since the watermark (minus overlap)."""
    since = since_utc - datetime.timedelta(minutes=WATERMARK_OVERLAP_MIN)
    space_list = ",".join(f'"{s}"' for s in spaces)
    cql = (
        f"space in ({space_list}) and type=page"
        f' and lastmodified >= "{since.strftime("%Y/%m/%d %H:%M")}"'
    )
    ids: set[str] = set()
    start = 0
    while True:
        res = api_get(
            "/wiki/rest/api/content/search",
            {"cql": cql, "limit": 100, "start": start},
        )
        ids.update(r["id"] for r in res.get("results", []))
        if len(res.get("results", [])) < 100:
            return ids
        start += 100


def write_page(page: dict, out_dir: pathlib.Path) -> dict:
    """Write one page as HTML; return its manifest entry."""
    title = page["title"]
    html_body = page["body"]["export_view"]["value"]
    doc = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n</head>\n<body>\n"
        f"<h1>{title}</h1>\n{html_body}\n</body>\n</html>\n"
    )
    filename = f"{page['id']}.html"
    (out_dir / filename).write_text(doc, encoding="utf-8")
    return {
        "id": page["id"],
        "title": title,
        "url": BASE + "/wiki" + page["_links"]["webui"],
        "version": page["version"]["number"],
        "when": page["version"]["when"],
        "space": page["space"]["key"],
        "file": filename,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spaces", nargs="+", required=True, help="Space keys to crawl")
    parser.add_argument("--out", required=True, help="Output directory for HTML files")
    parser.add_argument("--incremental", action="store_true",
                        help="Use CQL delta + deletion diff against state file")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    state_path = out_dir / "state.json"

    manifest: dict[str, dict] = (
        json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    )
    state: dict = json.loads(state_path.read_text()) if state_path.exists() else {}
    run_started = datetime.datetime.now(datetime.timezone.utc)

    known_versions: dict[str, int] = state.get("pages", {})
    stats = {"fetched": 0, "unchanged": 0, "deleted": 0, "api_calls_saved": 0}

    # Current inventory (id -> version) across all spaces: needed for deletion
    # detection in both modes, and as the fetch list in full mode.
    inventory: dict[str, int] = {}
    for space in args.spaces:
        inventory.update(list_space_page_ids(space))

    if args.incremental and state.get("last_sync"):
        watermark = datetime.datetime.fromisoformat(state["last_sync"])
        candidates = changed_page_ids(args.spaces, watermark)
        # Also anything present in inventory but unknown to state (new pages
        # CQL may have missed due to timezone skew).
        candidates.update(pid for pid in inventory if pid not in known_versions)
        to_fetch = {
            pid for pid in candidates
            if pid in inventory and inventory[pid] != known_versions.get(pid)
        }
        stats["unchanged"] = len(inventory) - len(to_fetch)
        stats["api_calls_saved"] = stats["unchanged"]
    else:
        to_fetch = set(inventory)

    for pid in sorted(to_fetch):
        entry = write_page(fetch_page(pid), out_dir)
        manifest[entry["file"]] = entry
        stats["fetched"] += 1
        print(f"  fetched [{entry['space']}] v{entry['version']} {entry['title']}")

    # Deletion diff: anything on disk whose page id vanished from inventory.
    for filename in list(manifest):
        pid = manifest[filename]["id"]
        if pid not in inventory:
            (out_dir / filename).unlink(missing_ok=True)
            del manifest[filename]
            stats["deleted"] += 1
            print(f"  deleted {filename}")

    manifest_path.write_text(json.dumps(manifest, indent=2))
    state_path.write_text(json.dumps({
        "last_sync": run_started.isoformat(),
        "spaces": args.spaces,
        "pages": inventory,
    }, indent=2))

    mode = "incremental" if args.incremental and state.get("last_sync") else "full"
    print(f"[{mode}] spaces={args.spaces} fetched={stats['fetched']} "
          f"unchanged={stats['unchanged']} deleted={stats['deleted']} "
          f"total_on_disk={len(manifest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
