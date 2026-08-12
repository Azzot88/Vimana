// T_TEST.6 — shared setup for every k6 scenario.
//
// Two things live here because both are easy to get wrong once per file:
// where the load goes, and what counts as a pass.

const PROD_HOSTS = ['vimana.dealvault.club', 'dealvault.club'];

export const BASE_URL = (__ENV.BASE_URL || '').replace(/\/+$/, '');

if (!BASE_URL) {
  throw new Error('BASE_URL is required, e.g. BASE_URL=https://staging.example');
}

const host = BASE_URL.replace(/^https?:\/\//, '').split('/')[0].split(':')[0];

// Staging, not production (PRD T_TEST.6). The guard is here rather than in a
// README line because a load test aimed at prod is not a mistake you notice
// while it is happening — you notice it in someone else's failed deal. The
// escape hatch exists and is deliberately awkward: ALLOW_PROD=1, typed on
// purpose, by someone who meant it.
if (PROD_HOSTS.includes(host) && __ENV.ALLOW_PROD !== '1') {
  throw new Error(
    `${host} looks like production. Point BASE_URL at staging, or set ALLOW_PROD=1 if you truly mean it.`,
  );
}

export const VUS = Number(__ENV.K6_VUS || 100);
export const DURATION = __ENV.K6_DURATION || '5m';

// The acceptance criterion from the roadmap, in the one place k6 reads it.
export const THRESHOLDS = {
  http_req_duration: ['p(95)<500'],
  http_req_failed: ['rate<0.01'],
};

export const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** Same convention as the Playwright suite (`frontend/e2e/helpers.ts`): the
 *  `.local` TLD is unresolvable, so nothing ever leaves the building, and
 *  `cleanup_e2e_users` prunes these accounts after 24 h. Load runs create a lot
 *  of them — that task is the only reason this is safe to repeat. */
export function uniqueEmail(prefix) {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now().toString(36)}-${__VU}-${rand}@e2e.vimana.local`;
}

/** T_TEST.6 — the seeded accounts' password, supplied per run.
 *
 *  Not a constant any more. These are real accounts on a real deployment, and
 *  a credential committed to a repository is a credential — anybody reading
 *  the file would know both the address pattern and the way in.
 */
export const PASSWORD = __ENV.K6_PASSWORD || '';

/** Deterministic addresses, matching `backend/app/cli/load_seed.email_for`.
 *
 *  Duplicated rather than fetched: k6 has no way to ask, and a scenario that
 *  had to be handed a list of accounts would be a scenario nobody can run from
 *  one command line. The pattern is named in both places so a change to either
 *  is a change somebody makes on purpose.
 */
export function seededEmail(index) {
  return `k6-load-${index}@e2e.vimana.local`;
}

/** Sign in as one of the seeded accounts. Used from `setup()`, which runs once
 *  — doing this per iteration would measure nginx's `auth_zone` (60 r/min per
 *  IP) rather than the application.
 *
 *  **Replaced `registerAndLogin` on 2026-08-11.** That helper posted to
 *  `POST /auth/register`, removed in `T3.28 pt.3b`, so every scenario needing a
 *  session had been dying in `setup()` since 2026-08-10 — which is why nothing
 *  is known about the product's write path. Accounts now come from
 *  `app.cli.load_seed`, run once before a session, and this signs in with the
 *  password they were given.
 */
export function loginAs(http, index) {
  if (!PASSWORD) {
    throw new Error(
      'setup: K6_PASSWORD is not set. Seed the accounts first:\n' +
        "  docker compose exec -T backend python -m app.cli.load_seed --password '<secret>'\n" +
        'then pass the same value as -e K6_PASSWORD=<secret>.',
    );
  }
  const email = seededEmail(index);
  const login = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({ login: email, password: PASSWORD }),
    { headers: JSON_HEADERS },
  );
  if (login.status !== 200) {
    throw new Error(
      `setup: login as ${email} failed ${login.status}. ` +
        'Seed the accounts and check that K6_PASSWORD matches what they were seeded with.',
    );
  }
  return { email, token: login.json('access_token') };
}

export function auth(token) {
  return { headers: { ...JSON_HEADERS, Authorization: `Bearer ${token}` } };
}
