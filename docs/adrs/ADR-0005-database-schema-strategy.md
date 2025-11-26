# ADR-0005: Database Schema and Migration Strategy

## Status
**Accepted** - 2024-01-16

## Context
The platform requires a robust database schema supporting multi-tenancy, billing integration, and usage tracking, with safe migration practices for production deployments.

## Decision

### 1. Core Tables

```sql
-- Users (mirrors Supabase auth with Stripe linkage)
users (id, email, stripe_customer_id, created_at, updated_at)

-- Subscriptions (current subscription state)
subscriptions (id, user_id, stripe_subscription_id, plan, status, current_period_start, current_period_end)

-- Usage Counters (aggregated per billing period)
usage_counters (id, user_id, period_start, period_end, jobs_used, jobs_limit, credits_remaining, last_reconciled_at)

-- Usage Events (append-only audit log)
usage_events (id, user_id, kind, amount, job_id, stripe_event_id, metadata, occurred_at)

-- Jobs (enhanced with user context)
jobs (id, user_id, correlation_id, status, payload, attempts, max_attempts, last_error, created_at, updated_at)
```

### 2. Schema Constraints

- **Foreign Keys**: All user-related tables reference `users(id)` with appropriate `ON DELETE` behavior
- **Unique Constraints**: 
  - `users(email)` - case-insensitive via CITEXT
  - `subscriptions(stripe_subscription_id)`
  - `usage_counters(user_id, period_start, period_end)`
  - `usage_events(stripe_event_id)` WHERE NOT NULL (for idempotency)
- **Indexes**: Cover all query patterns (user_id, status, created_at, correlation_id)

### 3. Migration Strategy

**Additive-Only for Zero-Downtime Deploys**:
1. Add new columns as nullable first
2. Deploy code that writes to both old and new columns
3. Backfill data in background job
4. Deploy code that reads from new column
5. Remove old column in subsequent release

**Migration File Naming**:
```
YYYYMMDDHHMM_descriptive_name.py
Example: 202501010900_add_auth_billing_usage_tables.py
```

### 4. Alembic Best Practices

```python
# Always specify down_revision explicitly
revision = '202501010900'
down_revision = '202412150800'

# Use server_default for NOT NULL columns
sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), 
          server_default=sa.text('now()'), nullable=False)

# Partial unique indexes for conditional uniqueness
op.create_index('idx_unique_stripe_event', 'usage_events', ['stripe_event_id'], 
                unique=True, postgresql_where=sa.text('stripe_event_id IS NOT NULL'))
```

### 5. Data Integrity Rules

- `usage_events` is append-only (no updates or deletes)
- `usage_counters` is the source of truth for quota enforcement
- `stripe_event_id` ensures webhook idempotency
- `correlation_id` enables distributed tracing

## Consequences

### Positive
- Clear ownership of billing data
- Audit trail via usage_events
- Safe migration patterns for production

### Negative
- More complex than simple job table
- Requires careful coordination with Stripe
- Reconciliation job needed for consistency

## Related

- Migration file: `backend/alembic/versions/202501010900_add_auth_billing_usage_tables.py`
- SQLAlchemy models: `backend/app/models/`
- Usage accounting: `backend/app/services/usage.py`
