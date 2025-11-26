# ADR-0001: Core Architecture and Layering

## Status
**Accepted** - 2024-01-15

## Context
The Micro-SaaS platform requires a clear architectural layering to ensure maintainability, testability, and separation of concerns across the API, workers, and agents subsystems.

## Decision

### 1. Architectural Layers

```
┌────────────────────────────────────────────────────┐
│                   Presentation Layer                │
│    (FastAPI Routes, Middleware, Request/Response)   │
├────────────────────────────────────────────────────┤
│                   Application Layer                 │
│    (Services, Use Cases, Orchestration)             │
├────────────────────────────────────────────────────┤
│                     Domain Layer                    │
│    (Models, Business Logic, Validation)             │
├────────────────────────────────────────────────────┤
│                 Infrastructure Layer                │
│    (Database, Redis, External APIs, Storage)        │
└────────────────────────────────────────────────────┘
```

### 2. Package Structure

```
backend/
├── app/
│   ├── routes/          # Presentation: HTTP endpoints
│   ├── middleware/      # Presentation: Cross-cutting concerns
│   ├── services/        # Application: Business logic orchestration
│   ├── models/          # Domain: SQLAlchemy models
│   ├── schemas/         # Domain: Pydantic request/response schemas
│   ├── utils/           # Infrastructure: Shared utilities
│   ├── auth/            # Infrastructure: Authentication
│   ├── billing/         # Infrastructure: Stripe integration
│   └── telemetry/       # Infrastructure: Observability
├── worker/              # Separate worker process
├── agents/              # LLM/AI orchestration
└── alembic/             # Database migrations
```

### 3. Dependency Rules

- **Routes** may depend on **Services** and **Schemas**
- **Services** may depend on **Models**, **Schemas**, and **Utils**
- **Models** are self-contained with minimal dependencies
- **Utils** have no internal dependencies (pure infrastructure)

### 4. Error Handling Strategy

All errors flow through structured exception handlers:
- Domain errors → HTTP 4xx with structured response
- Infrastructure errors → HTTP 5xx with correlation_id
- All errors logged with context (correlation_id, user_id, job_id)

## Consequences

### Positive
- Clear boundaries enable independent testing
- New developers can understand architecture quickly
- Refactoring is contained to specific layers

### Negative
- Additional boilerplate for simple operations
- Requires discipline to maintain layer boundaries
- Some operations require passing through multiple layers

## Compliance

This ADR establishes the foundation for:
- ADR-0002: Worker conventions
- ADR-0003: Metrics naming
- ADR-0004: Frontend integration
