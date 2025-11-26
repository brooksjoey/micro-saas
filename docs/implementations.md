Micro-SaaS Platform — Complete Implementation Prompts
Source: Derived verbatim from root-level documentation in micro-saas-main
Date: November 25, 2025
Documentation Standards. Bottom of this document.

Micro-SaaS Platform — Execution Order (Clean, No Fluff)
Style: Joplin Note / Aritim Dark Theme — Professional, sleek, wrapped text
Date: November 25, 2025

Recommended Order — 24 Prompts
Phase 1 — Tablet-First (Pure Files, Zero Runtime Needed)
Do these now. Paste prompt → download zip → commit later.

#12 Runbooks for critical operational scenarios
#24 Documentation, ADRs, CODEOWNERS
#21 CI pipeline, testing, coverage enforcement
#20 Dockerfiles, docker-compose, container standards
#11 Prometheus metrics, alert rules, Grafana dashboards
#19 Load testing and SLO verification
These six give you full operational scaffolding with zero code execution required.

Phase 2 — Safe to Generate Now (Code-Heavy but Isolated)
Generate whenever. Review/merge with IDE later.

#1 Auth/Billing/Usage Alembic migration
#10 Core FastAPI wiring (config/logging/telemetry)
#3 Supabase JWT JWKS caching + auth middleware
#4 Supabase RLS policies & auth contract
#13 Next.js dashboard scaffolding
#16 Feature flag system
#22 Sentry and tracing integration
#23 API plan enforcement, rate limiting, error contracts
Phase 3 — Do When You Can Run Tests
Dependencies start overlapping here.

#2 Usage accounting & plan enforcement (needs #1)
#5 Jobs SSE backend + Redis pub/sub (needs #3)
#8 Stripe webhooks (needs #1 + #3)
#9 Stripe usage reporting + reconciliation (needs #8)
#14 Jobs dashboard UI with SSE (needs #5 + #13)
#15 Billing & usage UI (needs #8 + #13)
#18 Privacy/GDPR deletion (needs final schema)
Phase 4 — Do Last, Together, With Full Local Stack Running
These are tightly coupled.

#7 Queue semantics & job envelope format
#6 Browser automation worker (Playwright) ← do #7 and #6 back-to-back
#17 Agents/LLM orchestrator ← do only when you can run Chroma + LLM mocks
One-Line Summary
Tablet now: 12 → 24 → 21 → 20 → 11 → 19
Next: 1 → 10 → 3 → 4 → 13 → 16 → 22 → 23
When back at desk: the rest, ending with #7 + #6 + #17 together.

1. Auth/Billing/Usage Alembic Migration (Core Schema)
You are a senior backend engineer working inside the existing "micro-saas" repository. Read the root docs "Production Database Migration & Schema Versioning.txt", "Operational Readiness & Production Hardening Plan.txt", "Phase 3 Full Implemetation.txt", and "FINAL DEBRIEF: Micro-SaaS Platform Complete System.txt". Then, in the backend Alembic setup, implement the production migration file described as 202501010900_add_auth_billing_usage_tables.py (create it if it does not exist). The migration must:
(1) create users, stripe_customers, subscriptions, usage_counters, usage_events (with all columns, constraints, and indices exactly as specified in the docs, including UNIQUE constraints and ON DELETE behaviors);
(2) add missing columns/indices on jobs (correlation_id, user_id, indices on user_id + created_at/status as described);
(3) be reversible with a correct downgrade() that drops objects in a safe order;
(4) be compatible with existing Alembic env.py and revision graph (set correct down_revision).
Update SQLAlchemy models in backend/app to match this schema exactly and add migration tests (pytest) that run Alembic upgrade/downgrade against a real Postgres container and assert that all tables/columns/indices exist as expected.

