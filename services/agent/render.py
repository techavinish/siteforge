"""Site renderer — turns the agent's spec + pages into the final website.

This module is the single source of truth for what a generated site looks
like. The preview endpoint serves its output to the app's iframe, and
deploy_site will publish the very same documents to Firebase Hosting —
one renderer, zero drift between preview and production.
"""

import re
from datetime import datetime, timezone
from string import Template

import markdown as md


def _repair_links(body: str, page_paths: list[str], path: str, mode: str) -> str:
    """No dead buttons, ever. Anchor links (#contact) become real page
    links when a matching page exists; links to nonexistent pages fall
    back to the contact page (or home). Live pages use /path/ urls;
    preview keeps bare paths for postMessage interception."""

    def fix(match: re.Match) -> str:
        href = match.group(1)
        if href.startswith(("http", "mailto:", "tel:")):
            return match.group(0)
        target = "/" + href.lstrip("#/").split("/")[0] if href not in ("", "/") else "/"
        if target not in page_paths:
            target = "/contact" if "/contact" in page_paths else "/"
        if mode == "live":
            target = target if target == "/" else f"{target}/"
        return f'href="{target}"'

    return re.sub(r'href="([^"]*)"', fix, body)

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?$fonts_query&display=swap" rel="stylesheet">
<style>
  :root {
    --accent: $accent; --bg: $bg; --surface: $surface; --ink: $ink;
    --radius: ${radius}px;
  }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: "$body_font", system-ui, sans-serif; color: var(--ink); background: var(--bg); line-height: 1.7; }
  header {
    position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--surface) 88%, transparent);
    backdrop-filter: blur(8px); border-bottom: 1px solid color-mix(in srgb, var(--ink) 10%, transparent);
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px clamp(20px, 6vw, 56px);
  }
  .brand { font-family: "$head_font", serif; font-weight: 700; font-size: 1.15rem; color: var(--accent); }
  nav { display: flex; gap: 22px; flex-wrap: wrap; }
  nav a { color: color-mix(in srgb, var(--ink) 78%, transparent); text-decoration: none; font-size: 0.85rem; padding-bottom: 2px; border-bottom: 2px solid transparent; }
  nav a:hover { color: var(--accent); }
  nav a.on { color: var(--accent); border-bottom-color: var(--accent); }
  main { max-width: 860px; margin: 0 auto; padding: 40px clamp(20px, 5vw, 40px) 80px; }
  .hero-img { background: var(--surface); overflow: hidden; }
  .hero-img img { width: 100%; height: 100%; object-fit: cover; display: block; }
