# Vimana Smoke Suite (Playwright)

Наблюдаемые e2e-тесты для быстрой ручной проверки основных flow.

## Быстрый старт (на Mac)

Требования: **Node.js 20+**.

```bash
cd frontend/e2e
npm install
npm run install:browsers          # первый раз — качает Chromium (~200 MB)
npm run headed                    # запускает все 3 спека с наблюдением
```

При `headed` открывается настоящий Chromium окном, действия замедлены на
500 мс — видно каждый клик и заполнение поля.

## Режимы

| Скрипт | Что делает |
|---|---|
| `npm run headed` | Все спеки, headed, slow-mo=500 |
| `npm run headed:single` | То же в 1 worker (медленнее, но детерминированнее) |
| `npm run trace` | Headless + trace.zip (не открывает окно; для сервера/CI) |
| `npm run ci` | Headless, только failures пишут screenshot/video/trace |
| `npm run a11y` | Только `a11y.spec.ts` — axe-core по 5 страницам (T_TEST.8) |
| `npm run show-trace <file.zip>` | Просмотр trace как машины времени |
| `npm run show-report` | HTML-отчёт последнего прогона |

## Target environment

По умолчанию бьёт в **prod**: `https://vimana.dealvault.club`.

Переключить (например, на локальный dev):
```bash
SMOKE_BASE_URL=http://localhost:5173 npm run headed
```

## Тестовые пользователи

Все юзеры регистрируются с email `<prefix>-<ts>-<rand>@e2e.vimana.local`.
TLD `.local` не резолвится → реальные письма никому не уйдут.

Backend Celery task `cleanup_e2e_users` (см. `backend/app/tasks/cleanup.py`)
раз в сутки чистит юзеров старше 24 часов + каскадно все связанные Trips /
Deals / Messages / TrustEdges.

Ручная проверка что накопилось — `/admin/users` (superuser).

## Что покрыто

**MVP (pt.1)** — single-context smoke:
- **`golden-path.spec.ts`** — carrier → publish trip → sender → match → chat.
- **`verification.spec.ts`** — VerificationSection присутствует на profile.
- **`recipient.spec.ts`** — /join/deal/:token роут отвечает.

**pt.2** — multi-context (`browser.newContext()` × 2 для изоляции сессий):
- **`invite-flow.spec.ts`** — Alice создаёт invite → Bob (свежий контекст) открывает
  ссылку → connection появляется у обоих в /profile.
- **`auth-rehydrate.spec.ts`** — регистрируемся → закрываем страницу → открываем
  новую → hard-nav на /profile → `<AuthBootstrap>` регидрирует из localStorage,
  редиректа на /login быть не должно. Регрессионный тест на T_UX.3 pt.1.
- **`admin-guard.spec.ts`** — обычный юзер → /admin/{notices,users,disputes}
  → всегда редирект на /dashboard. Также проверяет что AdminPanelSection не
  протекает в /profile для не-admin ролей.

**T_TEST.8** — доступность:
- **`a11y.spec.ts`** — axe-core на `/`, `/login`, `/register`, `/dashboard`,
  `/profile`. Проверяются теги WCAG 2.2 AA (`wcag2a…wcag22aa`), исключения — в
  `axe-rules.json`, каждое с причиной. Зелёный прогон означает «машина не нашла
  нарушений», а не «стандарт выполнен»: axe покрывает примерно треть AA,
  осмысленность порядка фокуса и текста ошибок остаётся за человеком.
  Требует `npm install` (добавлен `@axe-core/playwright`).

Отложено: `smoke-nostr.spec.ts` (нужен T3.5 включённым), Docker profile
`smoke-live` (VNC), CI-hook, R2 trace артефакты.
