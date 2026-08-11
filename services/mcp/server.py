"""SiteForge MCP server — the site-builder as tools for ANY MCP client.

Remote transport (streamable HTTP), so Claude or any other agent can
connect over the network and build + publish real websites through the
same pipeline the product uses. This is the tool surface as a product.
"""

import os
import sys

# agent modules: sibling dir in the docker image, ../agent in the monorepo
_here = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_here, "agent"), os.path.join(_here, "..", "agent")):
    if os.path.isdir(_cand):
        sys.path.insert(0, _cand)
        break

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "siteforge",
    instructions=(
        "Build and publish small-business websites. Typical flow: "
        "build_website with the business brief, review the returned pages, "
        "then publish_website to put it live."
    ),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8003")),
)

RAG_URL = os.environ.get("RAG_URL", "http://localhost:8002")


@mcp.tool()
def search_knowledge(query: str, k: int = 3) -> list[dict]:
    """Search SiteForge's copywriting/SEO/page-structure knowledge base."""
    r = requests.post(f"{RAG_URL}/rag/search", json={"query": query, "k": k}, timeout=10)
    r.raise_for_status()
    return r.json()["results"]


@mcp.tool()
def build_website(
    business_name: str,
    business_type: str,
    location: str,
    offerings: str,
    target_customers: str,
    tone: str,
) -> dict:
    """Design and write a complete small-business website from a brief.
    Returns the site spec (theme, fonts, pages) and full page copy."""
    from nodes import critique, illustrate, plan, write

    state = {
        "brief": {
            "business_name": business_name,
            "business_type": business_type,
            "location": location,
            "offerings": offerings,
            "target_customers": target_customers,
            "tone": tone,
        },
        "brief_complete": True,
        "revisions": 0,
    }
    for node in (plan, illustrate, write, critique):
        state.update(node(state))
    return {
        "spec": state["spec"],
        "pages": state["pages"],
        "review_score": state["critique"].get("score"),
    }


@mcp.tool()
def publish_website(spec: dict, pages: dict) -> str:
    """Publish a built website to Firebase Hosting. Returns the live URL."""
    from publish import publish_site

    _, url = publish_site(spec, pages)
    return url


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
