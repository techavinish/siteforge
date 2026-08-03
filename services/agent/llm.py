"""LLM access — one place that knows OpenRouter exists."""

import json
import re

from langchain_openai import ChatOpenAI

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL


def chat_model(model: str, temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            # OpenRouter attribution headers (shown on their dashboard)
            "HTTP-Referer": "https://siteforge-dev-3977.web.app",
            "X-Title": "SiteForge",
        },
    )


def extract_json(text: str) -> dict:
    """Free models don't support strict JSON mode — parse defensively.

    Handles plain JSON, ```json fences, and JSON embedded in prose.
    Raises ValueError if nothing parseable is found (caller decides policy).
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    embedded = re.search(r"\{.*\}", text, re.DOTALL)
    if embedded:
        return json.loads(embedded.group(0))
    raise ValueError(f"no JSON found in model output: {text[:200]}")
