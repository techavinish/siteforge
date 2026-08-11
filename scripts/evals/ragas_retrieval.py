"""Ragas retrieval-quality check for the RAG service.

Measures context relevancy: do the chunks our search returns actually
belong to the question asked? Requires paid OpenRouter credits.

Run:  OPENROUTER_API_KEY=... python scripts/evals/ragas_retrieval.py
"""

import os
import sys

import requests

QUESTIONS = [
    "How should a bakery website's headline be written?",
    "What makes a gym website convert young professionals?",
    "Which palette suits a premium interior designer?",
    "How should the contact page reduce friction?",
]

RAG_URL = os.environ.get("RAG_URL", "http://localhost:8002")


def main() -> None:
    try:
        from datasets import Dataset
        from langchain_openai import ChatOpenAI
        from ragas import evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import ContextRelevance
    except ImportError:
        sys.exit("pip install ragas datasets  (see scripts/evals/requirements.txt)")

    llm = LangchainLLMWrapper(ChatOpenAI(
        model=os.environ.get("JUDGE_MODEL", "openai/gpt-4o-mini"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    ))

    rows = {"user_input": [], "retrieved_contexts": []}
    for q in QUESTIONS:
        r = requests.post(f"{RAG_URL}/rag/search", json={"query": q, "k": 3}, timeout=15)
        rows["user_input"].append(q)
        rows["retrieved_contexts"].append([c["content"] for c in r.json()["results"]])

    result = evaluate(Dataset.from_dict(rows), metrics=[ContextRelevance(llm=llm)])
    print(result)


if __name__ == "__main__":
    main()
