# SiteForge — Build Plan & Status

> Living document. Full architecture with diagrams: [`docs/whitepaper/architecture-blueprint.html`](whitepaper/architecture-blueprint.html)
> **The product:** a copilot that interviews a business owner, generates their website, deploys it, and continuously evaluates its own output.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| P0 | Monorepo, docker-compose spine (postgres+pgvector, redis, clickhouse, temporal), gitleaks CI | ✅ 2026-08-03 |
| P1 | Terraform + GCP foundation — state in GCS, budget alert, hello Cloud Run | ✅ 2026-08-03 |
| P2 | Firebase Hosting + Google SSO — live app, gateway verifying ID tokens | ✅ 2026-08-03 |
| P3 | Cloud SQL + schema, Artifact Registry, keyless CI/CD (WIF), `/api` rewrite live | ✅ 2026-08-03 |
| P4 | **LangGraph agent** — interview→plan→write→review graph, postgres checkpoints | 🔶 core done 2026-08-03 |
| P5 | Temporal — durable GenerateSiteWorkflow, approval signal, real deploy activity | ⬜ |
| P6 | RAG — ingestion, pgvector retrieval node, measured quality diff | ⬜ |
| P7 | Remote MCP server on Cloud Run — external clients build sites via our tools | ⬜ |
| P8 | ClickHouse medallion (bronze→silver→gold→platinum) + nightly eval cron | ⬜ |
| P9 | Redis patterns (rate limit, cache), Sentry, load test | ⬜ |
| P10 | Whitepaper on Notion, prod env, demo | ⬜ |

## P4 — remaining work

- [x] Chat UI wired to agent SSE — full protocol: thinking deltas, tokens, suggestions, error events; multi-chat, rename/delete, URL routing, stop, smart scrolling
- [x] Message store: agent-owned `chats` + `messages` tables (thinking + artifacts persisted per message)
- [x] `deploy_site` — Publish button → per-business Firebase Hosting site (VERIFIED LIVE: sf-sweet-rani-bakery-120d.web.app); `publish.py` is the SiteDeployer seam for the 36-site cap
- [x] Agent on Cloud Run: firebase ID token verification on every endpoint (identity from token, ownership checks), module gained `secret_env` + `cloudsql_instances`, secrets injected from Secret Manager, unix-socket to Cloud SQL, `deploy-agent.yml` CI
- [x] Hosting rewrite `/agent/**` → agent service — hosted app fully functional end to end
- [ ] `pick_images` tool (stock photo API) + logo into render pipeline
- [ ] Mirror drafts into Cloud SQL `sites` / `site_versions` tables (agent tables now live IN Cloud SQL for the hosted path; local docker pg for dev)

## Key decisions (and why)

- **Monorepo**, path-filtered CI — shared types, atomic changes, one-person team
- **FE:** Vite+React+TS (not Next — no SSR need behind login); **BE:** Python everywhere (agent ecosystem); OpenAPI as the FE/BE type bridge
- **Temporal = deterministic spine, LangGraph = reasoning inside an activity** (they nest, not compete)
- **Model routing as config:** free `gemma-4-26b` for all nodes now; when OpenRouter credits added → `deepseek-chat-v3.1` (writer) / `gpt-4o-mini` (structured). Cost policy lives in `services/agent/config.py`, nowhere else
- **Terraform owns service shape, CI owns image contents** (lifecycle ignore on image)
- **Secrets:** Secret Manager + `.env` (gitignored) only. Public repo carries identifiers, never credentials
- **`site_versions` append-only** — rollback is a pointer move; eval can score history

## Known issues / debts

- Gateway's direct `run.app` URL 404s at Google's edge (routes ready, DNS fine; hosting path unaffected). Fix if ever needed: destroy/recreate the service via terraform
- Free-tier OpenRouter ≈ 50 req/day — add $10 credits when the limit bites
- `python3` on this machine resolves to a broken Homebrew 3.14 — services pin `python3.12`
- Firebase Hosting caps 36 sites/project — generated-site deploys must go behind a `SiteDeployer` interface before customer #37

## Environments

- **Local:** docker-compose (see README); agent/gateway venvs on python3.12
- **Cloud dev:** GCP `siteforge-dev-3977` (asia-south1), all via `infra/envs/dev`; app at https://siteforge-dev-3977.web.app
- **Trial budget:** ₹28,694 credits to 2026-11-02; ₹2000/mo budget alert as code
