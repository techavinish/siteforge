"""RAG service — retrieval over the knowledge corpus.

Internal service: called by the agent's write node, not by browsers,
so it stays inside the private network (no token auth needed here —
Cloud Run ingress will restrict it later)."""

from fastapi import FastAPI
from pydantic import BaseModel

import store

app = FastAPI(title="siteforge-rag")
store.setup()


class SearchIn(BaseModel):
    query: str
    k: int = 3


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/rag/search")
def search(body: SearchIn):
    return {"results": store.search(body.query, min(max(body.k, 1), 10))}
