# Runbook: Billing Reconciliation Missing

## Overview
This runbook addresses the `BillingReconciliationMissing` alert, which fires when the daily billing reconciliation job has not successfully completed in over 24 hours.

## Symptoms
- Alert `BillingReconciliationMissing` firing
- Metric `billing_reconciliation_last_success_timestamp` is stale (>24h old)
- Logs missing `reconciliation_completed` events
- Potential discrepancies between internal `usage_counters` and Stripe usage records
- Cron job pods in `CrashLoopBackOff` or `Error` state

## Impact
- **Customer Impact**: Minimal immediate impact; usage limits may not be accurately enforced
- **Business Impact**: Revenue leakage if usage is underreported to Stripe
- **Data Impact**: Drift between internal usage tracking and Stripe billing records

## Immediate Actions

### 1. Acknowledge the Alert
- Acknowledge in PagerDuty/OpsGenie to prevent escalation
- Post in `#incidents` Slack channel: "Investigating billing reconciliation failure"

### 2. Quick Health Check
```bash
# Check reconciliation timestamp
curl -s http://billing-cron:8000/metrics | \
  grep 'billing_reconciliation_last_success_timestamp'

# Calculate hours since last success
LAST_SUCCESS=$(curl -s http://billing-cron:8000/metrics | \
  grep 'billing_reconciliation_last_success_timestamp' | \
  awk '{print $2}')
echo "Hours since last reconciliation: $(( ($(date +%s) - ${LAST_SUCCESS%.*}) / 3600 ))"

# Check cron job status
kubectl get cronjobs -n production | grep reconciliation
kubectl get pods -l job-name -n production --sort-by=.status.startTime | tail -5
```

### 3. Check Recent Job Attempts
```bash
# List recent reconciliation job pods
kubectl get pods -l app=billing-cron -n production --sort-by=.status.startTime | tail -10

# Check the most recent job's logs
kubectl logs -l app=billing-cron -n production --tail=200
```

## Diagnosis Steps

### 1. Identify Failure Mode

**A. Job Not Running**
```bash
# Check if CronJob is suspended
kubectl get cronjob billing-reconciliation -n production -o yaml | grep suspend

# Check cron schedule
kubectl get cronjob billing-reconciliation -n production -o jsonpath='{.spec.schedule}'

# Check last scheduled time
kubectl get cronjob billing-reconciliation -n production -o jsonpath='{.status.lastScheduleTime}'
```

**B. Job Failing**
```bash
# Get exit code of recent jobs
kubectl get pods -l job-name -n production \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.phase}{"\t"}{.status.containerStatuses[0].state}{"\n"}{end}'

# Check failure reason
kubectl logs $(kubectl get pods -l app=billing-cron -n production --sort-by=.status.startTime -o jsonpath='{.items[-1].metadata.name}') -n production
```

**C. Database Issues**
```bash
# Check for DB connection errors in logs
kubectl logs -l app=billing-cron -n production --since=24h | \
  grep -E "(database|connection|timeout)" | head -20

# Verify DB connectivity
kubectl exec -it deploy/api -n production -- \
  python -c "from app.utils.db import ensure_db_connected; import asyncio; asyncio.run(ensure_db_connected())"
```

**D. Stripe API Issues**
```bash
# Check for Stripe errors
kubectl logs -l app=billing-cron -n production --since=24h | \
  grep -E "(stripe|circuit)" | head -20

# Check Stripe circuit breaker
curl -s http://billing-cron:8000/metrics | grep 'circuit_state.*stripe'
```

### 2. Check Job Configuration
```bash
# View cron job configuration
kubectl get cronjob billing-reconciliation -n production -o yaml

# Verify environment variables
kubectl describe cronjob billing-reconciliation -n production | grep -A20 "Environment:"
```

### 3. Check for Data Issues
```bash
# Connect to DB and check for anomalies
kubectl exec -it deploy/api -n production -- python << 'EOF'
from app.utils.db import get_session_factory
import asyncio

async def check():
    factory = get_session_factory()
    async with factory() as session:
        # Check for users without usage counters
        result = await session.execute("""
            SELECT COUNT(*) FROM users u
            LEFT JOIN usage_counters uc ON u.id = uc.user_id
            WHERE uc.id IS NULL AND u.created_at < NOW() - INTERVAL '1 day'
        """)
        print(f"Users missing usage counters: {result.scalar()}")
        
        # Check for stale counters
        result = await session.execute("""
            SELECT COUNT(*) FROM usage_counters
            WHERE last_reconciled_at < NOW() - INTERVAL '2 days'
        """)
        print(f"Stale counters: {result.scalar()}")

asyncio.run(check())
EOF
```

