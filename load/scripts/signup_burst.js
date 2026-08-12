// T_TEST.6 — a burst against the public sign-up door.
//
// Was `register_burst.js` until 2026-08-11, when it started measuring an
// endpoint that no longer exists: `POST /auth/register` went in `T3.28 pt.3b`,
// and the door is now `POST /auth/otp/request` — type an address, get a code,
// and the account is born when the code comes back. Nothing about the shape of
// the test changes; the thing being hammered does.
//
// Read the result carefully: this measures the **limiters** as much as the
// application, and now there are two of them — nginx's zones and, since
// `T3.29`, a budget per mailbox (5/hour) and per source (10 distinct mailboxes
// an hour). From one machine the second trips within seconds and everything
// after is a refusal. That is worth measuring and is the point: refusing
// cheaply is a requirement, and a limiter that refuses slowly is a denial of
// service with extra steps. It is not "how many people can sign up".
//
// So 429 is an expected response rather than a failure, and counted
// separately. `http_req_failed` then keeps its meaning: a real error.
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

import { BASE_URL, DURATION, JSON_HEADERS, THRESHOLDS, VUS, uniqueEmail } from '../lib/config.js';
import { countFailure } from '../lib/failures.js';
import { summarise } from '../lib/summary.js';

const rateLimited = new Counter('rate_limited');
const accepted = new Counter('codes_accepted');

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 429));

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    ...THRESHOLDS,
    // The limiter must answer fast. A slow refusal is the failure mode that
    // matters here: it holds a worker while doing nothing useful.
    'http_req_duration{name:signup}': ['p(95)<500'],
  },
};

export default function () {
  const resp = http.post(
    `${BASE_URL}/api/auth/otp/request`,
    JSON.stringify({
      identifier: uniqueEmail('k6-signup'),
      channel: 'email',
      locale: 'en',
    }),
    { headers: JSON_HEADERS, tags: { name: 'signup' } },
  );

  if (resp.status === 429) {
    rateLimited.add(1);
  } else if (resp.status === 202) {
    accepted.add(1);
  }
  // Counted in the shared breakdown too. The two are not redundant: `429` here
  // is a success (the limiter working) and there it is a category, and a run
  // where the refusals are 503 rather than 429 means something entirely
  // different — the difference is invisible without both.
  countFailure(resp);

  check(resp, {
    'signup answered 202 or 429': (r) => r.status === 202 || r.status === 429,
  });
}

export function handleSummary(data) {
  return summarise('signup_burst', data);
}
