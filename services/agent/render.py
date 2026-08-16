"""Site renderer — turns the agent's spec + pages into the final website.

This module is the single source of truth for what a generated site looks
like. The preview endpoint serves its output to the app's iframe, and
deploy_site will publish the very same documents to Firebase Hosting —
one renderer, zero drift between preview and production.

v2: pages are no longer one column of markdown. The writer's structure IS
the design contract — `#` hero, `##` sections, lists, blockquotes — and
this renderer turns it into designed BANDS: a real hero, card grids,
testimonial bands, a photo gallery, alternating tints, a rich footer.
Code turns structure into design; the model never writes HTML.
"""

import html
import re
from datetime import datetime, timezone
from string import Template

import markdown as md


def _attr(value: str) -> str:
    """Attribute-context escaping — a site named O"Brien's must not
    break out of its own markup."""
    return html.escape(str(value or ""), quote=True)


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


# ── markdown → designed structure ──────────────────────────────────────

def _split_sections(md_text: str) -> tuple[str, list[str]]:
    """Hero = everything before the first `## `; each `## ` starts a band."""
    lines = (md_text or "").split("\n")
    starts = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if not starts:
        return md_text or "", []
    hero = "\n".join(lines[: starts[0]])
    sections = [
        "\n".join(lines[a:b]) for a, b in zip(starts, starts[1:] + [len(lines)])
    ]
    return hero, sections


def _md(chunk: str) -> str:
    return md.markdown(chunk or "", extensions=["extra"])


def _cardify(section_html: str) -> str:
    """A list of 3-8 short items is FEATURES, not prose — render as cards.
    Long-form lists (directions, paragraph-length points) stay lists."""

    def repl(m: re.Match) -> str:
        items = re.findall(r"<li>(.*?)</li>", m.group(0), re.DOTALL)
        if not (3 <= len(items) <= 8):
            return m.group(0)
        if any(len(re.sub(r"<[^>]+>", "", it).strip()) > 260 for it in items):
            return m.group(0)
        cards = "".join(f'<div class="card">{it.strip()}</div>' for it in items)
        return f'<div class="cards">{cards}</div>'

    return re.sub(r"<ul>.*?</ul>", repl, section_html, flags=re.DOTALL)


_STAT_LEAD = re.compile(r"^\s*<strong>\s*([^<]{1,18})</strong>\s*[—:–-]?\s*(.*)$", re.DOTALL)


def _is_stat(item_inner: str) -> tuple[str, str] | None:
    """A list item like '**200+** — Weddings captured' is a STAT: a short
    bold lead (number-ish) then a label. Returns (big, label) or None."""
    m = _STAT_LEAD.match(item_inner.strip())
    if not m:
        return None
    big = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    label = re.sub(r"<[^>]+>", "", m.group(2)).strip()
    # a STAT's lead must be a NUMBER (12 yrs, 8,000+, 48 hr, 100%) — a bare
    # word like "Sourdough" is a feature name, not a statistic
    if not label or len(big) > 16 or not re.search(r"\d", big):
        return None
    return (big, label)


def _statify(section_html: str) -> str | None:
    """Turn a bullet list of stat items into a big-number proof band."""
    m = re.search(r"<ul>.*?</ul>", section_html, re.DOTALL)
    if not m:
        return None
    items = re.findall(r"<li>(.*?)</li>", m.group(0), re.DOTALL)
    stats = [_is_stat(it) for it in items]
    if len(items) < 2 or not all(stats):
        return None
    cells = "".join(
        f'<div class="stat"><span class="stat-n">{_attr(b)}</span>'
        f'<span class="stat-l">{_attr(l)}</span></div>'
        for b, l in stats
    )
    grid = f'<div class="stats">{cells}</div>'
    return re.sub(r"<ul>.*?</ul>", grid, section_html, flags=re.DOTALL)


def _stepify(section_html: str) -> str:
    """An ordered list of 3-6 items is a PROCESS — render as numbered steps."""

    def repl(m: re.Match) -> str:
        items = re.findall(r"<li>(.*?)</li>", m.group(0), re.DOTALL)
        if not (3 <= len(items) <= 6):
            return m.group(0)
        steps = "".join(
            f'<div class="step"><span class="step-n">{i}</span>'
            f'<div class="step-b">{it.strip()}</div></div>'
            for i, it in enumerate(items, 1)
        )
        return f'<div class="steps">{steps}</div>'

    return re.sub(r"<ol>.*?</ol>", repl, section_html, flags=re.DOTALL)


