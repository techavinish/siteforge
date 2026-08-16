"""LLM access — one place that knows OpenRouter exists."""

import json
import re

from langchain_openai import ChatOpenAI

from config import (
    CHEAP_LLM_API_KEY,
    CHEAP_LLM_BASE_URL,
    INTERVIEW_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)


def chat_model(model: str, temperature: float = 0.7) -> ChatOpenAI:
    """Pick the endpoint from the model TIER: the cheap-tier model can live
    on a separate base URL (e.g. a local Ollama) so it never spends the
    OpenRouter daily budget. Everything else talks to OpenRouter. Both are
    OpenAI-compatible, so one client class serves both."""
    if CHEAP_LLM_BASE_URL and model == INTERVIEW_MODEL:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=CHEAP_LLM_API_KEY,
            base_url=CHEAP_LLM_BASE_URL,
        )
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


def text_of(content) -> str:
    """Model content is a string — until a model returns content BLOCKS
    (a list of {'type': 'text', ...} parts, seen on several OpenRouter
    models). Every consumer must flatten before regex/strip/parse."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in content
            if isinstance(part, (str, dict))
        )
    return str(content or "")


def extract_json(text) -> dict:
    """Free models don't support strict JSON mode — parse defensively.

    Handles plain JSON, ```json fences, JSON embedded in prose, and
    list-shaped content blocks. Raises ValueError if nothing parseable
    is found (caller decides policy).
    """
    text = text_of(text)
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
