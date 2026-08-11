"""The graph — the agent's control flow, drawn in code.

    START → understand → respond ──(incomplete)──→ END  (await next turn)
                            │
                     (complete / edit)
                            ↓
              plan → illustrate ──┬─ Send(write_page /)        ─┐
                                  ├─ Send(write_page /menu)     ├→ review
                                  └─ Send(write_page /contact) ─┘    │
                        (failing pages only, ≤1 revision) ←──────────┤
                                  deliver ←──────────(shippable)─────┘

Pages are written in PARALLEL branches (Send API) — a 4-page site costs
one page's latency, not four. Revisions re-write only the pages the
critic flagged. Determinism lives in the edges, creativity in the nodes.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nodes import critique, deliver, illustrate, plan, respond, understand, write_page
from state import AgentState


def _page_sends(state: AgentState, only_paths: set[str] | None = None,
                feedback: dict | None = None) -> list[Send]:
    """One Send per page — the payload is the branch's entire world."""
    sends = []
    for page in state["spec"]["pages"]:
        path = page["path"]
        if only_paths is not None and path not in only_paths:
            continue
        is_first_pass = state.get("revisions", 0) == 0
        sends.append(Send("write_page", {
            "page": page,
            "brief": state["brief"],
            "spec": {"site_name": state["spec"].get("site_name"),
                     "theme": {"mood": state["spec"].get("theme", {}).get("mood", "")},
                     "contact": state["spec"].get("contact", {}),
                     "pages": state["spec"]["pages"]},
            "feedback": (feedback or {}).get(path, ""),
            "existing": state.get("pages", {}).get(path, "")
            if is_first_pass and state.get("edit_target") == "copy" else "",
            "edit_request": state.get("edit_request", ""),
        }))
    return sends


def after_respond(state: AgentState):
    if not state["brief_complete"]:
        return END
    if not state.get("pages"):
        return "plan"  # first build: the full pipeline
    # site exists — run ONLY what the edit needs
    target = state.get("edit_target", "none")
    if target == "images":
        return "illustrate"
    if target == "copy":
        return _page_sends(state)
    if target == "design":
        return "plan"
    return END


def after_illustrate(state: AgentState):
    # image-only edit skips rewriting and review — straight to delivery
    if state.get("edit_target") == "images":
        return "deliver"
    return _page_sends(state)


def after_review(state: AgentState):
    """Revise ONLY the pages the critic flagged, at most one extra pass."""
    verdict = state.get("critique", {})
    failing = {
        path for path, note in (verdict.get("pages") or {}).items()
        if isinstance(note, str) and note.strip().upper() != "OK"
        and path in {p["path"] for p in state["spec"]["pages"]}
    }
    if verdict.get("score", 10) < 7 and state.get("revisions", 0) < 2 and failing:
        return _page_sends(state, only_paths=failing, feedback=verdict.get("pages"))
    return "deliver"


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    g.add_node("understand", understand)
    g.add_node("respond", respond)
    g.add_node("plan", plan)
    g.add_node("illustrate", illustrate)
    g.add_node("write_page", write_page)
    # node named "review" (not "critique") — LangGraph forbids a node name
    # that shadows a state key
    g.add_node("review", critique)
    g.add_node("deliver", deliver)

    g.add_edge(START, "understand")
    g.add_edge("understand", "respond")
    g.add_conditional_edges(
        "respond", after_respond,
        ["plan", "illustrate", "write_page", END],
    )
    g.add_edge("plan", "illustrate")
    g.add_conditional_edges(
        "illustrate", after_illustrate, ["deliver", "write_page"]
    )
    g.add_edge("write_page", "review")  # fan-in: review waits for ALL branches
    g.add_conditional_edges("review", after_review, ["write_page", "deliver"])
    g.add_edge("deliver", END)

    return g.compile(checkpointer=checkpointer)
