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
from publish import (
    LOGO_MIMES,
    decorate_spec as _decorate_spec,
    logo_path as _logo_path,
    logo_row as _logo_row,
    publish_site,
)
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

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    # every published business site (sf-*.web.app) posts bookings here,
    # and the app itself is a web.app origin — auth is the token/key, the
    # origin was never the security boundary
    allow_origin_regex=r"https://[a-z0-9-]+\.web\.app",
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

# A REAL pool: parallel Send branches checkpoint concurrently, and a
# dropped connection must not require a process restart.
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool = ConnectionPool(
    DATABASE_URL, min_size=1, max_size=8, open=True,
    kwargs={"autocommit": True, "row_factory": dict_row},
)
saver = PostgresSaver(_pool)
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
    # bookings from published sites — the client's dashboard reads these.
    # keyed by thread_id: one business per conversation, ownership via chats
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id         bigserial PRIMARY KEY,
            thread_id  text NOT NULL REFERENCES chats(thread_id) ON DELETE CASCADE,
            name       text NOT NULL,
            contact    text NOT NULL,
            service    text,
            message    text,
            status     text NOT NULL DEFAULT 'new',
            created_at timestamptz NOT NULL DEFAULT now()
        )""")
    _conn.execute("CREATE INDEX IF NOT EXISTS ix_bookings_thread ON bookings (thread_id, id DESC)")
    # owner-uploaded assets (the logo) — small binaries, versioned by upsert
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            thread_id  text NOT NULL REFERENCES chats(thread_id) ON DELETE CASCADE,
            kind       text NOT NULL,
            mime       text NOT NULL,
            data       bytea NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (thread_id, kind)
        )""")
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
    "booking": ["Use the SiteForge booking form", "Email me enquiries", "No form, just my details"],
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
    return build_site_html(_decorate_spec(state.get("spec", {}), thread_id, live=False), pages, path)


@app.get("/agent/draft/{thread_id}")
def draft(thread_id: str, uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    """Full draft for a conversation — spec, brief, and every page's copy."""
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT published_url FROM chats WHERE thread_id=%s", (thread_id,)
        ).fetchone()
        counts = dict(conn.execute(
            "SELECT status, count(*) FROM bookings WHERE thread_id=%s GROUP BY status",
            (thread_id,),
        ).fetchall())
    return {
        "phase": state.get("phase"),
        "brief": state.get("brief", {}),
        "spec": state.get("spec", {}),
        "pages": state.get("pages", {}),
        "score": state.get("critique", {}).get("score"),
        "live_url": row[0] if row else None,
        "bookings": {s: counts.get(s, 0) for s in ("new", "contacted", "closed")},
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

    spec = _decorate_spec(state.get("spec", {}), thread_id, live=True)
    logo = _logo_row(thread_id)
    extra = {_logo_path(logo[0]): bytes(logo[1])} if logo else None
    site_id, url = publish_site(spec, pages, existing, extra_files=extra)

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE chats SET published_site_id=%s, published_url=%s WHERE thread_id=%s",
            (site_id, url, thread_id),
        )
        conn.commit()
    return {"url": url}


class BookIn(BaseModel):
    key: str  # the site's thread_id, embedded in the published form
    name: str
    contact: str
    service: str = ""
    message: str = ""
    website: str = ""  # honeypot — humans never see it, bots fill it


def _ip_limit(bucket: str, limit: int) -> bool:
    """Best-effort Redis counter for unauthenticated surfaces. Redis down
    = allow — a booking lost to our outage is worse than spam."""
    import datetime

    try:
        import redis

        r = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"), socket_timeout=2
        )
        key = f"book:{bucket}:{datetime.date.today().isoformat()}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 90000)
        return count <= limit
    except Exception:
        return True


@app.post("/agent/book")
def book(body: BookIn, request: Request):
    """PUBLIC intake: the booking form on every published (and previewed)
    site posts here. No login — a visitor booking a haircut has no account.
    The key is the unguessable thread id baked into the site at render."""
    if body.website.strip():
        return {"ok": True}  # honeypot tripped: swallow silently
    name, contact = body.name.strip()[:80], body.contact.strip()[:120]
    if not name or not contact:
        raise HTTPException(status_code=422, detail="Name and contact are required")

    ip = (request.headers.get("X-Forwarded-For", "") or "?").split(",")[0].strip()
    if not _ip_limit(f"ip:{ip}", 20) or not _ip_limit(f"site:{body.key}", 200):
        raise HTTPException(status_code=429, detail="Too many requests — try again tomorrow")

    with psycopg.connect(DATABASE_URL) as conn:
        exists = conn.execute(
            "SELECT 1 FROM chats WHERE thread_id=%s", (body.key,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Unknown site")
        conn.execute(
            "INSERT INTO bookings (thread_id, name, contact, service, message) "
            "VALUES (%s,%s,%s,%s,%s)",
            (body.key, name, contact, body.service.strip()[:80] or None,
             body.message.strip()[:1000] or None),
        )
        conn.commit()
    return {"ok": True}


@app.get("/agent/bookings/{thread_id}")
def list_bookings(thread_id: str, cursor: str = "", limit: int = 50,
                  uid: str = Depends(current_uid)):
    """The owner's dashboard: newest first, keyset-paged, with the status
    counts that head the view."""
    own_thread(thread_id, uid)
    limit = min(max(limit, 1), 200)
    sql = ("SELECT id, name, contact, service, message, status, created_at "
           "FROM bookings WHERE thread_id=%s")
    params: list = [thread_id]
    if cursor:
        sql += " AND id < %s"
        params.append(int(cursor))
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit + 1)
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, params).fetchall()
        counts = dict(conn.execute(
            "SELECT status, count(*) FROM bookings WHERE thread_id=%s GROUP BY status",
            (thread_id,),
        ).fetchall())
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {"id": r[0], "name": r[1], "contact": r[2], "service": r[3],
             "message": r[4], "status": r[5], "created_at": r[6].isoformat()}
            for r in rows
        ],
        "counts": {s: counts.get(s, 0) for s in ("new", "contacted", "closed")},
        "next_cursor": str(rows[-1][0]) if more else None,
    }


