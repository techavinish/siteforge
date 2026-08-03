"""Deterministic quality checks — run against the LIVE published page.

These need no LLM: the judge handles taste, these handle facts. Each check
returns a 0–10 score with a human-readable detail.
"""

import re


def run_checks(html: str) -> list[dict]:
    text = re.sub(r"<[^>]+>", " ", html)
    results = []

    def check(name: str, ok: bool, detail: str, partial: float | None = None):
        results.append({
            "check": name,
            "score": 10.0 if ok else (partial if partial is not None else 0.0),
            "detail": detail,
        })

    h1s = re.findall(r"<h1[\s>]", html)
    check("single_h1", len(h1s) == 1, f"{len(h1s)} h1 tags", partial=5.0 if h1s else 0.0)

    ctas = re.findall(r"<a\s[^>]*href", html)
    check("has_cta", len(ctas) >= 2, f"{len(ctas)} links/CTAs", partial=5.0 if ctas else 0.0)

    check("has_title", bool(re.search(r"<title>[^<]{3,}</title>", html)), "title tag")
    check("meta_viewport", 'name="viewport"' in html, "mobile viewport meta")

    imgs = re.findall(r"<img\s[^>]*>", html)
    with_alt = [i for i in imgs if 'alt="' in i and 'alt=""' not in i]
    check(
        "images_with_alt",
        bool(imgs) and len(with_alt) == len(imgs),
        f"{len(with_alt)}/{len(imgs)} images have alt text",
        partial=5.0 if imgs else 0.0,
    )

    words = len(text.split())
    check("substantial_copy", 120 <= words <= 1500, f"{words} words",
          partial=5.0 if words >= 60 else 0.0)

    check("has_footer", "<footer" in html, "footer present")
    check("has_nav", "<nav" in html, "navigation present")

    return results
