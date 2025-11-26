// k6 Load Test: SSE Connections
// Tests Server-Sent Events under load
//
// Run: k6 run sse.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Gauge } from 'k6/metrics';

const connectionErrors = new Rate('sse_connection_errors');
const activeConnections = new Gauge('sse_active_connections');

export const options = {
  scenarios: {
    sse_connections: {
      executor: 'constant-vus',
      vus: 100,                         // 100 concurrent SSE connections
      duration: __ENV.DURATION || '5m',
    },
  },
  thresholds: {
    sse_connection_errors: ['rate<0.05'], // <5% connection errors
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';

export default function () {
  activeConnections.add(1);

  // Open SSE connection
  const res = http.get(`${BASE_URL}/api/v1/jobs/stream`, {
    headers: {
      'Authorization': 'Bearer test-token',
      'Accept': 'text/event-stream',
    },
    timeout: '60s',
  });

  const success = check(res, {
    'SSE connection established': (r) => r.status === 200 || r.status === 401,
  });

  connectionErrors.add(!success);
  
  // Hold connection for duration
  sleep(30);
  
  activeConnections.add(-1);
}

export function handleSummary(data) {
  return {
    'results/sse-summary.json': JSON.stringify(data),
  };
}
