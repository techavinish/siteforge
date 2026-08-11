"""Graph nodes — each one is a plain function: state in, state-update out.

Note what is NOT here: no while-loops, no retries, no routing logic.
Nodes do ONE unit of work; the GRAPH decides what happens next. That
separation is the entire point of LangGraph over a freeform agent loop.
"""

from langchain_core.messages import AIMessage, SystemMessage

from config import INTERVIEW_MODEL, WRITER_MODEL
from llm import chat_model, extract_json
from state import AgentState

REQUIRED_BRIEF_FIELDS = [
    "business_name",
    "business_type",
    "location",
    "offerings",
    "target_customers",
    "tone",
]

# captured when mentioned, never demanded — they make CTAs genuinely work
OPTIONAL_BRIEF_FIELDS = ["phone", "email"]

# The interview is SPLIT into two nodes so the user-visible half can stream:
#   understand — silent JSON extraction (the "thinking" step; unstreamable)
#   respond    — pure prose written for the owner (streamed token-by-token)
# Structured output and streamable output never mix well in one call.

UNDERSTAND_SYSTEM = f"""You extract structured facts from a conversation between
a website copilot and a business owner. Fields: {", ".join(REQUIRED_BRIEF_FIELDS)}.
Also capture when mentioned (never required): {", ".join(OPTIONAL_BRIEF_FIELDS)}.

Respond with ONLY JSON: {{"brief": {{...every field learned so far...}},
"complete": true/false,
"edit_target": "when the site ALREADY EXISTS and the latest message asks for a
 change, classify it: images (photo/picture changes) | copy (text/wording) |
 design (colors/fonts/layout/pages) | none (just chatting). Otherwise none."}}
complete=true only when every field has a real value."""


def understand(state: AgentState) -> dict:
    model = chat_model(INTERVIEW_MODEL, temperature=0.1)
    site_exists = bool(state.get("pages"))
    result = model.invoke(
        [SystemMessage(UNDERSTAND_SYSTEM)]
        + state["messages"]
        + [SystemMessage(
            f"Previously known brief: {state.get('brief', {})}\n"
            f"Site already exists: {site_exists}"
        )]
    )
    try:
        data = extract_json(result.content)
    except ValueError:
        data = {"brief": state.get("brief", {}), "complete": False}
    last_user = next(
        (m.content for m in reversed(state["messages"]) if m.type == "human"), ""
    )
    # merge, never replace: models often return only the latest turn's
    # fields, and a partial extraction must not erase earlier answers
    extracted = data.get("brief") or {}
    merged = {**state.get("brief", {}), **{k: v for k, v in extracted.items() if v}}
    return {
        "brief": merged,
        # completeness is ground truth we can compute — never outsource a
        # boolean the graph routes on to the model
        "brief_complete": all(merged.get(f) for f in REQUIRED_BRIEF_FIELDS),
        "edit_target": (data.get("edit_target") or "none") if site_exists else "none",
        "edit_request": last_user if site_exists else "",
        "revisions": 0,  # the quality loop is bounded PER RUN, not per thread
        "phase": "thinking",
    }


RESPOND_SYSTEM = """You are SiteForge, a friendly copilot that builds business
websites. Write your next message to the owner as PLAIN PROSE (no JSON, no markdown
headers). If the brief is incomplete: warmly ask for at most TWO of the missing
fields. If the brief is complete and no site exists yet: one-sentence summary of
what you'll build, ending exactly with: "Building your draft now…".
If a site exists and the owner asked for a change: confirm the specific change in
one sentence, ending exactly with: "Updating your site now…". Never re-describe
the whole site for a small change."""


def respond(state: AgentState) -> dict:
    missing = [f for f in REQUIRED_BRIEF_FIELDS if not state.get("brief", {}).get(f)]
    model = chat_model(INTERVIEW_MODEL, temperature=0.6)
    result = model.invoke(
        [SystemMessage(RESPOND_SYSTEM)]
        + state["messages"]
        + [SystemMessage(
            f"Brief so far: {state['brief']}\n"
            f"Missing fields: {missing or 'none'}\n"
            f"Brief complete: {state['brief_complete']}\n"
            f"Site exists: {bool(state.get('pages'))}\n"
            f"Requested change type: {state.get('edit_target', 'none')}"
        )]
    )
    return {"messages": [AIMessage(result.content)], "phase": "interviewing"}