class BookingStatusIn(BaseModel):
    status: str


@app.patch("/agent/bookings/{thread_id}/{booking_id}")
def update_booking(thread_id: str, booking_id: int, body: BookingStatusIn,
                   uid: str = Depends(current_uid)):
    own_thread(thread_id, uid)
    if body.status not in ("new", "contacted", "closed"):
        raise HTTPException(status_code=422, detail="Unknown status")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE bookings SET status=%s WHERE thread_id=%s AND id=%s",
            (body.status, thread_id, booking_id),
        )
        conn.commit()
    return {"ok": True}


class LogoIn(BaseModel):
    data_url: str  # "data:image/png;base64,...." from the composer


@app.post("/agent/logo/{thread_id}")
def upload_logo(thread_id: str, body: LogoIn, uid: str = Depends(current_uid)):
    """The owner's logo, straight from the paperclip button. Stored small
    (≤512KB) and re-served to the preview / published with the site."""
    own_thread(thread_id, uid)
    import base64
    import re as _re

    m = _re.match(r"data:([a-z0-9./+-]+);base64,(.+)$", body.data_url, _re.DOTALL | _re.I)
    if not m or m.group(1).lower() not in LOGO_MIMES:
        raise HTTPException(status_code=422, detail="Use a PNG, JPG, SVG or WebP image")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="Broken image data")
    if len(raw) > 512 * 1024:
        raise HTTPException(status_code=422, detail="Logo must be under 512 KB")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO assets (thread_id, kind, mime, data) VALUES (%s,'logo',%s,%s) "
            "ON CONFLICT (thread_id, kind) DO UPDATE SET mime=EXCLUDED.mime, "
            "data=EXCLUDED.data, updated_at=now()",
            (thread_id, m.group(1).lower(), raw),
        )
        conn.commit()
    return {"ok": True}


@app.get("/agent/asset/{thread_id}/logo")
def serve_logo(thread_id: str):
    """Public by design: the preview <img> can't carry a token, and the
    thread id is unguessable. Served with the stored mime."""
    row = _logo_row(thread_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    from fastapi.responses import Response

    return Response(bytes(row[1]), media_type=row[0],
                    headers={"Cache-Control": "private, max-age=300"})


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

    unsaved = {"answer": "", "thinks": []}  # mirror of what's on screen

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
            _save_message(body.thread_id, "agent", friendly)
            yield f"event: error\ndata: {json.dumps({'message': friendly})}\n\n"
        finally:
            # client disconnect or mid-run failure: text the user already
            # watched stream must exist in history when they reload
            if unsaved["answer"]:
                _save_message(
                    body.thread_id, "agent", unsaved["answer"],
                    thinking=unsaved["thinks"] or None,
                )

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
                    unsaved["answer"] = answer_acc
                    yield f"event: token\ndata: {json.dumps({'text': msg_chunk.content})}\n\n"
                else:
                    if think_acc and think_acc[-1]["node"] == node:
                        think_acc[-1]["text"] += msg_chunk.content
                    else:
                        think_acc.append(
                            {"node": node, "label": NODE_LABELS.get(node, node), "text": msg_chunk.content}
                        )
                    unsaved["thinks"] = think_acc
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
                    unsaved["answer"] = ""
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

        snapshot = {
            "phase": final.get("phase"),
            "brief": final.get("brief", {}),
            "spec": final.get("spec", {}),
            "pages": list(final.get("pages", {})),
            "score": final.get("critique", {}).get("score"),
        }
        yield f"event: done\ndata: {json.dumps(snapshot)}\n\n"

        # AFTER done: the UI is settled — chips and the title are bonuses
        # (each an LLM call), never blockers on a finished answer
        chips = _suggestions(final, last_reply)
        if chips:
            yield f"event: suggestions\ndata: {json.dumps({'items': chips})}\n\n"

        _ensure_title(body.thread_id, body.message)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