$layout_css
  h1, h2, h3 { font-family: "$head_font", serif; line-height: 1.12; }
  h1 { font-size: clamp(2.2rem, 5.5vw, 3.4rem); letter-spacing: -0.015em; margin: 0.3em 0; }
  h1 + p strong { font-size: 1.15rem; opacity: 0.72; font-weight: 600; }
  h2 { font-size: 1.7rem; color: var(--accent); margin: 2.2em 0 0.5em; }
  h3 { font-size: 1.15rem; margin: 1.5em 0 0.4em; }
  p { margin: 0.8em 0; }
  main a {
    display: inline-block; margin: 6px 10px 6px 0; padding: 11px 24px;
    background: var(--accent); color: #fff; text-decoration: none;
    border-radius: var(--radius); font-weight: 600; font-size: 0.9rem;
    transition: filter .15s ease, transform .12s ease;
  }
  main a:hover { filter: brightness(1.1); transform: translateY(-1px); }
  ul, ol { padding-left: 24px; margin: 0.8em 0; }
  li { margin-bottom: 6px; }
  blockquote { border-left: 3px solid var(--accent); background: var(--surface); padding: 14px 20px; margin: 1.2em 0; border-radius: 0 8px 8px 0; }
  hr { border: none; border-top: 1px solid color-mix(in srgb, var(--ink) 12%, transparent); margin: 2.5em 0; }
  footer { border-top: 1px solid color-mix(in srgb, var(--ink) 10%, transparent); padding: 28px; text-align: center; font-size: 0.8rem; color: #888; }
  .contact-form { margin-top: 2.5em; }
  .contact-form form { display: grid; gap: 14px; max-width: 460px; }
  .contact-form label { display: grid; gap: 6px; font-size: 0.85rem; font-weight: 600; }
  .contact-form input, .contact-form textarea {
    font: inherit; padding: 11px 14px; border-radius: calc(var(--radius) * 0.7);
    border: 1.5px solid color-mix(in srgb, var(--ink) 18%, transparent);
    background: var(--bg); color: var(--ink);
  }
  .contact-form input:focus, .contact-form textarea:focus {
    outline: none; border-color: var(--accent);
  }
  .contact-form button {
    font: inherit; font-weight: 600; padding: 12px; border: none;
    border-radius: var(--radius); background: var(--accent); color: #fff;
    cursor: pointer;
  }
  .mark {
    display: inline-grid; place-items: center; width: 30px; height: 30px;
    margin-right: 10px; border-radius: var(--radius);
    background: var(--accent); color: #fff;
    font-size: 0.95rem; vertical-align: -8px;
  }
  /* one orchestrated moment: the page settles in — then stillness */
  main { animation: settle 0.5s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
  @keyframes settle { from { opacity: 0; transform: translateY(12px); } }
  /* quality floor: keyboard focus visible, reduced motion respected */
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
  }
</style>
</head>
<body>
<header><span class="brand"><span class="mark">$initial</span>$site_name</span><nav>$nav</nav></header>
<main>$hero$body$contact_block</main>
<footer>© $year $site_name · Built with SiteForge$photo_credit</footer>
$nav_script
</body>
</html>""")

# Four layout personalities — the plan node picks one per brand, so sites
# stop being structural twins. Same markdown, different architecture.
LAYOUT_CSS = {
    "classic": """
  .hero-img { margin: 0 0 36px; border-radius: 16px; aspect-ratio: 21 / 9; }""",
    "split": """
  .hero-img {
    float: right; width: 44%; aspect-ratio: 4 / 5;
    border-radius: 14px; margin: 0 0 20px 32px;
  }
  @media (max-width: 720px) { .hero-img { float: none; width: 100%; aspect-ratio: 16/10; margin: 0 0 24px; } }
  h1 { max-width: 12ch; }""",
    "minimal": """
  main { max-width: 640px; padding-top: 72px; }
  body { line-height: 1.9; }
  .hero-img { margin: 40px auto; width: 82%; aspect-ratio: 16 / 10; border-radius: 4px; }
  h1 { font-size: clamp(1.9rem, 4.5vw, 2.6rem); font-weight: 500; }
  h2 { font-size: 0.95rem; letter-spacing: 0.14em; text-transform: uppercase; margin-top: 3em; }
  main a { background: none; color: var(--accent); border: 1.5px solid var(--accent); padding: 10px 22px; }
  hr { margin: 3.5em auto; width: 64px; }""",
    "bold": """
  .hero-img {
    margin: 0 calc(50% - 50vw) 44px; width: 100vw; max-width: 100vw;
    aspect-ratio: 16 / 6; border-radius: 0;
  }
  h1 {
    font-size: clamp(2.6rem, 7vw, 4.2rem); text-transform: uppercase;
    letter-spacing: -0.02em; line-height: 0.98;
  }
  h2 {
    display: inline-block; background: var(--accent); color: #fff;
    padding: 4px 14px; font-size: 1.2rem; border-radius: 4px;
  }
  main a { padding: 14px 32px; font-size: 1rem; border-radius: 4px; }""",
}


CONTACT_FORM = Template("""
<section class="contact-form">
  <h2>Send us a message</h2>
  <form action="https://formsubmit.co/$email" method="POST">
    <input type="hidden" name="_subject" value="New enquiry from your $site_name website">
    <input type="hidden" name="_captcha" value="false">
    <label>Your name<input type="text" name="name" required></label>
    <label>Your email<input type="email" name="email" required></label>
    <label>Message<textarea name="message" rows="4" required></textarea></label>
    <button type="submit">Send message</button>
  </form>
</section>""")


PREVIEW_NAV_SCRIPT = """<script>
  document.querySelectorAll('nav a, main a[href^="/"]').forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      parent.postMessage({ sfNav: a.dataset.path || a.getAttribute("href") }, "*");
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

    # a WORKING contact form on the contact page whenever the owner's
    # email is known — formsubmit.co posts to their inbox, no backend
    contact_block = ""
    contact = spec.get("contact") or {}
    if "contact" in path and contact.get("email"):
        contact_block = CONTACT_FORM.substitute(
            email=contact["email"], site_name=site_name
        )

    # real photography from the illustrate node, when present
    hero = ""
    image = (active or {}).get("image")
    if image:
        hero = (
            f'<div class="hero-img"><img src="{image["url"]}" '
            f'alt="{image.get("alt", "")}" loading="lazy"></div>'
        )
    any_photos = any(p.get("image") for p in page_list)

    palette = theme.get("palette") or {}
    body_html = _repair_links(
        md.markdown(pages.get(path, ""), extensions=["extra"]),
        [p["path"] for p in page_list], path, mode,
    )
    return PAGE.substitute(
        title=title,
        initial=(site_name.strip()[:1] or "•").upper(),
        fonts_query=fonts_query,
        accent=theme.get("primary_color") or "#333",
        bg=palette.get("background") or "#ffffff",
        surface=palette.get("surface") or "#f6f6f4",
        ink=palette.get("ink") or "#222222",
        radius=int(theme.get("radius") or 8),
        head_font=head_font,
        body_font=body_font,
        site_name=site_name,
        nav=nav,
        body=body_html,
        year=datetime.now(timezone.utc).year,
        nav_script="" if mode == "live" else PREVIEW_NAV_SCRIPT,
        contact_block=contact_block,
        hero=hero,
        photo_credit=" · Photos via Pexels" if any_photos else "",
        layout_css=LAYOUT_CSS.get(theme.get("layout", "classic"), LAYOUT_CSS["classic"]),
    )
