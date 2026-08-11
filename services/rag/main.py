"""RAG service — retrieval over the knowledge corpus.

Internal service: called by the agent's write node, not by browsers,
so it stays inside the private network (no token auth needed here —
Cloud Run ingress will restrict it later)."""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import store

if os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1)

app = FastAPI(title="siteforge-rag")
store.setup()


class SearchIn(BaseModel):
    query: str
    k: int = 3
    exclude: str = ""


class IngestIn(BaseModel):
    source: str
    chunks: list[str]


@app.post("/rag/ingest")
def ingest(body: IngestIn):
    """Used by the eval flywheel to promote platinum examples. Curated
    corpus sources are only writable via ingest.py — the HTTP surface
    must never be able to clobber them."""
    if not body.source.startswith("platinum-"):
        raise HTTPException(status_code=403, detail="only platinum- sources")
    n = store.replace_source(body.source, body.chunks)
    return {"ingested": n}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/rag/search")
def search(body: SearchIn):
    return {"results": store.search(body.query, min(max(body.k, 1), 10), body.exclude)}
