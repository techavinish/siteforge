"""Agent service — HTTP surface over the graph.

POST /agent/chat {"thread_id": "...", "message": "..."}
Streams Server-Sent Events: one `node` event per graph step (so the UI can
show live progress: interviewing → planning → writing…), then `done` with
the final state snapshot.

The thread_id maps to the checkpointer's conversation: same id = same
resumed conversation, from any client, after any restart.
"""

import json
import uuid

import psycopg
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

# conversation index — the checkpointer stores state PER thread but can't
# answer "which threads belong to this user", so we keep our own registry
with psycopg.connect(DATABASE_URL) as _conn:
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            thread_id  text PRIMARY KEY,
            uid        text NOT NULL,
            title      text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )""")
    _conn.execute("CREATE INDEX IF NOT EXISTS ix_chats_uid ON chats (uid, updated_at DESC)")
    _conn.commit()


class ChatIn(BaseModel):
    thread_id: str
    message: str


class NewChatIn(BaseModel):
    uid: str


@app.post("/agent/chats")
def create_chat(body: NewChatIn):
    thread_id = f"c-{uuid.uuid4().hex[:12]}"
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("INSERT INTO chats (thread_id, uid) VALUES (%s, %s)", (thread_id, body.uid))
        conn.commit()
    return {"thread_id": thread_id}


@app.get("/agent/chats")
def list_chats(uid: str):
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT thread_id, title, updated_at FROM chats WHERE uid=%s ORDER BY updated_at DESC",
            (uid,),
        ).fetchall()
    return [{"thread_id": r[0], "title": r[1] or "New chat", "updated_at": r[2].isoformat()} for r in rows]


class RenameIn(BaseModel):
    title: str


@app.patch("/agent/chats/{thread_id}")
def rename_chat(thread_id: str, body: RenameIn):
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET title=%s WHERE thread_id=%s",
            (body.title.strip()[:60] or "Untitled", thread_id),
        )
        conn.commit()
    return {"ok": True}


@app.delete("/agent/chats/{thread_id}")
def delete_chat(thread_id: str):
    """Remove the chat and its checkpointed state."""
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    with conn:
        conn.execute("DELETE FROM chats WHERE thread_id=%s", (thread_id,))
        # langgraph's saver tables — autocommit so a missing table can't
        # poison the transaction across saver versions
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE thread_id=%s", (thread_id,))
            except psycopg.Error:
                pass
    return {"ok": True}


def _ensure_title(thread_id: str, first_message: str) -> None:
    """Name the chat like ChatGPT does — a short LLM-written title.

    Runs AFTER the response streams, so it never delays the reply.
    Falls back to truncation if the model call fails.
    """
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT title FROM chats WHERE thread_id=%s", (thread_id,)).fetchone()
    if not row or row[0]:
        return
    try:
        from config import INTERVIEW_MODEL
        from llm import chat_model

        r = chat_model(INTERVIEW_MODEL, temperature=0.2).invoke([
            ("system", "Write a 2-5 word title for a conversation that starts with the user message. Reply with ONLY the title. No quotes, no punctuation at the end."),
            ("user", first_message),
        ])
        title = r.content.strip().strip('"').strip() or first_message
    except Exception:
        title = first_message
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("UPDATE chats SET title=%s WHERE thread_id=%s", (title[:60], thread_id))
        conn.commit()


@app.get("/agent/chats/{thread_id}/messages")
def chat_messages(thread_id: str):
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    out = []
    for m in state.get("messages", []):
        role = "user" if m.type == "human" else "agent"
        if m.content:
            out.append({"role": role, "text": m.content})
    return out


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

    # bump recency; the title is LLM-generated after the reply streams
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET updated_at = now() WHERE thread_id = %s",
            (body.thread_id,),
        )
        conn.commit()

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

        _ensure_title(body.thread_id, body.message)

    return StreamingResponse(events(), media_type="text/event-stream")
