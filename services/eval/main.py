"""Evaluation service — the flywheel's engine.

POST /eval/run:
  1. discover every published SiteForge site (Firebase Hosting API)
  2. fetch each live page, run deterministic checks + LLM judge
  3. bronze: raw run events · silver: typed results · gold: auto-aggregated
  4. platinum: top-scoring pages re-ingested into the RAG corpus so the
     next generation writes like the best previous one

Called on a Temporal schedule (see workers/workflows.py) — the same
orchestrator that runs generation runs evaluation.
"""

import os

import google.auth
import requests
from fastapi import FastAPI
from google.auth.transport.requests import Request as GRequest

import checks
import judge
import warehouse

if os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1)

app = FastAPI(title="siteforge-eval")
warehouse.setup()

GCP_PROJECT = os.environ.get("GCP_PROJECT", "siteforge-dev-3977")
RAG_URL = os.environ.get("RAG_URL", "http://localhost:8002")
PLATINUM_THRESHOLD = 8.0


def discover_sites() -> list[str]:
    """Every published business site in the project (sf-* naming)."""
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(GRequest())
    r = requests.get(
        f"https://firebasehosting.googleapis.com/v1beta1/projects/{GCP_PROJECT}/sites",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=30,
    )
    r.raise_for_status()
    return [
        s["defaultUrl"]
        for s in r.json().get("sites", [])
        if s["name"].split("/")[-1].startswith("sf-")
    ]


def promote_to_platinum(url: str, html: str) -> None:
    """The flywheel: excellent pages become RAG knowledge."""
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()[:1200]
    slug = url.replace("https://", "").split(".")[0]
    requests.post(
        f"{RAG_URL}/rag/ingest",
        json={"source": f"platinum-{slug}", "chunks": [f"## Proven example ({slug})\n{text}"]},
        timeout=30,
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/eval/run")
def run():
    sites = discover_sites()
    report = []
    for url in sites:
        try:
            html = requests.get(url, timeout=20).text
        except Exception as e:
            warehouse.bronze("eval_fetch_failed", url, {"error": str(e)})
            continue

        results = checks.run_checks(html) + judge.judge_page(html)
        warehouse.bronze("eval_run", url, {"checks": len(results)})
        warehouse.silver([{"site": url, "page": "/", **r} for r in results])

        avg = sum(r["score"] for r in results) / max(len(results), 1)
        if avg >= PLATINUM_THRESHOLD:
            promote_to_platinum(url, html)
        report.append({"site": url, "avg_score": round(avg, 2), "checks": len(results)})
    return {"evaluated": report}
