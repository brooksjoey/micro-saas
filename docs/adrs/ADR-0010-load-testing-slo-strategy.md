# ADR-0010: Load Testing and SLO Strategy

## Status
**Accepted** - 2024-01-16

## Context
The platform targets enterprise-grade reliability with defined SLOs. Load testing validates these targets before production deployment and during capacity planning.

## Decision

### 1. SLO Targets

| Service | Metric | Target | Measurement Window |
|---------|--------|--------|-------------------|
| API | p99 latency | < 50ms | 5 minutes |
| API | Error rate | < 0.1% | 5 minutes |
| API | Availability | 99.9% | 30 days |
| Auth middleware | Overhead | < 2ms | Per request |
| Browser worker | p95 job duration | < 30s | 15 minutes |
| Browser worker | Failure rate | < 5% | 15 minutes |
| Agent workflows | p95 duration | < 5s | 15 minutes |
| Agent workflows | Failure rate | < 10% | 15 minutes |

### 2. Load Test Tool

**k6** selected for:
- JavaScript/TypeScript test scripts
- Built-in metrics and thresholds
- CI/CD integration
- Support for WebSocket/SSE

### 3. Test Scenarios

**Scenario 1: API Baseline**
```javascript
// infra/loadtest/api-baseline.js
export const options = {
  stages: [
    { duration: '1m', target: 100 },   // Ramp up
    { duration: '5m', target: 100 },   // Steady state
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<50'],
    http_req_failed: ['rate<0.001'],
  },
};
```

**Scenario 2: Peak Load**
```javascript
// 10,000 requests/minute target
export const options = {
  stages: [
    { duration: '2m', target: 167 },   // Ramp to 10k/min
    { duration: '10m', target: 167 },  // Sustained
    { duration: '2m', target: 0 },
  ],
};
```

**Scenario 3: SSE Stress**
```javascript
// 1,000 concurrent SSE connections
export const options = {
  scenarios: {
    sse_connections: {
      executor: 'constant-vus',
      vus: 1000,
      duration: '10m',
    },
  },
};
```

**Scenario 4: Browser Job Backlog**
```javascript
// Submit jobs faster than processing capacity
export const options = {
  scenarios: {
    job_flood: {
      executor: 'constant-arrival-rate',
      rate: 100,
      duration: '5m',
    },
  },
};
```

### 4. Test Infrastructure

```yaml
# infra/loadtest/docker-compose.yaml
services:
  k6:
    image: grafana/k6:latest
    volumes:
      - ./scripts:/scripts
    environment:
      - K6_PROMETHEUS_RW_SERVER_URL=http://prometheus:9090/api/v1/write
```

### 5. CI Integration

Load tests run:
- On-demand via manual trigger
- Weekly against staging
- Before major releases

```yaml
# .github/workflows/loadtest.yaml
on:
  workflow_dispatch:
    inputs:
      scenario:
        description: 'Test scenario'
        required: true
        type: choice
        options: [baseline, peak, sse, backlog]
```

### 6. Results Analysis

Results exported to:
- Prometheus (real-time during test)
- Grafana Cloud (historical analysis)
- JSON summary in CI artifacts

## Consequences

### Positive
- Validated SLO targets
- Capacity planning data
- Regression detection

### Negative
- Infrastructure cost for staging
- Test maintenance overhead
- May not catch all production issues

## Related

- Load test scripts: `infra/loadtest/`
- Grafana dashboards: `infra/grafana/`
- CI workflow: `.github/workflows/loadtest.yaml`