PLAN_SYSTEM = """You are an award-winning design director planning a small-business
website. This is a PERSUADE surface: its job is a visitor's decision (call, visit,
order, book) — every page must build the case or lower the barrier.

Design discipline:
- Ground every choice in THIS business's world — its materials, light, and
  vernacular. A tattoo studio and a bakery must not feel like siblings.
- Avoid the AI-default looks (cream+serif+terracotta; black+acid-green;
  broadsheet hairlines) unless the brand truly demands one.
- Derive the palette as a SYSTEM with jobs (background, surface, ink, accent),
  honest contrast, from the subject's real world. Use retrieved theme seeds as
  inspiration, never verbatim.
- Choose one place to be bold; keep everything else quiet.
- The owner's stated tone always wins over your taste.

Respond with ONLY JSON:
{"site_name": str,
 "theme": {
   "mood": str,
   "primary_color": "#RRGGBB accent chosen from THIS brand's world — never a
    generic default blue, never the AI-default cream/terracotta or
    black/acid-green combos unless the brand truly demands them",
   "palette": {
     "background": "#RRGGBB page background — usually near-white, tinted
      toward the brand's world (warm for food, cool for wellness)",
     "surface": "#RRGGBB cards/header tint, a step off the background",
     "ink": "#RRGGBB text color — near-black, tinted to match"
   },
   "radius": "corner rounding in px as a number: 0 (sharp, editorial) to
    18 (soft, friendly) — pick to match the brand personality",
   "layout": "pick the ONE that fits the brand personality:
     classic — trustworthy, established (framed hero image, generous sections);
     split   — editorial, boutique (image beside the opening text, magazine feel);
     minimal — premium, calm (narrow measure, airy space, understated image);
     bold    — loud, young, energetic (full-bleed hero, oversized headline)",
   "fonts": {
     "heading": "pick ONE that fits the brand: Playfair Display | DM Serif Display |
      Lora | Sora | Space Grotesk | Poppins | Montserrat | Cormorant Garamond",
     "body": "pick ONE: Inter | Source Sans 3 | Nunito Sans | IBM Plex Sans | Karla"
   }
 },
 "pages": [{"path": "/", "title": str, "purpose": str, "sections": [str, ...]}, ...]}
3 to 5 pages. Always include "/" (home) and a contact page."""


def plan(state: AgentState) -> dict:
    model = chat_model(INTERVIEW_MODEL, temperature=0.5)
    # the planner designs WITH the design-craft knowledge, not from vibes
    craft = _retrieve_guidelines(state["brief"], topic="design")
    messages = [SystemMessage(PLAN_SYSTEM)]
    if craft:
        messages.append(SystemMessage(f"Design craft to apply:\n{craft}"))
    messages.append(SystemMessage(f"Brief: {state['brief']}"))
    if state.get("edit_target") == "design" and state.get("edit_request"):
        import json as _json

        messages.append(SystemMessage(
            "CURRENT spec — change ONLY what the owner asked, keep everything "
            f"else identical:\n{_json.dumps(state.get('spec', {}))}\n"
            f"Owner's request: {state['edit_request']}"
        ))
    try:
        result = model.invoke(messages)
        spec = extract_json(result.content)
    except ValueError as err:
        # one retry with the parse error in view, then a minimal valid spec —
        # a malformed plan must never kill the whole run
        try:
            retry = model.invoke(messages + [SystemMessage(
                f"Your previous reply was not valid JSON ({err}). Reply with ONLY the JSON object."
            )])
            spec = extract_json(retry.content)
        except ValueError:
            name = state["brief"].get("business_name", "Your Business")
            spec = {
                "site_name": name,
                "theme": {"mood": state["brief"].get("tone", ""), "primary_color": "#2f4f4f"},
                "pages": [
                    {"path": "/", "title": "Home", "purpose": "introduce the business", "sections": ["hero", "offerings", "why us"]},
                    {"path": "/contact", "title": "Contact", "purpose": "get in touch", "sections": ["details", "hours"]},
                ],
            }
    spec = _validate_spec(spec, state["brief"])
    # contact details ride on the spec deterministically — the renderer
    # turns them into a working form and tappable actions
    spec["contact"] = {
        k: state["brief"].get(k, "") for k in ("phone", "email", "location")
    }
    return {"spec": spec, "phase": "planning"}


def illustrate(state: AgentState) -> dict:
    """Deterministic node — no LLM. Every page gets a real photo matched to
    the business and the page's purpose. On an image-edit request, the
    owner's own words steer the search and force fresh picks."""
    from images import find_image

    spec = dict(state["spec"])
    business = state["brief"].get("business_type", "business")
    editing = state.get("edit_target") == "images"
    hint = state.get("edit_request", "") if editing else ""
    pages = []
    for page in spec.get("pages", []):
        p = dict(page)
        img = find_image(
            f"{business} {p.get('purpose') or p.get('title', '')} {hint}".strip(),
            avoid_url=(p.get("image") or {}).get("url") if editing else None,
        )
        if img:
            p["image"] = img
        pages.append(p)
    spec["pages"] = pages
    return {"spec": spec, "phase": "illustrating"}


