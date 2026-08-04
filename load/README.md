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

| file | what it puts under load |
|---|---|
| `scripts/browse_trips.js` | the anonymous read path — listing, cursor page 2, airports, categories |
| `scripts/register_burst.js` | registration under burst; measures the rate limiter as much as the app |
| `scripts/chat_hammer.js` | concurrent writes into **one** DealVault — the per-deal advisory lock |
| `scripts/mixed_workload.js` | all three at once, 70 / 20 / 10 |

Knobs (all env): `BASE_URL` (required), `K6_VUS` (default 100), `K6_DURATION`
(default `5m`), `ALLOW_PROD=1` to override the production guard, `K6_IMAGE` to
pin the k6 version.

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
more than **±10%** away. There is no baseline file in the repository on
purpose: numbers copied from somebody else's machine are not a baseline, they
are a rumour. Record one, and record the k6 version alongside it (`K6_IMAGE`)
if you want it to survive a k6 upgrade.

## Reading the results honestly

- **`register_burst`** — nginx `auth_zone` allows 10 r/min per IP with burst 5,
  and slowapi sits behind it. From one machine, most of this run is refusals.
  429 is therefore counted as expected (`rate_limited` metric) rather than as a
  failure; what is being measured is whether the refusal is *cheap*.
- **`chat_hammer`** — the deviation from the roadmap's "100 users in one
  DealVault" is deliberate and explained in the file header: two real
  participants writing concurrently hit the same per-deal advisory lock, and a
  hundred registrations would mostly measure the limiter.
- **Cold start** — the first request after a deploy pays for the GeoNames index
  load and the boto3 client. Discard the first few seconds or warm the instance
  before recording a baseline.