def _faqify(section_html: str) -> str:
    """### question + following block become a native <details> accordion."""
    parts = re.split(r"(<h3>.*?</h3>)", section_html, flags=re.DOTALL)
    out, i = [parts[0]], 1
    while i < len(parts):
        q = re.sub(r"</?h3>", "", parts[i]).strip()
        a = parts[i + 1] if i + 1 < len(parts) else ""
        out.append(f"<details><summary>{q}</summary><div class='faq-a'>{a}</div></details>")
        i += 2
    return "".join(out)


def _quote_grid(section_html: str) -> str:
    """Two or more testimonials read better side by side than stacked.
    python-markdown collapses consecutive > quotes into ONE blockquote with
    a <p> per testimonial, so split on paragraphs, not blockquote tags."""
    blocks = re.findall(r"<blockquote>(.*?)</blockquote>", section_html, re.DOTALL)
    paras: list[str] = []
    for b in blocks:
        paras += re.findall(r"<p>.*?</p>", b, re.DOTALL)
    if len(paras) < 2:
        return section_html  # a single quote stays the big centered band
    cards = "".join(f"<blockquote>{p}</blockquote>" for p in paras)
    grid = f'<div class="quote-grid">{cards}</div>'
    # replace the whole run of blockquotes with the grid, in place
    return re.sub(
        r"<blockquote>.*</blockquote>", grid, section_html, count=1, flags=re.DOTALL
    )


def _hero_html(hero_md: str, image: dict | None, layout: str) -> str:
    """The hero is the page's thesis: headline, tagline, action — beside
    (or behind, for `bold`) the photograph."""
    hero = _md(hero_md)
    h1 = ""
    m = re.search(r"<h1>.*?</h1>", hero, re.DOTALL)
    if m:
        h1 = m.group(0)
        hero = hero.replace(h1, "", 1)
    tagline = ""
    m = re.search(r"<p><strong>(.*?)</strong></p>", hero, re.DOTALL)
    if m:
        tagline = f'<p class="tagline">{m.group(1)}</p>'
        hero = hero.replace(m.group(0), "", 1)

    img_html = ""
    if image:
        img_html = (
            f'<img src="{_attr(image["url"])}" alt="{_attr(image.get("alt", ""))}" loading="eager">'
        )

    if layout == "bold" and img_html:
        # image AS the hero: full-bleed photograph, headline on a scrim
        return (
            f'<section class="hero hero-cover">{img_html}<div class="scrim"></div>'
            f'<div class="hero-copy">{h1}{tagline}{hero}</div></section>'
        )
    img_block = f'<div class="hero-img">{img_html}</div>' if img_html else ""
    return (
        f'<section class="hero"><div class="hero-copy">{h1}{tagline}{hero}</div>'
        f"{img_block}</section>"
    )


def _gallery_html(shots: list[dict]) -> str:
    if not shots:
        return ""
    figs = "".join(
        f'<figure><img src="{_attr(s["url"])}" alt="{_attr(s.get("alt", ""))}" loading="lazy"></figure>'
        for s in shots
    )
    return f'<section class="band gallery"><div class="wrap"><div class="shots">{figs}</div></div></section>'


def _classify(section_md: str) -> str:
    """Map a section's markdown SHAPE to its band kind — the writer picks
    the shape (stat list, ordered list, ## FAQ, blockquotes), code renders
    each as a distinct designed band. Returns one of:
    stats | steps | faq | quotes | plain."""
    heading = ""
    m = re.search(r"^##\s+(.*)$", section_md, re.M)
    if m:
        heading = m.group(1).lower()
    if "faq" in heading or "question" in heading:
        return "faq"
    if re.search(r"^\s*>", section_md, re.M):
        return "quotes"
    if re.search(r"^\s*\d+\.\s", section_md, re.M):
        return "steps"
    body = _md(section_md)
    if _statify(body):
        return "stats"
    return "plain"


