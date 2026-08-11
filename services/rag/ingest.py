"""Ingestion — corpus markdown → chunks → embeddings → pgvector.

Chunking strategy: one chunk per `##` section. The corpus is written with
self-contained sections, so structural chunking beats arbitrary character
windows — each chunk is one complete idea with its heading as context.

Run:  python ingest.py            (ingests ./corpus)
"""

import pathlib
import re
import sys

import store


def chunk_markdown(text: str) -> list[str]:
    parts = re.split(r"\n(?=## )", text)
    chunks = []
    for part in parts:
        section = part.strip()
        if section.startswith("# "):  # document title line only
            section = "\n".join(section.splitlines()[1:]).strip()
        if section:
            chunks.append(section)
    return chunks


# which knowledge serves which stage of generation
TOPIC_BY_SOURCE = {
    "design-craft": "design",
    "surface-modes": "design",
    "theme-library": "design",
}


def main(corpus_dir: str = "corpus") -> None:
    store.setup()
    total = 0
    for path in sorted(pathlib.Path(corpus_dir).glob("*.md")):
        chunks = chunk_markdown(path.read_text())
        n = store.replace_source(path.stem, chunks, TOPIC_BY_SOURCE.get(path.stem, "copy"))
        print(f"  {path.stem}: {n} chunks")
        total += n
    print(f"ingested {total} chunks")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "corpus")