WRITE_SYSTEM = """You are a conversion copywriter for small-business websites. The
page you write is a PERSUADE surface — every section either builds the case or
lowers the barrier to action. Copy is design material: active voice, the
customer's vocabulary, specificity over adjectives (a verifiable detail beats
"high quality" every time). The headline must pass the "so what" test in three
seconds and could belong to no other business.

Write the FINAL copy for ONE page as clean Markdown that renders directly as
the website:

- Start with # (the page's hero headline), then one bold tagline line.
- Then ## sections with real content: short paragraphs, bullet lists where natural.
- Calls to action are markdown links that render as buttons. They must point
  ONLY at pages that exist in this site's plan, using the exact path —
  e.g. [Book a Class](/contact) or [See the Menu](/menu). NEVER link to
  #anchors, external URLs, or pages that don't exist. Never invent forms.
- The contact page must be genuinely usable: if a phone number is in the brief,
  include it as a tappable link like [Call us: +91 98xxx](tel:+9198xxx) and a
  WhatsApp link [Message on WhatsApp](https://wa.me/9198xxx); if an email is
  known, include [Email us](mailto:...). State expected response time.
- NO placeholder notes, NO "(Visual: ...)" or photo descriptions, NO commentary
  about the page — output only what a visitor would read.
Be specific to this business — never generic filler. Match the requested tone."""


def _retrieve_guidelines(brief: dict, topic: str = "copy", page: dict | None = None) -> str:
    """Pull proven craft from the RAG service — grounding the planner and
    writer in knowledge instead of vibes. Queries are phrased as natural
    questions (bge retrieves questions better than keyword soup) and are
    PER PAGE for copy, so contact-page wisdom reaches contact pages.
    Absent service = no guidelines, never a failed generation."""
    import os

    import requests

    url = os.environ.get("RAG_URL", "http://localhost:8002")
    biz = brief.get("business_type", "business")
    tone = brief.get("tone", "")
    if topic == "design":
        query = (
            f"How should a {tone} website for a {biz} serving "
            f"{brief.get('target_customers', 'customers')} choose its palette, "
            "typography, layout and signature element?"
        )
    elif page:
        query = (
            f"How should the {page.get('title', '')} page of a {tone} {biz} "
            f"website be structured and written? Purpose: {page.get('purpose', '')}. "
            f"Offerings: {brief.get('offerings', '')}."
        )
    else:
        query = (
            f"How should a {tone} website for a {biz} selling "
            f"{brief.get('offerings', '')} write its headlines and pages?"
        )
    # flavoured retrieval: the query's topic scopes which knowledge answers.
    # design questions consult design craft + theme seeds; copy questions
    # consult writing craft AND proven platinum examples
    payload = {"query": query, "k": 4 if topic == "design" else 3}
    payload["topics"] = ["design"] if topic == "design" else ["copy", "platinum"]
    try:
        r = requests.post(f"{url}/rag/search", json=payload, timeout=6)
        r.raise_for_status()
        return "\n\n".join(c["content"] for c in r.json()["results"])
    except Exception:
        return ""


def write(state: AgentState) -> dict:
    model = chat_model(WRITER_MODEL, temperature=0.8)
    feedback = state.get("critique", {}).get("feedback", "")
    pages = {}
    for page in state["spec"]["pages"]:
        site_map = ", ".join(
            f"{p['path']} ({p['title']})" for p in state["spec"]["pages"]
        )
        prompt = (
            f"Site: {state['spec'].get('site_name', '')} — mood: "
            f"{state['spec'].get('theme', {}).get('mood', '')}\n"
            f"Site pages (the ONLY valid link targets): {site_map}\n"
            f"Business brief: {state['brief']}\n"
            f"Page: {page['title']} ({page['path']}) — {page['purpose']}\n"
            f"Sections: {page['sections']}"
        )
        if feedback:
            prompt += f"\nA reviewer said: {feedback}\nFix those issues this time."
        if state.get("edit_target") == "copy" and state.get("edit_request") and state.get("revisions", 0) == 0:
            prompt += (
                f"\nEXISTING page copy:\n{state.get('pages', {}).get(page['path'], '')}\n"
                f"The owner asked: {state['edit_request']}\n"
                "Apply that change and keep everything else as close as possible."
            )
        # per-page retrieval: the contact page gets contact-page craft,
        # the menu page gets menu craft — not one generic blend
        guidelines = _retrieve_guidelines(state["brief"], topic="copy", page=page)
        system = WRITE_SYSTEM
        if guidelines:
            system += f"\n\nProven guidelines from our knowledge base — apply them:\n{guidelines}"
        result = model.invoke([SystemMessage(system), ("user", prompt)])
        pages[page["path"]] = result.content
    return {"pages": pages, "phase": "writing"}


