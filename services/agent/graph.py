"""The graph — the agent's control flow, drawn in code.

    START → interview ──(brief incomplete)──→ END   (wait for user's next turn)
                │
         (brief complete)
                ↓
              plan → write → critique ──(score < 7, first try)──→ write (revise)
                                │
                          (good enough)
                                ↓
                             deliver → END

Two ideas to notice:
1. The interview LOOP is not a loop here — each user turn is one graph run
   that ends after `interview`. The Postgres checkpointer preserves state
   between runs, so the conversation continues where it left off. Durable
   multi-turn chat without a single long-lived process.
2. The revise cycle is bounded IN THE GRAPH (revisions < 2), not by trusting
   the model to stop. Determinism lives in the edges, creativity in the nodes.
"""

from langgraph.graph import END, START, StateGraph

from nodes import critique, deliver, plan, respond, understand, write
from state import AgentState


def after_respond(state: AgentState) -> str:
    return "plan" if state["brief_complete"] else END


def after_critique(state: AgentState) -> str:
    if state["critique"].get("score", 10) < 7 and state["revisions"] < 2:
        return "write"
    return "deliver"


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    g.add_node("understand", understand)
    g.add_node("respond", respond)
    g.add_node("plan", plan)
    g.add_node("write", write)
    # node named "review" (not "critique") — LangGraph forbids a node name
    # that shadows a state key
    g.add_node("review", critique)
    g.add_node("deliver", deliver)

    g.add_edge(START, "understand")
    g.add_edge("understand", "respond")
    g.add_conditional_edges("respond", after_respond, {"plan": "plan", END: END})
    g.add_edge("plan", "write")
    g.add_edge("write", "review")
    g.add_conditional_edges("review", after_critique, {"write": "write", "deliver": "deliver"})
    g.add_edge("deliver", END)

    return g.compile(checkpointer=checkpointer)
