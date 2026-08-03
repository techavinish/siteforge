"""Central config — every knob is an env var, no values in code.

Model strategy (design decision, not accident):
- INTERVIEW_MODEL: cheap/free — extracting answers into a brief is easy work
- WRITER_MODEL:    the best we can afford — customer-visible copy
- On the free tier both point at the same free model; when credits are
  added, only these two lines change. Cost policy lives HERE, not in nodes.
"""

import os

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

INTERVIEW_MODEL = os.environ.get("INTERVIEW_MODEL", "google/gemma-4-26b-a4b-it:free")
WRITER_MODEL = os.environ.get("WRITER_MODEL", "google/gemma-4-26b-a4b-it:free")

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
