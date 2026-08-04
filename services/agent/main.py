"""Agent service — HTTP surface over the graph.

POST /agent/chat {"thread_id": "...", "message": "..."}
Streams Server-Sent Events: one `node` event per graph step (so the UI can
show live progress: interviewing → planning → writing…), then `done` with
the final state snapshot.

The thread_id maps to the checkpointer's conversation: same id = same
resumed conversation, from any client, after any restart.
"""

import json
import os
import uuid

import psycopg

# errors from every request land in sentry (no-op without the DSN)
if os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1)
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel

from config import DATABASE_URL, GCP_PROJECT
from graph import build_graph
from publish import publish_site
from render import build_site_html

_token_adapter = google_requests.Request()


def current_uid(request: Request) -> str:
    """Verify the Firebase ID token — header for API calls, ?token= for
    resources loaded by the browser itself (the preview iframe can't set
    headers). The client is never trusted with a bare uid."""
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing credentials")
    try:
        claims = google_id_token.verify_firebase_token(
            token, _token_adapter, audience=GCP_PROJECT
        )
        return claims["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def own_thread(thread_id: str, uid: str) -> None:
    """404 for strangers — don't even confirm the thread exists."""
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT uid FROM chats WHERE thread_id=%s", (thread_id,)
        ).fetchone()
    if not row or row[0] != uid:
        raise HTTPException(status_code=404, detail="Not found")

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
    _conn.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS published_site_id text")
    _conn.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS published_url text")
    # our own message store — the checkpointer holds graph STATE, but the
    # conversation as the user saw it (thinking, artifacts included) is
    # product data and lives in a queryable table
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         bigserial PRIMARY KEY,
            thread_id  text NOT NULL REFERENCES chats(thread_id) ON DELETE CASCADE,
            role       text NOT NULL,
            content    text NOT NULL,
            thinking   jsonb,
            attachment text,
            created_at timestamptz NOT NULL DEFAULT now()
        )""")
    _conn.execute("CREATE INDEX IF NOT EXISTS ix_messages_thread ON messages (thread_id, id)")
    _conn.commit()


def _mirror_draft(thread_id: str, uid: str) -> None:
    """Mirror the finished draft into the product schema (users/projects/
    sites/site_versions) — append-only versioning, rollback = pointer move.
    Best-effort: a mirror failure must never break the chat stream."""
    try:
        state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
        spec, pages, brief = state.get("spec", {}), state.get("pages", {}), state.get("brief", {})
        if not pages:
            return
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "INSERT INTO users (uid, email) VALUES (%s, '') ON CONFLICT (uid) DO NOTHING",
                (uid,),
            )
            brief_doc = json.dumps({**brief, "thread_id": thread_id})
            row = conn.execute(
                "SELECT id FROM projects WHERE owner_uid=%s AND business_brief->>'thread_id'=%s",
                (uid, thread_id),
            ).fetchone()
            if row:
                project_id = row[0]
                conn.execute(
                    "UPDATE projects SET name=%s, business_brief=%s, updated_at=now() WHERE id=%s",
                    (spec.get("site_name", "Untitled"), brief_doc, project_id),
                )
            else:
                project_id = conn.execute(
                    "INSERT INTO projects (owner_uid, name, business_brief) VALUES (%s,%s,%s) RETURNING id",
                    (uid, spec.get("site_name", "Untitled"), brief_doc),
                ).fetchone()[0]

            row = conn.execute(
                "SELECT id FROM sites WHERE project_id=%s", (project_id,)
            ).fetchone()
            site_id = row[0] if row else conn.execute(
                "INSERT INTO sites (project_id, status) VALUES (%s, 'draft') RETURNING id",
                (project_id,),
            ).fetchone()[0]

            version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM site_versions WHERE site_id=%s",
                (site_id,),
            ).fetchone()[0]
            version_id = conn.execute(
                "INSERT INTO site_versions (site_id, version, spec, pages) VALUES (%s,%s,%s,%s) RETURNING id",
                (site_id, version, json.dumps(spec), json.dumps(pages)),
            ).fetchone()[0]
            conn.execute(
                "UPDATE sites SET current_version_id=%s WHERE id=%s", (version_id, site_id)
            )
            conn.commit()
    except Exception:
        pass


def _save_message(thread_id: str, role: str, content: str, thinking=None, attachment=None):
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO messages (thread_id, role, content, thinking, attachment) VALUES (%s,%s,%s,%s,%s)",
            (thread_id, role, content, json.dumps(thinking) if thinking else None, attachment),
        )
        conn.commit()


class ChatIn(BaseModel):
    thread_id: str
    message: str


NODE_LABELS = {
    "understand": "Understanding your business",
    "plan": "Designing the site structure",
    "illustrate": "Finding photos",
    "write": "Writing page copy",
    "review": "Reviewing quality",
}

# canned quick-reply options for interview fields that have generic answers
FIELD_SUGGESTIONS = {
    "target_customers": ["Local families", "Young professionals", "Tourists and visitors"],
    "tone": ["Warm and friendly", "Modern and minimal", "Bold and energetic", "Premium and elegant"],
}

DONE_SUGGESTIONS = [
    "Make the tone more premium",
    "Change the color theme",
    "Add a pricing page",
    "Shorten the homepage copy",
]


def _suggestions(state: dict, last_reply: str = "") -> list[str]:
    """Quick replies grounded in what the agent just said (LLM), with the
    deterministic canned options as fallback when the model is unavailable."""
    if last_reply:
        try:
            import json as _json
            import re as _re

            from config import INTERVIEW_MODEL
            from llm import chat_model

            r = chat_model(INTERVIEW_MODEL, temperature=0.4).invoke([
                ("system",
                 "The assistant of a website-building copilot just said the message "
                 "below. Suggest 3 short replies the USER would likely tap next "
                 "(each under 6 words, no punctuation at the end). "
                 'Reply with ONLY a JSON array of 3 strings.'),
                ("user", last_reply),
            ])
            m = _re.search(r"\[.*\]", r.content, _re.DOTALL)
            items = _json.loads(m.group(0) if m else r.content)
            if isinstance(items, list) and items:
                return [str(s)[:48] for s in items[:4]]
        except Exception:
            pass  # fall through to canned options

    if state.get("phase") == "done":
        return DONE_SUGGESTIONS
    if not state.get("brief_complete"):
        brief = state.get("brief", {})
        for field, options in FIELD_SUGGESTIONS.items():
            if not brief.get(field):
                return options
    return []


class NewChatIn(BaseModel):
    uid: str = ""  # ignored — identity comes from the verified token


@app.post("/agent/chats")
def create_chat(body: NewChatIn, uid: str = Depends(current_uid)):
    thread_id = f"c-{uuid.uuid4().hex[:12]}"
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("INSERT INTO chats (thread_id, uid) VALUES (%s, %s)", (thread_id, uid))
        conn.commit()
    return {"thread_id": thread_id}


@app.get("/agent/chats")
def list_chats(q: str = "", cursor: str = "", limit: int = 30, uid: str = Depends(current_uid)):
    """Server-side search + keyset pagination (cursor = updated_at|thread_id)."""
    limit = min(max(limit, 1), 100)
    sql = "SELECT thread_id, title, updated_at FROM chats WHERE uid=%s"
    params: list = [uid]
    if q.strip():
        sql += " AND title ILIKE %s"
        params.append(f"%{q.strip()}%")
    if cursor:
        ts, _, tid = cursor.partition("|")
        sql += " AND (updated_at, thread_id) < (%s, %s)"
        params += [ts, tid]
    sql += " ORDER BY updated_at DESC, thread_id DESC LIMIT %s"
    params.append(limit + 1)  # one extra row = "there's more"

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, params).fetchall()

    more = len(rows) > limit
    rows = rows[:limit]
    items = [
        {"thread_id": r[0], "title": r[1] or "New chat", "updated_at": r[2].isoformat()}
        for r in rows
    ]
    next_cursor = f"{rows[-1][2].isoformat()}|{rows[-1][0]}" if more else None
    return {"items": items, "next_cursor": next_cursor}


class RenameIn(BaseModel):
    title: str


@app.patch("/agent/chats/{thread_id}")
def rename_chat(thread_id: str, body: RenameIn, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET title=%s WHERE thread_id=%s",
            (body.title.strip()[:60] or "Untitled", thread_id),
        )
        conn.commit()
    return {"ok": True}


@app.delete("/agent/chats/{thread_id}")
def delete_chat(thread_id: str, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
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
def chat_messages(thread_id: str, cursor: str = "", limit: int = 50, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    """Latest page first; cursor (a message id) walks backwards in history."""
    limit = min(max(limit, 1), 200)
    sql = "SELECT id, role, content, thinking, attachment FROM messages WHERE thread_id=%s"
    params: list = [thread_id]
    if cursor:
        sql += " AND id < %s"
        params.append(int(cursor))
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit + 1)

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, params).fetchall()

    more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()  # oldest-first for rendering
    if rows:
        return {
            "items": [
                {"role": r[1], "text": r[2], "thinking": r[3], "attachment": r[4]}
                for r in rows
            ],
            "next_cursor": str(rows[0][0]) if more else None,
        }

    # threads older than the messages table: fall back to checkpointer state
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    out = []
    for m in state.get("messages", []):
        role = "user" if m.type == "human" else "agent"
        if m.content:
            out.append({"role": role, "text": m.content, "thinking": None, "attachment": None})
    return {"items": out, "next_cursor": None}


@app.get("/healthz")
@app.get("/agent/healthz")  # hosting forwards the full /agent/* path
def healthz():
    return {"ok": True}


@app.get("/agent/site/{thread_id}", response_class=HTMLResponse)
def site(thread_id: str, path: str = "/", uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    """The rendered website itself — the same document deploy_site publishes."""
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    pages = state.get("pages", {})
    if not pages:
        raise HTTPException(status_code=404, detail="No site generated yet")
    if path not in pages:
        path = next(iter(pages))
    return build_site_html(state.get("spec", {}), pages, path)


@app.get("/agent/draft/{thread_id}")
def draft(thread_id: str, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    """Full draft for a conversation — spec, brief, and every page's copy."""
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT published_url FROM chats WHERE thread_id=%s", (thread_id,)
        ).fetchone()
    return {
        "phase": state.get("phase"),
        "brief": state.get("brief", {}),
        "spec": state.get("spec", {}),
        "pages": state.get("pages", {}),
        "score": state.get("critique", {}).get("score"),
        "live_url": row[0] if row else None,
    }


TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


def _trace_config(thread_id: str, uid: str) -> dict:
    """Langfuse tracing for every agent run — full LLM call tree with
    latency and token counts, grouped by conversation. No-op without keys."""
    if not os.environ.get("LANGFUSE_SECRET_KEY"):
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        return {
            "callbacks": [CallbackHandler()],
            "metadata": {
                "langfuse_session_id": thread_id,
                "langfuse_user_id": uid,
            },
        }
    except Exception:
        return {}


async def _temporal():
    from temporalio.client import Client

    return await Client.connect(TEMPORAL_ADDRESS)


@app.post("/agent/workflows/generate/{thread_id}")
async def wf_generate(thread_id: str, regenerate: bool = True, uid: str = Depends(current_uid)):
    """Start the durable generation workflow. One per thread — starting
    again while one runs returns the running one."""
    own_thread(thread_id, uid)
    from temporalio.exceptions import WorkflowAlreadyStartedError

    client = await _temporal()
    wf_id = f"gen-{thread_id}"
    try:
        await client.start_workflow(
            "GenerateSiteWorkflow",
            args=[thread_id, regenerate],
            id=wf_id,
            task_queue="siteforge",
        )
    except WorkflowAlreadyStartedError:
        pass
    return {"workflow_id": wf_id}


