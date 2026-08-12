// T_TEST.6 — the three paths at once, in roughly the proportion a real hour has.
//
// Browsing dominates, chatting is a minority of sessions, registration is rare.
// Run in isolation each scenario looks fine; run together they share a
// connection pool, a Redis, and one Celery queue, and that is where a limit
// shows up first.
import http from 'k6/http';
import { check, sleep } from 'k6';

import { BASE_URL, DURATION, JSON_HEADERS, THRESHOLDS, VUS, auth, loginAs, uniqueEmail } from '../lib/config.js';
import { countFailure } from '../lib/failures.js';
import { summarise } from '../lib/summary.js';

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 429));

const BROWSE_VUS = Math.max(1, Math.round(VUS * 0.7));
const CHAT_VUS = Math.max(1, Math.round(VUS * 0.2));
const REGISTER_VUS = Math.max(1, Math.round(VUS * 0.1));

export const options = {
  thresholds: THRESHOLDS,
  scenarios: {
    browse: {
      executor: 'constant-vus',
      exec: 'browse',
      vus: BROWSE_VUS,
      duration: DURATION,
    },
    chat: {
      executor: 'constant-vus',
      exec: 'chat',
      vus: CHAT_VUS,
      duration: DURATION,
    },
    register: {
      executor: 'constant-vus',
      exec: 'register',
      vus: REGISTER_VUS,
      duration: DURATION,
    },
  },
};

export function setup() {
  // Accounts 2 and 3, so a mixed run and a `chat_hammer` run can share a
  // deployment without writing into each other's deal.
  const carrier = loginAs(http, 2);
  const sender = loginAs(http, 3);

  const departAt = new Date(Date.now() + 5 * 24 * 3600 * 1000).toISOString();
  const trip = http.post(
    `${BASE_URL}/api/trips`,
    JSON.stringify({
      origin: 'MIX',
      destination: 'LDW',
      depart_at: departAt,
      capacity: 8.0,
      allowed_categories: ['document'],
    }),
    auth(carrier.token),
  );
  if (trip.status !== 201) throw new Error(`setup: trip ${trip.status} ${trip.body}`);

  const deal = http.post(
    `${BASE_URL}/api/deals/match`,
    JSON.stringify({
      trip_id: trip.json('id'),
      order: {
        recipient_contact: '+10000000098',
        origin: 'MIX',
        destination: 'LDW',
        category: 'document',
        declared_value: 75.0,
      },
    }),
    auth(sender.token),
  );
  if (deal.status !== 201) throw new Error(`setup: match ${deal.status} ${deal.body}`);

  return { dealId: deal.json('id'), sender: sender.token };
}

export function browse() {
  const list = http.get(`${BASE_URL}/api/trips`, { tags: { name: 'trips:list' } });
  check(list, { 'trips 200': (r) => r.status === 200 });
  http.get(`${BASE_URL}/api/categories`, { tags: { name: 'categories' } });
  sleep(Math.random() * 3);
}

export function chat(data) {
  const opts = auth(data.sender);
  const write = http.post(
    `${BASE_URL}/api/deals/${data.dealId}/dealvault/messages`,
    JSON.stringify({ text: `k6 mixed vu=${__VU}` }),
    { ...opts, tags: { name: 'vault:write' } },
  );
  countFailure(write);
  check(write, { 'message 201': (r) => r.status === 201 });
  sleep(Math.random() * 2);
}

export function register() {
  // The sign-up door as it is since `T3.28`: an address goes in, a code comes
  // back by mail, and the account exists when the code is spent. Only the first
  // half is load-bearing here — k6 cannot read a mailbox, and the point of this
  // slice is the traffic the door takes, not the accounts it makes.
  const resp = http.post(
    `${BASE_URL}/api/auth/otp/request`,
    JSON.stringify({
      identifier: uniqueEmail('k6-mix'),
      channel: 'email',
      locale: 'en',
    }),
    { headers: JSON_HEADERS, tags: { name: 'signup' } },
  );
  countFailure(resp);
  check(resp, { 'signup 202 or 429': (r) => r.status === 202 || r.status === 429 });
  sleep(5);
}

export function handleSummary(data) {
  return summarise('mixed_workload', data);
}
