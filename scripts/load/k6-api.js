import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const RUN_ID = __ENV.RUN_ID || `${Date.now()}`;
const PASSWORD = __ENV.LOAD_TEST_PASSWORD || 'LoadTestAa12';
const USER_COUNT = Number(__ENV.USER_COUNT || __ENV.VUS || 3);
const REQ_P95_MS = Number(__ENV.REQ_P95_MS || 20000);
const HEALTH_P95_MS = Number(__ENV.HEALTH_P95_MS || 500);
const AGENT_P95_MS = Number(__ENV.AGENT_P95_MS || 12000);
const EVALUATE_P95_MS = Number(__ENV.EVALUATE_P95_MS || 20000);
const QUERY_P95_MS = Number(__ENV.QUERY_P95_MS || 1500);

export const options = {
  scenarios: {
    local_baseline: {
      executor: 'ramping-vus',
      stages: [
        { duration: __ENV.RAMP_UP || '15s', target: Number(__ENV.VUS || 3) },
        { duration: __ENV.HOLD || '45s', target: Number(__ENV.VUS || 3) },
        { duration: __ENV.RAMP_DOWN || '10s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: [`p(95)<${REQ_P95_MS}`],
    'http_req_duration{endpoint:health}': [`p(95)<${HEALTH_P95_MS}`],
    'http_req_duration{endpoint:agent_query}': [`p(95)<${AGENT_P95_MS}`],
    'http_req_duration{endpoint:evaluate}': [`p(95)<${EVALUATE_P95_MS}`],
    'http_req_duration{endpoint:tasks_list}': [`p(95)<${QUERY_P95_MS}`],
    'http_req_duration{endpoint:trace_detail}': [`p(95)<${QUERY_P95_MS}`],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  const users = [];

  for (let index = 0; index < USER_COUNT; index += 1) {
    const username = `load_user_${RUN_ID}_${index}`;
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

    const token = loginRes.json('access_token');
    const taskId = createSeedTask(token, username);
    const traceId = createSeedTrace(token, index);
    users.push({ username, token, taskId, traceId });
  }

  return { users };
}

export default function (data) {
  const user = data.users[(__VU - 1) % data.users.length];
  const authHeaders = {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${user.token}`,
    },
  };
  const step = ((__ITER * Number(__ENV.VUS || 3)) + (__VU - 1)) % 10;

  if (step === 0) {
    group('health', () => {
      const res = http.get(`${BASE_URL}/health`, { tags: { endpoint: 'health' } });
      check(res, { 'health 200': (response) => response.status === 200 });
    });
  } else if (step <= 3) {
    group('agent_query', () => {
      const res = http.post(
        `${BASE_URL}/agent/query`,
        JSON.stringify({
          session_id: `load-session-${RUN_ID}-${__VU}`,
          query: '深圳湾明天上午9点到11点可以进行无人机巡检吗',
        }),
        withTags(authHeaders, { endpoint: 'agent_query' }),
      );
      check(res, {
        'agent query 200': (response) => response.status === 200,
        'agent query success': (response) => response.json('success') === true,
      });
    });
  } else if (step <= 5) {
    group('evaluate', () => {
      const res = http.post(
        `${BASE_URL}/cruise/evaluate`,
        JSON.stringify({
          location: '深圳湾',
          date: '2026-08-27',
          start_time: '09:00',
          end_time: '11:00',
          task_type: 'inspection',
          purpose: `load baseline ${RUN_ID}`,
        }),
        withTags(jsonHeaders(), { endpoint: 'evaluate' }),
      );
      check(res, { 'evaluate 200': (response) => response.status === 200 });
    });
  } else if (step <= 7) {
    group('tasks_list', () => {
      const res = http.get(
        `${BASE_URL}/tasks?page=1&page_size=20`,
        withTags(authHeaders, { endpoint: 'tasks_list' }),
      );
      check(res, { 'tasks list 200': (response) => response.status === 200 });
    });
  } else {
    group('trace_detail', () => {
      if (!user.traceId) {
        return;
      }
      const res = http.get(
        `${BASE_URL}/agent/traces/${user.traceId}`,
        withTags(authHeaders, { endpoint: 'trace_detail' }),
      );
      check(res, { 'trace detail 200': (response) => response.status === 200 });
    });
  }

  sleep(Number(__ENV.SLEEP_SECONDS || 1));
}

function createSeedTask(token, username) {
  const res = http.post(
    `${BASE_URL}/tasks`,
    JSON.stringify({
      title: `load seed task ${username}`,
      purpose: 'load baseline seed task',
      location: '深圳湾',
      date: '2026-08-27',
      start_time: '09:00',
      end_time: '11:00',
      task_type: 'inspection',
      candidate_locations: ['深圳湾', '南山区'],
      metadata: { run_id: RUN_ID },
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      tags: { endpoint: 'setup_task_create' },
    },
  );

  check(res, { 'seed task created': (response) => response.status === 201 });
  return res.status === 201 ? res.json('id') : null;
}

function createSeedTrace(token, index) {
  const res = http.post(
    `${BASE_URL}/agent/query`,
    JSON.stringify({
      session_id: `load-seed-session-${RUN_ID}-${index}`,
      query: '深圳湾明天上午9点到11点可以进行无人机巡检吗',
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      tags: { endpoint: 'setup_agent_query' },
    },
  );

  check(res, { 'seed agent query 200': (response) => response.status === 200 });
  return res.status === 200 ? res.json('agent_runtime.trace_id') : null;
}

function jsonHeaders() {
  return {
    headers: {
      'Content-Type': 'application/json',
    },
  };
}

function withTags(params, tags) {
  return {
    ...params,
    tags: {
      ...(params.tags || {}),
      ...tags,
    },
  };
}
