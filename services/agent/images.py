"""pick_images — real photography for generated sites, via Pexels."""

import os

import requests

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")


def find_image(query: str, avoid_url: str | None = None) -> dict | None:
    """Best landscape photo for a query, or None (missing key, no results,
    network trouble — a site without photos beats a broken generation).
    avoid_url skips the current photo so an image edit visibly changes."""
    if not PEXELS_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if avoid_url:
            photos = [p for p in photos if p["src"]["landscape"] != avoid_url] or photos
        if not photos:
            return None
        p = photos[0]
        return {
            "url": p["src"]["landscape"],
            "alt": p.get("alt") or query,
            "credit": p.get("photographer", ""),
        }
    except Exception:
        return None
