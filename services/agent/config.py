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

# checkpointer target: local docker postgres in dev, Cloud SQL in prod
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://siteforge:siteforge_dev@localhost:5432/siteforge",
)
