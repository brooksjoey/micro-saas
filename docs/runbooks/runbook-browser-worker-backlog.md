# Runbook: Browser Worker Backlog High

## Overview
This runbook addresses the `JobBacklogHigh` and browser-specific backlog alerts, which fire when the browser worker job queue exceeds 1000 pending messages for more than 15 minutes.

## Symptoms
- Alert `JobBacklogHigh` firing with `queue_name=jobs:browser:stream`
- Grafana panel "Browser Pending Messages" showing `jobs_browser_pending_messages > 1000`
- Metric `msaas_queue_depth{queue_kind="redis_stream", queue_name="jobs:browser:stream"}` rising
- Users reporting delayed job completions or timeouts
- Logs showing high `job_wait_time_seconds` values

## Impact
- **Customer Impact**: Browser automation jobs taking longer than SLA (>30s p95)
- **Business Impact**: Degraded service quality; potential SLA violations
- **Data Impact**: Jobs may timeout and require retry, increasing overall load

## Immediate Actions

### 1. Acknowledge the Alert
- Acknowledge in PagerDuty/OpsGenie to prevent escalation
- Post in `#incidents` Slack channel: "Investigating browser worker backlog alert"

### 2. Quick Health Check
```bash
# Check current queue depth
redis-cli XLEN jobs:browser:stream

# Check pending messages (unacknowledged)
redis-cli XPENDING jobs:browser:stream jobs:browser:group

# Check worker pod count and status
kubectl get pods -l app=browser-worker -n production
```

### 3. Verify Worker Health
```bash
# Check browser worker logs for errors
kubectl logs -l app=browser-worker -n production --since=15m --tail=100

# Check Playwright circuit breaker status
curl -s http://browser-worker:8000/metrics | grep 'circuit_state.*playwright'
```

## Diagnosis Steps

### 1. Identify Bottleneck Type

**A. Worker Capacity Issue**
```bash
# Count active workers
kubectl get pods -l app=browser-worker -n production -o json | \
  jq '[.items[] | select(.status.phase == "Running")] | length'

# Check resource utilization
kubectl top pods -l app=browser-worker -n production
```

**B. Slow Job Processing**
```bash
# Check job processing latency
curl -s http://browser-worker:8000/metrics | \
  grep 'jobs_browser_processing_seconds'

# Look for timeout patterns
kubectl logs -l app=browser-worker -n production --since=30m | \
  grep -c "job_timeout"
```

**C. Playwright/Browser Issues**
```bash
# Check for Playwright errors
kubectl logs -l app=browser-worker -n production --since=30m | \
  grep -E "(playwright_error|browser_crash|navigation_timeout)"

# Check circuit breaker status
curl -s http://browser-worker:8000/metrics | \
  grep 'circuit_state{breaker_name="playwright"}'
```

**D. Upstream Traffic Spike**
```bash
# Check job enqueue rate
curl -s http://api:8000/metrics | \
  grep 'msaas_job_processing_duration_seconds_count{job_type="browser"}'
```

### 2. Check Feature Flags
```bash
# Verify browser worker is enabled
echo "FF_BROWSER_WORKER_ENABLED: $FF_BROWSER_WORKER_ENABLED"
echo "FF_BROWSER_TASK_NAVIGATE_EXTRACT_ENABLED: $FF_BROWSER_TASK_NAVIGATE_EXTRACT_ENABLED"
```

### 3. Check Consumer Group Health
```bash
# View consumer group info
redis-cli XINFO GROUPS jobs:browser:stream

# Check for stuck consumers
redis-cli XINFO CONSUMERS jobs:browser:stream jobs:browser:group
```

## Remediation

### A. Scale Workers (Immediate Relief)
```bash
# Scale up browser workers
kubectl scale deployment/browser-worker --replicas=10 -n production

# Verify scaling
kubectl get pods -l app=browser-worker -n production -w
```

### B. Clear Stuck Messages (If Consumers Stale)
```bash
# Claim messages from dead consumers (messages pending > 5 minutes)
redis-cli XAUTOCLAIM jobs:browser:stream jobs:browser:group new-consumer-1 300000 0-0 COUNT 100

# For permanently failed jobs, move to DLQ
python -m backend.scripts.move_to_dlq --stream jobs:browser:stream --min-idle 600000
```

### C. Restart Unhealthy Workers
```bash
# If Playwright circuit is open, restart workers
kubectl rollout restart deployment/browser-worker -n production

# Watch rollout
kubectl rollout status deployment/browser-worker -n production
```

### D. Reduce Incoming Load (If Traffic Spike)
```bash
# Enable rate limiting on job submission endpoint
kubectl set env deployment/api BROWSER_JOB_RATE_LIMIT=50 -n production

# Or temporarily disable browser job acceptance
kubectl set env deployment/api FF_BROWSER_WORKER_ENABLED=false -n production
```

### E. Address Playwright Issues
If browser crashes are frequent:
```bash
# Check browser worker memory limits
kubectl describe deployment/browser-worker -n production | grep -A5 "Limits"

# Increase memory if needed
kubectl set resources deployment/browser-worker --limits=memory=4Gi -n production
```

## Follow-up / Prevention

### Post-Incident
1. Create incident report with:
   - Peak queue depth reached
   - Time to recovery
   - Root cause (capacity, traffic spike, browser issues)
   - Jobs affected (count, duration of delay)
2. Review HPA configuration for browser workers
3. Update capacity planning based on incident

### Prevention Measures
- **Autoscaling**: Configure HPA based on queue depth:
  ```yaml
  metrics:
    - type: External
      external:
        metric:
          name: jobs_browser_pending_messages
        target:
          type: AverageValue
          averageValue: 50
  ```
- **Alerting**: Tune thresholds based on traffic patterns
- **Capacity Planning**: Regular review of worker-to-job ratio
- **Circuit Breaker Tuning**: Adjust Playwright circuit breaker for faster recovery

## Related Resources
- **Alert Definition**: `infra/alerts/alerts.yaml` → `JobBacklogHigh`, `BrowserJobFailureRateHigh`
- **Grafana Dashboard**: `infra/grafana/jobs-overview.json`
- **Worker Code**: `backend/worker/run.py`
- **Consumer Group**: `jobs:browser:group` on stream `jobs:browser:stream`
- **Metrics**: 
  - `jobs_browser_pending_messages`
  - `msaas_queue_depth{queue_name="jobs:browser:stream"}`
  - `jobs_browser_processing_seconds`
  - `circuit_state{breaker_name="playwright"}`
- **Feature Flags**: `FF_BROWSER_WORKER_ENABLED`, `FF_BROWSER_TASK_*_ENABLED`
