# ADR-0008: Feature Flags System

## Status
**Accepted** - 2024-01-16

## Context
The platform needs feature flags for gradual rollout, kill switches, and per-tenant/per-user feature gating across backend and frontend.

## Decision

### 1. Flag Naming Convention

**Backend** (environment variables):
```
FF_{FEATURE_AREA}_{FEATURE_NAME}_ENABLED
```

Examples:
- `FF_BROWSER_WORKER_ENABLED` - Master switch for browser workers
- `FF_BROWSER_TASK_NAVIGATE_EXTRACT_ENABLED` - Per-task toggle
- `FF_BILLING_ENFORCEMENT_ENABLED` - Enable plan limit enforcement
- `FF_AGENTS_ENABLED` - Enable LLM agent workflows

**Frontend** (NEXT_PUBLIC_ prefix):
```
NEXT_PUBLIC_FF_{FEATURE_NAME}
```

Examples:
- `NEXT_PUBLIC_FF_JOB_SUBMISSION` - Show job submission UI
- `NEXT_PUBLIC_FF_REAL_TIME_UPDATES` - Enable SSE connections
- `NEXT_PUBLIC_FF_BILLING_PORTAL` - Show billing management

### 2. Backend Implementation

```python
# backend/app/config.py
class Settings(BaseSettings):
    FF_BROWSER_WORKER_ENABLED: bool = True
    FF_BROWSER_TASK_NAVIGATE_EXTRACT_ENABLED: bool = True
    FF_BILLING_ENFORCEMENT_ENABLED: bool = False
    FF_AGENTS_ENABLED: bool = False

# backend/app/utils/feature_flags.py
from app.config import get_settings

def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature flag is enabled."""
    settings = get_settings()
    attr_name = f"FF_{feature_name.upper()}_ENABLED"
    return getattr(settings, attr_name, False)

def require_feature(feature_name: str) -> None:
    """Raise if feature is disabled."""
    if not is_feature_enabled(feature_name):
        raise FeatureDisabledError(feature_name)
```

### 3. Flag Behavior

| Scenario | Behavior |
|----------|----------|
| Worker disabled | Worker exits cleanly with log message |
| Task disabled | Job fails with `feature_flag_disabled` reason |
| API feature disabled | Returns 503 with structured error |
| UI feature disabled | Component not rendered |

### 4. Structured Error Response

```json
{
  "error": "feature_disabled",
  "detail": "Feature 'browser_worker' is currently disabled",
  "feature_flag": "FF_BROWSER_WORKER_ENABLED",
  "correlation_id": "uuid"
}
```

### 5. Frontend Feature Flag Hook

```typescript
// hooks/useFeatureFlag.ts
export function useFeatureFlag(flagName: string): boolean {
  const envVar = `NEXT_PUBLIC_FF_${flagName.toUpperCase()}`;
  return process.env[envVar] !== 'false';
}

// Usage
function JobSubmitButton() {
  const enabled = useFeatureFlag('JOB_SUBMISSION');
  if (!enabled) return null;
  return <Button>Submit Job</Button>;
}
```

### 6. Logging and Metrics

When a feature flag blocks an operation:
```python
logger.info(
    "feature_flag_blocked",
    feature=feature_name,
    flag=f"FF_{feature_name.upper()}_ENABLED",
    correlation_id=correlation_id,
)
```

### 7. Flag Sources (Future)

Current: Environment variables only

Future phases may add:
- Database-backed flags (per-tenant)
- Redis-cached flags (fast evaluation)
- LaunchDarkly/Unleash integration

## Consequences

### Positive
- Safe feature rollout
- Quick kill switches for incidents
- Per-environment configuration

### Negative
- Flag cleanup discipline required
- Testing matrix complexity
- Potential for stale flags

## Related

- Config: `backend/app/config.py`
- Feature flags utility: `backend/app/utils/feature_flags.py`
- Frontend config: `frontend/lib/config.ts`
