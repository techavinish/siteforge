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


def promote_to_platinum(url: str, html: str, avg_score: float) -> None:
    """The flywheel: excellent pages become RAG knowledge.

    Prefer the STRUCTURED source of truth — the mirrored draft in
    site_versions holds clean per-page markdown and the design spec.
    Stripped live HTML (nav soup, footer noise) is only the fallback."""
    import json as _json
    import re

    import psycopg

    slug = url.replace("https://", "").split(".")[0]
    chunks: list[str] = []
    try:
        db = os.environ.get(
            "DATABASE_URL", "postgresql://siteforge:siteforge_dev@localhost:5432/siteforge"
        )
        with psycopg.connect(db) as conn:
            row = conn.execute(
                """SELECT sv.spec, sv.pages FROM sites s
                   JOIN site_versions sv ON sv.id = s.current_version_id
                   ORDER BY sv.created_at DESC LIMIT 1"""
            ).fetchone()
        if row:
            spec = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
            pages = row[1] if isinstance(row[1], dict) else _json.loads(row[1])
            biz = spec.get("site_name", slug)
            for path, md_copy in list(pages.items())[:3]:
                head = md_copy.strip()[:700]
                chunks.append(
                    f"## Proven page — {biz} {path} (judge {avg_score}/10)\n{head}"
                )
    except Exception:
        pass

    if not chunks:  # fallback: the old stripped-HTML representation
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()[:1200]
        chunks = [f"## Proven example ({slug})\n{text}"]

    requests.post(
        f"{RAG_URL}/rag/ingest",
        json={"source": f"platinum-{slug}", "chunks": chunks},
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
            promote_to_platinum(url, html, round(avg, 2))
        report.append({"site": url, "avg_score": round(avg, 2), "checks": len(results)})
    return {"evaluated": report}