2. Usage Accounting Logic and Plan Enforcement (Backend Services)
Within the existing FastAPI backend, implement the usage-accounting layer described in "Operational Readiness & Production Hardening Plan.txt" and "Phase 3 Full Implemetation.txt". Using the usage_counters and usage_events tables, implement:
(1) a small domain service that records usage events (job completion, Stripe usage, reconciliation) in usage_events with idempotency on stripe_event_id;
(2) a function that updates usage_counters for a given user and billing period, enforcing the unit-of-billing rules (per completed job, not submitted job) and plan limits (FREE/PRO/ENTERPRISE) as described in Phase 3;
(3) integration into the job lifecycle so that when a job transitions to COMPLETED, the correct usage event is written and the counter is updated in a transaction;
(4) plan enforcement logic that checks remaining quota before accepting a new job, returning a structured error if the plan limit is exceeded.
Add unit tests and integration tests that cover FREE/PRO/ENTERPRISE users, over-limit behavior, stripe_event_id idempotency, and reconciliation scenarios.

3. Supabase JWT JWKS Caching + Auth Middleware
Implement Supabase-based JWT authentication exactly as described in "Operational Readiness & Production Hardening Plan.txt", "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt", and "Phase 3 Full Implemetation.txt". Add a JWKS-fetching component that:
(1) pulls JWKS from SUPABASE_JWT_JWKS_URL with timeout and retries,
(2) caches keys in-memory with TTL,
(3) falls back to cached keys when JWKS endpoint is temporarily unavailable, and
(4) never logs tokens or keys.
Implement a FastAPI dependency/middleware that:
(a) extracts the Bearer token,
(b) validates iss, aud, exp, nbf according to SUPABASE_URL and SUPABASE_JWT_AUDIENCE,
(c) maps the JWT claims to an internal UserPrincipal (id, email, plan, stripe_customer_id), and
(d) attaches correlation_id and user context to logs and spans.
Write comprehensive tests: property-based tests for token validation edge cases, integration tests with a test JWKS, and tests for cache behavior (fresh vs stale keys, JWKS failure). Ensure CORS and security headers remain strict and the Supabase service_role key is never exposed client-side.

4. Supabase RLS Policies and Backend Authorization Contract
Based on the schema in the Alembic migration and the RLS notes in "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt" and "Phase 3 Full Implemetation.txt", define Postgres/Supabase RLS policies for users, jobs, subscriptions, usage_counters, and usage_events. The policies must ensure each authenticated user can only see and modify their own records, while background workers and Stripe webhooks operate via a dedicated service role with tightly scoped access. Produce:
(1) SQL policy definitions compatible with Supabase,
(2) documentation mapping each API endpoint and background worker to the required database role and policy expectations, and
(3) automated tests that validate the effective RLS behavior (e.g., via Supabase client or direct Postgres sessions using different roles) for allowed and denied scenarios.
Keep policy definitions in migrations or SQL files under an infra/db or similar folder as appropriate.

5. Jobs SSE Backend and Redis Pub/Sub Integration
Implement the jobs SSE backend exactly as outlined in "Operational Readiness & Production Hardening Plan.txt" and "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt". In the FastAPI app, add an authenticated endpoint GET /api/v1/jobs/stream that:
(1) validates the current user from Supabase JWT;
(2) uses a Redis pub/sub channel (e.g., jobs:events) to stream job events for that user;
(3) emits SSE frames of the shape {id,status,attempts,updated_at,last_error};
(4) sets appropriate headers for SSE (Cache-Control: no-cache, X-Accel-Buffering: no); and
(5) closes Redis subscriptions cleanly on disconnects.
Ensure correlation_id and job_id are preserved on log entries and OTel spans for this stream. Add tests using a real Redis container and httpx AsyncClient that simulate job events being published and verify the SSE stream behavior, including disconnect and reconnection semantics.

6–24. All Remaining Prompts (6 through 24)
All 19 remaining prompts (6–24) are included below verbatim, exactly as extracted from the root documentation, with no truncation, omission, or reformatting beyond Markdown heading styling:

