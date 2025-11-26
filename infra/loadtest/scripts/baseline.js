// k6 Load Test: API Baseline
// Tests basic API endpoints under normal load
//
// Run: k6 run baseline.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const jobCreateLatency = new Trend('job_create_latency');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp up to 50 VUs
    { duration: '5m', target: 50 },   // Stay at 50 VUs
    { duration: '1m', target: 100 },  // Ramp up to 100 VUs
    { duration: '5m', target: 100 },  // Stay at 100 VUs
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200', 'p(99)<500'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';

// Simulated JWT token (replace with actual auth in real tests)
const AUTH_HEADERS = {
  'Authorization': 'Bearer test-token',
  'Content-Type': 'application/json',
};

export default function () {
  // Health check endpoint
  const healthRes = http.get(`${BASE_URL}/api/v1/health`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
  });

  // Metrics endpoint
  const metricsRes = http.get(`${BASE_URL}/metrics`);
  check(metricsRes, {
    'metrics status is 200': (r) => r.status === 200,
  });

  // Jobs list endpoint (authenticated)
  const jobsRes = http.get(`${BASE_URL}/api/v1/jobs`, {
    headers: AUTH_HEADERS,
  });
  
  const jobsSuccess = check(jobsRes, {
    'jobs list status is 200 or 401': (r) => r.status === 200 || r.status === 401,
  });
  
  errorRate.add(!jobsSuccess);

  // Job creation endpoint
  const payload = JSON.stringify({
    payload: {
      task_type: 'test',
      params: { url: 'https://example.com' },
    },
    idempotency_key: `load-test-${__VU}-${__ITER}`,
  });

  const createStart = Date.now();
  const createRes = http.post(`${BASE_URL}/api/v1/jobs`, payload, {
    headers: AUTH_HEADERS,
  });
  jobCreateLatency.add(Date.now() - createStart);

  const createSuccess = check(createRes, {
    'job create status is 201, 200, or 401': (r) => 
      r.status === 201 || r.status === 200 || r.status === 401,
  });
  
  errorRate.add(!createSuccess);

  sleep(1);
}

export function handleSummary(data) {
  return {
    'results/baseline-summary.json': JSON.stringify(data),
  };
}
