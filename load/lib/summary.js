// T_TEST.6 — write the run's numbers and compare them with the recorded baseline.
//
// A single run tells you whether the thresholds held. The baseline tells you
// whether something got slower since the last time anybody looked — which is
// the question a load test is actually for, and the one a pass/fail line
// cannot answer.
//
// `open()` is init-context only, so the baseline is read at import time. A
// missing file is normal (first run, or a scenario nobody has recorded yet)
// and must not abort the test.

let BASELINE = null;
try {
  BASELINE = JSON.parse(open('../baseline.json'));
} catch (e) {
  BASELINE = null;
}

const TOLERANCE = 0.10; // ±10%, per the roadmap.

function metric(data, name, stat) {
  const m = data.metrics[name];
  if (!m || !m.values) return null;
  const v = m.values[stat];
  return typeof v === 'number' ? v : null;
}

/** The numbers worth keeping: enough to spot a regression, few enough to read.
 *
 * `waiting` was added 2026-08-11, chasing the p95 the first run left open
 * (1064 ms against a 500 ms threshold). **`duration` is not server time** — it
 * is connect + TLS + send + wait + receive, and a run aimed across the internet
 * at a single small instance pays all of those. `http_req_waiting` is
 * time-to-first-byte, which is the part the application actually controls. If
 * the two disagree, the answer is in the network, and tuning a query would be
 * work aimed at the wrong half of the number.
 */
export function extract(data) {
  return {
    p95: metric(data, 'http_req_duration', 'p(95)'),
    med: metric(data, 'http_req_duration', 'med'),
    waiting_p95: metric(data, 'http_req_waiting', 'p(95)'),
    waiting_med: metric(data, 'http_req_waiting', 'med'),
    connecting_p95: metric(data, 'http_req_connecting', 'p(95)'),
    tls_p95: metric(data, 'http_req_tls_handshaking', 'p(95)'),
    failed: metric(data, 'http_req_failed', 'rate'),
    reqs: metric(data, 'http_reqs', 'count'),
    rps: metric(data, 'http_reqs', 'rate'),
  };
}

/** Per-endpoint p95, for scenarios that record `ep_*` trends.
 *
 * An aggregate p95 over four endpoints answers "is something slow" and never
 * "which". The first run said the tail was slower than the median by a factor
 * of two, which is the shape of one endpoint dragging the rest — so the run has
 * to be able to name it.
 *
 * Custom trends rather than threshold sub-metrics on tags: a sub-metric only
 * appears in the summary if a threshold is declared for it, which would make
 * the breakdown a side effect of a pass/fail line rather than a measurement.
 */
function endpoints(data) {
  return Object.keys(data.metrics)
    .filter((name) => name.startsWith('ep_'))
    .map((name) => ({
      name: name.slice(3),
      p95: metric(data, name, 'p(95)'),
      med: metric(data, name, 'med'),
      count: metric(data, name, 'count'),
    }))
    .sort((a, b) => (b.p95 || 0) - (a.p95 || 0));
}

function line(label, now, before) {
  if (now === null) return `  ${label}: —`;
  const shown = now.toFixed(label === 'failed' ? 4 : 2);
  if (before === null || before === undefined || before === 0) {
    return `  ${label}: ${shown}  (no baseline)`;
  }
  const delta = (now - before) / before;
  const pct = (delta * 100).toFixed(1);
  // Only slower/worse counts as a regression. Faster is printed too, because a
  // sudden improvement is usually a scenario that stopped doing its work.
  const flag = delta > TOLERANCE ? '  ⚠ REGRESSION' : delta < -TOLERANCE ? '  ↓ faster' : '';
  return `  ${label}: ${shown}  (baseline ${before.toFixed(2)}, ${delta > 0 ? '+' : ''}${pct}%)${flag}`;
}

/** Use as: `export function handleSummary(data) { return summarise('name', data) }` */
export function summarise(scenarioName, data) {
  const now = extract(data);
  const before = BASELINE ? BASELINE[scenarioName] : null;

  const perEndpoint = endpoints(data);
  const breakdown = perEndpoint.length
    ? [
        '',
        '  by endpoint (p95 / med / requests):',
        ...perEndpoint.map(
          (e) =>
            `    ${e.name.padEnd(14)} ${String(Math.round(e.p95 || 0)).padStart(6)} ms` +
            ` / ${String(Math.round(e.med || 0)).padStart(5)} ms` +
            ` / ${e.count || 0}`,
        ),
      ]
    : [];

  const report = [
    '',
    `── ${scenarioName} ─────────────────────────────`,
    line('p95', now.p95, before && before.p95),
    line('med', now.med, before && before.med),
    // Printed right under the totals rather than in a footnote: the gap between
    // these two lines is the whole question of whether a slow p95 is ours.
    line('waiting p95', now.waiting_p95, before && before.waiting_p95),
    line('connect p95', now.connecting_p95, before && before.connecting_p95),
    line('tls p95', now.tls_p95, before && before.tls_p95),
    line('failed', now.failed, before && before.failed),
    line('rps', now.rps, before && before.rps),
    ...breakdown,
    before
      ? ''
      : '  (no baseline recorded — see load/README.md to make this run the baseline)',
    '',
  ].join('\n');

  const out = {};
  out.stdout = report;
  now.endpoints = perEndpoint;
  // Written inside the container, where the repo's `load/` is mounted at
  // `/load` — so this lands in `load/results/` on the host, next to the
  // baseline it will be compared against.
  out[`/load/results/${scenarioName}.json`] = JSON.stringify({ [scenarioName]: now }, null, 2);
  return out;
}