def _validate_spec(spec: dict, brief: dict) -> dict:
    """Deterministic guard: whatever the model returned becomes a valid,
    renderable spec. Code checks what code can check."""
    import re as _re

    spec.setdefault("site_name", brief.get("business_name", "Your Business"))
    theme = spec.setdefault("theme", {})
    if not _re.fullmatch(r"#[0-9a-fA-F]{6}", str(theme.get("primary_color", ""))):
        theme["primary_color"] = "#2f4f4f"
    try:
        theme["radius"] = max(0, min(18, int(theme.get("radius", 8))))
    except (TypeError, ValueError):
        theme["radius"] = 8
    if theme.get("layout") not in ("classic", "split", "minimal", "bold"):
        theme["layout"] = "classic"
    pages = [p for p in spec.get("pages", []) if isinstance(p, dict) and p.get("path")]
    for p in pages:
        p["path"] = "/" + p["path"].strip("/") if p["path"] != "/" else "/"
        p.setdefault("title", p["path"].strip("/").title() or "Home")
        p.setdefault("purpose", "")
        p.setdefault("sections", [])
    paths = {p["path"] for p in pages}
    if "/" not in paths:
        pages.insert(0, {"path": "/", "title": "Home", "purpose": "introduce the business", "sections": []})
    if "/contact" not in paths:
        pages.append({"path": "/contact", "title": "Contact", "purpose": "get in touch", "sections": []})
    spec["pages"] = pages[:6]
    return spec


def write_page(payload: dict) -> dict:
    """ONE page, written in its own parallel branch (Send API). The payload
    carries everything: page, brief, site voice, valid link targets, and —
    on revision passes — this page's own feedback only."""
    model = chat_model(WRITER_MODEL, temperature=0.8)
    page, brief, spec = payload["page"], payload["brief"], payload["spec"]
    guidelines = _retrieve_guidelines(brief, topic="copy", page=page)
    site_map = ", ".join(f"{p['path']} ({p['title']})" for p in spec["pages"])
    prompt = (
        f"Site: {spec.get('site_name', '')} — mood: {spec.get('theme', {}).get('mood', '')}\n"
        f"Site pages (the ONLY valid link targets): {site_map}\n"
        f"Business brief: {brief}\n"
        f"Page: {page['title']} ({page['path']}) — {page.get('purpose', '')}\n"
        f"Sections: {page.get('sections', [])}"
    )
    if payload.get("feedback"):
        prompt += f"\nA reviewer said about THIS page: {payload['feedback']}\nFix those issues."
    if payload.get("existing"):
        prompt += (
            f"\nEXISTING page copy:\n{payload['existing']}\n"
            f"The owner asked: {payload.get('edit_request', '')}\n"
            "Apply that change and keep everything else as close as possible."
        )
    system = WRITE_SYSTEM
    if guidelines:
        system += f"\n\nProven guidelines from our knowledge base — apply them:\n{guidelines}"
    result = model.invoke([SystemMessage(system), ("user", prompt)])
    return {"pages": {page["path"]: result.content}, "phase": "writing"}


CRITIQUE_SYSTEM = """You are a strict reviewer of small-business website copy.
Anchor: 7 means shippable — specific to this business, correct tone, no generic
filler; below 7 means blocking issues exist. Review EVERY page separately.
Respond with ONLY JSON:
{"score": <overall 1-10>,
 "pages": {"<path>": "OK" or "concrete fixes for this page only", ...}}"""


def critique(state: AgentState) -> dict:
    model = chat_model(INTERVIEW_MODEL, temperature=0.2)
    result = model.invoke(
        [
            SystemMessage(CRITIQUE_SYSTEM),
            ("user", f"Brief: {state['brief']}\n\nDraft pages: {state['pages']}"),
        ]
    )
    try:
        verdict = extract_json(result.content)
        if not isinstance(verdict.get("pages"), dict):
            verdict["pages"] = {}
    except ValueError:
        verdict = {"score": 7, "pages": {}}  # unparseable critic never blocks delivery
    return {"critique": verdict, "revisions": state.get("revisions", 0) + 1, "phase": "critiquing"}


def deliver(state: AgentState) -> dict:
    spec, pages = state["spec"], state["pages"]
    if state.get("edit_target") and state.get("edit_target") != "none":
        summary = f"Done — I've updated the {state['edit_target']} on **{spec.get('site_name', 'your site')}**. Take a look!"
    else:
        summary = (
            f"Your draft for **{spec.get('site_name', 'your site')}** is ready — "
            f"{len(pages)} pages: {', '.join(pages)}. "
            f"Reviewer score: {state['critique'].get('score', '?')}/10."
        )
    return {"messages": [AIMessage(summary)], "phase": "done", "edit_target": "none"}
