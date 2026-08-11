"""Activities — the non-deterministic work Temporal retries for us.

They reuse the agent's own modules (graph nodes, renderer, publisher), so
generation logic has exactly one implementation. PYTHONPATH gains the agent
directory; the proper long-term home is packages/py-shared.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import psycopg
from temporalio import activity


@activity.defn
def generate_draft(thread_id: str) -> dict:
    """Re-runs the generation half of the graph (plan → illustrate → write
    → review) for an interviewed thread, heartbeating between stages so
    Temporal can detect a dead worker mid-generation."""
    from langgraph.checkpoint.postgres import PostgresSaver

    from config import DATABASE_URL
    from graph import build_graph
    from nodes import critique, illustrate, plan, write

    with PostgresSaver.from_conn_string(DATABASE_URL) as saver:
        graph = build_graph(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        state = dict(graph.get_state(config).values)
        if not state.get("brief_complete"):
            raise ValueError("brief incomplete — interview first")

        for stage, node in (("plan", plan), ("illustrate", illustrate), ("write", write), ("review", critique)):
            activity.heartbeat(stage)
            state.update(node(state))

        graph.update_state(
            config,
            {
                "spec": state["spec"],
                "pages": state["pages"],
                "critique": state["critique"],
                "revisions": state.get("revisions", 0),
                "phase": "done",
            },
        )
    return {"pages": list(state["pages"]), "score": state["critique"].get("score")}


@activity.defn
def run_evaluation() -> dict:
    """Triggers the eval service — checks + judge + medallion + platinum."""
    import requests

    eval_url = os.environ.get("EVAL_URL", "http://localhost:8004")
    r = requests.post(f"{eval_url}/eval/run", timeout=600)
    r.raise_for_status()
    return r.json()


@activity.defn
def publish_draft(thread_id: str) -> str:
    """Renders and releases the site — same code path as the Publish button."""
    from langgraph.checkpoint.postgres import PostgresSaver

    from config import DATABASE_URL
    from graph import build_graph
    from publish import publish_site

    with PostgresSaver.from_conn_string(DATABASE_URL) as saver:
        graph = build_graph(checkpointer=saver)
        state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    pages = state.get("pages", {})
    if not pages:
        raise ValueError("nothing to publish")

    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT published_site_id FROM chats WHERE thread_id=%s", (thread_id,)
        ).fetchone()
    # same decoration as the Publish button: booking form key, logo, endpoint
    from publish import decorate_spec, logo_path, logo_row

    spec = decorate_spec(state.get("spec", {}), thread_id, live=True)
    logo = logo_row(thread_id)
    extra = {logo_path(logo[0]): bytes(logo[1])} if logo else None
    site_id, url = publish_site(spec, pages, row[0] if row else None, extra_files=extra)
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET published_site_id=%s, published_url=%s WHERE thread_id=%s",
            (site_id, url, thread_id),
        )
        conn.commit()
    return url
