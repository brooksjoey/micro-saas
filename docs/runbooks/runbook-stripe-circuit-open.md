# Runbook: Stripe Circuit Breaker Open

## Overview
This runbook addresses the `StripeCircuitOpen` alert, which fires when the Stripe integration circuit breaker has been open for more than 5 minutes.

## Symptoms
- Alert `StripeCircuitOpen` firing in PagerDuty/OpsGenie
- Grafana panel "Stripe Circuit State" showing `circuit_state{breaker_name="stripe"} == 1` (open)
- Logs showing `circuit_breaker_open` events with `target=stripe`
- Users reporting billing-related errors or inability to subscribe/upgrade plans
- Job failures with `error_type=stripe_unavailable` in `msaas_job_errors_total`

## Impact
- **Customer Impact**: Users cannot complete billing operations (subscriptions, upgrades, usage reporting)
- **Business Impact**: Revenue operations halted; usage not being reported to Stripe
- **Data Impact**: Usage events queued locally but not reconciled with Stripe

## Immediate Actions

### 1. Acknowledge the Alert
- Acknowledge in PagerDuty/OpsGenie to prevent escalation
- Post in `#incidents` Slack channel: "Investigating StripeCircuitOpen alert"

### 2. Check Stripe Status
- Visit [Stripe Status Page](https://status.stripe.com/)
- Check for ongoing incidents or degraded performance

### 3. Verify Current State
```bash
# Check circuit breaker metric
curl -s http://api-service:8000/metrics | grep 'circuit_state.*stripe'

# Check recent logs for Stripe errors
kubectl logs -l app=api -n production --since=15m | grep -i stripe

# Count recent Stripe-related errors
kubectl logs -l app=api -n production --since=15m | grep -c "stripe_api_error"
```

## Diagnosis Steps

### 1. Identify Root Cause
Check logs for specific Stripe error types:
```bash
# Filter for Stripe error details
kubectl logs -l app=api -n production --since=30m | \
  jq 'select(.event == "stripe_api_error") | {time: .timestamp, error: .error, correlation_id: .correlation_id}'
```

Common causes:
- **Stripe Outage**: Check status page and wait
- **Rate Limiting**: Check for `429` status codes
- **Auth Issues**: Invalid API key or key rotation
- **Network Issues**: Firewall or DNS problems

### 2. Check Circuit Breaker Configuration
```bash
# Current settings in environment
echo "Failure threshold: $CIRCUIT_BREAKER_FAILURE_THRESHOLD"
echo "Recovery timeout: $CIRCUIT_BREAKER_RECOVERY_TIMEOUT"
echo "Rolling window: $CIRCUIT_BREAKER_ROLLING_WINDOW"
```

### 3. Review Recent Deployments
```bash
# Check if recent deployment changed Stripe-related code
kubectl rollout history deployment/api -n production
git log --oneline --since="1 hour ago" -- backend/app/billing/
```

## Remediation

### If Stripe is Down
1. Wait for Stripe to recover (monitor status page)
2. Circuit breaker will auto-recover after `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` seconds
3. Monitor `billing_reconciliation_last_success_timestamp` for successful recovery

### If Rate Limiting
1. Reduce request rate:
   ```bash
   kubectl set env deployment/api STRIPE_REQUEST_RATE_LIMIT=10 -n production
   ```
2. Review and batch usage reporting if possible

### If Auth/Key Issues
1. Verify Stripe API keys in secrets:
   ```bash
   kubectl get secret stripe-credentials -n production -o jsonpath='{.data.STRIPE_SECRET_KEY}' | base64 -d | head -c 10
   ```
2. Rotate key if compromised (via Stripe dashboard)
3. Update Kubernetes secret and restart pods

### If Network Issues
1. Check DNS resolution:
   ```bash
   kubectl exec -it deploy/api -n production -- nslookup api.stripe.com
   ```
2. Check egress policies/firewall rules

### Manual Circuit Reset
If the underlying issue is resolved but circuit remains open:
```bash
# Force a controlled restart to reset circuit breaker state
kubectl rollout restart deployment/api -n production
```

## Follow-up / Prevention

### Post-Incident
1. Create incident report documenting:
   - Timeline of events
   - Root cause
   - Resolution steps
   - Customer impact
2. Review and adjust circuit breaker thresholds if false positive
3. Update this runbook with lessons learned

### Prevention Measures
- Enable Stripe webhooks for proactive failure detection
- Implement usage event buffering for Stripe outages
- Set up Stripe status page monitoring via webhook
- Review rate limit handling in billing code

## Related Resources
- **Alert Definition**: `infra/alerts/alerts.yaml` → `StripeCircuitOpen`
- **Grafana Dashboard**: `infra/grafana/auth-billing.json`
- **Circuit Breaker Code**: `backend/app/utils/circuit_breaker.py`
- **Stripe Client**: `backend/app/billing/stripe_client.py`
- **Metrics**: `circuit_state{breaker_name="stripe"}`, `billing_reconciliation_last_success_timestamp`
