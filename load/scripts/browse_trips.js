// T_TEST.6 — the read path an anonymous visitor takes.
//
// Everything here is public by design (`GET /api/trips`, airports, categories,
// notices), so no token is involved. That is the point: this scenario measures
// the database and the cursor pagination, with authentication out of the
// picture. When p95 moves here, it moved in a query.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

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

/** Record a response against both its endpoint trend and its check. */
function timed(res, key, ok) {
  EP[key].add(res.timings.duration);
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
