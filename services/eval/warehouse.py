"""ClickHouse medallion — bronze/silver/gold over plain HTTP (no driver).

Bronze: append-only raw events, exactly as they happened.
Silver: typed evaluation results, one row per check per page.
Gold:   daily aggregates, maintained by a materialized view — the tables
        a dashboard reads directly.
(Platinum is not a table here: it's the top-scoring content re-ingested
into the RAG corpus — see flywheel.py.)
"""

import json
import os

import requests

CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
AUTH = (os.environ.get("CLICKHOUSE_USER", "siteforge"),
        os.environ.get("CLICKHOUSE_PASSWORD", "siteforge_dev"))

DDL = [
    """CREATE TABLE IF NOT EXISTS bronze_events (
        ts DateTime DEFAULT now(),
        kind String,
        site String,
        payload String
    ) ENGINE = MergeTree ORDER BY (kind, ts)""",
    """CREATE TABLE IF NOT EXISTS silver_evals (
        ts DateTime DEFAULT now(),
        site String,
        page String,
        check String,
        score Float64,
        detail String
    ) ENGINE = MergeTree ORDER BY (site, ts)""",
    """CREATE TABLE IF NOT EXISTS gold_daily (
        day Date,
        site String,
        avg_score AggregateFunction(avg, Float64),
        checks AggregateFunction(count, UInt64)
    ) ENGINE = AggregatingMergeTree ORDER BY (day, site)""",
    """CREATE MATERIALIZED VIEW IF NOT EXISTS gold_daily_mv TO gold_daily AS
        SELECT toDate(ts) AS day, site,
               avgState(score) AS avg_score,
               countState() AS checks
        FROM silver_evals GROUP BY day, site""",
]


def query(sql: str, data: str | None = None) -> str:
    r = requests.post(CLICKHOUSE_URL, params={"query": sql}, data=data,
                      auth=AUTH, timeout=30)
    r.raise_for_status()
    return r.text


def setup() -> None:
    for stmt in DDL:
        query(stmt)


def bronze(kind: str, site: str, payload: dict) -> None:
    row = json.dumps({"kind": kind, "site": site, "payload": json.dumps(payload)})
    query("INSERT INTO bronze_events (kind, site, payload) FORMAT JSONEachRow", row)


def silver(rows: list[dict]) -> None:
    data = "\n".join(json.dumps(r) for r in rows)
    query("INSERT INTO silver_evals (site, page, check, score, detail) FORMAT JSONEachRow", data)


def gold_report() -> str:
    return query(
        "SELECT day, site, round(avgMerge(avg_score), 2) AS score, "
        "countMerge(checks) AS checks FROM gold_daily "
        "GROUP BY day, site ORDER BY day DESC, site FORMAT PrettyCompact"
    )
