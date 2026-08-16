"""Central config — every knob is an env var, no values in code.

Model strategy (design decision, not accident) — TWO TIERS by task:
- WRITER_MODEL / PLAN_MODEL: the best we can afford — these produce the
  customer-visible copy and the design decisions, where quality shows.
- INTERVIEW_MODEL: the "cheap" tier — extraction, scoring, quick-replies,
  titles. Easy structured work that doesn't need a frontier model.

Why two tiers matters on the free tier: OpenRouter's 50/day cap is shared
across ALL free models, so routing the cheap tier to another *free
OpenRouter* model saves nothing. The real lever is pointing the cheap tier
at a LOCAL model (Ollama) that never touches OpenRouter — then only the
writer + planner spend the daily budget. Flip it on with:
    CHEAP_LLM_BASE_URL=http://localhost:11434/v1
    INTERVIEW_MODEL=llama3.1:8b            (any pulled Ollama model)
Everything defaults to the current single-model behaviour — zero regression
when the vars are unset. Cost/quality policy lives HERE, not in nodes.
"""

import os

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_FREE = "google/gemma-4-26b-a4b-it:free"
# quality tier — website copy + the design plan
WRITER_MODEL = os.environ.get("WRITER_MODEL", _FREE)
PLAN_MODEL = os.environ.get("PLAN_MODEL", WRITER_MODEL)
# cheap tier — extraction, critique, quick-replies, titles; can live on a
# separate (e.g. local Ollama) endpoint to stay off the OpenRouter budget
INTERVIEW_MODEL = os.environ.get("INTERVIEW_MODEL", _FREE)
# when set, the cheap tier talks to this base URL / key instead of OpenRouter
CHEAP_LLM_BASE_URL = os.environ.get("CHEAP_LLM_BASE_URL", "")
CHEAP_LLM_API_KEY = os.environ.get("CHEAP_LLM_API_KEY", "ollama")

GCP_PROJECT = os.environ.get("GCP_PROJECT", "siteforge-dev-3977")

# checkpointer target — three forms, most specific wins:
#   DATABASE_URL          explicit (local dev via docker postgres)
#   CLOUDSQL_CONN + DB_*  Cloud Run: unix socket mounted at /cloudsql,
#                         password injected from Secret Manager
#   fallback              local docker default
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
