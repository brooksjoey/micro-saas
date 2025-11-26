# ADR-0009: GDPR and Data Deletion Policy

## Status
**Accepted** - 2024-01-16

## Context
The platform handles PII (emails, usage history) and must support GDPR-style deletion requests while maintaining business-critical aggregates for billing and analytics.

## Decision

### 1. Deletion Scope

| Table | Deletion Type | Rationale |
|-------|--------------|-----------|
| users | Anonymize | Keep record for foreign key integrity |
| stripe_customers | Coordinate with Stripe API | Follow Stripe's data deletion |
| subscriptions | Soft delete | Needed for billing history |
| usage_counters | Anonymize | Keep aggregates for analytics |
| usage_events | Anonymize | Keep for reconciliation |
| jobs | Anonymize payload | Keep job metadata for ops |
| vector_store | Hard delete | Remove all user-related embeddings |

### 2. Anonymization Strategy

```python
# Anonymization transformations
{
    "users.email": "deleted_{user_id}@anonymized.local",
    "users.stripe_customer_id": None,
    "jobs.payload": {"anonymized": True, "deleted_at": "ISO8601"},
    "usage_events.metadata": {},
}
```

### 3. Deletion Pipeline

```python
async def delete_user_data(user_id: UUID, correlation_id: str) -> DeletionReport:
    """
    Execute GDPR-compliant user data deletion.
    
    Returns a DeletionReport with:
    - tables_affected: List of tables modified
    - rows_anonymized: Count per table
    - stripe_deletion_status: Stripe API response
    - vector_store_deleted: Number of embeddings removed
    """
```

### 4. Implementation Order

1. **Vector Store Cleanup**: Delete all user embeddings from Chroma
2. **Stripe Coordination**: Request customer deletion via Stripe API
3. **Database Anonymization**: Update tables in reverse dependency order
4. **Audit Log**: Record deletion in dedicated audit table

### 5. Audit Trail

```sql
CREATE TABLE deletion_audit (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    requested_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL,  -- 'pending', 'completed', 'failed'
    report jsonb NOT NULL DEFAULT '{}'
);
```

### 6. API Endpoint

```
DELETE /api/v1/admin/users/{user_id}/data
Authorization: Bearer {admin_token}
X-Correlation-ID: {uuid}

Response:
{
  "status": "completed",
  "deletion_id": "uuid",
  "report": {
    "tables_affected": ["users", "jobs", "usage_events"],
    "rows_anonymized": {"users": 1, "jobs": 42, "usage_events": 156},
    "stripe_deletion_status": "requested",
    "vector_store_deleted": 15
  }
}
```

### 7. Retention Policy

| Data Category | Retention Period | Post-Deletion |
|---------------|------------------|---------------|
| Active user data | Indefinite | N/A |
| Deleted user records | 30 days (soft delete) | Hard delete |
| Billing aggregates | 7 years | Anonymized |
| Logs with PII | 90 days | Auto-purge |

## Consequences

### Positive
- GDPR/CCPA compliant
- Preserves business analytics
- Auditable deletion process

### Negative
- Complex multi-system coordination
- Stripe deletion may be asynchronous
- Testing deletion is complex

## Related

- Deletion service: `backend/app/services/privacy.py` (to be implemented)
- Audit table migration: `backend/alembic/versions/`
- Documentation: `docs/PRIVACY.md`