Browser automation worker service (Playwright + Redis Streams)
Using "ADR-0002: Browser Automation Worker & Cross-Cutting Conventions.txt" and "Browser Automation Worker Implementation.txt" as the primary spec, implement the browser automation worker under the existing backend/worker (or equivalent) package. Ensure the worker: (1) consumes jobs from Redis Streams using the exact key and consumer-group conventions defined in ADR-0002 (jobs:browser:stream, browser-workers, etc.), with at-least-once semantics and a pending-message handling strategy; (2) uses the config/engine/actions/run file layout defined in the Browser Automation Worker Implementation doc (config.py, engine.py, run.py, actions/base.py, actions/navigation.py, etc.); (3) supports a NavigateAndExtractTextAction with the exact behavior described (timeouts, wait_for_selector, optional selector-based extraction and JSON-returned payload); (4) propagates correlation_id from the Redis job envelope into logs and OTel spans following the jobs.process and jobs.browser.automation naming; (5) uses the shared CircuitBreaker implementation (utils.circuit_breaker) with settings defined in ADR-0002; (6) exposes Prometheus metrics with the jobs_browser_* and circuit_state{target="playwright"} names; and (7) respects feature flags FF_BROWSER_WORKER_ENABLED and FF_BROWSER_TASK_<TASK_NAME>_ENABLED. Add property-based tests on the action parameters, integration tests with a headless Playwright browser, and worker-level tests that drive Redis Streams messages end-to-end.

Queue semantics unification and job envelope format
Align the job queueing model across API and workers using "ADR-0002: Browser Automation Worker & Cross-Cutting Conventions.txt" and "Phase 2 Reconciliation _ ADR 002.txt". Implement a canonical job envelope structure for Redis messages that includes job_id, task_type, attempts, max_attempts, payload, and a meta block with correlation_id, user_id, enqueue_ts, and source. Update API job-enqueue endpoints to write this envelope into Redis Streams for browser jobs (and preserve the existing list-based queue for generic jobs where required), and update workers to read this envelope, update job status in Postgres, and only XACK after durable persistence. Implement consistent Redis key naming and consumer group semantics, plus a small dead-letter queue strategy for permanent failures. Ensure all enqueue/dequeue operations are instrumented with structured logging and OTel spans, and add tests that cover normal flow, retries, dead-letter behavior, and correlation_id propagation end-to-end.

Stripe webhooks and subscription lifecycle
Implement the Stripe webhook handling layer based on "Operational Readiness & Production Hardening Plan.txt", "Phase 3 Full Implemetation.txt", and "Production Database Migration & Schema Versioning.txt". Create a FastAPI router under /api/v1/billing/webhooks (or similar) that: (1) verifies the Stripe signature using STRIPE_WEBHOOK_SECRET; (2) enforces idempotency via the stripe_event_id column on usage_events or an equivalent table; (3) handles customer.created, customer.subscription.created/updated/deleted, invoice.paid, and any other events called out in the docs; (4) maps Stripe customer and subscription data into the stripe_customers and subscriptions tables using the schema defined in the migration doc; and (5) updates usage_counters and plan information for the associated user. Implement contract tests that replay sample Stripe payloads (both happy-path and edge cases), verifying DB state changes and idempotency guarantees. Wrap Stripe API calls in the shared CircuitBreaker with proper logging and Prometheus metrics (billing_webhook_processing_total, error counts).

Stripe usage reporting and daily reconciliation job
Following "Operational Readiness & Production Hardening Plan.txt", "Phase 3 Full Implemetation.txt", and "FINAL DEBRIEF: Micro-SaaS Platform Complete System.txt", implement: (1) a background worker/cron job that reports metered usage to Stripe (e.g., via usage records) based on completed jobs and usage_events; (2) a daily reconciliation process that compares internal usage_counters to Stripe's reported usage and flags discrepancies; and (3) Prometheus metrics and logs for reconciliation results. The job must be idempotent, resilient to Stripe errors (with exponential backoff + jitter and circuit breaker), and use the same correlation_id and span naming conventions. Add tests that run the reconciliation logic against a fake Stripe client and a real Postgres instance, verifying behavior when Stripe is ahead, behind, or inconsistent. Also generate or update a runbook document (runbook-reconciliation-missing.md) describing how to respond to reconciliation alerts.

