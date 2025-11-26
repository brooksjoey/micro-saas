# Database Authorization Contract

This document maps API endpoints and background workers to their required database roles and RLS policy expectations.

## Roles

| Role | Purpose | Used By |
|------|---------|---------|
| `authenticated` | Regular users authenticated via Supabase JWT | Frontend API calls |
| `service_role` | Trusted backend services | Workers, Webhooks, Cron jobs |
| `anon` | Unauthenticated users | Public endpoints only |

## API Endpoints

### User Management

| Endpoint | HTTP Method | DB Role | Policy | Notes |
|----------|-------------|---------|--------|-------|
| `GET /api/v1/users/me` | GET | authenticated | users_select_own | User profile |
| `PATCH /api/v1/users/me` | PATCH | authenticated | users_update_own | Limited fields |

### Jobs

| Endpoint | HTTP Method | DB Role | Policy | Notes |
|----------|-------------|---------|--------|-------|
| `GET /api/v1/jobs` | GET | authenticated | jobs_select_own | User's jobs only |
| `GET /api/v1/jobs/{id}` | GET | authenticated | jobs_select_own | Single job |
| `POST /api/v1/jobs` | POST | authenticated | jobs_insert_own | Create job |
| `DELETE /api/v1/jobs/{id}` | DELETE | authenticated | jobs_update_own | Cancel job |
| `GET /api/v1/jobs/stream` | GET (SSE) | authenticated | jobs_select_own | Real-time updates |

### Billing

| Endpoint | HTTP Method | DB Role | Policy | Notes |
|----------|-------------|---------|--------|-------|
| `GET /api/v1/billing/subscription` | GET | authenticated | subscriptions_select_own | Current plan |
| `GET /api/v1/billing/usage` | GET | authenticated | usage_counters_select_own | Usage stats |
| `POST /api/v1/billing/webhooks` | POST | service_role | *_service_* | Stripe webhooks |

### Health & Metrics

| Endpoint | HTTP Method | DB Role | Policy | Notes |
|----------|-------------|---------|--------|-------|
| `GET /health` | GET | anon | N/A | No DB access |
| `GET /metrics` | GET | anon | N/A | No DB access |

## Background Workers

### Generic Job Worker

| Operation | DB Role | Tables | Policies |
|-----------|---------|--------|----------|
| Claim job | service_role | jobs | jobs_service_all |
| Update job status | service_role | jobs | jobs_service_all |
| Record usage event | service_role | usage_events | usage_events_service_insert |
| Update usage counter | service_role | usage_counters | usage_counters_service_all |

### Browser Worker

| Operation | DB Role | Tables | Policies |
|-----------|---------|--------|----------|
| Read job | service_role | jobs | jobs_service_all |
| Update job status | service_role | jobs | jobs_service_all |
| Record usage event | service_role | usage_events | usage_events_service_insert |

### Billing Cron

| Operation | DB Role | Tables | Policies |
|-----------|---------|--------|----------|
| Read all usage | service_role | usage_counters | usage_counters_service_all |
| Read all events | service_role | usage_events | usage_events_service_select |
| Update counters | service_role | usage_counters | usage_counters_service_all |
| Sync with Stripe | service_role | subscriptions | subscriptions_service_all |

## Stripe Webhook Handler

| Stripe Event | Tables Affected | Policies Used |
|--------------|-----------------|---------------|
| customer.created | users | users_service_update |
| customer.subscription.created | subscriptions | subscriptions_service_all |
| customer.subscription.updated | subscriptions | subscriptions_service_all |
| customer.subscription.deleted | subscriptions | subscriptions_service_all |
| invoice.paid | usage_events | usage_events_service_insert |

## Security Considerations

1. **Never expose service_role key to clients**: The `SUPABASE_SERVICE_ROLE_KEY` bypasses all RLS and must only be used by trusted backend services.

2. **JWT validation happens before RLS**: The Supabase JWT contains the `auth.uid()` that RLS policies use. Invalid JWTs are rejected at the API layer before reaching the database.

3. **Correlation ID propagation**: All service_role operations should include correlation_id for audit trails, logged at the application level.

4. **Usage events are append-only**: No UPDATE or DELETE policies exist for usage_events. This ensures audit integrity for billing reconciliation.

5. **Stripe idempotency**: The `stripe_event_id` unique constraint prevents duplicate processing of webhooks, critical for billing accuracy.

## Testing RLS Policies

```sql
-- Test as authenticated user
SET LOCAL role = 'authenticated';
SET LOCAL request.jwt.claim.sub = 'user-uuid-here';

SELECT * FROM jobs;  -- Should only see own jobs

-- Test as service role
SET LOCAL role = 'service_role';
SELECT * FROM jobs;  -- Should see all jobs
```

## Migration Notes

RLS policies should be applied after the initial schema migration. They can be applied via:

1. Supabase Dashboard SQL editor
2. A separate Alembic migration
3. The `infra/db/rls_policies.sql` script

Ensure policies are applied in all environments (dev, staging, production) with the same configuration.
