"""Site renderer — turns the agent's spec + pages into the final website.

This module is the single source of truth for what a generated site looks
like. The preview endpoint serves its output to the app's iframe, and
deploy_site will publish the very same documents to Firebase Hosting —
one renderer, zero drift between preview and production.
"""

from datetime import datetime, timezone
from string import Template

import markdown as md

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?$fonts_query&display=swap" rel="stylesheet">
<style>
  :root { --accent: $accent; }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: "$body_font", system-ui, sans-serif; color: #222; background: #fff; line-height: 1.7; }
  header {
    position: sticky; top: 0; z-index: 5; background: rgba(255,255,255,0.92);
    backdrop-filter: blur(8px); border-bottom: 1px solid #eee;
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px clamp(20px, 6vw, 56px);
  }
  .brand { font-family: "$head_font", serif; font-weight: 700; font-size: 1.15rem; color: var(--accent); }
  nav { display: flex; gap: 22px; flex-wrap: wrap; }
  nav a { color: #444; text-decoration: none; font-size: 0.85rem; padding-bottom: 2px; border-bottom: 2px solid transparent; }
  nav a:hover { color: var(--accent); }
  nav a.on { color: var(--accent); border-bottom-color: var(--accent); }
  main { max-width: 860px; margin: 0 auto; padding: 40px clamp(20px, 5vw, 40px) 80px; }
  .hero-img {
    margin: 0 0 36px; border-radius: 16px; overflow: hidden;
    aspect-ratio: 21 / 9; background: #f3f3f3;
  }
  .hero-img img { width: 100%; height: 100%; object-fit: cover; display: block; }
  h1, h2, h3 { font-family: "$head_font", serif; line-height: 1.12; }
  h1 { font-size: clamp(2.2rem, 5.5vw, 3.4rem); letter-spacing: -0.015em; margin: 0.3em 0; }
  h1 + p strong { font-size: 1.15rem; color: #555; font-weight: 600; }
  h2 { font-size: 1.7rem; color: var(--accent); margin: 2.2em 0 0.5em; }
  h3 { font-size: 1.15rem; margin: 1.5em 0 0.4em; }
  p { margin: 0.8em 0; }
  main a {
    display: inline-block; margin: 6px 10px 6px 0; padding: 11px 24px;
    background: var(--accent); color: #fff; text-decoration: none;
    border-radius: 8px; font-weight: 600; font-size: 0.9rem;
    transition: filter .15s ease, transform .12s ease;
  }
  main a:hover { filter: brightness(1.1); transform: translateY(-1px); }
  ul, ol { padding-left: 24px; margin: 0.8em 0; }
  li { margin-bottom: 6px; }
  blockquote { border-left: 3px solid var(--accent); background: #fafafa; padding: 14px 20px; margin: 1.2em 0; border-radius: 0 8px 8px 0; }
  hr { border: none; border-top: 1px solid #eee; margin: 2.5em 0; }
  footer { border-top: 1px solid #eee; padding: 28px; text-align: center; font-size: 0.8rem; color: #888; }
</style>
</head>
<body>
<header><span class="brand">$site_name</span><nav>$nav</nav></header>
<main>$hero$body</main>
<footer>© $year $site_name · Built with SiteForge$photo_credit</footer>
$nav_script
</body>
</html>""")

PREVIEW_NAV_SCRIPT = """<script>
  document.querySelectorAll("nav a").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      parent.postMessage({ sfNav: a.dataset.path }, "*");
    });
  });
</script>"""


def build_site_html(spec: dict, pages: dict, path: str, mode: str = "preview") -> str:
    theme = spec.get("theme") or {}
    fonts = theme.get("fonts") or {}
    head_font = (fonts.get("heading") or "Georgia").strip()
    body_font = (fonts.get("body") or "system-ui").strip()
    site_name = spec.get("site_name") or "Your Site"
    page_list = spec.get("pages") or [{"path": p, "title": p} for p in pages]

    # preview: nav clicks postMessage up to the app; live: real hrefs
    if mode == "live":
        nav = "".join(
            f'<a href="{p["path"] if p["path"] == "/" else p["path"] + "/"}"'
            f' class="{"on" if p["path"] == path else ""}">{p["title"]}</a>'
            for p in page_list
        )
    else:
        nav = "".join(
            f'<a href="#" data-path="{p["path"]}" class="{"on" if p["path"] == path else ""}">{p["title"]}</a>'
            for p in page_list
        )
    fonts_query = "&".join(
        f"family={f.replace(' ', '+')}:wght@400;600;700" for f in (head_font, body_font)
    )
    active = next((p for p in page_list if p["path"] == path), None)
    title = f"{active['title']} — {site_name}" if active and path != "/" else site_name

    # real photography from the illustrate node, when present
    hero = ""
    image = (active or {}).get("image")
    if image:
        hero = (
            f'<div class="hero-img"><img src="{image["url"]}" '
            f'alt="{image.get("alt", "")}" loading="lazy"></div>'
        )
    any_photos = any(p.get("image") for p in page_list)

    return PAGE.substitute(
        title=title,
        fonts_query=fonts_query,
        accent=theme.get("primary_color") or "#333",
        head_font=head_font,
        body_font=body_font,
        site_name=site_name,
        nav=nav,
        body=md.markdown(pages.get(path, ""), extensions=["extra"]),
        year=datetime.now(timezone.utc).year,
        nav_script="" if mode == "live" else PREVIEW_NAV_SCRIPT,
        hero=hero,
        photo_credit=" · Photos via Pexels" if any_photos else "",
    )