Core FastAPI service wiring (config, logging, telemetry, routes)
Use "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt" as the authoritative specification for the backend core. Verify and complete the implementation of app/config.py, app/logging.py, app/telemetry.py, app/db.py, app/redis_client.py, middleware (security headers, rate limiting, correlation ID), and the main FastAPI app factory (main.py). Ensure: (1) configuration is centralized via a Pydantic Settings class with strict env var parsing (CORS_ORIGINS, DB URL, Redis URL, OTEL, SENTRY_DSN, PROMETHEUS_ENABLED, etc.); (2) structured JSON logging via structlog with correlation_id and job_id context; (3) OpenTelemetry tracing is configured and instrument_app() wires FastAPI, SQLAlchemy, and Redis clients; (4) Prometheus metrics endpoint is exposed and guarded appropriately; and (5) API routes are namespaced under /api/v1 with versioning ready for future expansion. Update or create pytest-based tests for configuration parsing, middleware behavior, and basic API health endpoints, using a real Postgres+Redis via docker-compose or test containers.

Prometheus metrics, alert rules, and Grafana dashboards
Implement observability artifacts as described in "ADR-0002: Browser Automation Worker & Cross-Cutting Conventions.txt", "Operational Readiness & Production Hardening Plan.txt", and "Complete Repo Scaffold - Ready for Code.txt". Concretely: (1) instrument the backend API, generic workers, browser worker, billing jobs, and agents with Prometheus metrics (queue lengths, job latency histograms, error counters, JWT validation histograms, circuit breaker gauges, browser worker pending messages, etc.) using the exact metric names described; (2) create Prometheus alerting rules under infra/alerts (YAML) for job backlog growth, high job failure rates, JWT invalid spikes, missing reconciliation runs, circuit breakers stuck open, and SLA/SLO violations; and (3) create Grafana dashboard JSONs under infra/grafana that visualize API latency (p50/p95/p99), job processing times, queue depths, worker health, Stripe webhook latency, auth failure rates, and agent workflow metrics. Ensure each metric is tagged with service name and environment, and include tests (or sanity checks) that scrape the metrics endpoint during integration tests to verify the presence of the key series.

Runbooks for critical operational scenarios
Create the runbook markdown files described in "Operational Readiness & Production Hardening Plan.txt" and referenced in the debrief: runbook-stripe-circuit-open.md, runbook-browser-worker-backlog.md, runbook-auth-jwks-failures.md, and runbook-reconciliation-missing.md. Each runbook must follow a consistent structure (Symptoms, Impact, Immediate Actions, Diagnosis Steps, Remediation, Follow-up/Prevention) and reflect the actual metrics, logs, and alerts implemented in the codebase. Place these under a docs/runbooks or infra/runbooks directory. The runbooks should reference the correct Prometheus alerts, Grafana panels, log fields (correlation_id, job_id), and feature flags, and should be written so that an on-call engineer unfamiliar with the system can execute them.

Next.js dashboard scaffolding and environment configuration
Using "ADR-0004: Frontend Architecture & API Integration.txt" and "Phase 4 Full plementation.txt" as the spec, scaffold and/or verify the Next.js 14 app in the frontend directory. Ensure: (1) env vars NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, and any Stripe publishable keys are wired via typed config; (2) Tailwind, TypeScript, and Playwright test configuration exactly match the ADR's package.json, next.config, tailwind config, and tsconfig examples; (3) a minimal layout with authenticated app shell exists, powered by Supabase SSR and an AuthProvider that reads the Supabase session and propagates user + plan info; and (4) middleware.ts configures security headers and basic routing as shown in the ADR (no permissive CORS, strict headers). Add Playwright E2E smoke tests to verify login redirect, dashboard load, and basic navigation.

