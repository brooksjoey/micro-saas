# ADR-0003: Metrics Naming and Observability Conventions

## Status
**Accepted** - 2024-01-16

## Context
As the platform grows to include multiple services (API, workers, agents, billing cron), consistent metrics naming is critical for operational clarity and dashboard creation.

## Decision

### 1. Metric Naming Convention

All metrics follow the pattern:
```
{namespace}_{subsystem}_{metric_type}_{unit}
```

**Namespace**: `msaas` for custom metrics, standard names for HTTP/runtime metrics

**Subsystem**: Logical component (job, auth, billing, agent)

**Metric Type**: 
- `_total` for counters
- `_seconds` for duration histograms
- `_bytes` for size histograms
- No suffix for gauges

### 2. Standard Metrics by Service

#### API Service
```python
http_server_request_duration_seconds     # Histogram
http_server_requests_total               # Counter
msaas_jwt_validation_duration_seconds    # Histogram
auth_jwt_invalid_total                   # Counter
```

#### Generic Worker
```python
msaas_job_processing_duration_seconds    # Histogram
msaas_job_errors_total                   # Counter
msaas_queue_depth                        # Gauge
```

#### Browser Worker
```python
jobs_browser_processing_seconds          # Histogram
jobs_browser_errors_total                # Counter
jobs_browser_processed_total             # Counter
jobs_browser_pending_messages            # Gauge
circuit_state{target="playwright"}       # Gauge (0=closed, 1=open, 2=half_open)
```

#### Billing/Cron
```python
billing_reconciliation_last_success_timestamp  # Gauge (unix timestamp)
circuit_state{target="stripe"}                 # Gauge
```

#### Agents
```python
agents_workflow_execution_seconds        # Histogram
agents_llm_calls_total                   # Counter
agents_llm_tokens_total                  # Counter
msaas_agent_fallback_total               # Counter
```

### 3. Required Labels

All metrics MUST include:
- `service`: Logical service name (api, worker-generic, worker-browser, billing-cron, agents)
- `env`: Environment (local, dev, staging, prod)

Additional labels as appropriate:
- `route`, `method`, `status_code` for HTTP metrics
- `job_type`, `result` for job metrics
- `workflow_name`, `outcome` for agent metrics

### 4. Histogram Buckets

Standard bucket configurations:
- **HTTP latency**: [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
- **Job processing**: [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
- **Agent workflows**: [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
- **JWT validation**: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]

### 5. Cardinality Guidelines

- Limit label cardinality to <100 unique values per label
- Never use user_id, job_id, or correlation_id as labels
- Use error_type buckets, not raw error messages
- Path templates (/jobs/{id}) not raw paths (/jobs/abc-123)

## Consequences

### Positive
- Unified dashboards work across all services
- Alert rules can use consistent metric names
- Grafana panels are reusable

### Negative
- Existing metrics may need migration
- All services must update to new conventions
- Additional documentation overhead

## Related

- Grafana dashboards: `infra/grafana/`
- Alert rules: `infra/alerts/alerts.yaml`
- Metrics implementation: `backend/app/telemetry/metrics.py`
