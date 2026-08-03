"""LLM-as-judge — content quality scoring via OpenRouter.

Degrades gracefully: no key or a rate limit yields no judge rows, never a
failed evaluation run. DeepEval's GEval can wrap this later; the rubric
below is the contract either way.
"""

import json
import os
import re

import requests

RUBRIC = """Score this small-business web page copy 1-10 on each dimension:
- specificity: concrete details vs generic filler
- clarity: a stranger understands what's offered and what to do next
- tone_consistency: one voice throughout
Reply ONLY JSON: {"specificity": n, "clarity": n, "tone_consistency": n}"""


def judge_page(page_text: str) -> list[dict]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return []
    model = os.environ.get("JUDGE_MODEL", "google/gemma-4-26b-a4b-it:free")
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": RUBRIC},
                    {"role": "user", "content": page_text[:6000]},
                ],
                "max_tokens": 100,
            },
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.DOTALL)
        scores = json.loads(m.group(0))
        return [
            {"check": f"judge_{k}", "score": float(v), "detail": f"llm judge ({model})"}
            for k, v in scores.items()
            if isinstance(v, (int, float))
        ]
    except Exception:
        return []  # judge unavailable — deterministic checks still stand