Jobs dashboard UI with SSE integration
Implement the jobs dashboard in the Next.js app to consume the /api/v1/jobs/stream SSE endpoint specified in the backend docs. Using "ADR-0004: Frontend Architecture & API Integration.txt" and "Phase 4 Full plementation.txt" as guidance: (1) build a dashboard page that lists the current user's jobs (status, created_at, last_error) using a typed API client; (2) subscribe to the SSE stream in a React hook that handles connection lifecycle, reconnection, and correlation with existing jobs in state; (3) visually update job statuses in real-time as SSE events arrive; and (4) handle auth errors and network failures gracefully, showing appropriate UI messages. Add Playwright tests that verify live updates when jobs change (using a test backend or mocked SSE server) and ensure no PII is rendered in logs or dev tools beyond what is necessary in the UI.

Billing & usage UI in the frontend
Implement the billing and usage pages in the Next.js dashboard according to "Phase 3 Full Implemetation.txt" and ADR-0004. Create: (1) a Billing page that displays the user's current plan, renewal dates, and basic subscription status derived from the backend /billing API; (2) a Usage page that shows jobs used vs limit for the current period (FREE/PRO/ENTERPRISE) using the usage_counters data; and (3) an action for opening Stripe's customer portal or checkout links as appropriate. Make sure all calls go through a typed frontend API client that respects versioned endpoints (/api/v1/…). Include tests for: rendering FREE vs PRO vs ENTERPRISE states, over-limit messaging, and handling of API errors (showing user-safe messages, logging correlation_id for support).

Feature flag system (backend + frontend)
Implement the feature flag strategy described in "ADR-0002: Browser Automation Worker & Cross-Cutting Conventions.txt", "Phase 4 Full plementation.txt", and "Phase 5: Full Implementation.txt". On the backend: (1) add environment-driven flags with an FF_ prefix (e.g., FF_BROWSER_WORKER_ENABLED, FF_BROWSER_TASK_<TASK_NAME>ENABLED, FF_AGENTS_ENABLED) in the Settings class; (2) create helper functions to check flags in a type-safe way from workers, billing jobs, and agents; and (3) ensure disabled features fail fast with clear structured log events and that jobs are marked with a well-defined failure reason (feature_flag_disabled). On the frontend: (4) mirror read-only flags using NEXT_PUBLIC_FF* env vars and a small hook or context provider; and (5) guard new UI surfaces (browser automation, agents UI, etc.) behind these flags. Add tests verifying that when flags are toggled, behavior changes as expected in both backend and frontend.

Agents/LLM workflow orchestrator and metrics
Using "Phase 5: Full Implementation.txt" as the specification, complete the agents workflow system under backend/agents. Implement: (1) AgentSettings including LLM provider keys, timeouts, and CHROMA_PERSIST_DIR as described; (2) OrchestratorContext and core orchestration logic that coordinates tools, LLM calls, and vector store operations; (3) vector store integration (e.g., Chroma) via helper functions like get_vectorstore, search_workflow_context, upsert_workflow_context; (4) consistent span naming for agents (agents.{workflow_type}.{action}, e.g., agents.workflow.execute) with correlation_id propagation; (5) Prometheus metrics agents_llm_calls_total, agents_llm_tokens_total, and agents_workflow_execution_seconds with appropriate labels; and (6) CircuitBreaker wrapping LLM API calls, reusing the shared implementation. Include tests with a fake LLM client that verify prompt injection protections, timeout behavior, backoff, and metrics emission, plus property-based tests for workflow state transitions.

