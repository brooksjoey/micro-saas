# ADR-0007: Circuit Breaker Pattern

## Status
**Accepted** - 2024-01-16

## Context
External dependencies (Stripe, Playwright, Supabase) can fail or become slow. The circuit breaker pattern prevents cascade failures and enables graceful degradation.

## Decision

### 1. Shared Implementation

All circuit breakers use `backend/app/utils/circuit_breaker.py`:

```python
class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        rolling_window: int = 60,
        success_threshold: int = 2,
    ): ...
    
    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
```

### 2. Circuit Breaker Targets

| Target | Default Threshold | Recovery Timeout | Used By |
|--------|------------------|------------------|---------|
| stripe | 5 failures / 60s | 30s | Billing service |
| playwright | 5 failures / 60s | 60s | Browser worker |
| supabase_storage | 5 failures / 60s | 30s | File service |
| llm_provider | 3 failures / 60s | 45s | Agents |

### 3. State Machine

```
┌─────────┐  failure >= threshold  ┌─────────┐
│ CLOSED  │ ────────────────────▶  │  OPEN   │
│ (0)     │                        │  (1)    │
└────┬────┘                        └────┬────┘
     │                                  │
     │ success                          │ recovery_timeout
     │                                  ▼
     │                            ┌───────────┐
     └─────────────────────────── │ HALF_OPEN │
        success >= success_threshold │   (2)   │
                                  └───────────┘
```

### 4. Metrics

```python
circuit_state{breaker_name, target}  # Gauge: 0=closed, 1=open, 2=half_open
```

### 5. Configuration

```python
# backend/app/config.py
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
CIRCUIT_BREAKER_ROLLING_WINDOW: int = 60
CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30
CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2

# Worker-specific overrides
PLAYWRIGHT_CIRCUIT_FAILURE_THRESHOLD: int = 5
PLAYWRIGHT_CIRCUIT_RESET_TIMEOUT_SECONDS: int = 60
```

### 6. Error Handling

When circuit is OPEN:
- Raise `CircuitBreakerOpenError` immediately
- Log with circuit state and target
- Emit metric update
- Return structured error to caller

```python
class CircuitBreakerOpenError(Exception):
    def __init__(self, breaker_name: str, target: str):
        self.breaker_name = breaker_name
        self.target = target
```

### 7. Integration Pattern

```python
# Example: Stripe integration
stripe_circuit = CircuitBreaker(
    name="stripe",
    failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
)

async def create_customer(email: str) -> Customer:
    return await stripe_circuit.call(
        _stripe_create_customer,
        email
    )
```

## Consequences

### Positive
- Prevents cascade failures
- Enables graceful degradation
- Observable via metrics

### Negative
- Adds latency to first failure detection
- May mask underlying issues if not monitored
- Requires careful threshold tuning

## Related

- Implementation: `backend/app/utils/circuit_breaker.py`
- Metrics: `backend/app/telemetry/metrics.py`
- Runbooks: `docs/runbooks/runbook-stripe-circuit-open.md`
