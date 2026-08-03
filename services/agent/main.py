"""Agent service — HTTP surface over the graph.

POST /agent/chat {"thread_id": "...", "message": "..."}
Streams Server-Sent Events: one `node` event per graph step (so the UI can
show live progress: interviewing → planning → writing…), then `done` with
the final state snapshot.

The thread_id maps to the checkpointer's conversation: same id = same
resumed conversation, from any client, after any restart.
"""

import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel

from config import DATABASE_URL
from graph import build_graph

app = FastAPI(title="siteforge-agent")

# One pool for the process; .setup() creates the checkpoint tables on first run.
saver_cm = PostgresSaver.from_conn_string(DATABASE_URL)
saver = saver_cm.__enter__()
saver.setup()
graph = build_graph(checkpointer=saver)


class ChatIn(BaseModel):
    thread_id: str
    message: str


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/agent/draft/{thread_id}")
def draft(thread_id: str):
    """Full draft for a conversation — spec, brief, and every page's copy."""
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    return {
        "phase": state.get("phase"),
        "brief": state.get("brief", {}),
        "spec": state.get("spec", {}),
        "pages": state.get("pages", {}),
        "score": state.get("critique", {}).get("score"),
    }


@app.post("/agent/chat")
def chat(body: ChatIn):
    config = {"configurable": {"thread_id": body.thread_id}}

    def events():
        for update in graph.stream(
            {"messages": [("user", body.message)]}, config, stream_mode="updates"
        ):
            for node_name, node_update in update.items():
                payload = {"node": node_name, "phase": node_update.get("phase")}
                # surface user-facing text as it's produced
                for m in node_update.get("messages", []):
                    payload["reply"] = m.content
                yield f"event: node\ndata: {json.dumps(payload)}\n\n"

        final = graph.get_state(config).values
        snapshot = {
            "phase": final.get("phase"),
            "brief": final.get("brief", {}),
            "spec": final.get("spec", {}),
            "pages": list(final.get("pages", {})),
            "score": final.get("critique", {}).get("score"),
        }
        yield f"event: done\ndata: {json.dumps(snapshot)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
