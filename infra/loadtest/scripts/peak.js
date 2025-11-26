// k6 Load Test: Peak Load
// Tests API under peak load conditions (10,000 req/min target)
//
// Run: k6 run peak.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Counter } from 'k6/metrics';

const errorRate = new Rate('errors');
const requestsTotal = new Counter('requests_total');

export const options = {
  stages: [
    { duration: '2m', target: 167 },   // Ramp to ~10k/min
    { duration: '10m', target: 167 },  // Sustained peak
    { duration: '2m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<50'],   // SLO: p99 < 50ms
    http_req_failed: ['rate<0.001'],   // SLO: <0.1% error rate
    errors: ['rate<0.001'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';

export default function () {
  // Mixed workload: 70% reads, 30% writes
  const isWrite = Math.random() < 0.3;

  if (isWrite) {
    const payload = JSON.stringify({
      payload: {
        task_type: 'benchmark',
        params: { iteration: __ITER },
      },
    });

    const res = http.post(`${BASE_URL}/api/v1/jobs`, payload, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer test-token',
      },
    });

    const success = check(res, {
      'write status ok': (r) => r.status < 400,
    });
    
    errorRate.add(!success);
    requestsTotal.add(1);
  } else {
    const res = http.get(`${BASE_URL}/api/v1/jobs`, {
      headers: { 'Authorization': 'Bearer test-token' },
    });

    const success = check(res, {
      'read status ok': (r) => r.status < 400,
    });
    
    errorRate.add(!success);
    requestsTotal.add(1);
  }

  sleep(0.1);
}

export function handleSummary(data) {
  return {
    'results/peak-summary.json': JSON.stringify(data),
  };
}
