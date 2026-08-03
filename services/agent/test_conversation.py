"""Scripted end-to-end conversation — the Phase 4 acceptance test.

Drives the graph directly (no HTTP) through a multi-turn interview and
prints what happens at each stage. Each turn is a SEPARATE graph run
resumed from the Postgres checkpoint — proving conversations survive
process boundaries.
"""

import uuid

from langgraph.checkpoint.postgres import PostgresSaver

from config import DATABASE_URL
from graph import build_graph

TURNS = [
    "Hi! I want a website for my bakery.",
    "It's called Sweet Rani Bakery, we're in Jaipur. We sell cakes, "
    "pastries, cookies and we specialise in custom wedding cakes.",
    "Our customers are local families and wedding planners. "
    "I'd like the tone to be warm and friendly.",
]

thread_id = f"bakery-demo-{uuid.uuid4().hex[:6]}"
print(f"thread: {thread_id}\n")

with PostgresSaver.from_conn_string(DATABASE_URL) as saver:
    saver.setup()

    for i, turn in enumerate(TURNS, 1):
        # a FRESH graph object per turn — state comes from postgres, not RAM
        graph = build_graph(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}

        print(f"--- turn {i} ---")
        print(f"owner: {turn}")
        for update in graph.stream({"messages": [("user", turn)]}, config, stream_mode="updates"):
            for node, out in update.items():
                for m in out.get("messages", []):
                    print(f"agent [{node}]: {m.content[:400]}")
                if node in ("plan", "write", "critique") and not out.get("messages"):
                    print(f"       [{node}] done")
        print()

    final = graph.get_state(config).values
    print("=== FINAL STATE ===")
    print("phase:    ", final.get("phase"))
    print("brief:    ", final.get("brief"))
    spec = final.get("spec", {})
    print("site:     ", spec.get("site_name"))
    print("pages:    ", [p["path"] for p in spec.get("pages", [])])
    print("score:    ", final.get("critique", {}).get("score"), "/10")
    home = final.get("pages", {}).get("/", "")
    print("\n--- homepage copy (first 500 chars) ---")
    print(home[:500])
