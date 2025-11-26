// k6 Load Test: Job Backlog
// Tests system behavior when jobs are submitted faster than processing
//
// Run: k6 run backlog.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';

const submissionErrors = new Rate('job_submission_errors');
const jobsSubmitted = new Counter('jobs_submitted');
const submissionLatency = new Trend('job_submission_latency');

export const options = {
  scenarios: {
    job_flood: {
      executor: 'constant-arrival-rate',
      rate: 200,                          // 200 jobs/second
      timeUnit: '1s',
      duration: __ENV.DURATION || '5m',
      preAllocatedVUs: 50,
      maxVUs: 100,
    },
  },
  thresholds: {
    job_submission_errors: ['rate<0.1'],  // <10% errors under backlog
    job_submission_latency: ['p(95)<1000'], // <1s even under load
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';

export default function () {
  const payload = JSON.stringify({
    payload: {
      task_type: 'browser',
      params: {
        url: 'https://example.com',
        action: 'navigate_extract',
      },
    },
  });

  const start = Date.now();
  const res = http.post(`${BASE_URL}/api/v1/jobs`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer test-token',
    },
    timeout: '10s',
  });
  submissionLatency.add(Date.now() - start);

  const success = check(res, {
    'job submitted': (r) => r.status === 201 || r.status === 200 || r.status === 429,
  });

  submissionErrors.add(!success);
  
  if (success) {
    jobsSubmitted.add(1);
  }
}

export function handleSummary(data) {
  return {
    'results/backlog-summary.json': JSON.stringify(data),
  };
}
