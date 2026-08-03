"""pgvector store — one table, cosine search. Embeddings are computed
locally with fastembed (bge-small, 384 dims): free, fast, no API quota."""

import os
from functools import lru_cache

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://siteforge:siteforge_dev@localhost:5432/siteforge",
)
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


def search(query: str, k: int = 3) -> list[dict]:
    qvec = _vec(embed([query])[0])
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """SELECT source, content, 1 - (embedding <=> %s::vector) AS score
               FROM rag_chunks ORDER BY embedding <=> %s::vector LIMIT %s""",
            (qvec, qvec, k),
        ).fetchall()
    return [{"source": r[0], "content": r[1], "score": round(float(r[2]), 4)} for r in rows]
