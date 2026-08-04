// T_TEST.6 — the read path an anonymous visitor takes.
//
// Everything here is public by design (`GET /api/trips`, airports, categories,
// notices), so no token is involved. That is the point: this scenario measures
// the database and the cursor pagination, with authentication out of the
// picture. When p95 moves here, it moved in a query.
import http from 'k6/http';
import { check, sleep } from 'k6';

import { BASE_URL, DURATION, THRESHOLDS, VUS } from '../lib/config.js';
import { summarise } from '../lib/summary.js';

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

  const list = http.get(`${BASE_URL}/api/trips${query}`, { tags: { name: 'trips:list' } });
  check(list, { 'trips 200': (r) => r.status === 200 });

  // Page two, the way the UI does it — a cursor, never an offset. A regression
  // in `paginate_desc` shows up here and nowhere else in this file.
  const cursor = list.status === 200 ? list.json('next_cursor') : null;
  if (cursor) {
    const next = http.get(`${BASE_URL}/api/trips${query ? query + '&' : '?'}after=${cursor}`, {
      tags: { name: 'trips:page2' },
    });
    check(next, { 'page 2 200': (r) => r.status === 200 });
  }

  // The two lookups every trip form fires while someone types.
  const airports = http.get(`${BASE_URL}/api/airports?q=du`, { tags: { name: 'airports' } });
  check(airports, { 'airports 200': (r) => r.status === 200 });

  const categories = http.get(`${BASE_URL}/api/categories`, { tags: { name: 'categories' } });
  check(categories, { 'categories 200': (r) => r.status === 200 });

  sleep(Math.random() * 2);
}

export function handleSummary(data) {
  return summarise('browse_trips', data);
}
