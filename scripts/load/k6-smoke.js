import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const RUN_ID = __ENV.RUN_ID || `${Date.now()}`;
const PASSWORD = __ENV.LOAD_TEST_PASSWORD || 'LoadTestAa12';

export const options = {
  vus: Number(__ENV.VUS || 1),
  iterations: Number(__ENV.ITERATIONS || 1),
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<5000'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  const username = `load_smoke_${RUN_ID}`;
  const registerRes = http.post(
    `${BASE_URL}/auth/register`,
    JSON.stringify({
      username,
      password: PASSWORD,
      display_name: username,
    }),
    jsonHeaders(),
  );

  check(registerRes, {
    'register created or already exists': (res) => res.status === 201 || res.status === 409,
  });

  const loginRes = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ username, password: PASSWORD }),
    jsonHeaders(),
  );

  check(loginRes, {
    'login ok': (res) => res.status === 200 && Boolean(res.json('access_token')),
  });

  return {
    token: loginRes.json('access_token'),
    username,
  };
}

export default function (data) {
  const authHeaders = {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${data.token}`,
    },
  };

  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health 200': (res) => res.status === 200,
  });

  const agentRes = http.post(
    `${BASE_URL}/agent/query`,
    JSON.stringify({
      session_id: `load-smoke-session-${RUN_ID}`,
      query: '深圳湾明天上午9点到11点可以进行无人机巡检吗',
    }),
    authHeaders,
  );
  check(agentRes, {
    'agent query 200': (res) => res.status === 200,
    'agent query success': (res) => res.json('success') === true,
  });

  const evaluateRes = http.post(
    `${BASE_URL}/cruise/evaluate`,
    JSON.stringify({
      location: '深圳湾',
      date: '2026-08-27',
      start_time: '09:00',
      end_time: '11:00',
      task_type: 'inspection',
      purpose: 'load smoke evaluate',
    }),
    jsonHeaders(),
  );
  check(evaluateRes, {
    'evaluate 200': (res) => res.status === 200,
  });

  sleep(1);
}

function jsonHeaders() {
  return {
    headers: {
      'Content-Type': 'application/json',
    },
  };
}
