"""RAG service — retrieval over the knowledge corpus.

Internal service: called by the agent's write node, not by browsers,
so it stays inside the private network (no token auth needed here —
Cloud Run ingress will restrict it later)."""

import os

from fastapi import FastAPI
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
    """Used by the eval flywheel to promote platinum examples."""
    n = store.replace_source(body.source, body.chunks)
    return {"ingested": n}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/rag/search")
def search(body: SearchIn):
    return {"results": store.search(body.query, min(max(body.k, 1), 10), body.exclude)}