def _section_html(section_md: str, kind: str, tint: bool) -> str:
    body = _md(section_md)
    classes = ["band"]
    if kind == "stats":
        body = _statify(body) or body
        classes.append("stats-band")
        classes.append("tint")
    elif kind == "steps":
        body = _stepify(body)
        if tint:
            classes.append("tint")
    elif kind == "faq":
        body = _faqify(body)
        classes.append("faq")
        if tint:
            classes.append("tint")
    elif kind == "quotes":
        body = _quote_grid(body)
        classes.append("quotes")  # carries its own surface
    else:
        body = _cardify(body)
        if tint:
            classes.append("tint")
    return f'<section class="{" ".join(classes)}"><div class="wrap">{body}</div></section>'


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
    --soft: color-mix(in srgb, var(--ink) 10%, transparent);
    --muted: color-mix(in srgb, var(--ink) 62%, transparent);
  }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: "$body_font", system-ui, sans-serif; color: var(--ink); background: var(--bg); line-height: 1.7; }
  /* a whisper of the brand colour behind the top of the page — depth, not decoration */
  body::before {
    content: ""; position: fixed; inset: 0 0 auto; height: 60vh; z-index: -1; pointer-events: none;
    background: radial-gradient(120% 80% at 80% -20%,
      color-mix(in srgb, var(--accent) 9%, transparent), transparent 60%);
  }
  img { max-width: 100%; display: block; }
  ::selection { background: color-mix(in srgb, var(--accent) 22%, transparent); }

  header {
    position: sticky; top: 0; z-index: 5;
    background: color-mix(in srgb, var(--bg) 86%, transparent);
    backdrop-filter: blur(10px); border-bottom: 1px solid var(--soft);
    display: flex; align-items: center; gap: 18px;
    padding: 14px clamp(20px, 5vw, 48px);
  }
  .brand { font-family: "$head_font", serif; font-weight: 700; font-size: 1.12rem; color: var(--ink); display: inline-flex; align-items: center; }
  nav { display: flex; gap: 20px; flex-wrap: wrap; margin-left: auto; }
  nav a { color: var(--muted); text-decoration: none; font-size: 0.85rem; padding-bottom: 2px; border-bottom: 2px solid transparent; }
  nav a:hover { color: var(--accent); }
  nav a.on { color: var(--accent); border-bottom-color: var(--accent); }
  .nav-cta {
    flex: none; font-size: 0.82rem; font-weight: 700; text-decoration: none;
    padding: 9px 18px; border-radius: var(--radius);
    background: var(--accent); color: #fff;
    transition: filter .15s ease;
  }
  .nav-cta:hover { filter: brightness(1.1); }
  .mark {
    display: inline-grid; place-items: center; width: 30px; height: 30px;
    margin-right: 10px; border-radius: var(--radius);
    background: var(--accent); color: #fff; font-size: 0.95rem;
  }
  .logo-img { height: 32px; max-width: 150px; object-fit: contain; margin-right: 10px; border-radius: 4px; }

  /* ── the hero: the page's thesis ── */
  .hero {
    display: grid; grid-template-columns: 1.05fr 0.95fr; gap: clamp(28px, 5vw, 64px);
    align-items: center; max-width: 1100px; margin: 0 auto;
    padding: clamp(40px, 7vw, 88px) clamp(20px, 5vw, 48px) clamp(36px, 5vw, 64px);
  }
  @media (max-width: 780px) { .hero { grid-template-columns: 1fr; } }
  .hero h1 {
    font-family: "$head_font", serif; font-size: clamp(2.3rem, 5.4vw, 3.6rem);
    line-height: 1.06; letter-spacing: -0.018em; text-wrap: balance; margin: 0 0 0.35em;
  }
  .tagline { font-size: 1.14rem; color: var(--muted); font-weight: 500; margin-bottom: 0.9em; max-width: 46ch; }
  .hero p { max-width: 52ch; }
  .hero-img img { border-radius: calc(var(--radius) * 1.6); aspect-ratio: 4 / 3.2; object-fit: cover; width: 100%;
    box-shadow: 0 18px 50px color-mix(in srgb, var(--ink) 18%, transparent); }
  /* bold personality: the photograph IS the hero */
  .hero-cover { position: relative; display: block; max-width: none; padding: 0; }
  .hero-cover img { width: 100%; height: min(72vh, 640px); object-fit: cover; }
  .hero-cover .scrim { position: absolute; inset: 0;
    background: linear-gradient(to top, rgb(0 0 0 / 0.68), rgb(0 0 0 / 0.12) 60%); }
  .hero-cover .hero-copy { position: absolute; left: 0; right: 0; bottom: 0;
    max-width: 1100px; margin: 0 auto; padding: clamp(24px, 5vw, 56px) clamp(20px, 5vw, 48px); color: #fff; }
  .hero-cover h1 { color: #fff; }
  .hero-cover .tagline { color: rgb(255 255 255 / 0.85); }

  /* ── bands: the page's rhythm ── */
  .band { padding: clamp(36px, 5.5vw, 72px) clamp(20px, 5vw, 48px); }
  .band.tint { background: var(--surface); }
  .wrap { max-width: 1060px; margin: 0 auto; }
  .band h2 {
    font-family: "$head_font", serif; font-size: clamp(1.5rem, 2.8vw, 2.1rem);
    letter-spacing: -0.012em; text-wrap: balance; margin: 0 0 0.6em;
  }
  .band h3 { font-size: 1.1rem; margin: 1.4em 0 0.4em; }
  .band p { margin: 0.8em 0; max-width: 68ch; }
  .band ul, .band ol { padding-left: 24px; margin: 0.8em 0; max-width: 68ch; }
  .band li { margin-bottom: 6px; }

  /* feature cards: short lists become a grid */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 16px; margin: 1.4em 0 0.6em; }
  .card {
    background: var(--bg); border: 1px solid var(--soft);
    border-radius: calc(var(--radius) * 1.3); padding: 22px 24px;
    font-size: 0.95rem; line-height: 1.6;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
  }
  .band.tint .card { background: var(--bg); }
  .band:not(.tint) .card { background: var(--surface); border-color: transparent; }
  .card:hover {
    transform: translateY(-3px);
    border-color: color-mix(in srgb, var(--accent) 40%, transparent);
    box-shadow: 0 12px 30px color-mix(in srgb, var(--ink) 12%, transparent);
  }
  .card > strong:first-child { display: block; font-size: 1.05rem; margin-bottom: 6px; color: var(--accent); }

  /* stats: instant proof a business is established */
  .stats-band { padding-top: clamp(30px, 4vw, 52px); padding-bottom: clamp(30px, 4vw, 52px); }
  .stats-band h2 { text-align: center; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 20px; margin-top: 1em; text-align: center; }
  .stat { display: flex; flex-direction: column; gap: 4px; }
  .stat-n { font-family: "$head_font", serif; font-size: clamp(2rem, 4.4vw, 3rem);
    line-height: 1; color: var(--accent); font-weight: 700; }
  .stat-l { font-size: 0.85rem; color: var(--muted); }

  /* process: a numbered path, not a bare list */
  .steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 18px; margin: 1.4em 0 0.4em; counter-reset: step; }
  .step { position: relative; padding: 22px 22px 22px 22px;
    background: var(--bg); border: 1px solid var(--soft); border-radius: calc(var(--radius) * 1.3);
    transition: transform .16s ease, box-shadow .16s ease; }
  .band.tint .step { background: var(--bg); }
  .band:not(.tint) .step { background: var(--surface); border-color: transparent; }
  .step:hover { transform: translateY(-3px);
    box-shadow: 0 12px 30px color-mix(in srgb, var(--ink) 12%, transparent); }
  .step-n { display: inline-grid; place-items: center; width: 34px; height: 34px; margin-bottom: 12px;
    border-radius: 50%; background: var(--accent); color: #fff; font-weight: 700; font-size: 0.95rem; }
  .step-b > *:first-child { margin-top: 0; }
  .step-b strong { display: block; margin-bottom: 4px; }

  /* FAQ: native disclosure, styled */
  .band.faq .wrap { max-width: 760px; }
  .band.faq details { border-bottom: 1px solid var(--soft); padding: 4px 0; }
  .band.faq summary { cursor: pointer; list-style: none; padding: 16px 34px 16px 2px;
    position: relative; font-weight: 600; font-size: 1.02rem; }
  .band.faq summary::-webkit-details-marker { display: none; }
  .band.faq summary::after { content: "+"; position: absolute; right: 6px; top: 14px;
    font-size: 1.4rem; color: var(--accent); line-height: 1; transition: transform .2s ease; }
  .band.faq details[open] summary::after { content: "\\2212"; }
  .band.faq .faq-a { padding: 0 2px 16px; color: var(--muted); }
  .band.faq .faq-a > *:first-child { margin-top: 0; }

  /* testimonials: a voice, not a box */
  .quote-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; text-align: left; }
  .quote-grid blockquote { max-width: none; margin: 0; padding: 24px 26px;
    background: var(--bg); border-radius: calc(var(--radius) * 1.3); font-size: 1.05rem; }
  .quote-grid blockquote::before { font-size: 2.2rem; }
  .band.quotes { text-align: center; background: var(--surface); }
  .band.quotes blockquote {
    max-width: 46ch; margin: 1em auto; padding: 0;
    border: none; background: none;
    font-family: "$head_font", serif; font-size: clamp(1.15rem, 2.2vw, 1.5rem); line-height: 1.5;
  }
  .band.quotes blockquote::before { content: "“"; display: block; font-size: 3rem; line-height: 0.6;
    color: var(--accent); margin-bottom: 14px; }
  .band.quotes blockquote em, .band.quotes blockquote cite { font-family: "$body_font", sans-serif;
    font-size: 0.85rem; color: var(--muted); font-style: normal; display: block; margin-top: 12px; }

  /* the gallery: proof in pictures */
  .gallery { padding-top: 0; }
  .shots { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  .shots figure { margin: 0; }
  .shots img { border-radius: calc(var(--radius) * 1.2); aspect-ratio: 4 / 3; object-fit: cover; width: 100%; }

  /* CTAs: links render as buttons */
  main a:not(.plain) {
    display: inline-block; margin: 8px 10px 4px 0; padding: 12px 26px;
    background: var(--accent); color: #fff; text-decoration: none;
    border-radius: var(--radius); font-weight: 600; font-size: 0.9rem;
    transition: filter .15s ease, transform .12s ease;
  }
  main a:hover { filter: brightness(1.1); transform: translateY(-1px); }
  main a[href^="tel:"], main a[href^="mailto:"], main a[href^="https://wa.me"] {
    background: transparent; color: var(--accent); border: 1.5px solid var(--accent);
  }
  hr { border: none; border-top: 1px solid var(--soft); margin: 2em 0; }

  /* forms (email + booking) */
  .contact-form { max-width: 520px; }
  .contact-form h2 { font-family: "$head_font", serif; }
  .contact-form form { display: grid; gap: 14px; margin-top: 1em; }
  .contact-form label { display: grid; gap: 6px; font-size: 0.85rem; font-weight: 600; }
  .contact-form input, .contact-form textarea, .contact-form select {
    font: inherit; padding: 12px 14px; border-radius: calc(var(--radius) * 0.7);
    border: 1.5px solid color-mix(in srgb, var(--ink) 18%, transparent);
    background: var(--bg); color: var(--ink);
  }
  .contact-form input:focus, .contact-form textarea:focus, .contact-form select:focus {
    outline: none; border-color: var(--accent);
  }
  .contact-form button {
    font: inherit; font-weight: 600; padding: 13px; border: none;
    border-radius: var(--radius); background: var(--accent); color: #fff; cursor: pointer;
  }
  .contact-form button:disabled { opacity: 0.6; cursor: default; }
  .form-note { font-size: 0.85rem; color: var(--muted); margin: 0; }
  .form-note:empty { display: none; }
  .form-done { padding: 18px 20px; border-radius: var(--radius);
    background: var(--surface); border: 1.5px solid var(--accent); }
  .hp { position: absolute; left: -5000px; }

  /* footer: a real ending, not a copyright line */
  .site-foot {
    border-top: 1px solid var(--soft); background: var(--surface);
    padding: clamp(32px, 5vw, 56px) clamp(20px, 5vw, 48px) 28px;
  }
  .foot-grid { max-width: 1060px; margin: 0 auto; display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 28px; }
  .foot-brand { font-family: "$head_font", serif; font-weight: 700; font-size: 1.05rem; }
  .site-foot nav { display: grid; gap: 8px; margin: 0; }
  .site-foot a { color: var(--muted); text-decoration: none; font-size: 0.85rem; }
  .site-foot a:hover { color: var(--accent); }
  .foot-contact { display: grid; gap: 6px; font-size: 0.85rem; color: var(--muted); }
  .foot-credit { max-width: 1060px; margin: 28px auto 0; padding-top: 18px;
    border-top: 1px solid var(--soft); font-size: 0.75rem; color: var(--muted); }

  /* one orchestrated moment: the page settles in — then stillness */
  main { animation: settle 0.5s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
  @keyframes settle { from { opacity: 0; transform: translateY(12px); } }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
  }
$layout_css
</style>
</head>
<body>
<header><span class="brand">$brand_mark$site_name</span><nav>$nav</nav>$nav_cta</header>
<main>$main</main>
<footer class="site-foot">
  <div class="foot-grid">
    <div><div class="foot-brand">$site_name</div></div>
    <nav>$foot_nav</nav>
    <div class="foot-contact">$foot_contact</div>
  </div>
  <div class="foot-credit">© $year $site_name · Built with SiteForge$photo_credit</div>
</footer>
$nav_script
</body>
</html>""")

# Four layout personalities — same structure, different accent on the hero
# and bands, so sites stop being structural twins.
LAYOUT_CSS = {
    "classic": "",
    "split": """
  .hero { grid-template-columns: 1fr 0.85fr; }
  .hero-img img { aspect-ratio: 4 / 5; }
  .hero h1 { max-width: 14ch; }""",
    "minimal": """
  .hero { grid-template-columns: 1fr; text-align: center; max-width: 760px; padding-top: clamp(56px, 9vw, 110px); }
  .hero p, .hero .tagline { margin-left: auto; margin-right: auto; }
  .hero-img img { aspect-ratio: 16 / 9; box-shadow: none; }
  body { line-height: 1.85; }
  .band.tint { background: transparent; border-top: 1px solid var(--soft); }
  main a:not(.plain) { background: none; color: var(--accent); border: 1.5px solid var(--accent); }
  .card { border: 1px solid var(--soft) !important; background: transparent !important; }""",
    "bold": """
  .band h2 { text-transform: uppercase; letter-spacing: 0.02em; font-size: clamp(1.3rem, 2.4vw, 1.7rem); }
  .band h2::after { content: ""; display: block; width: 44px; height: 4px; background: var(--accent);
    margin-top: 10px; border-radius: 2px; }
  main a:not(.plain) { padding: 14px 32px; font-size: 1rem; }""",
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


# tracker mode: bookings land in the owner's SiteForge dashboard. In the
# app preview ($endpoint empty) submission demos the success state without
# touching the network — the form goes live with the site.
BOOKING_FORM = Template("""
<section class="contact-form">
  <h2>Request a booking</h2>
  <form id="sf-book">
    <input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
    <label>Your name<input type="text" name="name" required maxlength="80"></label>
    <label>Phone or email<input type="text" name="contact" required maxlength="120"></label>
    $service_field
    <label>Anything we should know?<textarea name="message" rows="3" maxlength="1000"></textarea></label>
    <button type="submit">Request booking</button>
    <p class="form-note" id="sf-book-note" role="status"></p>
  </form>
</section>
<script>
(function () {
  var form = document.getElementById("sf-book");
  var note = document.getElementById("sf-book-note");
  var endpoint = "$endpoint";
  var thanks = "<p class='form-done'><strong>Booking received.</strong> " +
    "We&rsquo;ll get back to you shortly &mdash; thank you!</p>";
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!endpoint) { form.innerHTML = thanks; return; }
    var data = { key: "$key" };
    new FormData(form).forEach(function (v, k) { data[k] = v; });
    var btn = form.querySelector("button");
    btn.disabled = true; btn.textContent = "Sending\\u2026";
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    }).then(function (r) {
      if (!r.ok) throw new Error("failed");
      form.innerHTML = thanks;
    }).catch(function () {
      btn.disabled = false; btn.textContent = "Request booking";
      note.textContent = "That didn\\u2019t send \\u2014 please try again, " +
        "or reach us directly with the details on this page.";
    });
  });
})();
</script>""")


PREVIEW_NAV_SCRIPT = """<script>
  document.querySelectorAll('header a, nav a, main a[href^="/"]').forEach(function (a) {
    a.addEventListener("click", function (e) {
      if ((a.getAttribute("href") || "").match(/^(http|mailto:|tel:)/)) return;
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
    layout = theme.get("layout", "classic")
    page_list = spec.get("pages") or [{"path": p, "title": p} for p in pages]
    page_paths = [p["path"] for p in page_list]

    def live_href(p: str) -> str:
        return p if p == "/" or mode != "live" else f"{p}/"

    # preview: nav clicks postMessage up to the app; live: real hrefs
    if mode == "live":
        nav = "".join(
            f'<a href="{live_href(p["path"])}" class="{"on" if p["path"] == path else ""}">{p["title"]}</a>'
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

    contact = spec.get("contact") or {}
    form_mode = contact.get("mode") or ("email" if contact.get("email") else "none")

    # header action mirrors the owner's choice: book, or just reach out
    cta_label = "Book now" if form_mode == "tracker" else "Get in touch"
    if "/contact" in page_paths and path != "/contact":
        if mode == "live":
            nav_cta = f'<a class="nav-cta" href="{live_href("/contact")}">{cta_label}</a>'
        else:
            nav_cta = f'<a class="nav-cta" href="#" data-path="/contact">{cta_label}</a>'
    else:
        nav_cta = ""

    # ── assemble the page as designed bands ──
    hero_md, section_mds = _split_sections(pages.get(path, ""))
    image = (active or {}).get("image")
    parts = [_hero_html(hero_md, image, layout)]

    shots = (active or {}).get("shots") or []
    # tint alternates over ORDINARY bands only — stats/quotes bring their
    # own surface, so they're skipped in the rhythm count
    sections, tintable = [], 0
    for s in section_mds:
        kind = _classify(s)
        owns_surface = kind in ("stats", "quotes")
        sections.append(_section_html(s, kind, tint=not owns_surface and tintable % 2 == 1))
        if not owns_surface:
            tintable += 1
    if shots:
        # the gallery lands after the first section — proof right after the pitch
        sections.insert(min(1, len(sections)), _gallery_html(shots))
    parts += sections

    # the contact page carries the form the OWNER chose:
    #   tracker — SiteForge booking form, feeding their Bookings dashboard
    #   email   — formsubmit.co posts to their inbox, no backend
    #   none    — contact details only, no form
    if "contact" in path:
        contact_block = ""
        if form_mode == "tracker" and spec.get("booking_key"):
            services = [s for s in (spec.get("services") or []) if s]
            service_field = ""
            if len(services) >= 2:
                options = "".join(f"<option>{_attr(s)}</option>" for s in services)
                service_field = (
                    "<label>What would you like to book?"
                    f'<select name="service"><option value="">Choose…</option>{options}</select></label>'
                )
            contact_block = BOOKING_FORM.substitute(
                service_field=service_field,
                endpoint=f"{spec.get('agent_base', '')}/agent/book" if mode == "live" else "",
                key=spec["booking_key"],
            )
        elif form_mode == "email" and contact.get("email"):
            contact_block = CONTACT_FORM.substitute(
                email=contact["email"], site_name=site_name
            )
        if contact_block:
            parts.append(f'<section class="band tint"><div class="wrap">{contact_block}</div></section>')

    main_html = _repair_links("".join(parts), page_paths, path, mode)

    # footer: navigation + real contact details — a page's honest ending
    if mode == "live":
        foot_nav = "".join(f'<a href="{live_href(p["path"])}">{p["title"]}</a>' for p in page_list)
    else:
        foot_nav = "".join(f'<a href="#" data-path="{p["path"]}">{p["title"]}</a>' for p in page_list)
    foot_bits = []
    if contact.get("location"):
        foot_bits.append(f"<span>{_attr(contact['location'])}</span>")
    if contact.get("phone"):
        foot_bits.append(f'<a class="plain" href="tel:{_attr(contact["phone"])}">{_attr(contact["phone"])}</a>')
    if contact.get("email"):
        foot_bits.append(f'<a class="plain" href="mailto:{_attr(contact["email"])}">{_attr(contact["email"])}</a>')
    foot_contact = "".join(foot_bits)

    any_photos = bool(image) or any(p.get("image") for p in page_list) or bool(shots)

    # the owner's uploaded logo replaces the initial mark everywhere
    if spec.get("logo_url"):
        brand_mark = f'<img class="logo-img" src="{_attr(spec["logo_url"])}" alt="{_attr(site_name)} logo">'
    else:
        brand_mark = f'<span class="mark">{(site_name.strip()[:1] or "•").upper()}</span>'

    palette = theme.get("palette") or {}
    return PAGE.substitute(
        title=title,
        brand_mark=brand_mark,
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
        nav_cta=nav_cta,
        main=main_html,
        foot_nav=foot_nav,
        foot_contact=foot_contact,
        year=datetime.now(timezone.utc).year,
        nav_script="" if mode == "live" else PREVIEW_NAV_SCRIPT,
        photo_credit=" · Photos via Pexels" if any_photos else "",
        layout_css=LAYOUT_CSS.get(layout, LAYOUT_CSS["classic"]),
    )
