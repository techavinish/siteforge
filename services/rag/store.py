"""pgvector store — one table, cosine search. Embeddings are computed
locally with fastembed (bge-small, 384 dims): free, fast, no API quota."""

import os
from functools import lru_cache

import psycopg

# local docker pg by default; Cloud Run builds the unix-socket DSN from
# parts (password arrives via Secret Manager, never in an env literal)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _conn = os.environ.get("CLOUDSQL_CONN", "")
    if _conn:
        DATABASE_URL = (
            f"postgresql://{os.environ.get('DB_USER', 'app')}:{os.environ['DB_PASS']}"
            f"@/{os.environ.get('DB_NAME', 'siteforge')}?host=/cloudsql/{_conn}"
        )
    else:
        DATABASE_URL = "postgresql://siteforge:siteforge_dev@localhost:5432/siteforge"
EMBED_DIM = 384


@lru_cache(maxsize=1)
def embedder():
    from fastembed import TextEmbedding

    return TextEmbedding("BAAI/bge-small-en-v1.5")


def embed(texts: list[str]) -> list[list[float]]:
    return [list(map(float, v)) for v in embedder().embed(texts)]


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def setup() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id        bigserial PRIMARY KEY,
                source    text NOT NULL,
                content   text NOT NULL,
                embedding vector({EMBED_DIM}) NOT NULL
            )""")
        conn.commit()


def replace_source(source: str, chunks: list[str]) -> int:
    """Idempotent ingest: re-running a source replaces its chunks."""
    vectors = embed(chunks)
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM rag_chunks WHERE source=%s", (source,))
        for content, vector in zip(chunks, vectors):
            conn.execute(
                "INSERT INTO rag_chunks (source, content, embedding) VALUES (%s, %s, %s::vector)",
                (source, content, _vec(vector)),
            )
        conn.commit()
    return len(chunks)


def search(query: str, k: int = 3, exclude: str = "") -> list[dict]:
    """exclude: source prefix to skip — e.g. 'platinum-' keeps the flywheel's
    own outputs from drowning out the curated craft on design queries."""
    qvec = _vec(embed([query])[0])
    sql = "SELECT source, content, 1 - (embedding <=> %s::vector) AS score FROM rag_chunks"
    params: list = [qvec]
    if exclude:
        sql += " WHERE source NOT LIKE %s"
        params.append(f"{exclude}%")
    sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params += [qvec, k]
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{"source": r[0], "content": r[1], "score": round(float(r[2]), 4)} for r in rows]
