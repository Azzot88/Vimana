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

/** The numbers worth keeping: enough to spot a regression, few enough to read. */
export function extract(data) {
  return {
    p95: metric(data, 'http_req_duration', 'p(95)'),
    med: metric(data, 'http_req_duration', 'med'),
    failed: metric(data, 'http_req_failed', 'rate'),
    reqs: metric(data, 'http_reqs', 'count'),
    rps: metric(data, 'http_reqs', 'rate'),
  };
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

  const report = [
    '',
    `── ${scenarioName} ─────────────────────────────`,
    line('p95', now.p95, before && before.p95),
    line('med', now.med, before && before.med),
    line('failed', now.failed, before && before.failed),
    line('rps', now.rps, before && before.rps),
    before
      ? ''
      : '  (no baseline recorded — see load/README.md to make this run the baseline)',
    '',
  ].join('\n');

  const out = {};
  out.stdout = report;
  // Written inside the container, where the repo's `load/` is mounted at
  // `/load` — so this lands in `load/results/` on the host, next to the
  // baseline it will be compared against.
  out[`/load/results/${scenarioName}.json`] = JSON.stringify({ [scenarioName]: now }, null, 2);
  return out;
}
