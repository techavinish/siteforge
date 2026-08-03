# SiteForge: An AI Copilot that Builds, Publishes, and Improves Business Websites

## Abstract

SiteForge is a production-grade learning project: a copilot where a business owner signs in with Google, describes their business in one sentence, and receives a complete, photographed, published website in minutes. It was built to exercise every layer of the modern agent stack — LangGraph agents, Temporal durable execution, RAG, remote MCP, a medallion data platform, and full infrastructure-as-code on Google Cloud — with each technology earning its place by teaching one concept properly.

## System architecture

Two deployment surfaces, both created entirely by Terraform. Firebase Hosting serves the copilot app and every generated customer site; GCP Cloud Run hosts the microservices: gateway (token verification), agent (LangGraph), rag (retrieval), mcp (remote tool surface), workers (Temporal), and eval. Postgres (Cloud SQL) is the operational store; ClickHouse carries the analytical medallion; Redis handles rate limits and caching; secrets exist only in Secret Manager.

The public repository is github.com/techavinish/siteforge. Zero resources were created in a console.

## The Temporal × LangGraph pattern

The two orchestrators are not competitors — they nest. Temporal workflows must be deterministic (that is how they replay after a crash), so every non-deterministic step — each LLM call, each external API — lives in an activity. LangGraph is the agent's brain: an explicit graph (understand → respond → plan → illustrate → write → review → deliver) whose control flow is decided by edges, never by trusting the model to stop.

The proof this pattern works: a GenerateSiteWorkflow was started, its worker process was killed mid-wait at the human-approval gate, a brand-new worker process picked the workflow up with state intact, received the approve signal, and published the site. Workers are disposable; work is not.

## The agent

The interview is split into two nodes because structured output and streamable output never mix in one call: `understand` silently extracts a typed brief (surfacing as a "Thinking" block in the UI), and `respond` speaks pure prose, streamed token by token. Generation is grounded by retrieval: before writing, the agent pulls the top guidelines for the business type and tone from a pgvector knowledge base — headline craft, local SEO discipline, page structure patterns, industry notes. Photography is a deterministic node: no LLM, just Pexels queried with the business and page purpose.

Every conversation is checkpointed in Postgres. Each user turn is a separate graph run resumed from the checkpoint — durable multi-turn chat without a long-lived process.

## The artifact is backend-born

An early frontend prototype assembled the website preview in the browser. That was wrong, and the fix became a design principle: everything the customer's site is made of — HTML, theme, fonts, photos — is produced by the backend renderer, and the preview iframe merely points at it. The published site and the preview are the same bytes; they cannot drift.

## Security model

All agent endpoints verify Firebase ID tokens cryptographically; identity comes from the token's claims, never from the client. Thread ownership returns 404 to strangers. CI deploys through Workload Identity Federation — GitHub proves its identity to Google per-run with short-lived OIDC tokens; no service-account keys exist anywhere. Secrets live in Secret Manager and are injected into Cloud Run at runtime; the public repo carries identifiers, never credentials, with gitleaks scanning every push.

## Data platform

The medallion lives in ClickHouse. Bronze is append-only raw events — every agent turn, publish, and evaluation. Silver types those events into queryable steps with costs and scores. Gold aggregates business metrics: generation success rates, score trends, cost per site. Platinum closes the flywheel: the highest-scoring generated pages are re-ingested into the RAG corpus as proven examples, so every excellent site makes the next site better.

Evaluation runs on a Temporal schedule: deterministic checks (structure, CTAs, alt text, locality signals) always, LLM-as-judge scoring for content quality, with DeepEval metrics for generation and Ragas for retrieval quality.

## Lessons that only debugging teaches

A full disk broke everything at once and looked like five unrelated bugs. Timeouts across multiple services meant resource starvation, not code. Firebase Hosting caps 36 sites per project, so publishing hides behind a SiteDeployer seam. CSS variables do not resolve inside SVG presentation attributes — an invisible-icon hunt worth a page of its own. Free-tier LLM quotas are a real architectural constraint: retries with backoff in Temporal activities turned rate limits from failures into delays.

## Costs

Development ran almost entirely on free tiers: Cloud Run scale-to-zero, the GCP trial, local embeddings via fastembed (zero API cost), Pexels' free API, and OpenRouter's free model tier. The one fixed cost is Cloud SQL's smallest instance. A complete generated website costs a few cents in tokens on paid models — or nothing on free ones.

## Status and results

Phases complete: infrastructure, auth, CI/CD, agent, durable workflows, RAG, remote MCP, observability (Sentry, Langfuse, Grafana). Three demonstration sites are live on Firebase Hosting, built end-to-end by the agent — interview to photography to publish — including one built and published entirely through the MCP tool surface by an external client.

Built in public, by one person, learning each layer properly — with an AI pair programmer doing the typing.
