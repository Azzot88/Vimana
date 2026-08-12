// T_TEST.6 — many writers, one DealVault.
//
// What this is really testing: `append_deal_event` takes a
// `pg_advisory_xact_lock` on the deal before it reads the chain head and
// writes the next entry (T3.6). That lock is per-deal and it is the one
// deliberate serialisation point in the product — every message adds a
// `message_added` entry through it. Concurrency on *one* deal is therefore the
// shape that finds it; a hundred VUs spread over a hundred deals would not.
//
// Deviation from the roadmap wording, written down rather than hidden: the PRD
// says "100 users in one DealVault". A hundred distinct accounts would need a
// hundred registrations plus a hundred recipient invites, and `auth_zone` would
// refuse most of them — the run would measure the limiter again. Two real
// participants writing concurrently exercise the same lock, so the scenario
// keeps the contention and drops the crowd.
import http from 'k6/http';
import { check, sleep } from 'k6';

import { BASE_URL, DURATION, THRESHOLDS, VUS, auth, loginAs } from '../lib/config.js';
import { countFailure } from '../lib/failures.js';
import { summarise } from '../lib/summary.js';

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: THRESHOLDS,
};

export function setup() {
  // Two seeded accounts, 0 and 1. Both can carry and send, so which is which
  // is decided here rather than at seeding time — the deal needs one of each,
  // and nothing else about them differs.
  const carrier = loginAs(http, 0);
  const sender = loginAs(http, 1);

  const departAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();
  const trip = http.post(
    `${BASE_URL}/api/trips`,
    JSON.stringify({
      origin: 'LOD',
      destination: 'TST',
      depart_at: departAt,
      capacity: 10.0,
      allowed_categories: ['document'],
    }),
    auth(carrier.token),
  );
  if (trip.status !== 201) {
    throw new Error(`setup: trip failed ${trip.status} ${trip.body}`);
  }

  const deal = http.post(
    `${BASE_URL}/api/deals/match`,
    JSON.stringify({
      trip_id: trip.json('id'),
      order: {
        recipient_contact: '+10000000099',
        origin: 'LOD',
        destination: 'TST',
        category: 'document',
        declared_value: 100.0,
      },
    }),
    auth(sender.token),
  );
  if (deal.status !== 201) {
    throw new Error(`setup: match failed ${deal.status} ${deal.body}`);
  }

  return { dealId: deal.json('id'), sender: sender.token, carrier: carrier.token };
}

export default function (data) {
  // Alternate sides so both ends of the deal write into the same chain.
  const token = __VU % 2 === 0 ? data.sender : data.carrier;
  const opts = auth(token);

  const write = http.post(
    `${BASE_URL}/api/deals/${data.dealId}/dealvault/messages`,
    JSON.stringify({ text: `k6 message vu=${__VU} iter=${__ITER}` }),
    { ...opts, tags: { name: 'vault:write' } },
  );
  countFailure(write);
  check(write, { 'message 201': (r) => r.status === 201 });

  const read = http.get(`${BASE_URL}/api/deals/${data.dealId}/dealvault?limit=20`, {
    ...opts,
    tags: { name: 'vault:read' },
  });
  countFailure(read);
  check(read, { 'vault 200': (r) => r.status === 200 });

  // The chain check is the expensive read: it recomputes hashes from genesis.
  // Sampled rather than every iteration — the UI opens it on demand, and doing
  // it every time would drown the write numbers this scenario is about.
  if (__ITER % 10 === 0) {
    const chain = http.get(`${BASE_URL}/api/deals/${data.dealId}/chain`, {
      ...opts,
      tags: { name: 'vault:chain' },
    });
    countFailure(chain);
    check(chain, { 'chain 200': (r) => r.status === 200 });
  }

  sleep(Math.random());
}

export function handleSummary(data) {
  return summarise('chat_hammer', data);
}
