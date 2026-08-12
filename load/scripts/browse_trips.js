// T_TEST.6 — the read path an anonymous visitor takes.
//
// Everything here is public by design (`GET /api/trips`, airports, categories,
// notices), so no token is involved. That is the point: this scenario measures
// the database and the cursor pagination, with authentication out of the
// picture. When p95 moves here, it moved in a query.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

import { BASE_URL, DURATION, THRESHOLDS, VUS } from '../lib/config.js';
import { summarise } from '../lib/summary.js';

// One trend per endpoint, so the summary can say *which* one owns the tail.
// The 2026-08-03 run reported p95 1064 ms against a 500 ms threshold with a
// median of 543 — a shape that means one endpoint is dragging the aggregate,
// and an aggregate cannot name it. The `ep_` prefix is what `summarise` looks
// for; the tags stay for anyone reading a raw k6 export.
const EP = {
  'trips:list': new Trend('ep_trips_list', true),
  'trips:page2': new Trend('ep_trips_page2', true),
  airports: new Trend('ep_airports', true),
  categories: new Trend('ep_categories', true),
};

// A `Trend` carries avg/min/med/max/percentiles and **no count** — the first
// breakdown printed "0 requests" for every row, which is worse than printing
// nothing because it looks like a measurement. The count matters: the run of
// 2026-08-11 fired zero `trips:page2` requests, and only the row's absence said
// so. A counter says it in the row itself.
const HITS = {
  'trips:list': new Counter('epc_trips_list'),
  'trips:page2': new Counter('epc_trips_page2'),
  airports: new Counter('epc_airports'),
  categories: new Counter('epc_categories'),
};

// Who refused, not merely how often. The 2026-08-11 run with two workers put
// `http_req_failed` at 1.8 % — over the 1 % threshold — and a rate alone cannot
// tell nginx's rate limiter (429) from an upstream that fell over (502/504)
// from the application raising (500). Those are three different repairs, and
// guessing between them is a run wasted.
const ERR = {
  rate_limited: new Counter('err_429'),
  gateway: new Counter('err_gateway'),
  server: new Counter('err_5xx'),
  client: new Counter('err_4xx'),
  none: new Counter('err_other'),
};

function classify(status) {
  if (status === 429) return ERR.rate_limited;
  if (status === 502 || status === 503 || status === 504) return ERR.gateway;
  if (status >= 500) return ERR.server;
  if (status >= 400) return ERR.client;
  // k6 reports a transport failure — refused, reset, timed out — as status 0.
  return ERR.none;
}

/** Record a response against its endpoint trend, its counter and its check. */
function timed(res, key, ok) {
  EP[key].add(res.timings.duration);
  HITS[key].add(1);
  if (res.status < 200 || res.status >= 400) classify(res.status).add(1);
  check(res, ok);
  return res;
}

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: THRESHOLDS,
};

const CORRIDORS = [
  ['DXB', 'JFK'],
  ['JFK', 'DXB'],
  ['WAW', 'DXB'],
  ['', ''], // unfiltered listing — the heaviest of the three
];

export default function () {
  const [origin, destination] = CORRIDORS[Math.floor(Math.random() * CORRIDORS.length)];
  const query = origin ? `?origin=${origin}&destination=${destination}` : '';

  const list = timed(
    http.get(`${BASE_URL}/api/trips${query}`, { tags: { name: 'trips:list' } }),
    'trips:list',
    { 'trips 200': (r) => r.status === 200 },
  );

  // Page two, the way the UI does it — a cursor, never an offset. A regression
  // in `paginate_desc` shows up here and nowhere else in this file.
  const cursor = list.status === 200 ? list.json('next_cursor') : null;
  if (cursor) {
    timed(
      http.get(`${BASE_URL}/api/trips${query ? query + '&' : '?'}after=${cursor}`, {
        tags: { name: 'trips:page2' },
      }),
      'trips:page2',
      { 'page 2 200': (r) => r.status === 200 },
    );
  }

  // The two lookups every trip form fires while someone types.
  timed(
    http.get(`${BASE_URL}/api/airports?q=du`, { tags: { name: 'airports' } }),
    'airports',
    { 'airports 200': (r) => r.status === 200 },
  );

  timed(
    http.get(`${BASE_URL}/api/categories`, { tags: { name: 'categories' } }),
    'categories',
    { 'categories 200': (r) => r.status === 200 },
  );

  sleep(Math.random() * 2);
}

export function handleSummary(data) {
  return summarise('browse_trips', data);
}
