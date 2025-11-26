# Micro-SaaS Platform Implementation Guide

## Overview

This document provides a comprehensive guide for implementing and maintaining the Micro-SaaS platform. It references the Architecture Decision Records (ADRs) and provides practical guidance for developers.

## Quick Start

### Local Development Setup

1. **Clone and install dependencies**:
   ```bash
   git clone <repository>
   cd micro-saas
   ```

2. **Backend setup**:
   ```bash
   cd backend
   pip install -r requirements.txt
   cp .env.example .env  # Configure environment
   ```

3. **Start services with Docker Compose**:
   ```bash
   docker-compose up -d postgres redis
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

4. **Frontend setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Architecture Overview

The platform follows a layered architecture (see [ADR-0001](adrs/ADR-0001-core-architecture-and-layering.md)):

```
┌─────────────────────────────────────────┐
│            Presentation Layer           │
│  (FastAPI Routes, Next.js Dashboard)    │
├─────────────────────────────────────────┤
│            Application Layer            │
│     (Services, Use Cases, Workers)      │
├─────────────────────────────────────────┤
│              Domain Layer               │
│    (Models, Schemas, Business Logic)    │
├─────────────────────────────────────────┤
│           Infrastructure Layer          │
│   (Database, Redis, Stripe, Supabase)   │
└─────────────────────────────────────────┘
```

## Key ADRs

| ADR | Topic | Status |
|-----|-------|--------|
| [ADR-0001](adrs/ADR-0001-core-architecture-and-layering.md) | Core Architecture | Accepted |
| [ADR-0002](adrs/ADR-0002%3A%20Browser%20Automation%20Worker%20%26%20Cross-Cutting%20Conventions.txt) | Browser Worker & Conventions | Accepted |
| [ADR-0003](adrs/ADR-0003-metrics-naming-conventions.md) | Metrics Naming | Accepted |
| [ADR-0004](adrs/ADR-0004%3A%20Frontend%20Architecture%20%26%20API%20Integration.txt) | Frontend Architecture | Accepted |
| [ADR-0005](adrs/ADR-0005-database-schema-strategy.md) | Database Schema | Accepted |
| [ADR-0006](adrs/ADR-0006-redis-streams-queue-semantics.md) | Redis Streams | Accepted |
| [ADR-0007](adrs/ADR-0007-circuit-breaker-pattern.md) | Circuit Breaker | Accepted |
| [ADR-0008](adrs/ADR-0008-feature-flags-system.md) | Feature Flags | Accepted |
| [ADR-0009](adrs/ADR-0009-gdpr-data-deletion-policy.md) | GDPR Deletion | Accepted |
| [ADR-0010](adrs/ADR-0010-load-testing-slo-strategy.md) | Load Testing & SLOs | Accepted |

## Implementation Phases

### Phase 1: Foundation (Tablet-First)
- Runbooks for operational scenarios
- Documentation and ADRs
- CI/CD pipeline
- Docker configuration
- Prometheus metrics and Grafana dashboards
- Load testing scripts

### Phase 2: Core Backend
- Auth/Billing/Usage Alembic migration
- Core FastAPI wiring
- Supabase JWT authentication
- RLS policies
- Feature flag system
- Sentry integration
- API plan enforcement

### Phase 3: Integration
- Usage accounting
- Jobs SSE backend
- Stripe webhooks
- Usage reporting
- Frontend dashboards
- GDPR deletion

### Phase 4: Advanced Features
- Queue semantics unification
- Browser automation worker
- LLM/Agents orchestrator

## Code Standards

### Backend (Python)

- **Style**: PEP 8, black formatter
- **Types**: Full type hints with mypy
- **Testing**: pytest with 85%+ coverage
- **Async**: Use async/await consistently

### Frontend (TypeScript)

- **Style**: ESLint + Prettier
- **Types**: Strict TypeScript
- **Testing**: Playwright E2E tests
- **Components**: React functional components with hooks

### Observability

All code must include:
- Structured JSON logging with `correlation_id`
- Prometheus metrics following ADR-0003 naming
- OpenTelemetry spans for distributed tracing

## Operational Runbooks

When incidents occur, consult the appropriate runbook:

| Alert | Runbook |
|-------|---------|
| StripeCircuitOpen | [runbook-stripe-circuit-open.md](runbooks/runbook-stripe-circuit-open.md) |
| JobBacklogHigh | [runbook-browser-worker-backlog.md](runbooks/runbook-browser-worker-backlog.md) |
| JWTInvalidRateHigh | [runbook-auth-jwks-failures.md](runbooks/runbook-auth-jwks-failures.md) |
| BillingReconciliationMissing | [runbook-reconciliation-missing.md](runbooks/runbook-reconciliation-missing.md) |

## Implementation Records

Every implementation task must produce an Implementation Record following the template:

```
docs/records/{YYYY-MM-DD}-{short-key}.md
```

See [Implementation Record Policy](../README.md) for details.

## Environment Variables

### Backend Core
```
APP_ENV=local|dev|staging|prod
SERVICE_NAME=api|worker-generic|worker-browser|billing-cron|agents
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
POSTGRES_DSN=postgresql+asyncpg://...
REDIS_URL=redis://...
```

### Supabase
```
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_JWKS_URL=https://.../.well-known/jwks.json
SUPABASE_JWT_AUDIENCE=authenticated
```

### Stripe
```
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_...
```

### Feature Flags
```
FF_BROWSER_WORKER_ENABLED=true|false
FF_BILLING_ENFORCEMENT_ENABLED=true|false
FF_AGENTS_ENABLED=true|false
```

## Testing

### Unit Tests
```bash
cd backend
pytest app/tests/ -v --cov=app --cov-report=term-missing
```

### Integration Tests
```bash
docker-compose up -d postgres redis
pytest app/tests/ -v -m integration
```

### E2E Tests
```bash
cd frontend
npx playwright test
```

### Load Tests
```bash
cd infra/loadtest
k6 run scripts/api-baseline.js
```

## Contributing

1. Create a feature branch from `main`
2. Make changes following code standards
3. Write tests (85%+ coverage required)
4. Create Implementation Record
5. Submit PR with CODEOWNERS review
6. Address review comments
7. Merge after approval

## Support

- **Documentation**: This guide and ADRs
- **Incidents**: Check runbooks first
- **Questions**: Platform team Slack channel
