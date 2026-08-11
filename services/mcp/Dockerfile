# build context is services/ (see cloudbuild-mcp.yaml) — the MCP server
# reuses the agent's pipeline modules directly
FROM python:3.12-slim

WORKDIR /app
COPY agent/requirements.txt agent-requirements.txt
COPY mcp/requirements.txt .
RUN pip install --no-cache-dir -r agent-requirements.txt -r requirements.txt

COPY agent/ agent/
COPY mcp/server.py .

ENV PORT=8003
CMD exec python server.py
