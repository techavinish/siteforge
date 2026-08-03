# SiteForge

**An AI copilot that builds business websites.** A business owner signs in with Google, describes their business in chat, and the agent plans the site, writes the copy, assembles the pages, deploys it live — then keeps evaluating and improving it.

> This is a learning-driven build: one real product touching every layer of the modern agent stack. Full architecture + 12-week plan: [`docs/whitepaper/architecture-blueprint.html`](docs/whitepaper/architecture-blueprint.html)

## Architecture at a glance

| Layer | Tech |
|---|---|
| Frontend + generated sites | React (Vite) + Firebase Hosting, Google SSO via Firebase Auth |
| Backend (6 microservices) | Python / FastAPI on GCP Cloud Run |
| Agent | LangGraph + OpenRouter |
| Durable orchestration | Temporal (agent runs inside an activity) |
| RAG | pgvector on Postgres |
| Tools surface | Remote MCP server |
| Evaluation | Cloud Scheduler cron → LLM-as-judge → ClickHouse |
| Data platform | Medallion (Bronze/Silver/Gold/Platinum) on ClickHouse |
| Operational stores | Postgres (Cloud SQL), Redis |
| Infra | 100% Terraform — zero console-created resources |
| Observability | Sentry + self-built traces in ClickHouse |

## Local development

```sh
docker-compose up -d
```

| Service | Where |
|---|---|
| Postgres (+pgvector) | `localhost:5432` (user/db: `siteforge`) |
| Redis | `localhost:6379` |
| ClickHouse | `http://localhost:8123` |
| Temporal | `localhost:7233` (gRPC) |
| Temporal Web UI | `http://localhost:8233` |

## Repo layout

```
apps/web/           copilot UI (React + Vite)
services/           gateway · agent · rag · workers · mcp · eval  (Python/FastAPI)
packages/py-shared/ shared Pydantic models, event schemas, prompt library
infra/              Terraform — modules + envs (dev/prod)
docs/whitepaper/    architecture blueprint → becomes the Notion whitepaper
```

## Build phases

- [x] **P0** — repo, docker-compose spine, secret scanning
- [ ] **P1** — Terraform + GCP foundation
- [ ] **P2** — Firebase Hosting + Google SSO
- [ ] **P3** — Postgres schema + CI/CD
- [ ] **P4** — LangGraph agent + OpenRouter
- [ ] **P5** — Temporal durable generation
- [ ] **P6** — RAG pipeline (pgvector)
- [ ] **P7** — Remote MCP server
- [ ] **P8** — ClickHouse medallion + eval flywheel
- [ ] **P9** — Redis patterns + Sentry hardening
- [ ] **P10** — Whitepaper + prod
