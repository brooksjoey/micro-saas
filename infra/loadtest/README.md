# Micro-SaaS Load Testing

This directory contains k6 load testing scripts for the Micro-SaaS platform.

## Prerequisites

- [k6](https://k6.io/docs/getting-started/installation/) installed
- Running API instance (local or staging)

## Test Scenarios

### Baseline (`baseline.js`)
Tests basic API endpoints under normal load.
- Ramps from 0 → 50 → 100 VUs
- Duration: ~14 minutes
- Thresholds: p95 < 200ms, p99 < 500ms, error rate < 1%

```bash
k6 run scripts/baseline.js
```

### Peak Load (`peak.js`)
Tests API under peak load conditions targeting 10,000 req/min.
- 167 concurrent VUs (≈10k req/min)
- Duration: ~14 minutes
- Thresholds: p99 < 50ms (SLO target), error rate < 0.1%

```bash
k6 run scripts/peak.js
```

### SSE Connections (`sse.js`)
Tests Server-Sent Events under concurrent connection load.
- 100 concurrent SSE connections
- Duration: 5 minutes (configurable)
- Thresholds: connection error rate < 5%

```bash
k6 run scripts/sse.js
```

### Job Backlog (`backlog.js`)
Tests system behavior when jobs are submitted faster than processing capacity.
- 200 jobs/second submission rate
- Duration: 5 minutes (configurable)
- Thresholds: submission error rate < 10%, p95 latency < 1s

```bash
k6 run scripts/backlog.js
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TARGET_URL` | API base URL | `http://localhost:8000` |
| `DURATION` | Test duration | Varies by script |

### Example Usage

```bash
# Run against staging
TARGET_URL=https://staging-api.example.com k6 run scripts/baseline.js

# Custom duration
DURATION=10m k6 run scripts/sse.js

# Output to cloud
k6 run --out cloud scripts/peak.js
```

## Results

Test results are saved to the `results/` directory:
- `baseline-summary.json`
- `peak-summary.json`
- `sse-summary.json`
- `backlog-summary.json`

## CI Integration

Load tests can be triggered via GitHub Actions workflow:

```bash
gh workflow run loadtest.yaml -f scenario=peak -f environment=staging
```

## SLO Targets

| Metric | Target |
|--------|--------|
| API p99 latency | < 50ms |
| API error rate | < 0.1% |
| SSE connection errors | < 5% |
| Job submission under backlog | < 10% errors |