@app.post("/agent/workflows/{thread_id}/approve")
async def wf_approve(thread_id: str, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    client = await _temporal()
    await client.get_workflow_handle(f"gen-{thread_id}").signal("approve")
    return {"ok": True}


@app.get("/agent/workflows/{thread_id}/status")
async def wf_status(thread_id: str, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    client = await _temporal()
    handle = client.get_workflow_handle(f"gen-{thread_id}")
    desc = await handle.describe()
    out = {"run_status": desc.status.name if desc.status else "UNKNOWN"}
    try:
        out["stage"] = await handle.query("status")
    except Exception:
        out["stage"] = None
    if desc.status and desc.status.name == "COMPLETED":
        out["result"] = await handle.result()
    return out


@app.post("/agent/publish/{thread_id}")
def publish(thread_id: str, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    """deploy_site: render every page live-mode and release it to Firebase
    Hosting on the business's own sub-site. Re-publishing reuses the site."""
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    pages = state.get("pages", {})
    if not pages:
        raise HTTPException(status_code=404, detail="No site to publish yet")

    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT published_site_id FROM chats WHERE thread_id=%s", (thread_id,)
        ).fetchone()
    existing = row[0] if row else None

    site_id, url = publish_site(state.get("spec", {}), pages, existing)

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET published_site_id=%s, published_url=%s WHERE thread_id=%s",
            (site_id, url, thread_id),
        )
        conn.commit()
    return {"url": url}


def _rate_limit(uid: str) -> None:
    """Per-user daily message cap in Redis (design-review cost guardrail).
    Redis down = no limiting, never an outage."""
    import datetime

    limit = int(os.environ.get("CHAT_DAILY_LIMIT", "100"))
    try:
        import redis

        r = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"), socket_timeout=2
        )
        key = f"rl:{uid}:{datetime.date.today().isoformat()}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 90000)  # a bit over a day
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily limit of {limit} messages reached — resets at midnight.",
            )
    except HTTPException:
        raise
    except Exception:
        pass


