// T_TEST.6 — who refused, not merely how often.
//
// Lived inside `browse_trips.js` until 2026-08-11, and then a deploy-time run of
// `write_spread` printed `failed: 0.0720` with no breakdown at all — the
// scenario had no counters, so the one number that would have named the cause
// was missing from the run that most needed it. A rate cannot tell nginx's rate
// limiter (429) from an upstream that is not there (502/503/504) from the
// application raising (500), and those are three different repairs.
//
// Shared here so a new scenario gets the breakdown by importing one function
// rather than by remembering to reinvent five counters.
import { Counter } from 'k6/metrics';

// Created at init, as k6 requires. The names are what `lib/summary.js` looks
// for; changing one means changing both.
const ERR = {
  rate_limited: new Counter('err_429'),
  gateway: new Counter('err_gateway'),
  server: new Counter('err_5xx'),
  client: new Counter('err_4xx'),
  transport: new Counter('err_other'),
};

/** Count a response if it failed. Safe to call on every response.
 *
 *  Returns true when the response was counted as a failure, so a caller can
 *  branch on it without repeating the range check.
 */
export function countFailure(res) {
  const status = res.status;
  if (status >= 200 && status < 400) return false;

  if (status === 429) ERR.rate_limited.add(1);
  else if (status === 502 || status === 503 || status === 504) ERR.gateway.add(1);
  else if (status >= 500) ERR.server.add(1);
  else if (status >= 400) ERR.client.add(1);
  // k6 reports a transport failure — refused, reset, timed out — as status 0.
  else ERR.transport.add(1);

  return true;
}