## Remediation

### A. Job Not Scheduled
```bash
# Resume if suspended
kubectl patch cronjob billing-reconciliation -n production -p '{"spec":{"suspend":false}}'

# Verify schedule is correct (should be something like "0 2 * * *" for 2am daily)
kubectl patch cronjob billing-reconciliation -n production \
  -p '{"spec":{"schedule":"0 2 * * *"}}'
```

### B. Manual Job Trigger
```bash
# Create a manual job run
kubectl create job --from=cronjob/billing-reconciliation manual-reconciliation-$(date +%s) -n production

# Watch the job
kubectl logs -f job/manual-reconciliation-* -n production
```

### C. Fix Configuration Issues
```bash
# Update Stripe credentials if needed
kubectl create secret generic stripe-credentials \
  --from-literal=STRIPE_SECRET_KEY="sk_live_xxx" \
  --from-literal=STRIPE_WEBHOOK_SECRET="whsec_xxx" \
  -n production --dry-run=client -o yaml | kubectl apply -f -

# Restart cron pods
kubectl rollout restart deployment/billing-cron -n production
```

### D. Stripe Circuit Open
If Stripe circuit breaker is open:
1. Check Stripe status page
2. Wait for auto-recovery or reset:
   ```bash
   kubectl rollout restart deployment/billing-cron -n production
   ```

### E. Database Recovery
If DB issues:
```bash
# Check connection pool status
kubectl logs -l app=billing-cron -n production | grep -i pool

# Increase pool size if needed
kubectl set env deployment/billing-cron DB_POOL_SIZE=20 -n production
```

### F. Catch-up Reconciliation
For extended outages, run reconciliation for specific date ranges:
```bash
kubectl exec -it deploy/billing-cron -n production -- \
  python -m app.cron.run reconcile --start-date 2025-01-01 --end-date 2025-01-15
```

## Follow-up / Prevention

### Post-Incident
1. Create incident report documenting:
   - Duration of missed reconciliations
   - Root cause
   - Data discrepancies found and corrected
2. Audit Stripe vs internal usage for affected period
3. Notify finance team if discrepancies affected billing

### Verify Data Integrity
```bash
# Run discrepancy report
kubectl exec -it deploy/billing-cron -n production -- \
  python -m app.billing.usage_reconciliation --report-only

# Export discrepancies for review
kubectl exec -it deploy/billing-cron -n production -- \
  python -m app.billing.usage_reconciliation --export-discrepancies > /tmp/discrepancies.csv
```

### Prevention Measures
- **Alerting**: Lower alert threshold to 12 hours for earlier detection
- **Redundancy**: Run reconciliation twice daily instead of once
- **Monitoring**: Add job duration and success rate metrics
- **Retry Logic**: Ensure cron job has proper retry configuration:
  ```yaml
  spec:
    backoffLimit: 3
    activeDeadlineSeconds: 3600
  ```
- **Dead Man's Switch**: Implement secondary monitoring that expects periodic pings

### Recommended CronJob Configuration
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: billing-reconciliation
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid
  failedJobsHistoryLimit: 5
  successfulJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 3
      activeDeadlineSeconds: 3600
      template:
        spec:
          restartPolicy: OnFailure
```

## Related Resources
- **Alert Definition**: `infra/alerts/alerts.yaml` → `BillingReconciliationMissing`
- **Grafana Dashboard**: `infra/grafana/auth-billing.json`
- **Cron Job Code**: `backend/app/cron/run.py`
- **Reconciliation Logic**: `backend/app/billing/usage_reconciliation.py`
- **Metrics**: 
  - `billing_reconciliation_last_success_timestamp`
  - `billing_reconciliation_duration_seconds` (if implemented)
  - `billing_reconciliation_discrepancies_total` (if implemented)
- **Tables**: `usage_counters`, `usage_events`, `subscriptions`
