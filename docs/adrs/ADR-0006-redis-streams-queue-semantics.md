# ADR-0006: Redis Streams and Queue Semantics

## Status
**Accepted** - 2024-01-16

## Context
The platform uses Redis for both simple job queues (generic worker) and Redis Streams (browser worker). This ADR establishes unified conventions for queue naming, message formats, and consumer group management.

## Decision

### 1. Queue Types

| Worker Type | Queue Implementation | Delivery Semantics |
|-------------|---------------------|-------------------|
| Generic | Redis List (`LPUSH`/`BRPOP`) | At-most-once |
| Browser | Redis Streams (`XADD`/`XREADGROUP`) | At-least-once |

### 2. Redis Key Naming Convention

```
{prefix}:{env}:queue:{type}:{purpose}
```

**Generic Worker**:
- `msaas:{env}:queue:jobs.generic` (list)
- `msaas:{env}:queue:jobs.generic:scheduled` (sorted set for delayed jobs)
- `msaas:{env}:queue:jobs.generic:lock:{job_id}` (distributed lock)

**Browser Worker**:
- `msaas:{env}:stream:jobs.browser` (stream)
- Consumer group: `browser-workers`
- `msaas:{env}:stream:jobs.browser:dlq` (dead-letter queue)

### 3. Canonical Job Envelope

All queued messages use this envelope:

```json
{
  "job_id": "uuid",
  "task_type": "navigate_extract",
  "attempts": 0,
  "max_attempts": 5,
  "payload": {
    "url": "https://example.com",
    "selector": ".content"
  },
  "meta": {
    "correlation_id": "uuid",
    "user_id": "uuid",
    "enqueue_ts": "2025-01-01T00:00:00Z",
    "source": "api"
  }
}
```

### 4. Consumer Group Management

```python
# Consumer naming: {hostname}:{pid}:{index}
consumer_name = f"{socket.gethostname()}:{os.getpid()}:{worker_index}"

# Claim pending messages older than 5 minutes
XAUTOCLAIM msaas:prod:stream:jobs.browser browser-workers new-consumer 300000 0-0

# Acknowledge after successful processing
XACK msaas:prod:stream:jobs.browser browser-workers {message_id}
```

### 5. Dead-Letter Queue Strategy

Messages are moved to DLQ when:
- `attempts >= max_attempts`
- Permanent failure (validation error, missing user)

DLQ entries include original envelope plus:
```json
{
  "dlq_ts": "2025-01-01T00:00:00Z",
  "dlq_reason": "max_attempts_exceeded",
  "last_error": "playwright_timeout"
}
```

### 6. Retry Backoff

```python
# Exponential backoff with jitter
delay_seconds = min(
    base_delay * (2 ** attempt) + random.uniform(0, 1),
    max_delay  # 300 seconds
)
```

## Consequences

### Positive
- Clear message contract across workers
- At-least-once delivery for critical browser jobs
- Operational visibility via consumer groups

### Negative
- Mixed queue types add operational complexity
- Requires understanding of both list and stream semantics
- DLQ monitoring and recovery needed

## Related

- Browser worker: `backend/worker/run.py`
- Generic worker: `backend/app/workers/job_worker.py`
- Redis client: `backend/app/utils/redis_client.py`
