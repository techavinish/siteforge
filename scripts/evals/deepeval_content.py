"""DeepEval content-quality check for a generated site.

GEval judges a live page against the same rubric dimensions the nightly
judge uses, giving a second, framework-standard opinion. Requires paid
OpenRouter credits (deepeval drives an openai-compatible judge model).

Run:  OPENROUTER_API_KEY=... python scripts/evals/deepeval_content.py <url>
"""

import os
import re
import sys

import requests


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://sf-ink-iron-tattoo-stud-6fd7.web.app"
    try:
        from deepeval import evaluate
        from deepeval.metrics import GEval
        from deepeval.models import GPTModel
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except ImportError:
        sys.exit("pip install deepeval  (see scripts/evals/requirements.txt)")

    # deepeval speaks openai — point it at openrouter
    os.environ.setdefault("OPENAI_API_KEY", os.environ["OPENROUTER_API_KEY"])
    os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    judge = GPTModel(model=os.environ.get("JUDGE_MODEL", "openai/gpt-4o-mini"))

    html = requests.get(url, timeout=20).text
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)[:6000]

    metric = GEval(
        name="small-business-site-quality",
        criteria=(
            "The copy is specific to this exact business (names, places, real "
            "details), clear about what is offered and what to do next, and "
            "holds one consistent tone throughout."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model=judge,
        threshold=0.7,
    )
    case = LLMTestCase(input=f"Website copy for {url}", actual_output=text)
    result = evaluate([case], [metric])
    print(result)


if __name__ == "__main__":
    main()
