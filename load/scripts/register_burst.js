// T_TEST.6 — a burst of registrations.
//
// Read the result carefully: with nginx's `auth_zone` (10 r/min per IP, burst 5)
// and slowapi behind it, a burst from one machine measures the **rate limiter**
// as much as the application. That is worth measuring — refusing cheaply is a
// requirement, and a limiter that refuses slowly is a denial of service with
// extra steps — but it is not "how many users can register".
//
// So 429 is declared an expected response rather than a failure, and counted
// separately. `http_req_failed` then keeps its meaning: a real error.
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

import { BASE_URL, DURATION, JSON_HEADERS, PASSWORD, THRESHOLDS, VUS, uniqueEmail } from '../lib/config.js';
import { summarise } from '../lib/summary.js';

const rateLimited = new Counter('rate_limited');
const created = new Counter('accounts_created');

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 429));

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    ...THRESHOLDS,
    // The limiter must answer fast. A slow refusal is the failure mode that
    // matters here: it holds a worker while doing nothing useful.
    'http_req_duration{name:register}': ['p(95)<500'],
  },
};

export default function () {
  const email = uniqueEmail('k6-reg');
  const resp = http.post(
    `${BASE_URL}/api/auth/register`,
    JSON.stringify({
      email,
      password: PASSWORD,
      display_name: 'k6 burst',
    }),
    { headers: JSON_HEADERS, tags: { name: 'register' } },
  );

  if (resp.status === 429) {
    rateLimited.add(1);
  } else if (resp.status === 201) {
    created.add(1);
  }

  check(resp, {
    'register answered 201 or 429': (r) => r.status === 201 || r.status === 429,
  });
}

export function handleSummary(data) {
  return summarise('register_burst', data);
}
