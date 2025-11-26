# Runbook: Auth JWKS Failures

## Overview
This runbook addresses JWT Key Set (JWKS) related failures, including the `JWTInvalidRateHigh` alert and JWKS refresh failures that impact authentication.

## Symptoms
- Alert `JWTInvalidRateHigh` firing (>5% invalid JWT rate)
- Logs showing `jwks_refresh_failed` events
- Increasing `auth_jwt_invalid_total{reason="unknown_kid"}` metric
- Users reporting 401 Unauthorized errors on authenticated endpoints
- Spike in `msaas_jwt_validation_duration_seconds` latency

## Impact
- **Customer Impact**: Users cannot access authenticated API endpoints
- **Business Impact**: All user-facing features unavailable
- **Data Impact**: No data loss, but jobs cannot be submitted or viewed

## Immediate Actions

### 1. Acknowledge the Alert
- Acknowledge in PagerDuty/OpsGenie to prevent escalation
- Post in `#incidents` Slack channel: "Investigating JWT/JWKS authentication failures"

### 2. Determine Failure Mode
```bash
# Check JWT validation metrics
curl -s http://api:8000/metrics | grep 'auth_jwt_invalid_total'

# Check JWKS refresh status in logs
kubectl logs -l app=api -n production --since=15m | \
  grep -E "(jwks_refreshed|jwks_refresh_failed)"
```

### 3. Check Supabase Status
- Visit Supabase project dashboard
- Check [Supabase Status Page](https://status.supabase.com/) for incidents
- Verify JWKS endpoint is accessible:
  ```bash
  curl -s "$SUPABASE_JWT_JWKS_URL" | jq '.keys | length'
  ```

## Diagnosis Steps

### 1. Identify Root Cause Type

**A. JWKS Endpoint Unavailable**
```bash
# Test JWKS endpoint from within cluster
kubectl exec -it deploy/api -n production -- \
  curl -s -w "\n%{http_code}" "$SUPABASE_JWT_JWKS_URL"

# Check DNS resolution
kubectl exec -it deploy/api -n production -- \
  nslookup $(echo $SUPABASE_URL | sed 's|https://||')
```

**B. Key Rotation / Unknown KID**
```bash
# Check for unknown_kid errors
kubectl logs -l app=api -n production --since=30m | \
  grep "unknown_kid" | head -20

# List cached key IDs vs incoming tokens
kubectl logs -l app=api -n production --since=5m | \
  jq 'select(.event == "jwt_validation_failed") | .kid' | sort | uniq -c
```

**C. Token Issues (Client-Side)**
```bash
# Check for specific failure reasons
curl -s http://api:8000/metrics | grep 'auth_jwt_invalid_total' | sort -t'=' -k2

# Common reasons: expired, invalid_signature, missing_token, wrong_audience
```

**D. Configuration Mismatch**
```bash
# Verify environment configuration
kubectl exec -it deploy/api -n production -- env | grep -E "(SUPABASE_URL|SUPABASE_JWT)"

# Check expected issuer and audience
echo "Expected issuer: $SUPABASE_URL"
echo "Expected audience: $SUPABASE_JWT_AUDIENCE"
```

### 2. Check Cache State
```bash
# Look for cache-related log entries
kubectl logs -l app=api -n production --since=15m | \
  grep -E "(jwks_cache|keys_cached|cache_fallback)"

# Check cache TTL status
kubectl logs -l app=api -n production --since=5m | \
  jq 'select(.event == "jwks_refreshed") | {time: .timestamp, key_count: .key_count}'
```

### 3. Check Client Token Validity
```bash
# Sample a failing request's correlation_id
CORR_ID=$(kubectl logs -l app=api -n production --since=5m | \
  jq -r 'select(.event == "jwt_validation_failed") | .correlation_id' | head -1)

# Trace the full request
kubectl logs -l app=api -n production --since=15m | \
  jq --arg cid "$CORR_ID" 'select(.correlation_id == $cid)'
```

## Remediation

### A. JWKS Endpoint Unavailable (Use Cache)
The system automatically falls back to cached keys. Verify fallback is working:
```bash
# Check if requests are succeeding with cached keys
kubectl logs -l app=api -n production --since=5m | \
  grep -c "jwt_validation.*valid"

# If cache is stale (no valid keys), consider manual intervention
```

### B. Force JWKS Refresh
```bash
# Restart API pods to force JWKS re-fetch
kubectl rollout restart deployment/api -n production

# Monitor JWKS refresh
kubectl logs -l app=api -n production -f | grep jwks
```

### C. Key Rotation Handling
If Supabase rotated keys and clients have old tokens:
1. Wait for clients to re-authenticate (tokens expire naturally)
2. For immediate relief, extend cache TTL temporarily
3. Communicate to clients that re-login may be needed

### D. Fix Configuration
```bash
# If environment variables are wrong
kubectl set env deployment/api \
  SUPABASE_JWT_JWKS_URL="https://your-project.supabase.co/rest/v1/.well-known/jwks.json" \
  SUPABASE_JWT_AUDIENCE="authenticated" \
  -n production

# Restart to apply
kubectl rollout restart deployment/api -n production
```

### E. Client-Side Token Issues
For widespread `expired` or `wrong_audience` issues:
1. Check frontend configuration for correct Supabase project
2. Verify client is using correct `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. Check for clock skew issues

## Follow-up / Prevention

### Post-Incident
1. Create incident report documenting:
   - Root cause (Supabase outage, key rotation, misconfiguration)
   - Duration of authentication failures
   - Number of affected users
2. Review JWKS cache TTL settings
3. Consider adding JWKS endpoint health check to probes

### Prevention Measures
- **Cache TTL**: Ensure cache TTL is long enough to survive temporary outages (minimum 5 minutes recommended)
- **Retry Logic**: Implement exponential backoff for JWKS fetches
- **Monitoring**: 
  - Add alert for JWKS refresh failures
  - Monitor cache age vs TTL
- **Multiple Keys**: Ensure JWKS contains both old and new keys during rotation periods
- **Documentation**: Keep Supabase project credentials in secure location with rotation procedures

### Cache Configuration
Recommended settings:
```python
# backend/app/config.py
JWKS_CACHE_TTL_SECONDS: int = 300  # 5 minutes
JWKS_STALE_TTL_SECONDS: int = 3600  # 1 hour fallback
JWKS_REFRESH_TIMEOUT_SECONDS: float = 5.0
JWKS_REFRESH_RETRIES: int = 3
```

## Related Resources
- **Alert Definition**: `infra/alerts/alerts.yaml` → `JWTInvalidRateHigh`
- **Grafana Dashboard**: `infra/grafana/auth-billing.json`
- **JWT Validator Code**: `backend/app/auth/jwt_validator.py`
- **Metrics**: 
  - `auth_jwt_invalid_total{reason}`
  - `msaas_jwt_validation_duration_seconds`
- **Configuration**: 
  - `SUPABASE_URL`
  - `SUPABASE_JWT_JWKS_URL`
  - `SUPABASE_JWT_AUDIENCE`
- **Supabase Docs**: [Supabase JWT Documentation](https://supabase.com/docs/guides/auth/jwts)
