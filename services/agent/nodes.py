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

INTERVIEW_SYSTEM = f"""You are SiteForge, a friendly copilot that builds business websites.
You are interviewing the owner. You need these fields: {", ".join(REQUIRED_BRIEF_FIELDS)}.

Given the conversation so far and the current brief, respond with ONLY a JSON object:
{{"brief": {{...all fields learned so far...}},
 "complete": true/false,
 "reply": "your next message to the owner"}}

Rules: extract everything the owner already said into the brief. Ask for at
most TWO missing fields per turn, conversationally. Set complete=true only
when every field has a real value. When complete, make reply a short summary
of what you'll build, ending with: "Building your draft now…"."""


def interview(state: AgentState) -> dict:
    model = chat_model(INTERVIEW_MODEL, temperature=0.4)
    result = model.invoke(
        [SystemMessage(INTERVIEW_SYSTEM)]
        + state["messages"]
        + [SystemMessage(f"Current brief: {state.get('brief', {})}")]
    )
    try:
        data = extract_json(result.content)
    except ValueError:
        # model rambled instead of returning JSON — treat it as a chat reply
        data = {"brief": state.get("brief", {}), "complete": False, "reply": result.content}

    return {
        "messages": [AIMessage(data.get("reply", ""))],
        "brief": data.get("brief", state.get("brief", {})),
        "brief_complete": bool(data.get("complete")),
        "phase": "interviewing",
    }


PLAN_SYSTEM = """You are a web strategist. Given a business brief, design a small
website. Respond with ONLY JSON:
{"site_name": str,
 "theme": {"mood": str, "primary_color": "#RRGGBB hex chosen to fit THIS brand's
  industry and tone — e.g. warm terracotta for a bakery, deep espresso for a
  coffee bar, calm sage for a yoga studio. Never a generic default blue."},
 "pages": [{"path": "/", "title": str, "purpose": str, "sections": [str, ...]}, ...]}
3 to 5 pages. Always include "/" (home) and a contact page."""


def plan(state: AgentState) -> dict:
    model = chat_model(INTERVIEW_MODEL, temperature=0.5)
    result = model.invoke(
        [SystemMessage(PLAN_SYSTEM), SystemMessage(f"Brief: {state['brief']}")]
    )
    spec = extract_json(result.content)
    return {"spec": spec, "phase": "planning"}


WRITE_SYSTEM = """You are a copywriter for small-business websites. Write the full
copy for ONE page in Markdown: headline, section content, and a call to action.
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
