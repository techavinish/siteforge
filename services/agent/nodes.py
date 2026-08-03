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

# The interview is SPLIT into two nodes so the user-visible half can stream:
#   understand — silent JSON extraction (the "thinking" step; unstreamable)
#   respond    — pure prose written for the owner (streamed token-by-token)
# Structured output and streamable output never mix well in one call.

UNDERSTAND_SYSTEM = f"""You extract structured facts from a conversation between
a website copilot and a business owner. Fields: {", ".join(REQUIRED_BRIEF_FIELDS)}.

Respond with ONLY JSON: {{"brief": {{...every field learned so far...}},
"complete": true/false}}. complete=true only when every field has a real value."""


def understand(state: AgentState) -> dict:
    model = chat_model(INTERVIEW_MODEL, temperature=0.1)
    result = model.invoke(
        [SystemMessage(UNDERSTAND_SYSTEM)]
        + state["messages"]
        + [SystemMessage(f"Previously known brief: {state.get('brief', {})}")]
    )
    try:
        data = extract_json(result.content)
    except ValueError:
        data = {"brief": state.get("brief", {}), "complete": False}
    return {
        "brief": data.get("brief", state.get("brief", {})),
        "brief_complete": bool(data.get("complete")),
        "phase": "thinking",
    }


RESPOND_SYSTEM = """You are SiteForge, a friendly copilot that builds business
websites. Write your next message to the owner as PLAIN PROSE (no JSON, no markdown
headers). If the brief is incomplete: warmly ask for at most TWO of the missing
fields. If complete: give a one-sentence summary of the site you'll build and end
with exactly: "Building your draft now…"."""


def respond(state: AgentState) -> dict:
    missing = [f for f in REQUIRED_BRIEF_FIELDS if not state.get("brief", {}).get(f)]
    model = chat_model(INTERVIEW_MODEL, temperature=0.6)
    result = model.invoke(
        [SystemMessage(RESPOND_SYSTEM)]
        + state["messages"]
        + [SystemMessage(
            f"Brief so far: {state['brief']}\n"
            f"Missing fields: {missing or 'none'}\n"
            f"Brief complete: {state['brief_complete']}"
        )]
    )
    return {"messages": [AIMessage(result.content)], "phase": "interviewing"}


PLAN_SYSTEM = """You are a web strategist. Given a business brief, design a small
website. Respond with ONLY JSON:
{"site_name": str,
 "theme": {
   "mood": str,
   "primary_color": "#RRGGBB hex chosen to fit THIS brand's industry and tone —
    e.g. warm terracotta for a bakery, deep espresso for a coffee bar, calm sage
    for a yoga studio. Never a generic default blue.",
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
    result = model.invoke(
        [SystemMessage(PLAN_SYSTEM), SystemMessage(f"Brief: {state['brief']}")]
    )
    spec = extract_json(result.content)
    return {"spec": spec, "phase": "planning"}


WRITE_SYSTEM = """You are a copywriter for small-business websites. Write the FINAL
copy for ONE page as clean Markdown that renders directly as the website:

- Start with # (the page's hero headline), then one bold tagline line.
- Then ## sections with real content: short paragraphs, bullet lists where natural.
- Calls to action are markdown links like [Order Now](#contact) — they render
  as buttons.
- NO placeholder notes, NO "(Visual: ...)" or photo descriptions, NO commentary
  about the page — output only what a visitor would read.
Be specific to this business — never generic filler. Match the requested tone."""


def write(state: AgentState) -> dict:
    model = chat_model(WRITER_MODEL, temperature=0.8)
    feedback = state.get("critique", {}).get("feedback", "")
    pages = {}
    for page in state["spec"]["pages"]:
        prompt = (
            f"Business brief: {state['brief']}\n"
            f"Page: {page['title']} ({page['path']}) — {page['purpose']}\n"
            f"Sections: {page['sections']}"
        )
        if feedback:
            prompt += f"\nA reviewer said: {feedback}\nFix those issues this time."
        result = model.invoke([SystemMessage(WRITE_SYSTEM), ("user", prompt)])
        pages[page["path"]] = result.content
    return {"pages": pages, "phase": "writing"}


CRITIQUE_SYSTEM = """You are a strict reviewer of small-business website copy.
Score the draft 1-10 for: specificity to THIS business, clarity, and tone match.
Respond with ONLY JSON: {"score": int, "feedback": "one paragraph of concrete fixes"}"""


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
    except ValueError:
        verdict = {"score": 7, "feedback": ""}  # unparseable critic never blocks delivery
    return {"critique": verdict, "revisions": state.get("revisions", 0) + 1, "phase": "critiquing"}


def deliver(state: AgentState) -> dict:
    spec, pages = state["spec"], state["pages"]
    summary = (
        f"Your draft for **{spec.get('site_name', 'your site')}** is ready — "
        f"{len(pages)} pages: {', '.join(pages)}. "
        f"Reviewer score: {state['critique'].get('score', '?')}/10."
    )
    return {"messages": [AIMessage(summary)], "phase": "done"}