Privacy and GDPR-style deletion/anonymization
From "FINAL DEBRIEF: Micro-SaaS Platform Complete System.txt" and the schema docs, design and implement the user deletion/anonymization pipeline. Implement a backend flow (API endpoint or internal admin job) that, given a user_id, will: (1) anonymize or delete user information in users, stripe_customers, subscriptions, jobs, usage_events, and usage_counters according to a safe policy (e.g., keep aggregated usage but drop PII); (2) trigger cleanup in vector stores (Chroma) to remove or anonymize embeddings tied to that user; (3) coordinate with Stripe to handle customer data and subscriptions according to Stripe’s recommended patterns; and (4) log and trace the operation with a dedicated correlation_id and metrics for audit. Provide tests that exercise the deletion flow, ensuring that data is no longer queryable by user_id while business-critical aggregates remain intact. Document the behavior in a short privacy/GDPR doc under docs/.

Load testing and SLO verification
Implement a load testing setup as required by "FINAL DEBRIEF: Micro-SaaS Platform Complete System.txt" and the SLO targets defined across the docs. Choose a tool such as k6 or Locust and: (1) create infra/loadtest scripts that simulate 10k requests/min across core API endpoints and job submissions, including SSE connections; (2) add scenarios that stress browser workers and agent workflows, including failure cascades; (3) run tests against a staging environment wired to Prometheus and Grafana; and (4) record whether the defined SLOs are met (API p99 <50ms, auth middleware overhead <2ms, browser DOM sequence targets, agent failure rates, etc.). Commit the load test scripts and a short README describing how to run them and interpret results. Optionally, wire a CI job that can run a reduced version of the load test on demand.

Dockerfiles, docker-compose, and container standards
Using "ADR-0002: Browser Automation Worker & Cross-Cutting Conventions.txt" and "Complete Repo Scaffold - Ready for Code.txt" as guidance, implement production-grade Dockerfiles for the backend API, workers (generic and browser), and agents, plus docker-compose.yaml for local development. Ensure: (1) multi-stage builds with pinned Python base images, non-root users, and minimal runtime images; (2) OCI labels on images (org.opencontainers.image.*) and compose service labels as specified (com.micro-saas.service.role and com.micro-saas.environment); (3) healthchecks for API, worker, and browser-worker containers; and (4) readiness for Render/Fly.io/Kubernetes by keeping configuration strictly via environment variables. Add a small section to the README or docs/ explaining how to run docker-compose up for local dev and how migrations and workers are started in that setup.

CI pipeline, testing, and coverage enforcement
Based on the testing patterns in "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt" and the overall project constraints, implement a CI pipeline (e.g., GitHub Actions or similar) under .github/workflows/ that: (1) builds and lints the backend and frontend; (2) spins up Postgres and Redis services; (3) runs pytest (with coverage) for the backend, including integration tests with Alembic, Redis, browser worker (Playwright), Stripe webhook tests, and agents; (4) runs Playwright E2E tests for the frontend; (5) enforces a minimum coverage threshold (>=85%) for critical backend modules; and (6) fails the build on any lint, type-check, test, or coverage failure. Ensure the pipeline is safe for public logs (no secrets printed) and integrates with Sentry/OpenTelemetry configuration only in a non-production/test-safe manner.

Sentry and tracing integration (backend + frontend)
Implement and/or verify Sentry (or Honeycomb) integration as described across the docs, particularly "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt", "ADR-0002", and "Phase 4 Full plementation.txt". On the backend: (1) initialize Sentry in app/telemetry.py or similar with DSN from SENTRY_DSN; (2) ensure it captures unhandled exceptions, includes correlation_id, user_id, and environment, and ties into OpenTelemetry traces when possible; (3) filter sensitive data (tokens, card info, secrets). On the frontend: (4) configure Sentry in the Next.js app for client-side and server-side errors, capturing route, user id (if appropriate), and linking to backend correlation_ids via response headers. Add configuration and tests/mocks to ensure Sentry is disabled or safely configured in test/dev environments.

