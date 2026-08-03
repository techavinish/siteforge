"""Publish the whitepaper to Notion — markdown → Notion blocks via API.

Creates (or replaces) a page titled "SiteForge Whitepaper" under the first
page the integration can access. Prints the page URL.

Run:  NOTION_TOKEN=... python scripts/publish_whitepaper.py
"""

import os
import pathlib
import sys

import requests

TOKEN = os.environ["NOTION_TOKEN"]
API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
TITLE = "SiteForge Whitepaper"


def rich(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def md_to_blocks(md: str) -> list[dict]:
    blocks = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            blocks.append({"heading_3": {"rich_text": rich(line[4:])}})
        elif line.startswith("## "):
            blocks.append({"heading_2": {"rich_text": rich(line[3:])}})
        elif line.startswith("# "):
            blocks.append({"heading_1": {"rich_text": rich(line[2:])}})
        elif line.startswith("- "):
            blocks.append({"bulleted_list_item": {"rich_text": rich(line[2:])}})
        else:
            blocks.append({"paragraph": {"rich_text": rich(line)}})
    return [{"object": "block", "type": next(iter(b)), **b} for b in blocks]


def candidate_parents() -> list[str]:
    """All accessible pages — some Notion page types (e.g. person profiles)
    refuse children, so the caller tries them in order."""
    r = requests.post(f"{API}/search", headers=HEADERS,
                      json={"filter": {"property": "object", "value": "page"}}, timeout=30)
    r.raise_for_status()
    pages = r.json()["results"]
    if not pages:
        sys.exit("No page is shared with the integration — share one in Notion first.")
    return [p["id"] for p in pages]


def archive_existing(parent_id: str) -> None:
    r = requests.post(f"{API}/search", headers=HEADERS, json={"query": TITLE}, timeout=30)
    for res in r.json().get("results", []):
        title = res.get("properties", {}).get("title", {}).get("title", [])
        if title and title[0]["plain_text"] == TITLE:
            requests.patch(f"{API}/pages/{res['id']}", headers=HEADERS,
                           json={"archived": True}, timeout=30)


def main() -> None:
    md = pathlib.Path("docs/whitepaper/WHITEPAPER.md").read_text()
    blocks = md_to_blocks(md)
    archive_existing("")
    page = None
    for parent in candidate_parents():
        r = requests.post(f"{API}/pages", headers=HEADERS, timeout=60, json={
            "parent": {"page_id": parent},
            "icon": {"type": "emoji", "emoji": "🏗️"},
            "properties": {"title": {"title": rich(TITLE)}},
            "children": blocks[:100],  # API caps children per request
        })
        if r.ok:
            page = r.json()
            break
    if page is None:
        sys.exit(f"every accessible page refused the publish: {r.text[:200]}")
    # append remaining blocks in batches of 100
    for i in range(100, len(blocks), 100):
        requests.patch(f"{API}/blocks/{page['id']}/children", headers=HEADERS,
                       json={"children": blocks[i:i + 100]}, timeout=60).raise_for_status()
    print("PUBLISHED:", page["url"])


if __name__ == "__main__":
    main()
