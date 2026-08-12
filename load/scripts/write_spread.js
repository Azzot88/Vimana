// T_TEST.6 — writes spread across many deals, which is what a busy hour is.
//
// `chat_hammer` answers "how fast can one conversation go" and found the
// per-deal advisory lock at ~40 writes/second (2026-08-11). That is the right
// question for the lock and the wrong one for capacity: the lock is taken **per
// deal**, so a platform with fifty live conversations does not queue behind one
// of them.
//
// This scenario asks the other question. Same write, spread over `DEALS`
// chains, so contention per chain stays below the knee that `chat_hammer`
// found and whatever limit appears is a limit of the machine — connections,
// CPU, Postgres — rather than of the design.
//
// Read the pair together or neither number means much:
//   chat_hammer  → the ceiling of one conversation  (~40 rps, by design)
//   write_spread → the ceiling of the platform's write path
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

import { BASE_URL, DURATION, THRESHOLDS, VUS, auth, loginAs } from '../lib/config.js';
import { summarise } from '../lib/summary.js';

// Eight, so that fifty VUs put about six on each chain — comfortably under the
// ten where `chat_hammer` was still linear. More chains would measure the same
// thing and cost more setup; fewer would reintroduce the contention this
// scenario exists to avoid.
const DEALS = Number(__ENV.K6_DEALS || 8);

const write = new Trend('ep_vault_write', true);

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: THRESHOLDS,
};

export function setup() {
  // Accounts 0 and 1, the same pair `chat_hammer` uses. The two scenarios are
  // not run at once, and sharing the pair keeps the seeded set at four.
  const carrier = loginAs(http, 0);
  const sender = loginAs(http, 1);

  const departAt = new Date(Date.now() + 9 * 24 * 3600 * 1000).toISOString();
  const deals = [];

  for (let index = 0; index < DEALS; index += 1) {
    const trip = http.post(
      `${BASE_URL}/api/trips`,
      JSON.stringify({
        origin: 'SPR',
        destination: 'EAD',
        depart_at: departAt,
        capacity: 10.0,
        allowed_categories: ['document'],
      }),
      auth(carrier.token),
    );
    if (trip.status !== 201) {
      throw new Error(`setup: trip ${index} failed ${trip.status} ${trip.body}`);
    }

    const deal = http.post(
      `${BASE_URL}/api/deals/match`,
      JSON.stringify({
        trip_id: trip.json('id'),
        order: {
          recipient_contact: `+1000000${String(index).padStart(4, '0')}`,
          origin: 'SPR',
          destination: 'EAD',
          category: 'document',
          declared_value: 100.0,
        },
      }),
      auth(sender.token),
    );
    if (deal.status !== 201) {
      throw new Error(`setup: match ${index} failed ${deal.status} ${deal.body}`);
    }
    deals.push(deal.json('id'));
  }

  return { deals, sender: sender.token, carrier: carrier.token };
}

export default function (data) {
  // Each VU keeps to one chain for the whole run rather than hopping. Hopping
  // would spread every VU's writes over every lock and hide contention that a
  // real conversation would feel — the point is many chains, not many locks per
  // writer.
  const dealId = data.deals[__VU % data.deals.length];
  const token = __VU % 2 === 0 ? data.sender : data.carrier;

  const resp = http.post(
    `${BASE_URL}/api/deals/${dealId}/dealvault/messages`,
    JSON.stringify({ text: `k6 spread vu=${__VU} iter=${__ITER}` }),
    { ...auth(token), tags: { name: 'vault:write' } },
  );
  write.add(resp.timings.duration);
  check(resp, { 'message 201': (r) => r.status === 201 });

  sleep(Math.random());
}

export function handleSummary(data) {
  return summarise('write_spread', data);
}
