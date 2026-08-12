# Load / performance (T_TEST.6)

k6 scenarios. Activated before Фаза 4 — the roadmap requires them before money
touches the product, because that is the point past which a slow path stops
being an annoyance and starts being a failed payment.

## Run

```bash
docker compose -f docker-compose.dev.yml --profile load run --rm \
  -e BASE_URL=https://<staging-host> \
  k6 run /load/scripts/browse_trips.js
```

Scenarios:

| file | what it puts under load | needs seeding |
|---|---|---|
| `scripts/browse_trips.js` | the anonymous read path — listing, cursor page 2, airports, categories | trips, for page 2 |
| `scripts/signup_burst.js` | the public code form under burst; measures the limiters as much as the app | no |
| `scripts/chat_hammer.js` | concurrent writes into **one** DealVault — the per-deal advisory lock | accounts 0–1 |
| `scripts/write_spread.js` | the same write across **many** deals — the platform's write ceiling | accounts 0–1 |
| `scripts/mixed_workload.js` | all three at once, 70 / 20 / 10 | accounts 2–3 |

`chat_hammer` and `write_spread` are a pair and neither means much alone: the
first is the ceiling of one conversation (the lock, by design), the second is
the ceiling of the write path.

## Seeding

Three scenarios need a session, and since `T3.28` an account is born from a code
sent to a mailbox — which k6 cannot read. They sign in with a password instead,
as accounts created once by a command:

```bash
docker compose -f docker-compose.dev.yml exec -T backend \
  python -m app.cli.load_seed --password '<secret>'
```

Then give k6 the same value: `-e K6_PASSWORD='<secret>'`. The password has no
default on purpose — these are real accounts on a real deployment, and a
credential in a repository is a credential.

Seeded accounts are `k6-load-N@e2e.vimana.local`, pruned by `cleanup_e2e_users`
after 24 h like every other e2e account; `--purge` removes them now instead.
The same command seeds 40 open trips, without which `/api/trips` never returns a
`next_cursor` and the cursor path in `browse_trips` is never exercised — which
is what happened in every run up to 2026-08-11.

**Not a test-only endpoint.** The obvious alternative is a door that mints a
session for a load run. An endpoint that mints sessions is an endpoint that
mints sessions, whatever the comment above it says, and it would live in
production forever for a test that runs monthly.

Knobs (all env): `BASE_URL` (required), `K6_VUS` (default 100), `K6_DURATION`
(default `5m`), `RUN_LABEL` (suffixes the results file so a sweep does not
overwrite itself), `ALLOW_PROD=1` to override the production guard, `K6_IMAGE`
to pin the k6 version.

## Measuring a change of machine

A single number at a single concurrency cannot tell a slow application from a
small box. A **curve** can: run the same scenario at several concurrencies, and
read the shape.

```bash
for vus in 10 25 50 100; do
  docker compose -f docker-compose.dev.yml --profile load run --rm \
    -e BASE_URL=https://<host> -e ALLOW_PROD=1 \
    -e K6_VUS=$vus -e K6_DURATION=2m -e RUN_LABEL=small-$vus \
    k6 run /load/scripts/browse_trips.js
done
```

What the shape means:

- **p95 at 10 VUs is the floor** — one request, nothing queueing. If that number
  is already large, the cost is per-request and no instance size removes it.
- **Flat until some concurrency, then climbing** — the knee is where capacity
  ends. Everything left of it is the application; everything right of it is the
  machine.
- **Halving the cores halves the latency at the same VUs** — pure capacity.
  Latency that refuses to fall when cores are added means something serialises,
  and then the box is not the answer.

Set the worker count to match the cores of whatever you are measuring:
`UVICORN_WORKERS=4` in the project `.env`, then recreate `backend`. The default
is 2, which is what a two-core box wants.

## Staging only

`lib/config.js` refuses to start against a host that looks like production. A
load run against prod is not a mistake you notice while it happens — you notice
it in somebody's failed deal. The override exists, is one variable, and is
meant to be typed deliberately.

## Accounts it creates

Every account registers as `…@e2e.vimana.local`, the same convention the
Playwright suite uses. The TLD is unresolvable, so no mail is ever sent, and
`cleanup_e2e_users` (hourly Celery) prunes them and everything cascading off
them after 24 h. That task is the only reason repeated runs are safe — if it is
disabled, staging fills up with deals nobody will ever close.

## Первый прогон по проду, 2026-08-03

`browse_trips`, 100 VUs × 5 мин: **p95 1064 ms · median 543 ms · failed 0.08 % · 105 rps · 10 606 итераций.**

Порог `p95 < 500` **не выполнен**, порог по ошибкам выполнен с большим запасом. Это не «тест сломался» — это ответ: под сотней параллельных читателей публичная выдача отвечает вдвое медленнее целевого. Дальше нужен разрез по тегам (`trips:list`, `trips:page2`, `airports`, `categories`), а не общий p95: они меряют разные запросы, и медиана вдвое ниже p95 говорит, что тормозит хвост, а не всё подряд.

Прогон был по **проду** (`ALLOW_PROD=1`) за неимением staging — то есть в числах сидит и TLS, и реальный размер инстанса.

## Baseline

The thresholds (`p95 < 500 ms`, `failed < 1%`) answer "is it acceptable". The
baseline answers the question a load test actually exists for: "did it get
slower than last time".

```bash
# after a run you trust, on a quiet staging box:
cp load/results/browse_trips.json load/baseline.json     # first scenario
# merging a second scenario: keep both top-level keys in baseline.json
```

`baseline.json` is a flat object keyed by scenario name:

```json
{ "browse_trips": { "p95": 180.4, "med": 90.1, "failed": 0, "reqs": 12000, "rps": 40.0 } }
```

Every later run prints its numbers next to the recorded ones and flags anything
more than **±10%** away.

`baseline.json` **is** in the repository now (recorded 2026-08-06 from the
2026-08-03 run), and it holds `browse_trips` only. Read it for what it is: the
state the product was in, not the state it should reach — its p95 is over the
threshold, and the threshold is the thing that says pass or fail. The baseline
answers the other question, the one a single run cannot: *did anything get
slower than last time.*

Conditions are part of the number and do not survive being changed: that run
went against **production** over TLS (no staging existed), 100 VUs, 5 minutes,
from the same host. Comparing a staging run against it says nothing. When you
record a new one, record the k6 version alongside (`K6_IMAGE`) if you want it to
outlive a k6 upgrade.

## Reading the results honestly

- **`signup_burst`** — three limiters stand in front of the code form: nginx's
  zones, slowapi's per-endpoint budget, and since `T3.29` a budget per mailbox
  (5/hour) and per source (10 distinct mailboxes an hour). From one machine the
  last of those trips within seconds and most of the run is refusals. 429 is
  therefore counted as expected (`rate_limited`) rather than as a failure; what
  is being measured is whether the refusal is *cheap*.
- **`chat_hammer`** — the deviation from the roadmap's "100 users in one
  DealVault" is deliberate and explained in the file header: two real
  participants writing concurrently hit the same per-deal advisory lock, and a
  hundred registrations would mostly measure the limiter.
- **Cold start** — the first request after a deploy pays for the GeoNames index
  load and the boto3 client. Discard the first few seconds or warm the instance
  before recording a baseline.