@app.post("/agent/chat")
def chat(body: ChatIn, uid: str = Depends(current_uid)):
    own_thread(body.thread_id, uid)
    _rate_limit(uid)
    config = {"configurable": {"thread_id": body.thread_id}, **_trace_config(body.thread_id, uid)}

    # bump recency; the title is LLM-generated after the reply streams
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET updated_at = now() WHERE thread_id = %s",
            (body.thread_id,),
        )
        conn.commit()
    _save_message(body.thread_id, "user", body.message)

    def events():
        try:
            yield from run_events()
        except Exception as e:  # the stream must never just go silent
            text = str(e)
            if "free-models-per-day" in text or "429" in text:
                friendly = (
                    "Daily free-model limit reached on OpenRouter. "
                    "It resets at midnight UTC — or add credits to raise the limit."
                )
            else:
                friendly = f"The agent hit an error: {text[:200]}"
            yield f"event: error\ndata: {json.dumps({'message': friendly})}\n\n"

    def run_events():
        # two stream modes multiplexed: "messages" gives token-by-token LLM
        # output (tagged with the node that produced it), "updates" gives
        # node results. The wire protocol mirrors claude/openai chat UIs:
        #   thinking  — deltas from silent nodes, shown in a thinking block
        #   token     — deltas of the user-visible answer (respond node)
        #   node      — a node finished (carries deliver's built message)
        #   suggestions / done — computed after the run
        #   error     — emitted by the wrapper above if anything raises
        # the BE mirrors what the client assembles, persisting each agent
        # message (with its thinking and artifacts) as it finalizes
        answer_acc = ""
        last_reply = ""
        think_acc: list[dict] = []

        for mode, chunk in graph.stream(
            {"messages": [("user", body.message)]},
            config,
            stream_mode=["updates", "messages"],
        ):
            if mode == "messages":
                msg_chunk, meta = chunk
                node = meta.get("langgraph_node")
                if not getattr(msg_chunk, "content", None):
                    continue
                if node == "respond":
                    answer_acc += msg_chunk.content
                    yield f"event: token\ndata: {json.dumps({'text': msg_chunk.content})}\n\n"
                else:
                    if think_acc and think_acc[-1]["node"] == node:
                        think_acc[-1]["text"] += msg_chunk.content
                    else:
                        think_acc.append(
                            {"node": node, "label": NODE_LABELS.get(node, node), "text": msg_chunk.content}
                        )
                    payload = {
                        "node": node,
                        "label": NODE_LABELS.get(node, node),
                        "text": msg_chunk.content,
                    }
                    yield f"event: thinking\ndata: {json.dumps(payload)}\n\n"
                continue

            for node_name, node_update in chunk.items():
                payload = {"node": node_name, "phase": node_update.get("phase")}
                # respond's full text was already streamed as tokens — the node
                # event just marks it finished. deliver's message is code-built
                # (no tokens exist), so it ships whole.
                if node_name == "respond" and answer_acc:
                    _save_message(body.thread_id, "agent", answer_acc, thinking=think_acc or None)
                    last_reply = answer_acc
                    answer_acc = ""
                    think_acc = []
                if node_name != "respond":
                    for m in node_update.get("messages", []):
                        payload["reply"] = m.content
                        last_reply = m.content
                        if node_name == "deliver":
                            _save_message(
                                body.thread_id, "agent", m.content,
                                thinking=think_acc or None, attachment="site",
                            )
                            think_acc = []
                            _mirror_draft(body.thread_id, uid)
                yield f"event: node\ndata: {json.dumps(payload)}\n\n"

        final = graph.get_state(config).values

        # quick replies grounded in the agent's answer — computed in the BE
        chips = _suggestions(final, last_reply)
        if chips:
            yield f"event: suggestions\ndata: {json.dumps({'items': chips})}\n\n"

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
