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
    """Passage-side embeddings — ingestion only."""
    return [list(map(float, v)) for v in embedder().embed(texts)]


@lru_cache(maxsize=256)
def embed_query(text: str) -> tuple[float, ...]:
    """Query-side embeddings. bge models expect the query instruction
    prefix (fastembed's query_embed adds it) — embedding queries
    passage-style measurably degrades short-query retrieval. Cached:
    the same brief drives several retrievals per generation."""
    return tuple(map(float, next(iter(embedder().query_embed([text])))))


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
        # seq-scan is fine at 71 rows; the platinum flywheel grows unbounded
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_rag_hnsw ON rag_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
        # flavour: every chunk carries its topic (design/copy/platinum) so
        # retrieval can be scoped to what the query is actually about
        conn.execute("ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS topic text NOT NULL DEFAULT 'copy'")
        # per-source content hash — startup sync reingests ONLY what changed,
        # so deploying new corpus IS the reingest and cold starts stay cheap
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_sources (
                source text PRIMARY KEY,
                hash   text NOT NULL
            )""")
        conn.commit()


def stored_hash(source: str) -> str | None:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT hash FROM rag_sources WHERE source=%s", (source,)
        ).fetchone()
    return row[0] if row else None


def record_hash(source: str, h: str) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO rag_sources (source, hash) VALUES (%s,%s) "
            "ON CONFLICT (source) DO UPDATE SET hash=EXCLUDED.hash",
            (source, h),
        )
        conn.commit()


def replace_source(source: str, chunks: list[str], topic: str = "copy") -> int:
    """Idempotent ingest: re-running a source replaces its chunks."""
    vectors = embed(chunks)
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM rag_chunks WHERE source=%s", (source,))
        for content, vector in zip(chunks, vectors):
            conn.execute(
                "INSERT INTO rag_chunks (source, content, embedding, topic) VALUES (%s, %s, %s::vector, %s)",
                (source, content, _vec(vector), topic),
            )
        conn.commit()
    return len(chunks)


def search(query: str, k: int = 3, exclude: str = "", topics: list[str] | None = None) -> list[dict]:
    """exclude: source prefix to skip — e.g. 'platinum-' keeps the flywheel's
    own outputs from drowning out the curated craft on design queries."""
    qvec = _vec(list(embed_query(query)))
    sql = "SELECT source, content, 1 - (embedding <=> %s::vector) AS score FROM rag_chunks WHERE TRUE"
    params: list = [qvec]
    if topics:
        sql += " AND topic = ANY(%s)"
        params.append(list(topics))
    if exclude:
        sql += " AND source NOT LIKE %s"
        params.append(f"{exclude}%")
    sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params += [qvec, k]
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{"source": r[0], "content": r[1], "score": round(float(r[2]), 4)} for r in rows]