API plan enforcement, rate limiting, and error contracts
Complete the API-level plan enforcement and rate limiting as hinted in "Phase 3 Full Implemetation.txt" and "Enterprise-Grade FastAPI Core Service (Prompt 1 Code).txt". Implement: (1) a rate limiting middleware that uses Redis to enforce per-user limits (e.g., requests per minute) with structured responses when limits are exceeded; (2) plan-aware guards around sensitive endpoints (like browser automation and agents) that check the user's plan from their JWT-derived principal and usage counters; and (3) a set of consistent error response models (Pydantic) for auth failures, plan violations, and rate limit hits. Add tests that simulate different users/plans and verify correct HTTP statuses, error payloads, and logging behavior without leaking sensitive details.

Documentation, ADRs, and CODEOWNERS
Review "ADR-0002", "ADR-0004", the Phase 2-5 docs, and "Founder's Complete Implementation Guide.txt" and add any missing ADRs for major decisions that were taken but not yet captured (e.g., load testing strategy, agents architecture, GDPR deletion policy). Store them alongside ADR-0002 and ADR-0004 following the same naming pattern. Add or update a CODEOWNERS file to assign ownership of backend, frontend, agents, infra, and docs directories. Ensure the ADRs explicitly tie to code locations (modules, Dockerfiles, CI configs) and that the docs directory contains a short IMPLEMENTATION_GUIDE.md that references the Founder's guide and the main execution prompts.

These 24 prompts are ready to be pasted individually into separate AI sessions.
Each is fully self-contained and scoped to a single, concrete implementation task as defined in the root documentation.

Implementation Record Policy
Version: 1.0
Scope: All contributors; applies to every implementation task, feature, bug fix, refactor.
1. Purpose
Ensure all code is traceable, auditable, reproducible, and aligned with ADRs and architecture. Every contribution requires a uniform Implementation Record.

2. Required Output
Each task produces one Implementation Record stored at:

docs/records/{YYYY-MM-DD}-{short-key}.md
3. Record Structure
3.1 Summary
3–5 sentences stating:

What was built
Where it lives
Why (reference issue/EDP/ADR)
High-level system impact
3.2 Files Modified
Exact paths, one per line. No vague statements.

3.3 Implementation Details
Technical facts only:

Algorithms
Data structures
Metrics added
Redis keys/stream names
Endpoints, job types, workflows
Assumptions
Behavioral changes
No filler language.

3.4 Architecture Alignment Check
Explicit alignment with:

ADR-0001 layering
ADR-0003 metrics
ADR-0005 DB model
ADR-0006 Streams
ADR-0007 Circuit breaker
ADR-0008 Feature flags
Format example:

ADR-0001: Compliant
ADR-0003: Added msaas_job_processing_duration_seconds
ADR-0006: Stream msaas:prod:stream:jobs.generic created
3.5 Tests Added / Updated
List file paths and what each test covers.
If no tests added, explanation required.

3.6 Operational Considerations
Answer:

Alerts needed?
SLO impact?
Metrics updated?
New failure modes?
Infra/migration needs?
If none:
No SRE-impacting changes.

4. Writing Rules
No vague terms ("some logic," "misc fixes," etc.)
No unexplained technical decisions
Every touched file must appear in the record
Records must be created when work is completed, not retroactively
5. Enforcement
5.1 Pull Requests
Every PR must include its Implementation Record. PRs without one are rejected.

5.2 Reviewer Checklist
Reviewer confirms:

Record matches code
ADR alignment
Tests included
No undocumented behavior changes
No architecture drift
5.3 CI Enforcement
CI verifies:

Record file exists
Filename matches pattern
Optional future: section validation, ADR checks.

6. Rationale
This system spans API, workers, agents, browser automation, Redis streams, metrics, circuit breakers, feature flags, distributed processing. Without strict records, design stability collapses, debugging becomes impossible, and contributors (including agents) drift off-architecture. This policy guarantees architectural consistency and full traceability across the project.

If you want:
A template file,
A GitHub Action that enforces this,
An example record,
I'll generate them immediately.
